from authentication.models import CustomUser
from django.dispatch import receiver
from django.db.models.signals import post_save


@receiver(post_save, sender=CustomUser)
def create_profile(sender, instance, created, **kwargs):
    if created:
        from .models import Vendor, Customer, BusinessAdmin

        # Create Vendor Profile
        if instance.role == CustomUser.Role.VENDOR and not hasattr(instance, "vendor_profile"):
            Vendor.objects.create(user=instance)

        # Create Customer Profile
        elif instance.role == CustomUser.Role.CUSTOMER and not hasattr(instance, "customer_profile"):
            Customer.objects.create(user=instance)

        # Create Business Admin Profile
        elif instance.role == CustomUser.Role.BUSINESS_ADMIN and not hasattr(instance, "business_admin_profile"):
            BusinessAdmin.objects.create(user=instance)


@receiver(post_save, sender=CustomUser)
def save_profile(sender, instance, **kwargs):
    # Save Vendor Profile
    if instance.role == CustomUser.Role.VENDOR and hasattr(instance, "vendor_profile"):
        instance.vendor_profile.save()

    # Save Customer Profile
    elif instance.role == CustomUser.Role.CUSTOMER and hasattr(instance, "customer_profile"):
        instance.customer_profile.save()

    # Save Business Admin Profile
    elif instance.role == CustomUser.Role.BUSINESS_ADMIN and hasattr(instance, "business_admin_profile"):
        instance.business_admin_profile.save()
