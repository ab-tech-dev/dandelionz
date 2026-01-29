from django.db import models
from django.utils import timezone
import uuid
from decimal import Decimal
from authentication.models import CustomUser


# ========================
# WALLET SYSTEM (Defined first for dependencies)
# ========================
class Wallet(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def credit(self, amount, source=None):
        """Add funds to the wallet"""
        self.balance += Decimal(amount)
        self.save(update_fields=['balance', 'updated_at'])
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type=WalletTransaction.TransactionType.CREDIT,
            amount=amount,
            source=source
        )

    def debit(self, amount, source=None):
        """Subtract funds from the wallet"""
        if self.balance < Decimal(amount):
            raise ValueError("Insufficient wallet balance")
        self.balance -= Decimal(amount)
        self.save(update_fields=['balance', 'updated_at'])
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type=WalletTransaction.TransactionType.DEBIT,
            amount=amount,
            source=source
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
        """Calculate and save delivery fee for this order using Radar API"""
        from .delivery_service import DeliveryFeeCalculator
        
        # Validate required coordinates
        if not all([self.restaurant_lat, self.restaurant_lng, 
                    self.customer_lat, self.customer_lng]):
            raise ValueError("All coordinate fields are required for delivery fee calculation")
        
        calculator = DeliveryFeeCalculator()
        result = calculator.calculate_fee(
            origin_lat=self.restaurant_lat,
            origin_lng=self.restaurant_lng,
            dest_lat=self.customer_lat,
            dest_lng=self.customer_lng
        )
        
        if result['success']:
            self.delivery_fee = Decimal(str(result['fee']))
            self.delivery_distance = result['distance']
            self.delivery_duration = result['duration']
            self.delivery_distance_miles = result['distance_miles']
            self.save(update_fields=['delivery_fee', 'delivery_distance', 'delivery_duration', 'delivery_distance_miles'])
            return True
        else:
            raise ValueError(f"Delivery fee calculation failed: {result.get('error')}")

    def is_within_delivery_radius(self):
        """Check if order is within delivery radius"""
        if not self.delivery_distance_miles:
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
        ONE_YEAR = '1_year', '1 Year'

    # Mapping of duration to number of installments
    DURATION_INSTALLMENTS = {
        '1_month': 1,
        '3_months': 3,
        '6_months': 6,
        '1_year': 12,
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
            self.status = 'COMPLETED'
            self.order.payment_status = 'PAID'
            self.order.status = Order.Status.PAID
            self.order.save(update_fields=['payment_status', 'status'])
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
