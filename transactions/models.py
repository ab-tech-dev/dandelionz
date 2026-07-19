from django.db import models, transaction
from django.utils import timezone
import uuid
from decimal import Decimal
from authentication.models import CustomUser

TWO_PLACES = Decimal('0.01')


def money(value):
    """Coerce any numeric input to a 2dp Decimal. All wallet maths goes through this."""
    return Decimal(str(value)).quantize(TWO_PLACES)


# ========================
# WALLET SYSTEM (Defined first for dependencies)
# ========================
class Wallet(models.Model):
    """
    A user's wallet, split into two buckets.

    ``spendable_balance``    - funded by the user's own Paystack deposits. Can be spent at
                               checkout but can NEVER be withdrawn to a bank. This is what
                               stops the wallet being used to cash out a stolen card.
    ``withdrawable_balance`` - money the platform owes the user (refunds, vendor earnings,
                               commissions, referral bonuses). Spendable AND withdrawable.

    ``balance`` is the sum of the two, kept as a cached column purely so the large amount of
    existing code that reads ``wallet.balance`` keeps working unchanged.

    All three columns are caches. The source of truth is the LedgerEntry table; run
    ``manage.py reconcile_wallets`` to assert they still agree.
    """
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Cached total. Always equals spendable_balance + withdrawable_balance.",
    )
    spendable_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="From the user's own deposits. Spendable at checkout, never withdrawable.",
    )
    withdrawable_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Refunds and earnings. Both spendable and withdrawable.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def credit(self, amount, source=None, *, bucket=None, entry_type=None,
               idempotency_key=None, reference=None, order=None, payment=None,
               payout_request=None, created_by=None, metadata=None):
        """
        Add funds to the wallet and record a ledger entry.

        Defaults to the WITHDRAWABLE bucket, which is correct for every historical caller
        (refunds, vendor earnings, commissions, referral bonuses). Deposits must pass
        ``bucket=LedgerEntry.Bucket.SPENDABLE`` explicitly.

        Pass ``idempotency_key`` to make the credit at-most-once; a repeat call with the same
        key is a silent no-op rather than a double credit.
        """
        return self._apply(
            direction=LedgerEntry.Direction.CREDIT,
            amount=amount,
            source=source,
            bucket=bucket or LedgerEntry.Bucket.WITHDRAWABLE,
            entry_type=entry_type,
            idempotency_key=idempotency_key,
            reference=reference,
            order=order,
            payment=payment,
            payout_request=payout_request,
            created_by=created_by,
            metadata=metadata,
        )

    def debit(self, amount, source=None, *, bucket=None, entry_type=None,
              idempotency_key=None, reference=None, order=None, payment=None,
              payout_request=None, created_by=None, metadata=None):
        """
        Subtract funds from the wallet and record a ledger entry.

        ``bucket=None`` (the default) spends SPENDABLE first, then WITHDRAWABLE - deposited
        money gets used up before money we owe the user, which keeps the withdrawable pool
        as small as possible.

        Withdrawals MUST pass ``bucket=LedgerEntry.Bucket.WITHDRAWABLE`` so deposited funds
        can never leave via a bank transfer.

        Raises ValueError if the selected bucket(s) can't cover the amount.
        """
        return self._apply(
            direction=LedgerEntry.Direction.DEBIT,
            amount=amount,
            source=source,
            bucket=bucket,
            entry_type=entry_type,
            idempotency_key=idempotency_key,
            reference=reference,
            order=order,
            payment=payment,
            payout_request=payout_request,
            created_by=created_by,
            metadata=metadata,
        )

    def _apply(self, *, direction, amount, source, bucket, entry_type, idempotency_key,
               reference, order, payment, payout_request, created_by, metadata):
        """
        The single place wallet balances change.

        Takes a row lock on the wallet for the duration, so concurrent credits/debits
        serialise instead of clobbering each other. Every caller gets this for free -
        the old read-modify-write in Python lost writes under concurrency.
        """
        amount = money(amount)
        if amount < 0:
            raise ValueError("Wallet movement amount cannot be negative")
        if amount == 0:
            # A no-op, not an error. The old credit()/debit() tolerated zero, and
            # credit_vendors_for_order legitimately computes a zero share for an order item
            # that is free or fully discounted - raising here would break order delivery.
            return []

        # `new_entries` are unsaved and get bulk-created below. The adopted opening entry is
        # saved separately by _adopt_legacy_balance, so it must stay out of that batch or
        # bulk_create will try to insert a row that already has a primary key.
        new_entries = []
        adopted = []
        with transaction.atomic():
            # Re-read under lock. Callers that already hold the lock re-enter harmlessly.
            locked = Wallet.objects.select_for_update().get(pk=self.pk)

            # Adopt any pre-ledger balance before touching anything else.
            opening = locked._adopt_legacy_balance()
            if opening is not None:
                adopted.append(opening)

            # Match on operation_key, not idempotency_key. A split debit stores per-leg
            # suffixed idempotency keys and never the bare caller key, so checking
            # idempotency_key here would never match and every replayed split debit would
            # run again.
            #
            # This check-then-insert is not racy in practice: every operation key names a
            # single wallet, and we hold that wallet's row lock, so two concurrent calls
            # with the same key serialise and the second sees the first's committed rows.
            # A duplicate key across *different* wallets would surface as an IntegrityError
            # rather than a silent no-op, but that would mean a key-naming bug upstream.
            if idempotency_key and LedgerEntry.objects.filter(
                operation_key=idempotency_key
            ).exists():
                # Already applied. Refresh our in-memory copy and report no new movement
                # (beyond any legacy adoption that just happened).
                self._sync_from(locked)
                return adopted

            if direction == LedgerEntry.Direction.CREDIT:
                plan = [(bucket, amount)]
            else:
                plan = locked._plan_debit(amount, bucket)

            for target_bucket, part in plan:
                if part <= 0:
                    continue
                current = locked._bucket_balance(target_bucket)
                new_value = (
                    current + part
                    if direction == LedgerEntry.Direction.CREDIT
                    else current - part
                )
                locked._set_bucket_balance(target_bucket, new_value)

                new_entries.append(LedgerEntry(
                    wallet=locked,
                    direction=direction,
                    bucket=target_bucket,
                    entry_type=entry_type or LedgerEntry.infer_type(direction, source),
                    amount=part,
                    balance_after=new_value,
                    description=source or '',
                    # Unique per row; suffixed per bucket when a debit spans both.
                    idempotency_key=self._leg_key(idempotency_key, target_bucket, len(plan)),
                    # Shared across legs - this is what the replay guard above matches.
                    operation_key=idempotency_key or '',
                    reference=reference or '',
                    order=order,
                    payment=payment,
                    payout_request=payout_request,
                    created_by=created_by,
                    metadata=metadata or {},
                ))

            locked.balance = money(locked.spendable_balance + locked.withdrawable_balance)
            locked.save(update_fields=[
                'balance', 'spendable_balance', 'withdrawable_balance', 'updated_at',
            ])

            LedgerEntry.objects.bulk_create(new_entries)

            # Keep the legacy denormalised table in step - admin screens and the
            # existing source__icontains idempotency checks still read from it.
            for entry in new_entries:
                WalletTransaction.objects.create(
                    wallet=locked,
                    transaction_type=(
                        WalletTransaction.TransactionType.CREDIT
                        if direction == LedgerEntry.Direction.CREDIT
                        else WalletTransaction.TransactionType.DEBIT
                    ),
                    amount=entry.amount,
                    source=source,
                )

            self._sync_from(locked)

        return adopted + new_entries

    def _adopt_legacy_balance(self):
        """
        Move any pre-ledger balance into the withdrawable bucket, once, on first touch.

        Before the ledger existed, ``balance`` was the only column. After the ledger ships,
        ``_apply`` recomputes ``balance`` as spendable + withdrawable - which would silently
        wipe an untracked legacy balance the first time such a wallet was credited.

        Doing this lazily rather than only in ``backfill_ledger`` means correctness does not
        depend on anyone remembering to run that command before real traffic arrives. The
        command stays useful for backfilling wallets that are never touched again, and for
        making the migration visible in one pass.

        Assumes the caller holds the row lock. Persists immediately so the adoption cannot
        be lost on an early return.
        """
        key = f"opening-balance-{self.pk}"
        if LedgerEntry.objects.filter(idempotency_key=key).exists():
            return None

        legacy = (
            money(self.balance)
            - money(self.spendable_balance)
            - money(self.withdrawable_balance)
        )
        if legacy <= 0:
            # Nothing untracked. A negative value would mean the caches are already
            # corrupt; reconcile_wallets reports that rather than silently papering over it.
            return None

        self.withdrawable_balance = money(self.withdrawable_balance + legacy)
        self.balance = money(self.spendable_balance + self.withdrawable_balance)
        self.save(update_fields=[
            'balance', 'spendable_balance', 'withdrawable_balance', 'updated_at',
        ])

        entry = LedgerEntry(
            wallet=self,
            direction=LedgerEntry.Direction.CREDIT,
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            entry_type=LedgerEntry.EntryType.OPENING_BALANCE,
            amount=legacy,
            balance_after=self.withdrawable_balance,
            description='Opening balance carried over from before the ledger',
            idempotency_key=key,
            operation_key=key,
        )
        entry.save()
        return entry

    def _plan_debit(self, amount, bucket):
        """Work out which bucket(s) a debit comes out of. Assumes self is lock-fresh."""
        if bucket is not None:
            available = self._bucket_balance(bucket)
            if available < amount:
                raise ValueError(
                    f"Insufficient {bucket.lower()} balance. "
                    f"Available: {available}, requested: {amount}"
                )
            return [(bucket, amount)]

        # No bucket named: spend deposits first, then money we owe the user.
        spendable = self.spendable_balance
        withdrawable = self.withdrawable_balance
        if spendable + withdrawable < amount:
            raise ValueError("Insufficient wallet balance")

        from_spendable = min(spendable, amount)
        from_withdrawable = amount - from_spendable

        # Only return legs that actually move money. A zero leg would still inflate
        # len(plan), which is what decides whether idempotency keys get bucket suffixes.
        legs = []
        if from_spendable > 0:
            legs.append((LedgerEntry.Bucket.SPENDABLE, from_spendable))
        if from_withdrawable > 0:
            legs.append((LedgerEntry.Bucket.WITHDRAWABLE, from_withdrawable))
        return legs

    @staticmethod
    def _leg_key(idempotency_key, bucket, leg_count):
        if not idempotency_key:
            return f"auto-{uuid.uuid4()}"
        if leg_count == 1:
            return idempotency_key
        return f"{idempotency_key}:{bucket}"

    def _bucket_balance(self, bucket):
        if bucket == LedgerEntry.Bucket.SPENDABLE:
            return money(self.spendable_balance)
        return money(self.withdrawable_balance)

    def _set_bucket_balance(self, bucket, value):
        if bucket == LedgerEntry.Bucket.SPENDABLE:
            self.spendable_balance = money(value)
        else:
            self.withdrawable_balance = money(value)

    def _sync_from(self, other):
        self.balance = other.balance
        self.spendable_balance = other.spendable_balance
        self.withdrawable_balance = other.withdrawable_balance

    @property
    def held_amount(self):
        """Sum of funds currently reserved by in-flight checkouts."""
        return money(
            self.holds.filter(status=WalletHold.Status.HELD)
            .aggregate(total=models.Sum('amount'))['total'] or 0
        )

    def __str__(self):
        return f"{self.user.email} Wallet - Balance: {self.balance}"


class WalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        CREDIT = 'CREDIT', 'Credit'
        DEBIT = 'DEBIT', 'Debit'

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=6, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wallet.user.email} - {self.transaction_type} {self.amount} ({self.source})"


# ========================
# ORDER SYSTEM
# ========================
class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        SHIPPED = 'SHIPPED', 'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        RETURNED = 'RETURNED', 'Returned'
        CANCELED = 'CANCELED', 'Canceled'

    # External reference UUID for API/tracking (separate from internal id)
    order_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True, help_text="Public order reference ID")
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    delivery_agent = models.ForeignKey('users.DeliveryAgent', on_delete=models.SET_NULL, related_name='assigned_orders', null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, help_text="Current order fulfillment status")
    products = models.ManyToManyField('store.Product', through='OrderItem', related_name='orders')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    payment_status = models.CharField(max_length=20, default='UNPAID')
    vendors_credited = models.BooleanField(default=False, help_text="Track if vendors have been credited for this delivered order")
    assigned_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    ordered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Delivery location coordinates (for fee calculation)
    restaurant_lat = models.FloatField(null=True, blank=True, help_text="Restaurant/store latitude for delivery calculation")
    restaurant_lng = models.FloatField(null=True, blank=True, help_text="Restaurant/store longitude for delivery calculation")
    customer_lat = models.FloatField(null=True, blank=True, help_text="Customer delivery address latitude")
    customer_lng = models.FloatField(null=True, blank=True, help_text="Customer delivery address longitude")
    
    # Delivery fee calculation results
    delivery_distance = models.CharField(max_length=50, blank=True, help_text="Distance from restaurant to delivery address")
    delivery_duration = models.CharField(max_length=50, blank=True, help_text="Estimated delivery time")
    delivery_distance_miles = models.FloatField(null=True, blank=True, help_text="Distance in miles")

    def calculate_total(self):
        items = self.order_items.all()
        subtotal = sum(item.item_subtotal for item in items)
        return subtotal - Decimal(self.discount) + Decimal(self.delivery_fee)

    def update_total(self):
        total = self.calculate_total()
        if total != self.total_price:
            self.total_price = total
            self.save(update_fields=['total_price'])

    @property
    def subtotal(self):
        return sum(item.item_subtotal for item in self.order_items.all())

    @property
    def total_with_delivery(self):
        return self.subtotal + self.delivery_fee - self.discount

    @property
    def is_paid(self):
        return self.payment_status.upper() == 'PAID'

    @property
    def is_delivered(self):
        return self.status == self.Status.DELIVERED

    def calculate_and_save_delivery_fee(self):
        """
        Calculate and save delivery fee for this order.
        UPDATED: Delivery is currently set to FREE for all orders.
        Distance-based calculation logic is commented out below.
        """
        # Set all orders to free delivery
        self.delivery_fee = Decimal('0.00')
        self.delivery_distance = '0.00 km'
        self.delivery_duration = '0 mins'
        self.delivery_distance_miles = 0.0
        self.save(update_fields=['delivery_fee', 'delivery_distance', 'delivery_duration', 'delivery_distance_miles'])
        return True

        # =========================================================================
        # COMMENTED OUT: Original distance-based calculation logic
        # To restore, remove the 'return True' above and uncomment this block.
        # =========================================================================
        # from .delivery_service import DeliveryFeeCalculator
        # from django.conf import settings

        # def has_coords(lat, lng):
        #     return lat is not None and lng is not None
        
        # min_total = Decimal(str(getattr(settings, 'DELIVERY_MIN_ORDER_TOTAL_NGN', 15000)))
        # if self.subtotal <= min_total:
        #     self.delivery_fee = Decimal('0.00')
        #     self.delivery_distance = ''
        #     self.delivery_duration = ''
        #     self.delivery_distance_miles = None
        #     self.save(update_fields=['delivery_fee', 'delivery_distance', 'delivery_duration', 'delivery_distance_miles'])
        #     return False

        # # Validate required coordinates
        # if not (has_coords(self.restaurant_lat, self.restaurant_lng) and has_coords(self.customer_lat, self.customer_lng)):
        #     raise ValueError("All coordinate fields are required for delivery fee calculation")
        
        # calculator = DeliveryFeeCalculator()
        # result = calculator.calculate_fee(
        #     origin_lat=self.restaurant_lat,
        #     origin_lng=self.restaurant_lng,
        #     dest_lat=self.customer_lat,
        #     dest_lng=self.customer_lng
        # )
        
        # if result['success']:
        #     self.delivery_fee = Decimal(str(result['fee']))
        #     self.delivery_distance = result['distance']
        #     self.delivery_duration = result['duration']
        #     self.delivery_distance_miles = result['distance_miles']
        #     self.save(update_fields=['delivery_fee', 'delivery_distance', 'delivery_duration', 'delivery_distance_miles'])
        #     return True
        # else:
        #     raise ValueError(f"Delivery fee calculation failed: {result.get('error')}")

    def is_within_delivery_radius(self):
        """Check if order is within delivery radius"""
        if self.delivery_distance_miles is None:
            try:
                self.calculate_and_save_delivery_fee()
            except ValueError:
                return False
        
        from django.conf import settings
        return self.delivery_distance_miles <= settings.DELIVERY_MAX_DISTANCE_MILES

    def __str__(self):
        return f"Order {self.order_id} ({getattr(self.customer, 'email', 'Unknown')})"


