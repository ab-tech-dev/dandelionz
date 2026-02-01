import logging
from celery import shared_task
from django.utils import timezone
from .notification_models import Notification
from authentication.models import CustomUser
from users.models import Vendor

logger = logging.getLogger("users.tasks")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={
        'max_retries': 5,
        'countdown': 60,
    },
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    name="users.send_scheduled_notification"
)
def send_scheduled_notification(self, notification_id: int):
    """
    Celery task to send a notification.
    
    Args:
        notification_id: The ID of the Notification object
    """
    try:
        notification = Notification.objects.get(id=notification_id)

        logger.info(
            f"[NotificationTask] Processing notification {notification_id}: {notification.title}"
        )

        # Mark notification as read after some processing
        notification.was_sent_websocket = True
        notification.save()

        return {
            "status": "success",
            "notification_id": notification_id,
        }

    except Notification.DoesNotExist:
        logger.warning(f"[NotificationTask] Notification with id {notification_id} not found.")
        return {"status": "failed", "reason": "notification_not_found"}

    except Exception as e:
        logger.error(
            f"[NotificationTask] Failed for notification {notification_id} "
            f"(attempt {self.request.retries}): {str(e)}"
        )
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="users.cleanup_old_notifications",
    ignore_result=True
)
def cleanup_old_notifications(self):
    """
    Celery task to clean up old notifications based on retention policy.
    Runs daily at 2 AM (configurable in CELERY_BEAT_SCHEDULE).
    
    Removes notifications older than NOTIFICATION_RETENTION_DAYS.
    """
    try:
        from django.conf import settings
        from django.utils import timezone
        from datetime import timedelta
        
        retention_days = getattr(settings, 'NOTIFICATION_RETENTION_DAYS', 30)
        cutoff_date = timezone.now() - timedelta(days=retention_days)
        
        # Delete old archived/deleted notifications
        deleted_count, _ = Notification.objects.filter(
            created_at__lt=cutoff_date,
            is_deleted=True
        ).delete()
        
        logger.info(
            f"[CleanupTask] Deleted {deleted_count} old notifications "
            f"(older than {retention_days} days)"
        )
        
        return {
            "status": "success",
            "notifications_deleted": deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
    
    except Exception as e:
        logger.error(f"[CleanupTask] Error cleaning up notifications: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)
