from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Vendor(models.Model):
    VENDOR_STATUS_CHOICES = [
        ('approved', 'Approved'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vendor_profile")
    store_name = models.CharField(max_length=150, default="Unnamed Store")
    store_description = models.TextField(blank=True)
    business_registration_number = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=200, blank=True, null=True, help_text="Name on the bank account")
    recipient_code = models.CharField(max_length=100, blank=True)
    is_verified_vendor = models.BooleanField(default=False)
    vendor_status = models.CharField(
        max_length=20, 
        choices=VENDOR_STATUS_CHOICES, 
        default='pending',
        help_text="Approval status of the vendor account"
    )

    def get_wallet_balance(self):
        """Get vendor's wallet balance"""
        from transactions.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=self.user)
        return wallet.balance
    
    def get_wallet_earnings(self):
        """Get vendor's total earnings from transactions"""
        from transactions.models import WalletTransaction
        credits = WalletTransaction.objects.filter(
            wallet__user=self.user,
            transaction_type='CREDIT'
        ).aggregate(models.Sum('amount'))['amount__sum'] or 0
        return credits
    
    def get_available_balance(self):
        """
        Get vendor's available balance (withdrawable).
        This is the wallet balance that vendors can withdraw.
        Includes funds from DELIVERED orders only.
        """
        from transactions.models import Wallet
        wallet, _ = Wallet.objects.get_or_create(user=self.user)
        return wallet.balance
    
    def get_pending_balance(self):
        """
        Get vendor's pending balance.
        This is the value of orders that have been paid but NOT YET DELIVERED.
        These funds are NOT yet available for withdrawal.
        """
        from transactions.models import Order
        from decimal import Decimal
        
        # Get all paid but undelivered orders for this vendor
        pending_orders = Order.objects.filter(
            order_items__product__store=self,
            payment_status='PAID',
            status__in=['PAID', 'SHIPPED']  # Paid but not yet delivered
        ).distinct()
        
        pending_amount = Decimal('0.00')
        for order in pending_orders:
            for item in order.order_items.filter(product__store=self):
                # Calculate vendor's share (90% after 10% platform commission)
                vendor_share = item.item_subtotal * Decimal('0.90')
                pending_amount += vendor_share
        
        return pending_amount
    
    def get_total_earnings(self):
        """Get total earnings from all delivered orders"""
        return self.get_available_balance() + self.get_pending_balance()
    
    def get_pending_order_count(self):
        """Get count of paid but undelivered orders"""
        from transactions.models import Order
        return Order.objects.filter(
            order_items__product__store=self,
            payment_status='PAID',
            status__in=['PAID', 'SHIPPED']
        ).distinct().count()
    
    def __str__(self):
        return f"{self.store_name} ({self.user.email})"


class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    shipping_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    loyalty_points = models.PositiveIntegerField(default=0)

class BusinessAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="business_admin_profile")
    position = models.CharField(max_length=100, default="Staff Admin")
    can_manage_vendors = models.BooleanField(default=True)
    can_manage_orders = models.BooleanField(default=True)
    can_manage_payouts = models.BooleanField(default=True)
    can_manage_inventory = models.BooleanField(default=True)

    def __str__(self):
        return self.user.full_name
    
    




class Notification(models.Model):
    RECIPIENT_TYPE_CHOICES = [
        ('USERS', 'Users'),
        ('VENDORS', 'Vendors'),
        ('ALL', 'All'),
    ]
    
    STATUS_CHOICES = [
        ('Sent', 'Sent'),
        ('Draft', 'Draft'),
        ('Scheduled', 'Scheduled'),
    ]

    # For individual notifications (backward compatibility)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    
    # For admin broadcast notifications
    recipient_type = models.CharField(
        max_length=20,
        choices=RECIPIENT_TYPE_CHOICES,
        null=True,
        blank=True,
        help_text="Type of recipients for admin broadcasts (USERS, VENDORS, or ALL)"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Sent',
        help_text="Status of the notification (Sent, Draft, or Scheduled)"
    )
    
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="ISO 8601 datetime for when to send scheduled notifications"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_notifications',
        help_text="Admin user who created the notification"
    )
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient_type', 'status']),
            models.Index(fields=['scheduled_at']),
        ]

    def __str__(self):
        if self.recipient:
            return f"{self.recipient.email}: {self.title}"
        return f"{self.recipient_type} - {self.title}"


class DeliveryAgent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentPIN(models.Model):
    """Model to store payment PIN for withdrawals (for vendors and customers)"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='payment_pin', null=True, blank=True)
    pin_hash = models.CharField(max_length=255)  # Hashed PIN, never store plain text
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def set_pin(self, pin):
        """Hash and set the PIN"""
        from django.contrib.auth.hashers import make_password
        self.pin_hash = make_password(pin)
        self.save(update_fields=['pin_hash', 'updated_at'])
    
    def verify_pin(self, pin):
        """Verify the provided PIN against the hash"""
        from django.contrib.auth.hashers import check_password
        return check_password(pin, self.pin_hash)
    
    def __str__(self):
        return f"PIN for {self.vendor.store_name}"


class PayoutRequest(models.Model):
    """Model to track withdrawal requests from vendors and customers"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('successful', 'Successful'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='payout_requests', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_requests', null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="Status of the payout request"
    )
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=200)
    recipient_code = models.CharField(max_length=100, blank=True, null=True)
    reference = models.CharField(max_length=100, unique=True)  # For tracking with payment provider
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, null=True)
    
    def __str__(self):
        if self.vendor:
            return f"Payout {self.id} - {self.vendor.store_name} - {self.status}"
        else:
            return f"Withdrawal {self.id} - {self.user.email} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['user', 'status']),
        ]