# ========================
# ORDER STATUS HISTORY
# ========================
class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=10, choices=Order.Status.choices)
    changed_by = models.CharField(
        max_length=20,
        choices=[('ADMIN', 'Admin'), ('SYSTEM', 'System'), ('VENDOR', 'Vendor'), ('CUSTOMER', 'Customer')],
        default='SYSTEM'
    )
    admin = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_status_changes'
    )
    reason = models.TextField(blank=True, null=True)
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['changed_at']
        verbose_name_plural = "Order Status Histories"

    def __str__(self):
        return f"Order {self.order.order_id} -> {self.status} at {self.changed_at}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='order_items')
    product = models.ForeignKey('store.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selected_variants = models.JSONField(
        default=dict,
        blank=True,
        help_text="Variant selections at time of purchase (e.g., {'color': 'Red', 'size': 'M'})"
    )

    @property
    def item_subtotal(self):
        return self.price_at_purchase * self.quantity

    def save(self, *args, **kwargs):
        if not self.price_at_purchase:
            self.price_at_purchase = self.product.price
        super().save(*args, **kwargs)

    @property
    def vendor(self):
        return self.product.store

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


# ========================
# PAYMENT SYSTEM
# ========================
class Payment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    reference = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='PENDING')  # PENDING, SUCCESS, FAILED
    gateway = models.CharField(max_length=50, default='Paystack')
    paid_at = models.DateTimeField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def mark_as_successful(self):
        """
        Mark payment as successful (idempotent - safe to call multiple times).
        
        Flow Step: 7 → 8
        - Payment verified → payment_status = 'PAID'
        - Vendors AND Admins notified of new order
        
        Updates order status to PAID and triggers stakeholder notification task.
        """
        # Return early if already successful to prevent duplicate processing
        if self.verified:
            return
        
        self.status = 'SUCCESS'
        self.verified = True
        self.paid_at = timezone.now()
        self.order.payment_status = 'PAID'
        self.order.status = Order.Status.PAID  # Mark order as paid when payment succeeds
        self.order.save(update_fields=['payment_status', 'status'])
        self.save(update_fields=['status', 'verified', 'paid_at'])
        
        # Trigger stakeholder notification task (async) - notifies vendors AND admins
        from .tasks import notify_stakeholders_order_paid
        notify_stakeholders_order_paid.delay(str(self.order.order_id))

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['order', 'reference'], name='unique_payment_reference')
        ]
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return f"Payment {self.reference} - {self.status}"


