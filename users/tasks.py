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
    Celery task to send a scheduled notification to the specified recipient group.
    This task is triggered by Celery Beat at the scheduled_at datetime.
    
    Args:
        notification_id: The ID of the scheduled Notification object
    """
    try:
        notification = Notification.objects.get(id=notification_id)

        logger.info(
            f"[ScheduledNotificationTask] Processing scheduled notification {notification_id}: "
            f"{notification.title} for {notification.recipient_type}"
        )

        # Only process if status is still 'Scheduled'
        if notification.status != 'Scheduled':
            logger.warning(
                f"[ScheduledNotificationTask] Notification {notification_id} "
                f"status is '{notification.status}', skipping."
            )
            return {"status": "skipped", "reason": "notification_not_scheduled"}

        # Determine recipients based on recipient_type
        recipients = _get_recipients_by_type(notification.recipient_type)

        # Create individual notifications for each recipient
        notifications_to_create = [
            Notification(
                recipient=recipient,
                title=notification.title,
                message=notification.message,
                status='Sent',
                created_by=notification.created_by,
                created_at=timezone.now()
            )
            for recipient in recipients
        ]

        if notifications_to_create:
            Notification.objects.bulk_create(notifications_to_create, batch_size=1000)
            logger.info(
                f"[ScheduledNotificationTask] Successfully sent {len(notifications_to_create)} "
                f"notifications to {notification.recipient_type}"
            )
        else:
            logger.warning(
                f"[ScheduledNotificationTask] No recipients found for {notification.recipient_type}"
            )

        # Update the broadcast notification status to 'Sent'
        notification.status = 'Sent'
        notification.save()

        return {
            "status": "success",
            "notification_id": notification_id,
            "recipients_count": len(notifications_to_create)
        }

    except Notification.DoesNotExist:
        logger.warning(f"[ScheduledNotificationTask] Notification with id {notification_id} not found.")
        return {"status": "failed", "reason": "notification_not_found"}

    except Exception as e:
        logger.error(
            f"[ScheduledNotificationTask] Failed for notification {notification_id} "
            f"(attempt {self.request.retries}): {str(e)}"
        )
        raise self.retry(exc=e)


def _get_recipients_by_type(recipient_type: str):
    """
    Helper function to get recipients based on the recipient_type.

    Args:
        recipient_type: One of 'ALL', 'USERS', or 'VENDORS'

    Returns:
        QuerySet of CustomUser objects
    """
    if recipient_type == 'ALL':
        # Send to all active users
        return CustomUser.objects.filter(is_active=True, status='ACTIVE')

    elif recipient_type == 'USERS':
        # Send to all customers (non-vendor, non-admin users)
        return CustomUser.objects.filter(
            is_active=True,
            status='ACTIVE',
            role=CustomUser.Role.CUSTOMER
        )

    elif recipient_type == 'VENDORS':
        # Send to all approved vendors
        vendor_user_ids = Vendor.objects.filter(
            vendor_status='approved'
        ).values_list('user_id', flat=True)
        return CustomUser.objects.filter(
            uuid__in=vendor_user_ids,
            is_active=True,
            status='ACTIVE'
        )

    else:
        logger.warning(f"Unknown recipient_type: {recipient_type}")
        return CustomUser.objects.none()


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
