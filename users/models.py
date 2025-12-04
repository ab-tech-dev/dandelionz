from django.db import models
from django.conf import settings
from authentication.models import CustomUser
from django.utils import timezone

User = settings.AUTH_USER_MODEL

class Vendor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="vendor_profile")
    store_name = models.CharField(max_length=150)
    store_description = models.TextField(blank=True)
    business_registration_number = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    recipient_code = models.CharField(max_length=100, blank=True)
    is_verified_vendor = models.BooleanField(default=False)

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
    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.recipient.email}: {self.title}"


class DeliveryAgent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