# ========================
# SHIPPING / DELIVERY DETAILS
# ========================
class ShippingAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipping_address')
    full_name = models.CharField(max_length=255)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    phone_number = models.CharField(max_length=20)

    def __str__(self):
        return f"Shipping for {self.order.order_id} - {self.city}, {self.country}"


class TransactionLog(models.Model):
    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'
        SUCCESS = 'SUCCESS', 'Success'
    
    class Action(models.TextChoices):
        PAYMENT_RECEIVED = 'PAYMENT_RECEIVED', 'Payment Received'
        PAYMENT_FAILED = 'PAYMENT_FAILED', 'Payment Failed'
        VENDOR_CREDITED = 'VENDOR_CREDITED', 'Vendor Credited'
        COMMISSION_DEDUCTED = 'COMMISSION_DEDUCTED', 'Commission Deducted'
        ORDER_SHIPPED = 'ORDER_SHIPPED', 'Order Shipped'
        ORDER_DELIVERED = 'ORDER_DELIVERED', 'Order Delivered'
        REFUND_APPROVED = 'REFUND_APPROVED', 'Refund Approved'
        REFUND_REJECTED = 'REFUND_REJECTED', 'Refund Rejected'
        WEBHOOK_PROCESSED = 'WEBHOOK_PROCESSED', 'Webhook Processed'
        OTHER = 'OTHER', 'Other'

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='logs', null=True, blank=True)
    message = models.TextField()
    action = models.CharField(max_length=50, choices=Action.choices, default=Action.OTHER)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    related_user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='transaction_logs')
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional context data for the transaction")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        permissions = [
            ("view_transactionlog_admin", "Can view transaction logs (admin only)"),
        ]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['level', '-created_at']),
        ]

    def __str__(self):
        order_info = f"{self.order.order_id}" if self.order else "SYSTEM"
        return f"[{self.level}] {order_info}: {self.message[:50]}"


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
    
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='refund')
    reason = models.TextField(blank=True, null=True)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    commission_reversed = models.BooleanField(default=False, help_text="Track if commissions have been reversed for this refund")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Refund {self.id} - {self.status} ({self.refunded_amount})"


