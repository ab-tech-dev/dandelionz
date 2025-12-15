from authentication.models import CustomUser
from django.dispatch import receiver
from django.db.models.signals import post_save


@receiver(post_save, sender=CustomUser)
def create_vendor_profile(sender, instance, created, **kwargs):
    if created:
        from .models import Vendor, Customer, BusinessAdmin

        if instance.role == CustomUser.Role.VENDOR:
            Vendor.objects.get_or_create(user=instance)
        elif instance.role == CustomUser.Role.CUSTOMER:
            Customer.objects.get_or_create(user=instance)
        elif instance.role == CustomUser.Role.BUSINESS_ADMIN:
            BusinessAdmin.objects.get_or_create(user=instance)
