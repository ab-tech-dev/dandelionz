from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from cloudinary.models import CloudinaryField


# =====================================================
# USER MANAGER
# =====================================================
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The email field must be set')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', CustomUser.Role.ADMIN)

        return self.create_user(email, password, **extra_fields)


# =====================================================
# USER MODEL
# =====================================================
class CustomUser(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        VENDOR = 'VENDOR', 'Vendor'
        CUSTOMER = 'CUSTOMER', 'Customer'

    # Core fields
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = CloudinaryField('image', null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)

    # System fields
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Manager
    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_vendor(self):
        return self.role == self.Role.VENDOR

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER


# =====================================================
# VENDOR PROFILE (One-to-One with User)
# =====================================================
class Vendor(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='vendor_profile')
    store_name = models.CharField(max_length=150)
    store_description = models.TextField(blank=True)
    business_registration_number = models.CharField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    recipient_code = models.CharField(max_length=100, blank=True, null=True, help_text="Paystack recipient code")
    is_verified_vendor = models.BooleanField(default=False)

    def __str__(self):
        return self.store_name or self.user.full_name


# =====================================================
# CUSTOMER PROFILE (One-to-One with User)
# =====================================================
class Customer(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='customer_profile')
    shipping_address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    loyalty_points = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.user.full_name or self.user.email


# =====================================================
# SIGNALS (auto-create profile)
# =====================================================
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == CustomUser.Role.VENDOR:
            Vendor.objects.create(user=instance)
        elif instance.role == CustomUser.Role.CUSTOMER:
            Customer.objects.create(user=instance)

@receiver(post_save, sender=CustomUser)
def save_user_profile(sender, instance, **kwargs):
    if instance.role == CustomUser.Role.VENDOR and hasattr(instance, 'vendor_profile'):
        instance.vendor_profile.save()
    elif instance.role == CustomUser.Role.CUSTOMER and hasattr(instance, 'customer_profile'):
        instance.customer_profile.save()