# ========================
# INSTALLMENT PAYMENT SYSTEM
# ========================
class InstallmentPlan(models.Model):
    class DurationChoice(models.TextChoices):
        ONE_MONTH = '1_month', '1 Month'
        THREE_MONTHS = '3_months', '3 Months'
        SIX_MONTHS = '6_months', '6 Months'
        EIGHT_MONTHS = '8_months', '8 Months'

    # Mapping of duration to number of installments
    DURATION_INSTALLMENTS = {
        '1_month': 1,
        '3_months': 3,
        '6_months': 6,
        '8_months': 8,
    }

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='installment_plan')
    duration = models.CharField(max_length=20, choices=DurationChoice.choices)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    installment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    number_of_installments = models.PositiveIntegerField()
    start_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='ACTIVE')  # ACTIVE, COMPLETED, CANCELLED
    vendors_credited = models.BooleanField(default=False)  # Track if vendors have been credited
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_installment_amount(self):
        """Calculate the amount per installment"""
        return self.total_amount / Decimal(self.number_of_installments)

    def get_paid_installments_count(self):
        """Get count of successfully paid installments"""
        return self.installments.filter(status='PAID').count()

    def get_pending_installments_count(self):
        """Get count of pending installments"""
        return self.installments.filter(status='PENDING').count()

    def is_fully_paid(self):
        """Check if all installments are paid"""
        return self.get_paid_installments_count() == self.number_of_installments

    def mark_as_completed(self):
        """Mark installment plan as completed (idempotent - safe to call multiple times)"""
        if self.is_fully_paid():
            # Ensure a Payment record exists for installment orders
            payment, created = Payment.objects.get_or_create(
                order=self.order,
                defaults={
                    "amount": self.total_amount,
                    "gateway": "Paystack",
                },
            )

            # Keep payment amount in sync with total_amount
            if payment.amount != self.total_amount:
                payment.amount = self.total_amount
                payment.save(update_fields=["amount"])

            # Mark payment successful (will update order status and notify stakeholders)
            if not payment.verified:
                payment.mark_as_successful()

            self.status = 'COMPLETED'
            self.save(update_fields=['status', 'updated_at', 'vendors_credited'])
            return True
        return False

    def __str__(self):
        return f"Installment Plan - {self.order.order_id} ({self.duration})"

    class Meta:
        ordering = ['-created_at']


