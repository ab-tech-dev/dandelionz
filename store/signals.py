from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
import logging

from .models import Product
from users.models import Notification
from authentication.models import CustomUser

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Product)
def log_approval_change(sender, instance, **kwargs):
    """
    Log when a product's approval status changes.
    Useful for audit trails and debugging.
    """
    if instance.pk:
        try:
            old_instance = Product.objects.get(pk=instance.pk)
            if old_instance.approval_status != instance.approval_status:
                logger.info(
                    f"Product '{instance.name}' approval status changed from "
                    f"'{old_instance.approval_status}' to '{instance.approval_status}' "
                    f"by admin {instance.approved_by}"
                )
        except Product.DoesNotExist:
            pass


@receiver(post_save, sender=Product)
def product_approval_notification(sender, instance, created, **kwargs):
    """
    Send notifications when:
    1. Vendor creates a product (product is pending) - notify vendor and admin
    2. Admin approves a product - notify vendor
    3. Admin rejects a product - notify vendor
    """
    if created:
        # NEW PRODUCT CREATED
        logger.info(f"New product '{instance.name}' created by vendor {instance.store.user} - Status: pending")
        
        # Notify vendor that product is pending approval
        vendor_user = instance.store.user
        Notification.objects.create(
            recipient=vendor_user,
            title="Product Pending Approval",
            message=f"Your product '{instance.name}' has been submitted and is pending admin approval. "
                   f"You will be notified once it's reviewed."
        )
        logger.info(f"Notification sent to vendor {vendor_user.email}: Product pending approval")
        
        # Notify all admins that a new product needs approval
        admin_users = CustomUser.objects.filter(is_admin=True)
        for admin in admin_users:
            Notification.objects.create(
                recipient=admin,
                title="New Product Pending Approval",
                message=f"New product '{instance.name}' from vendor '{instance.store.store_name}' "
                       f"needs your approval. Click to review."
            )
        logger.info(f"Notifications sent to {admin_users.count()} admins: New product needs approval")
    
    else:
        # PRODUCT UPDATED (approval status changed)
        
        if instance.approval_status == 'approved':
            logger.info(f"Product '{instance.name}' approved successfully")
            
            # Notify vendor that product is approved
            vendor_user = instance.store.user
            Notification.objects.create(
                recipient=vendor_user,
                title="Product Approved ✓",
                message=f"Great news! Your product '{instance.name}' has been approved and is now "
                       f"visible to customers."
            )
            logger.info(f"Notification sent to vendor {vendor_user.email}: Product approved")
        
        elif instance.approval_status == 'rejected':
            logger.info(f"Product '{instance.name}' rejected with reason: {instance.rejection_reason}")
            
            # Notify vendor that product is rejected with reason
            vendor_user = instance.store.user
            Notification.objects.create(
                recipient=vendor_user,
                title="Product Rejected - Action Required",
                message=f"Your product '{instance.name}' was rejected. "
                       f"Reason: {instance.rejection_reason}. "
                       f"Please review and resubmit with corrections."
            )
            logger.info(f"Notification sent to vendor {vendor_user.email}: Product rejected")

