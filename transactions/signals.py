from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
import logging
from transactions.models import OrderItem, TransactionLog, Wallet
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
