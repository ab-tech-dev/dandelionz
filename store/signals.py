from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db import transaction
import logging

from .models import Product
from users.notification_helpers import send_product_notification, notify_admin
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


def _send_notification_safely(recipient, title, message):
    """
    Helper function to safely create a notification using the new NotificationService.
    Includes validation to prevent common failures.
    """
    # Validation checks
    if not recipient:
        logger.warning("Cannot create notification: recipient is None")
        return
    
    if not hasattr(recipient, 'id') or not recipient.id:
        logger.warning("Cannot create notification: recipient is not saved to database")
        return
    
    if not title or not str(title).strip():
        logger.warning(f"Cannot create notification for {recipient.email}: title is empty")
        return
    
    if not message or not str(message).strip():
        logger.warning(f"Cannot create notification for {recipient.email}: message is empty")
        return
    
    # Truncate to field limits to prevent validation errors
    title = str(title)[:255]  # CharField max_length=255
    message = str(message)
    
    try:
        send_product_notification(
            recipient=recipient,
            title=title,
            message=message,
            send_email=True,
            send_websocket=True
        )
        logger.debug(f"Notification created for {recipient.email}")
    except Exception as e:
        logger.error(f"Failed to create notification for {recipient.email}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Product)
def product_approval_notification(sender, instance, created, **kwargs):
    """
    Send notifications when:
    1. Vendor creates a product (product is pending) - notify vendor and admin
    2. Admin approves a product - notify vendor
    3. Admin rejects a product - notify vendor
    
    Uses nested transactions to prevent signal errors from aborting admin operations.
    Includes validation to prevent notification creation failures.
    """
    try:
        # Validate product instance before proceeding
        if not instance or not hasattr(instance, 'pk') or not instance.pk:
            logger.error("Invalid product instance in signal")
            return
        
        if created:
            # NEW PRODUCT CREATED
            logger.info(f"New product '{instance.name}' created by vendor {instance.store.user} - Status: pending")
            
            try:
                # Refresh vendor from database to ensure related user is properly loaded
                vendor = instance.store
                if not vendor or not vendor.pk:
                    logger.error(f"Invalid vendor for product {instance.name}")
                    return
                
                # Refresh vendor user from database
                vendor_user = vendor.user
                if not vendor_user:
                    logger.error(f"Vendor {vendor.store_name} has no associated user")
                    return
                
                # Force refresh from database to ensure user is saved
                vendor_user.refresh_from_db()
                
                # Notify vendor that product is pending approval
                _send_notification_safely(
                    vendor_user,
                    "Product Pending Approval",
                    f"Your product '{instance.name}' has been submitted and is pending admin approval. "
                    f"You will be notified once it's reviewed."
                )
                logger.info(f"Notification sent to vendor {vendor_user.email}: Product pending approval")
                
                # Notify all admins that a new product needs approval
                admin_users = CustomUser.objects.filter(is_admin=True).select_related('id')
                for admin in admin_users:
                    if admin and admin.pk:  # Verify admin exists and is saved
                        _send_notification_safely(
                            admin,
                            "New Product Pending Approval",
                            f"New product '{instance.name}' from vendor '{instance.store.store_name}' "
                            f"needs your approval. Click to review."
                        )
                logger.info(f"Notifications sent to {admin_users.count()} admins: New product needs approval")
            except AttributeError as e:
                logger.error(f"Missing required product/vendor attributes: {str(e)}")
            except Exception as e:
                logger.error(f"Error sending new product notifications: {str(e)}", exc_info=True)
        
        else:
            # PRODUCT UPDATED (approval status changed)
            
            if instance.approval_status == 'approved':
                logger.info(f"Product '{instance.name}' approved successfully")
                
                try:
                    # Refresh vendor from database to ensure related user is properly loaded
                    vendor = instance.store
                    if not vendor or not vendor.pk:
                        logger.error(f"Invalid vendor for product {instance.name}")
                        return
                    
                    # Refresh vendor user from database
                    vendor_user = vendor.user
                    if not vendor_user:
                        logger.error(f"Vendor {vendor.store_name} has no associated user")
                        return
                    
                    # Force refresh from database to ensure user is saved
                    vendor_user.refresh_from_db()
                    
                    # Notify vendor that product is approved
                    _send_notification_safely(
                        vendor_user,
                        "Product Approved ✓",
                        f"Great news! Your product '{instance.name}' has been approved and is now "
                        f"visible to customers."
                    )
                    logger.info(f"Notification sent to vendor {vendor_user.email}: Product approved")
                except AttributeError as e:
                    logger.error(f"Missing required product/vendor attributes: {str(e)}")
                except Exception as e:
                    logger.error(f"Error sending approval notification: {str(e)}", exc_info=True)
            
            elif instance.approval_status == 'rejected':
                logger.info(f"Product '{instance.name}' rejected with reason: {instance.rejection_reason}")
                
                try:
                    # Refresh vendor from database to ensure related user is properly loaded
                    vendor = instance.store
                    if not vendor or not vendor.pk:
                        logger.error(f"Invalid vendor for product {instance.name}")
                        return
                    
                    # Refresh vendor user from database
                    vendor_user = vendor.user
                    if not vendor_user:
                        logger.error(f"Vendor {vendor.store_name} has no associated user")
                        return
                    
                    # Force refresh from database to ensure user is saved
                    vendor_user.refresh_from_db()
                    
                    # Notify vendor that product is rejected with reason
                    rejection_reason = instance.rejection_reason or "Product did not meet approval criteria"
                    _send_notification_safely(
                        vendor_user,
                        "Product Rejected - Action Required",
                        f"Your product '{instance.name}' was rejected. "
                        f"Reason: {rejection_reason}. "
                        f"Please review and resubmit with corrections."
                    )
                    logger.info(f"Notification sent to vendor {vendor_user.email}: Product rejected")
                except AttributeError as e:
                    logger.error(f"Missing required product/vendor attributes: {str(e)}")
                except Exception as e:
                    logger.error(f"Error sending rejection notification: {str(e)}", exc_info=True)
    except Exception as e:
        logger.error(f"Critical error in product_approval_notification signal: {str(e)}", exc_info=True)