class InstallmentPayment(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'
        OVERDUE = 'OVERDUE', 'Overdue'

    installment_plan = models.ForeignKey(InstallmentPlan, on_delete=models.CASCADE, related_name='installments')
    payment_number = models.PositiveIntegerField()  # 1st, 2nd, 3rd installment, etc.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    due_date = models.DateTimeField()
    payment_date = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    gateway = models.CharField(max_length=50, default='Paystack')
    paid_at = models.DateTimeField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_as_paid(self):
        """Mark this installment payment as paid (idempotent - safe to call multiple times)"""
        # Return early if already paid to prevent duplicate processing
        if self.status == self.PaymentStatus.PAID:
            return
        
        self.status = self.PaymentStatus.PAID
        self.verified = True
        self.paid_at = timezone.now()
        self.payment_date = timezone.now()
        self.save(update_fields=['status', 'verified', 'paid_at', 'payment_date', 'updated_at'])
        
        # Check if entire plan is completed
        self.installment_plan.mark_as_completed()

    def is_overdue(self):
        """Check if payment is overdue"""
        if self.status == self.PaymentStatus.PENDING and timezone.now() > self.due_date:
            return True
        return False

    def __str__(self):
        return f"Installment #{self.payment_number} - {self.amount} ({self.status})"

    class Meta:
        ordering = ['payment_number']
        unique_together = ['installment_plan', 'payment_number']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['reference']),
        ]


from django.contrib.auth import get_user_model
User = get_user_model()

class PayoutRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ========================
# SETTLEMENTS (Vendor Payouts)
# ========================
class Settlement(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        PROCESSED = 'PROCESSED', 'Processed'
        FAILED = 'FAILED', 'Failed'

    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4)  # set_XXXX format
    vendor = models.ForeignKey('users.Vendor', on_delete=models.CASCADE, related_name='settlements')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    payout_date = models.DateTimeField()  # Scheduled payout date
    processed_date = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['status', '-payout_date']),
        ]

    def __str__(self):
        return f"Settlement {self.id} - {self.vendor.store_name} - {self.status}"


class SettlementItem(models.Model):
    """Links orders/order items to a settlement"""
    settlement = models.ForeignKey(Settlement, on_delete=models.CASCADE, related_name='items')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='settlement_items')
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, null=True, blank=True)
    vendor_share = models.DecimalField(max_digits=12, decimal_places=2)  # 90% of item value
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Settlement Item - {self.settlement.id} - Order {self.order.order_id}"


class Dispute(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4)  # dsp_XXXX format
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='disputes')
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='disputes_created')
    vendor = models.ForeignKey('users.Vendor', on_delete=models.CASCADE, related_name='disputes_received')
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # Refund amount
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    admin_note = models.TextField(blank=True, null=True)
    resolved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='disputes_resolved')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['vendor', 'status']),
        ]

    def __str__(self):
        return f"Dispute {self.id} - Order {self.order.order_id} - {self.status}"


