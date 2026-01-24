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
    recipient_code = models.CharField(max_length=100, blank=True)
    is_verified_vendor = models.BooleanField(default=False)
    vendor_status = models.CharField(
        max_length=20, 
        choices=VENDOR_STATUS_CHOICES, 
        default='pending',
        help_text="Approval status of the vendor account"
    )


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
