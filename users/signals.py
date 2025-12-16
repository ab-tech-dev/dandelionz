from django.db.models.signals import post_save
from django.dispatch import receiver
from authentication.models import CustomUser
from users.models import Vendor, Customer, BusinessAdmin

@receiver(post_save, sender=CustomUser)
def create_role_profile(sender, instance, created, **kwargs):
    if not created:
        return

    if instance.role == CustomUser.Role.VENDOR:
        Vendor.objects.get_or_create(
            user=instance,
            defaults={
                "store_name": "Unnamed Store",
                "is_verified_vendor": False
            }
        )

    elif instance.role == CustomUser.Role.CUSTOMER:
        Customer.objects.get_or_create(user=instance)

    elif instance.role == CustomUser.Role.BUSINESS_ADMIN:
        BusinessAdmin.objects.get_or_create(user=instance)
