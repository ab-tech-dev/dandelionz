from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from transactions.models import OrderItem, TransactionLog, Wallet
from authentication.models import CustomUser

@receiver(post_save, sender=CustomUser)
def create_wallet_on_user_creation(sender, instance, created, **kwargs):
    """
    Automatically create a wallet when a new user is created.
    This ensures every user has a wallet for referral bonuses and transactions.
    Works for all creation methods: API, admin dashboard, management commands, etc.
    """
    if created:
        try:
            wallet, created_wallet = Wallet.objects.get_or_create(user=instance)
            if created_wallet:
                print(f"[signals.create_wallet_on_user_creation] Wallet created for user {instance.email}")
        except Exception as e:
            print(f"[signals.create_wallet_on_user_creation] Error creating wallet for user {instance.email}: {e}")


@receiver([post_save, post_delete], sender=OrderItem)
def update_order_total(sender, instance, **kwargs):
    """
    Recalculate order total whenever OrderItem is created/updated/deleted.
    Also create a TransactionLog entry (non-fatal).
    """
    order = instance.order
    if not order:
        return

    try:
        order.update_total()
    except Exception as e:
        # Prevent signal failure from breaking main flow; log to console and create a warning TransactionLog.
        print(f"[signals.update_order_total] error updating total for order {getattr(order,'order_id', None)}: {e}")
        try:
            TransactionLog.objects.create(
                order=order,
                message=f"Signal error updating order total: {e}",
                level="ERROR"
            )
        except Exception:
            pass
