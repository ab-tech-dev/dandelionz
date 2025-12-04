from authentication.models import CustomUser
from django.dispatch import receiver
from django.db.models.signals import post_save


@receiver(post_save, sender=CustomUser)
def create_profile(sender, instance, created, **kwargs):
    from .models import Vendor, Customer, BusinessAdmin  
    if created:
        if instance.role == CustomUser.Role.VENDOR:
            Vendor.objects.create(user=instance)
        elif instance.role == CustomUser.Role.CUSTOMER:
            Customer.objects.create(user=instance)
        elif instance.role == CustomUser.Role.BUSINESS_ADMIN:
            BusinessAdmin.objects.create(user=instance)


@receiver(post_save, sender=CustomUser)
def save_profile(sender, instance, **kwargs):
    if instance.role == CustomUser.Role.VENDOR and hasattr(instance, "vendor_profile"):
        instance.vendor_profile.save()

    elif instance.role == CustomUser.Role.CUSTOMER and hasattr(instance, "customer_profile"):
        instance.customer_profile.save()

    elif instance.role == CustomUser.Role.BUSINESS_ADMIN and hasattr(instance, "business_admin_profile"):
        instance.business_admin_profile.save()
