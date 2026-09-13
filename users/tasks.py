import logging
from celery import shared_task
from django.utils import timezone
from .notification_models import Notification
from .notification_service import NotificationService
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
    """Send a single notification by ID."""
    try:
        notification = Notification.objects.get(id=notification_id)

        logger.info(
            f"[NotificationTask] Processing notification {notification_id}: {notification.title}"
        )

        if notification.was_sent_websocket:
            return {"status": "skipped", "reason": "already_sent", "notification_id": notification_id}

        if notification.is_draft:
            return {"status": "skipped", "reason": "draft", "notification_id": notification_id}

        if notification.scheduled_for and notification.scheduled_for > timezone.now():
            return {"status": "skipped", "reason": "scheduled_for_future", "notification_id": notification_id}

        NotificationService.send_websocket_notification(notification)
        NotificationService.send_email_notification(notification)

        # Honour the push intent that was recorded at creation time.  The
        # _requested_push flag is set by AdminNotificationViewSet.create for
        # both broadcast and single-recipient notifications so it survives the
        # scheduling delay.  Default to True so older notifications (created
        # before this field existed) still get a push attempt.
        requested_push = notification.metadata.get('_requested_push', True) if notification.metadata else True
        if requested_push and not notification.was_sent_push:
            try:
                NotificationService.send_push_notification(notification)
            except Exception:
                logger.exception(
                    "[NotificationTask] Push failed for scheduled notification %s", notification.id
                )

        return {"status": "success", "notification_id": notification_id}

    except Notification.DoesNotExist:
        logger.warning(f"[NotificationTask] Notification {notification_id} not found.")
        return {"status": "failed", "reason": "notification_not_found"}


@shared_task(
    bind=True,
    name="users.sweep_due_notifications",
    ignore_result=True,
)
def sweep_due_notifications(self):
    """
    Runs every 5 minutes via Celery Beat. Finds all unsent scheduled
    notifications whose fire time has passed and dispatches each one
    as an individual send_scheduled_notification task.
    """
    now = timezone.now()
    due_ids = list(
        Notification.objects.filter(
            is_draft=False,
            is_deleted=False,
            scheduled_for__isnull=False,
            scheduled_for__lte=now,
            was_sent_websocket=False,
        ).values_list("id", flat=True)
    )

    if not due_ids:
        return

    logger.info(f"[SweepTask] Dispatching {len(due_ids)} due notification(s): {due_ids}")
    for nid in due_ids:
        send_scheduled_notification.apply_async(args=[nid], queue="notifications")


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
    name="users.send_bulk_push_notifications",
)
def send_bulk_push_notifications(self, notification_ids: list):
    """
    Send push notifications for a batch of already-created Notification rows.

    Used for admin group broadcasts: the notifications themselves are created
    synchronously (so the admin panel can show them immediately), but the
    Expo round-trip per recipient is deferred here so a broadcast to a large
    group can't hang or time out the admin's request.

    Per-recipient failures (missing token, disabled preference, a single bad
    Expo response) are caught and logged individually and do not stop the rest
    of the batch or trigger a task-level retry; only an unexpected error
    iterating the batch itself does.
    """
    notifications = Notification.objects.filter(
        id__in=notification_ids,
        is_draft=False,
        was_sent_push=False,
    )
    sent = 0
    failed = 0
    for notification in notifications:
        try:
            if NotificationService.send_push_notification(notification):
                sent += 1
            else:
                failed += 1
        except Exception:
            logger.exception(
                "[NotificationTask] Push failed for notification %s", notification.id
            )
            failed += 1

    logger.info(
        "[NotificationTask] Bulk push complete: %d sent, %d failed, %d total",
        sent, failed, len(notification_ids),
    )
    return {"status": "success", "sent": sent, "failed": failed, "total": len(notification_ids)}
