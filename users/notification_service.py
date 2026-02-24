"""
Notification Service Layer
Handles all notification business logic, delivery, and persistence.
"""

import logging
from typing import List, Dict, Any, Optional
from django.db.models import Q, Count
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta
import uuid

from .notification_models import (
    Notification, NotificationType, NotificationPreference, NotificationLog
)
from django.conf import settings
from django.contrib.auth import get_user_model
from authentication.core.task_dispatch import dispatch_task

User = get_user_model()
logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


class NotificationService:
    """Main service for managing notifications"""

    @staticmethod
    def create_notification(
        user: User,
        title: str,
        message: str,
        notification_type: Optional[NotificationType] = None,
        category: str = '',
        priority: str = 'normal',
        description: str = '',
        action_url: str = '',
        action_text: str = '',
        metadata: Dict[str, Any] = None,
        related_object_type: str = '',
        related_object_id: str = '',
        expires_at: Optional[timezone.datetime] = None,
        is_draft: bool = False,
        scheduled_for: Optional[timezone.datetime] = None,
        send_websocket: bool = True,
        send_email: bool = False,
        send_push: bool = False,
    ) -> Optional[Notification]:
        """
        Create and send a notification
        
        Args:
            user: Target user
            title: Notification title
            message: Notification message
            notification_type: NotificationType instance
            category: Category for filtering
            priority: low, normal, high, urgent
            description: Detailed description
            action_url: Deep link
            action_text: Button text
            metadata: Additional JSON data
            related_object_type: Type of related object
            related_object_id: ID of related object
            expires_at: When notification should expire
            send_websocket: Send via WebSocket
            send_email: Send via email
            send_push: Send via push notification
        
        Returns:
            Created Notification or None
        """
        try:
            if metadata is None:
                metadata = {}

            # Create notification record
            notification = Notification.objects.create(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                category=category,
                priority=priority,
                description=description,
                action_url=action_url,
                action_text=action_text,
                metadata=metadata,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                expires_at=expires_at,
                is_draft=is_draft,
                scheduled_for=scheduled_for,
            )

            # Log creation
            NotificationLog.objects.create(
                notification=notification,
                event_type='created',
                status='success',
                channel='websocket'
            )

            # Send via different channels (skip if draft or scheduled for future)
            send_now = True
            if is_draft:
                send_now = False
            if scheduled_for and scheduled_for > timezone.now():
                send_now = False

            if send_now:
                if send_websocket:
                    NotificationService.send_websocket_notification(notification)
                
                if send_email:
                    NotificationService.send_email_notification(notification)
                
                if send_push:
                    NotificationService.send_push_notification(notification)

            logger.info(f"Notification created: {notification.id} for user {user.email if hasattr(user, 'email') else user}")
            return notification

        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def send_websocket_notification(notification: Notification) -> bool:
        """Send notification via WebSocket"""
        try:
            if notification.is_draft:
                return False

            # Get user's personal group
            group_name = f"user_{notification.user.pk}"
            
            # Prepare notification data
            notification_data = notification.to_dict()
            
            # Send via channel layer
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'notification': notification_data,
                    'notification_id': str(notification.id),
                }
            )

            # Update flags
            notification.was_sent_websocket = True
            notification.sent_at = timezone.now()
            notification.send_attempts = (notification.send_attempts or 0) + 1
            notification.save(update_fields=['was_sent_websocket', 'sent_at', 'send_attempts'])

            # Log delivery
            NotificationLog.objects.create(
                notification=notification,
                event_type='sent',
                channel='websocket',
                status='success'
            )

            logger.debug(f"Notification {notification.id} sent via WebSocket to user {notification.user.pk}")
            return True

        except Exception as e:
            logger.error(f"Error sending WebSocket notification: {str(e)}", exc_info=True)
            NotificationLog.objects.create(
                notification=notification,
                event_type='sent',
                channel='websocket',
                status='failed',
                error_message=str(e)
            )
            return False

    @staticmethod
    def send_email_notification(notification: Notification) -> bool:
        """Send notification via email (async via Celery)"""
        try:
            # Import here to avoid circular imports
            from users.notification_tasks import send_notification_email
            
            # Queue async task
            if not dispatch_task(send_notification_email, str(notification.id)):
                return False
            
            notification.was_sent_email = True
            notification.save(update_fields=['was_sent_email'])

            logger.debug(f"Email notification {notification.id} queued for user {notification.user.email if hasattr(notification.user, 'email') else notification.user}")
            return True

        except Exception as e:
            logger.error(f"Error queuing email notification: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_push_notification(notification: Notification) -> bool:
        """Send notification via push (placeholder for FCM/APNs integration)"""
        try:
            # TODO: Implement push notification via FCM or APNs
            # This is a placeholder for future implementation
            logger.debug(f"Push notification {notification.id} would be sent here")
            return False
        except Exception as e:
            logger.error(f"Error sending push notification: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def broadcast_notification(
        title: str,
        message: str,
        notification_type: Optional[NotificationType] = None,
        group_filter: Optional[str] = None,
        **kwargs
    ) -> int:
        """
        Send notification to multiple users
        
        Args:
            title: Notification title
            message: Notification message
            notification_type: NotificationType
            group_filter: 'admin', 'vendor', 'customer', etc.
            **kwargs: Additional notification arguments
        
        Returns:
            Number of notifications created
        """
        try:
            # Determine target users
            if group_filter == 'admin':
                users = User.objects.filter(is_staff=True)
            elif group_filter == 'vendor':
                users = User.objects.filter(role='VENDOR')
            elif group_filter == 'customer':
                users = User.objects.filter(role='CUSTOMER')
            else:
                users = User.objects.filter(is_active=True)

            count = 0
            for user in users:
                if NotificationService.create_notification(
                    user=user,
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    **kwargs
                ):
                    count += 1

            logger.info(f"Broadcast notification sent to {count} users")
            return count

        except Exception as e:
            logger.error(f"Error in broadcast_notification: {str(e)}", exc_info=True)
            return 0

    @staticmethod
    def get_user_notifications(
        user: User,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[Notification], int]:
        """
        Fetch user notifications with filtering
        
        Args:
            user: Target user
            filters: Optional filters (is_read, category, priority, etc.)
            limit: Pagination limit
            offset: Pagination offset
        
        Returns:
            Tuple of (notifications, total_count)
        """
        try:
            query = Notification.objects.filter(
                user=user,
                is_deleted=False,
                is_draft=False
            )

            if filters:
                if 'is_read' in filters:
                    query = query.filter(is_read=filters['is_read'])
                if 'category' in filters:
                    query = query.filter(category=filters['category'])
                if 'priority' in filters:
                    query = query.filter(priority=filters['priority'])
                if 'is_archived' in filters:
                    query = query.filter(is_archived=filters['is_archived'])

            total_count = query.count()
            notifications = query[offset:offset + limit]

            return list(notifications), total_count

        except Exception as e:
            logger.error(f"Error fetching user notifications: {str(e)}", exc_info=True)
            return [], 0

    @staticmethod
    def get_unread_count(user: User) -> int:
        """Get unread notification count for user"""
        try:
            return Notification.objects.filter(
                user=user,
                is_read=False,
                is_deleted=False,
                is_draft=False
            ).count()
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            return 0

    @staticmethod
    def mark_as_read(user: User, notification_id: str) -> bool:
        """Mark notification as read"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=user
            )
            notification.mark_as_read()

            NotificationLog.objects.create(
                notification=notification,
                event_type='read',
                status='success'
            )

            return True
        except Notification.DoesNotExist:
            logger.warning(f"Notification {notification_id} not found for user {user.pk}")
            return False
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return False

    @staticmethod
    def mark_all_as_read(user: User) -> int:
        """Mark all unread notifications as read"""
        try:
            notifications = Notification.objects.filter(
                user=user,
                is_read=False,
                is_deleted=False
            )
            count = notifications.count()
            now = timezone.now()
            notifications.update(is_read=True, read_at=now)

            return count
        except Exception as e:
            logger.error(f"Error marking all as read: {str(e)}")
            return 0

    @staticmethod
    def archive_notification(user: User, notification_id: str) -> bool:
        """Archive notification"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=user
            )
            notification.archive()
            return True
        except Exception as e:
            logger.error(f"Error archiving notification: {str(e)}")
            return False

    @staticmethod
    def delete_notification(user: User, notification_id: str) -> bool:
        """Soft delete notification"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=user
            )
            notification.soft_delete()

            NotificationLog.objects.create(
                notification=notification,
                event_type='deleted',
                status='success'
            )

            return True
        except Exception as e:
            logger.error(f"Error deleting notification: {str(e)}")
            return False

    @staticmethod
    def get_stats(user: User) -> Dict[str, Any]:
        """Get notification statistics for user"""
        try:
            base_query = Notification.objects.filter(
                user=user,
                is_deleted=False
            )

            total = base_query.count()
            unread = base_query.filter(is_read=False).count()
            read = base_query.filter(is_read=True).count()
            archived = base_query.filter(is_archived=True).count()

            # By category
            by_category = dict(
                base_query.values('category').annotate(
                    count=Count('id')
                ).values_list('category', 'count')
            )

            # By priority
            by_priority = dict(
                base_query.values('priority').annotate(
                    count=Count('id')
                ).values_list('priority', 'count')
            )

            # Last notification
            last_notif = base_query.first()
            last_notification_time = last_notif.created_at if last_notif else None

            return {
                'total_notifications': total,
                'unread_count': unread,
                'read_count': read,
                'archived_count': archived,
                'by_category': by_category,
                'by_priority': by_priority,
                'last_notification_time': last_notification_time,
            }

        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {}

    @staticmethod
    def cleanup_expired_notifications() -> int:
        """Remove expired notifications (task for Celery)"""
        try:
            now = timezone.now()
            expired = Notification.objects.filter(
                expires_at__lt=now,
                is_deleted=False
            )
            count, _ = expired.delete()
            logger.info(f"Cleaned up {count} expired notifications")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up notifications: {str(e)}")
            return 0

    @staticmethod
    def get_or_create_preference(user: User) -> NotificationPreference:
        """Get or create notification preference for user"""
        preference, created = NotificationPreference.objects.get_or_create(user=user)
        return preference


class BulkNotificationService:
    """Service for handling bulk notification operations"""

    @staticmethod
    def create_bulk_notifications(
        user_ids: List[str],
        title: str,
        message: str,
        **kwargs
    ) -> int:
        """Create notifications for multiple users"""
        try:
            users = User.objects.filter(pk__in=user_ids)
            count = 0

            for user in users:
                if NotificationService.create_notification(
                    user=user,
                    title=title,
                    message=message,
                    **kwargs
                ):
                    count += 1

            return count
        except Exception as e:
            logger.error(f"Error in bulk create: {str(e)}")
            return 0

    @staticmethod
    def mark_bulk_as_read(user: User, notification_ids: List[str]) -> int:
        """Mark multiple notifications as read"""
        try:
            notifications = Notification.objects.filter(
                user=user,
                id__in=notification_ids,
                is_deleted=False
            )
            count = notifications.count()
            now = timezone.now()
            notifications.update(is_read=True, read_at=now)

            return count
        except Exception as e:
            logger.error(f"Error in bulk mark as read: {str(e)}")
            return 0

    @staticmethod
    def delete_bulk_notifications(user: User, notification_ids: List[str]) -> int:
        """Soft delete multiple notifications"""
        try:
            notifications = Notification.objects.filter(
                user=user,
                id__in=notification_ids
            )
            count = notifications.count()
            notifications.update(is_deleted=True)

            return count
        except Exception as e:
            logger.error(f"Error in bulk delete: {str(e)}")
            return 0