# ========================
# LEDGER (source of truth for all wallet movement)
# ========================
class LedgerEntry(models.Model):
    """
    An immutable record of one movement of money in or out of one wallet bucket.

    Append-only by design: rows are never updated or deleted, so the table is a complete,
    tamper-evident history. Wallet.balance and friends are caches derived from this table -
    if they ever disagree, this table wins.

    A single logical operation can produce more than one entry (a checkout that spends both
    deposited and refunded money writes one DEBIT per bucket). Group them via `reference`.
    """

    class Direction(models.TextChoices):
        CREDIT = 'CREDIT', 'Credit'
        DEBIT = 'DEBIT', 'Debit'

    class Bucket(models.TextChoices):
        SPENDABLE = 'SPENDABLE', 'Spendable'
        WITHDRAWABLE = 'WITHDRAWABLE', 'Withdrawable'

    class EntryType(models.TextChoices):
        OPENING_BALANCE = 'OPENING_BALANCE', 'Opening Balance'
        DEPOSIT = 'DEPOSIT', 'Wallet Deposit'
        DEPOSIT_REVERSAL = 'DEPOSIT_REVERSAL', 'Deposit Reversal'
        ORDER_PAYMENT = 'ORDER_PAYMENT', 'Order Payment'
        ORDER_PAYMENT_RELEASE = 'ORDER_PAYMENT_RELEASE', 'Order Payment Released'
        ORDER_REFUND = 'ORDER_REFUND', 'Order Refund'
        VENDOR_EARNING = 'VENDOR_EARNING', 'Vendor Earning'
        COMMISSION = 'COMMISSION', 'Platform Commission'
        COMMISSION_REVERSAL = 'COMMISSION_REVERSAL', 'Commission Reversal'
        DELIVERY_FEE = 'DELIVERY_FEE', 'Delivery Fee'
        REFERRAL_BONUS = 'REFERRAL_BONUS', 'Referral Bonus'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
        WITHDRAWAL_REVERSAL = 'WITHDRAWAL_REVERSAL', 'Withdrawal Reversal'
        DISPUTE_CREDIT = 'DISPUTE_CREDIT', 'Dispute Refund'
        DISPUTE_DEBIT = 'DISPUTE_DEBIT', 'Dispute Reversal'
        ADJUSTMENT = 'ADJUSTMENT', 'Manual Adjustment'
        OTHER = 'OTHER', 'Other'

    # PROTECT is deliberate: the money trail must outlive the account. Closing an account
    # anonymises the user rather than deleting the row (see AccountDeletion in users/views.py),
    # so this should never fire in normal operation - it is a backstop that turns "someone
    # added a hard delete" into a loud error instead of silently erased financial history.
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name='ledger_entries')
    direction = models.CharField(max_length=6, choices=Direction.choices)
    bucket = models.CharField(max_length=12, choices=Bucket.choices)
    entry_type = models.CharField(max_length=30, choices=EntryType.choices, default=EntryType.OTHER)

    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Always positive; direction carries the sign.",
    )
    balance_after = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="This bucket's balance immediately after this entry.",
    )

    idempotency_key = models.CharField(
        max_length=255, unique=True,
        help_text="Unique per row. A split debit writes one suffixed key per bucket leg.",
    )
    operation_key = models.CharField(
        max_length=255, blank=True, db_index=True,
        help_text=(
            "Shared by every leg of one logical operation, and the field the replay guard "
            "matches on. Deliberately not unique - a two-bucket debit writes two rows "
            "carrying the same operation_key."
        ),
    )
    reference = models.CharField(
        max_length=100, blank=True, db_index=True,
        help_text="Paystack or internal reference this movement relates to.",
    )
    description = models.CharField(max_length=255, blank=True)

    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='ledger_entries')
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name='ledger_entries')
    payout_request = models.ForeignKey(
        'users.PayoutRequest', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ledger_entries',
    )

    created_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ledger_entries_created',
        help_text="Set only for manual admin adjustments.",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Maps a legacy free-text source string onto a typed entry, so historical call sites
    # that only pass source= still land in the right section of the admin ledger report.
    _SOURCE_HINTS = (
        ('withdrawal refund', EntryType.WITHDRAWAL_REVERSAL),
        ('refund for failed withdrawal', EntryType.WITHDRAWAL_REVERSAL),
        ('withdrawal', EntryType.WITHDRAWAL),
        ('commission reversal', EntryType.COMMISSION_REVERSAL),
        ('commission', EntryType.COMMISSION),
        ('delivery fee', EntryType.DELIVERY_FEE),
        ('referral', EntryType.REFERRAL_BONUS),
        ('refund', EntryType.ORDER_REFUND),
        ('deposit', EntryType.DEPOSIT),
        ('delivery', EntryType.VENDOR_EARNING),
    )

    @classmethod
    def infer_type(cls, direction, source):
        if not source:
            return cls.EntryType.OTHER
        haystack = str(source).lower()
        for needle, entry_type in cls._SOURCE_HINTS:
            if needle in haystack:
                return entry_type
        return cls.EntryType.OTHER

    @property
    def signed_amount(self):
        """Amount with its sign applied - convenient for exports and running totals."""
        return self.amount if self.direction == self.Direction.CREDIT else -self.amount

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "LedgerEntry is append-only and cannot be modified. "
                "Write a compensating entry instead."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "LedgerEntry is append-only and cannot be deleted. "
            "Write a compensating entry instead."
        )

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name_plural = 'Ledger entries'
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name='ledger_amount_positive'),
        ]
        indexes = [
            models.Index(fields=['wallet', '-created_at']),
            models.Index(fields=['entry_type', '-created_at']),
            models.Index(fields=['direction', '-created_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        sign = '+' if self.direction == self.Direction.CREDIT else '-'
        return f"{sign}{self.amount} {self.bucket} ({self.entry_type}) - {self.wallet.user.email}"


class WalletHold(models.Model):
    """
    Money reserved out of a wallet while a split-payment checkout is in flight.

    Split payment has two legs that cannot be made atomic (we debit the wallet locally, then
    charge the card at Paystack). The hold makes that safe: the wallet is debited up front,
    so the funds cannot be double-spent on a second checkout, and the debit is reversed if
    the card leg never completes.

    HELD -> CAPTURED  card payment verified, the money is really gone
    HELD -> RELEASED  card payment failed, was cancelled, or the hold expired
    """

    class Status(models.TextChoices):
        HELD = 'HELD', 'Held'
        CAPTURED = 'CAPTURED', 'Captured'
        RELEASED = 'RELEASED', 'Released'

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='holds')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name='wallet_holds')
    reference = models.CharField(max_length=100, unique=True, db_index=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Remembered per bucket so a release returns each naira to where it came from.
    spendable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    withdrawable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HELD)
    expires_at = models.DateTimeField(help_text="After this, a sweeper releases the hold.")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def capture(self):
        """Confirm the spend. Idempotent."""
        if self.status != self.Status.HELD:
            return False
        self.status = self.Status.CAPTURED
        self.resolved_at = timezone.now()
        self.save(update_fields=['status', 'resolved_at'])
        return True

    def release(self, reason="Checkout not completed"):
        """
        Return held funds to their original buckets. Idempotent.

        Deposited money must go back to SPENDABLE, not WITHDRAWABLE - otherwise an abandoned
        checkout would quietly convert non-withdrawable funds into withdrawable ones.
        """
        if self.status != self.Status.HELD:
            return False

        with transaction.atomic():
            if self.spendable_amount > 0:
                self.wallet.credit(
                    self.spendable_amount,
                    source=f"{reason} {self.reference}",
                    bucket=LedgerEntry.Bucket.SPENDABLE,
                    entry_type=LedgerEntry.EntryType.ORDER_PAYMENT_RELEASE,
                    idempotency_key=f"hold-release-spendable-{self.reference}",
                    order=self.order,
                )
            if self.withdrawable_amount > 0:
                self.wallet.credit(
                    self.withdrawable_amount,
                    source=f"{reason} {self.reference}",
                    bucket=LedgerEntry.Bucket.WITHDRAWABLE,
                    entry_type=LedgerEntry.EntryType.ORDER_PAYMENT_RELEASE,
                    idempotency_key=f"hold-release-withdrawable-{self.reference}",
                    order=self.order,
                )
            self.status = self.Status.RELEASED
            self.resolved_at = timezone.now()
            self.save(update_fields=['status', 'resolved_at'])
        return True

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]

    def __str__(self):
        return f"Hold {self.reference} - {self.amount} ({self.status})"


