from django.db import models
from django.utils import timezone
import uuid
from decimal import Decimal
from authentication.models import CustomUser


# ========================
# ORDER SYSTEM
# ========================
class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        SHIPPED = 'SHIPPED', 'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELED = 'CANCELED', 'Canceled'

    order_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    products = models.ManyToManyField('store.Product', through='OrderItem', related_name='orders')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    payment_status = models.CharField(max_length=20, default='UNPAID')
    ordered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    def __str__(self):
        return f"Order {self.order_id} ({getattr(self.customer, 'email', 'Unknown')})"


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
        return getattr(self.product, 'vendor', None)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


# ========================
# PAYMENT SYSTEM
# ========================
class Payment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='PENDING')  # PENDING, SUCCESS, FAILED
    gateway = models.CharField(max_length=50, default='Paystack')
    paid_at = models.DateTimeField(null=True, blank=True)
    verified = models.BooleanField(default=False)

    def mark_as_successful(self):
        self.status = 'SUCCESS'
        self.verified = True
        self.paid_at = timezone.now()
        self.order.payment_status = 'PAID'
        self.order.status = Order.Status.PAID
        self.order.save(update_fields=['payment_status', 'status'])
        self.save(update_fields=['status', 'verified', 'paid_at'])

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
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='logs')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, default='INFO')  # INFO, WARNING, ERROR

    class Meta:
        permissions = [
            ("view_transactionlog_admin", "Can view transaction logs (admin only)"),
        ]

    def __str__(self):
        return f"[{self.level}] {self.order.order_id}: {self.message[:50]}"


class Refund(models.Model):
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='refund')
    reason = models.TextField(blank=True, null=True)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default='PENDING')  # PENDING, APPROVED, REJECTED
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def mark_as_approved(self):
        self.status = 'APPROVED'
        self.processed_at = timezone.now()
        self.save()


from django.db import models
from django.utils import timezone
from decimal import Decimal
import uuid
from authentication.models import CustomUser

# ========================
# WALLET SYSTEM
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
    source = models.CharField(max_length=255, blank=True, null=True)  # e.g., 'REFERRAL BONUS', 'ORDER PAYMENT'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.wallet.user.email} - {self.transaction_type} {self.amount} ({self.source})"


from django.contrib.auth import get_user_model
User = get_user_model()

class PayoutRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
