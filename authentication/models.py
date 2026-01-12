from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from cloudinary.models import CloudinaryField
import uuid


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

    def create_business_admin(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', CustomUser.Role.BUSINESS_ADMIN)
        return self.create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', CustomUser.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


# =====================================================
# CUSTOM USER MODEL
# =====================================================
class CustomUser(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        BUSINESS_ADMIN = 'BUSINESS_ADMIN', 'Business Admin'
        VENDOR = 'VENDOR', 'Vendor'
        CUSTOMER = 'CUSTOMER', 'Customer'
        DELIVERY_AGENT = 'DELIVERY_AGENT', 'Delivery Agent'

    # Primary key as UUID
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)

    # Core fields
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = CloudinaryField('image', null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    referral_code = models.CharField(
        max_length=12,
        unique=True,
        blank=True,
        null=True
    )

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

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self._generate_unique_referral_code()
        super().save(*args, **kwargs)

    def _generate_unique_referral_code(self):
        while True:
            code = uuid.uuid4().hex[:12].upper()
            if not CustomUser.objects.filter(referral_code=code).exists():
                return code

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_business_admin(self):
        return self.role == self.Role.BUSINESS_ADMIN

    @property
    def is_vendor(self):
        return self.role == self.Role.VENDOR

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_delivery_agent(self):
        return self.role == self.Role.DELIVERY_AGENT


# =====================================================
# REFERRAL MODEL 
# =====================================================
class Referral(models.Model):
    referrer = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='referrals_made'
    )
    referred_user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='referrals_received'
    )
    bonus_awarded = models.BooleanField(default=False)
    bonus_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)
