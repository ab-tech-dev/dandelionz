from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import OrderItem, TransactionLog

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