class PaystackEvent(models.Model):
    """
    Every webhook Paystack sends us, recorded before it is acted on.

    Paystack retries webhooks, and today the only thing standing between a retry and a
    double credit is a boolean flag on Payment. Recording the event id first - and skipping
    anything already seen - makes replay handling explicit rather than incidental.

    Also doubles as the evidence trail for the admin failed-payments screen.
    """

    class Status(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Received'
        PROCESSED = 'PROCESSED', 'Processed'
        DUPLICATE = 'DUPLICATE', 'Duplicate (ignored)'
        FAILED = 'FAILED', 'Failed'
        IGNORED = 'IGNORED', 'Ignored (unhandled type)'

    event_id = models.CharField(
        max_length=255, unique=True,
        help_text="Paystack event id, or a hash of the raw body when it sends none.",
    )
    event_type = models.CharField(max_length=100, db_index=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RECEIVED)

    payload = models.JSONField(default=dict, blank=True)
    signature_valid = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def mark(self, status, error=''):
        self.status = status
        self.error_message = error or ''
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'processed_at'])

    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['status', '-received_at']),
            models.Index(fields=['event_type', '-received_at']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return f"{self.event_type} {self.reference or self.event_id} - {self.status}"


class WalletDeposit(models.Model):
    """
    A customer topping their wallet up with their own money via Paystack.

    Deposits land in the SPENDABLE bucket: usable at checkout, never withdrawable to a
    bank. That asymmetry is the whole point - it is what stops the wallet being used to
    turn a stolen card into a bank transfer.

    ``paystack_transaction_id`` is captured at verification time because refunding a
    deposit to its original card (the safe way to return deposited money when an account
    closes) requires the Paystack transaction id, not our reference.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        ABANDONED = 'ABANDONED', 'Abandoned'

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='wallet_deposits')
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    authorization_url = models.URLField(blank=True)
    paystack_transaction_id = models.CharField(
        max_length=100, blank=True,
        help_text="Paystack's transaction id, needed to refund this deposit to source.",
    )
    failure_reason = models.TextField(blank=True)

    verified = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_as_successful(self, paystack_transaction_id=''):
        """
        Credit the deposit to the spendable bucket. Idempotent.

        Guarded twice: the ``verified`` flag short-circuits the common repeat, and the
        ledger idempotency key makes the credit itself at-most-once even if two callers
        (the verify endpoint and the webhook, which routinely race) get past the flag
        together.
        """
        if self.verified:
            return False

        with transaction.atomic():
            wallet, _ = Wallet.objects.select_for_update().get_or_create(user=self.user)
            wallet.credit(
                self.amount,
                source=f"Wallet deposit {self.reference}",
                bucket=LedgerEntry.Bucket.SPENDABLE,
                entry_type=LedgerEntry.EntryType.DEPOSIT,
                idempotency_key=f"deposit-{self.reference}",
                reference=self.reference,
            )

            self.status = self.Status.SUCCESS
            self.verified = True
            self.paid_at = timezone.now()
            if paystack_transaction_id:
                self.paystack_transaction_id = str(paystack_transaction_id)
            self.save(update_fields=[
                'status', 'verified', 'paid_at', 'paystack_transaction_id', 'updated_at',
            ])
        return True

    def mark_as_failed(self, reason=''):
        """Record a deposit that Paystack rejected. Never credits anything."""
        if self.verified:
            # A successful deposit must not be downgraded by a late failure webhook.
            return False
        self.status = self.Status.FAILED
        self.failure_reason = reason or ''
        self.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return True

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['reference']),
        ]

    def __str__(self):
        return f"Deposit {self.reference} - {self.amount} ({self.status})"
