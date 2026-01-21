from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
import logging
from authentication.models import CustomUser
from users.models import Vendor, Customer, BusinessAdmin

logger = logging.getLogger(__name__)

@receiver(post_save, sender=CustomUser)
def create_role_profile(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        # Use atomic transaction to prevent signal errors from aborting admin transactions
        with transaction.atomic():
            if instance.role == CustomUser.Role.VENDOR:
                try:
                    Vendor.objects.get_or_create(
                        user=instance,
                        defaults={
                            "store_name": "Unnamed Store",
                            "is_verified_vendor": False
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to create Vendor profile for user {instance.email}: {str(e)}")

            elif instance.role == CustomUser.Role.CUSTOMER:
                try:
                    Customer.objects.get_or_create(user=instance)
                except Exception as e:
                    logger.error(f"Failed to create Customer profile for user {instance.email}: {str(e)}")

            elif instance.role == CustomUser.Role.BUSINESS_ADMIN:
                try:
                    BusinessAdmin.objects.get_or_create(user=instance)
                except Exception as e:
                    logger.error(f"Failed to create BusinessAdmin profile for user {instance.email}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in create_role_profile signal for user {instance.email}: {str(e)}", exc_info=True)
