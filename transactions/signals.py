from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
import logging
from transactions.models import OrderItem, TransactionLog, Wallet, Order, OrderStatusHistory
from authentication.models import CustomUser

logger = logging.getLogger(__name__)

@receiver(post_save, sender=CustomUser)
def create_wallet_on_user_creation(sender, instance, created, **kwargs):
    """
    Automatically create a wallet when a new user is created.
    This ensures every user has a wallet for referral bonuses and transactions.
    Works for all creation methods: API, admin dashboard, management commands, etc.
    Uses atomic transaction with proper error handling to prevent transaction aborts.
    """
    if created:
        try:
            with transaction.atomic():
                wallet, created_wallet = Wallet.objects.get_or_create(user=instance)
                if created_wallet:
                    logger.info(f"[signals.create_wallet_on_user_creation] Wallet created for user {instance.email}")
        except Exception as e:
            logger.error(f"[signals.create_wallet_on_user_creation] Error creating wallet for user {instance.email}: {e}", exc_info=True)


@receiver(pre_save, sender=Order)
def cache_order_previous_state(sender, instance, **kwargs):
    """
    Cache previous order status/credit flag before save.
    This enables accurate post-save change detection even when update_fields is None.
    """
    if not instance.pk:
        instance._previous_status = None
        instance._previous_vendors_credited = False
        return

    prev = Order.objects.filter(pk=instance.pk).values('status', 'vendors_credited').first()
    instance._previous_status = prev['status'] if prev else None
    instance._previous_vendors_credited = prev['vendors_credited'] if prev else False


@receiver(post_save, sender=Order)
def track_order_status_changes(sender, instance, update_fields, **kwargs):
    """
    Automatically create OrderStatusHistory entries when order status changes.
    This ensures complete audit trail of order progression.
    Runs after order save to track status transitions.
    """
    if update_fields is None or 'status' in update_fields:
        try:
            with transaction.atomic():
                previous_status = getattr(instance, '_previous_status', None)
                previous_credited = getattr(instance, '_previous_vendors_credited', False)

                current_status = instance.status
                status_changed = previous_status and previous_status != current_status

                if status_changed:
                    # Determine who changed the status (default to SYSTEM)
                    changed_by = 'SYSTEM'
                    admin_user = None

                    # Create status history entry
                    OrderStatusHistory.objects.create(
                        order=instance,
                        status=current_status,
                        changed_by=changed_by,
                        admin=admin_user,
                        reason=f"Order status updated to {current_status}"
                    )

                    logger.info(f"[signals.track_order_status_changes] Order {instance.order_id} status changed to {current_status}")

                # Auto-credit vendors if order just moved to DELIVERED and not yet credited
                if current_status == Order.Status.DELIVERED and not previous_credited and not instance.vendors_credited:
                    from transactions.views import credit_vendors_for_order
                    try:
                        credit_vendors_for_order(instance, source_prefix="Delivery")
                        instance.vendors_credited = True
                        instance.save(update_fields=['vendors_credited'])
                        logger.info(f"[signals.track_order_status_changes] Vendors credited for delivered order {instance.order_id}")
                    except Exception as credit_error:
                        logger.error(
                            f"[signals.track_order_status_changes] Failed to credit vendors for order {instance.order_id}: {credit_error}",
                            exc_info=True
                        )
        except Exception as e:
            # Log error but don't fail the main transaction
            logger.error(f"[signals.track_order_status_changes] Error tracking status change for order {getattr(instance, 'order_id', None)}: {e}", exc_info=True)


@receiver([post_save, post_delete], sender=OrderItem)
def update_order_total(sender, instance, **kwargs):
    """
    Recalculate order total whenever OrderItem is created/updated/deleted.
    Also create a TransactionLog entry (non-fatal).
    Uses try-catch to prevent signal failures from breaking main flow.
    """
    order = instance.order
    if not order:
        return

    try:
        with transaction.atomic():
            order.update_total()
    except Exception as e:
        # Prevent signal failure from breaking main flow; log error and create a warning TransactionLog.
        logger.error(f"[signals.update_order_total] error updating total for order {getattr(order,'order_id', None)}: {e}", exc_info=True)
        try:
            TransactionLog.objects.create(
                order=order,
                message=f"Signal error updating order total: {e}",
                level="ERROR"
            )
        except Exception as log_error:
            logger.error(f"[signals.update_order_total] Failed to create TransactionLog: {log_error}")
