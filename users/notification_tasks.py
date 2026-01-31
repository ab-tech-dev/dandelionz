"""
Celery tasks for notification operations
"""

from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

from .notification_models import Notification, NotificationLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_notification_email(self, notification_id: str):
    """
    Send notification via email asynchronously.
    
    Args:
        notification_id: UUID of notification to send
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        user = notification.user
        
        if not notification.was_sent_email:
            # Prepare email context
            context = {
                'user_name': getattr(user, 'first_name', user.email.split('@')[0]),
                'title': notification.title,
                'message': notification.message,
                'description': notification.description,
                'action_url': notification.action_url,
                'action_text': notification.action_text,
                'priority': notification.priority,
                'created_at': notification.created_at,
                'notification_id': str(notification.id),
            }

            # Render HTML email
            html_message = render_to_string(
                'emails/notification_email.html',
                context
            )

            # Send email
            send_mail(
                subject=f"[{notification.priority.upper()}] {notification.title}",
                message=notification.message,
                from_email=settings.NOTIFICATION_EMAIL_FROM,
                recipient_list=[user.email if hasattr(user, 'email') else str(user)],
                html_message=html_message,
                fail_silently=False,
            )

            # Update notification
            notification.was_sent_email = True
            notification.send_attempts += 1
            notification.save(update_fields=['was_sent_email', 'send_attempts'])

            # Log success
            NotificationLog.objects.create(
                notification=notification,
                event_type='sent',
                channel='email',
                status='success'
            )

            logger.info(f"Email sent for notification {notification_id} to {user.email if hasattr(user, 'email') else user}")

    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
    except Exception as exc:
        logger.error(f"Error sending notification email: {str(exc)}", exc_info=True)
        
        # Retry with exponential backoff
        try:
            self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            # Log final failure
            try:
                notification = Notification.objects.get(id=notification_id)
                NotificationLog.objects.create(
                    notification=notification,
                    event_type='sent',
                    channel='email',
                    status='failed',
                    error_message=str(exc)
                )
            except:
                pass


@shared_task
def cleanup_expired_notifications():
    """
    Periodic task to clean up expired notifications.
    Run this via Celery Beat scheduler.
    
    Schedule: Every 24 hours
    """
    try:
        from django.utils import timezone
        from .notification_service import NotificationService
        
        count = NotificationService.cleanup_expired_notifications()
        logger.info(f"Cleanup task completed: removed {count} expired notifications")
        
        return {
            'status': 'success',
            'cleaned_up': count
        }
    except Exception as e:
        logger.error(f"Error in cleanup task: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task
def send_batch_notifications(notification_ids: list):
    """
    Send multiple notifications asynchronously.
    
    Args:
        notification_ids: List of notification UUIDs
    """
    try:
        from .notification_service import NotificationService
        
        count = 0
        errors = []
        
        for notification_id in notification_ids:
            try:
                notification = Notification.objects.get(id=notification_id)
                if NotificationService.send_websocket_notification(notification):
                    count += 1
            except Exception as e:
                logger.error(f"Error sending notification {notification_id}: {str(e)}")
                errors.append({
                    'notification_id': notification_id,
                    'error': str(e)
                })
        
        logger.info(f"Batch send completed: {count} sent, {len(errors)} failed")
        
        return {
            'status': 'completed',
            'sent': count,
            'failed': len(errors),
            'errors': errors
        }
    except Exception as e:
        logger.error(f"Error in batch send: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task
def resend_failed_notifications():
    """
    Retry sending failed notifications.
    Run this via Celery Beat scheduler periodically.
    
    Schedule: Every 30 minutes
    """
    try:
        from .notification_service import NotificationService
        
        # Get notifications that failed to send
        failed_notifications = Notification.objects.filter(
            was_sent_websocket=False,
            send_attempts__lt=3
        )[:100]
        
        count = 0
        for notification in failed_notifications:
            try:
                if NotificationService.send_websocket_notification(notification):
                    count += 1
            except Exception as e:
                logger.warning(f"Retry failed for notification {notification.id}: {str(e)}")
        
        logger.info(f"Retry task completed: resent {count} notifications")
        
        return {
            'status': 'success',
            'resent': count
        }
    except Exception as e:
        logger.error(f"Error in resend task: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task
def archive_old_notifications(days: int = 90):
    """
    Archive notifications older than specified days.
    
    Args:
        days: Age threshold in days
    """
    try:
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days)
        old_notifications = Notification.objects.filter(
            created_at__lt=cutoff_date,
            is_archived=False
        )
        
        count = old_notifications.count()
        old_notifications.update(is_archived=True)
        
        logger.info(f"Archived {count} old notifications")
        
        return {
            'status': 'success',
            'archived': count
        }
    except Exception as e:
        logger.error(f"Error archiving notifications: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e)
        }
