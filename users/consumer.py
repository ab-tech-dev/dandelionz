from channels.generic.websocket import AsyncWebsocketConsumer, AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from .notification_models import Notification, NotificationPreference, NotificationLog
from django.utils import timezone

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Enhanced WebSocket consumer for real-time notifications with:
    - Automatic group management based on user role
    - Error handling and logging
    - Heartbeat mechanism for connection monitoring
    - Message acknowledgment
    - Graceful disconnection
    """
    
    HEARTBEAT_INTERVAL = 30  # seconds
    MAX_MESSAGE_SIZE = 10240  # 10KB
    
    async def connect(self):
        """Handle WebSocket connection"""
        try:
            self.user = self.scope["user"]
            self.groups = []
            self.heartbeat_task = None
            
            # Validate user authentication
            if not self.user.is_authenticated:
                await self.close(code=4001, reason="Unauthenticated")
                logger.warning(f"Unauthenticated connection attempt: {self.scope.get('client')}")
                return
            
            # Assign to groups based on user role
            await self._assign_user_groups()
            
            # Accept the connection
            await self.accept()
            logger.info(f"User {self.user.email if hasattr(self.user, 'email') else self.user} connected to notifications")
            
            # Send connection confirmation
            await self.send_json({
                'type': 'connection_established',
                'timestamp': datetime.now().isoformat(),
                'user_id': str(self.user.pk),
                'message': 'Connected to notification service'
            })
            
            # Start heartbeat
            self.heartbeat_task = asyncio.create_task(self._send_heartbeat())
            
        except Exception as e:
            logger.error(f"Error in connect: {str(e)}", exc_info=True)
            await self.close(code=4000, reason="Connection failed")

    async def disconnect(self, close_code: int):
        """Handle WebSocket disconnection"""
        try:
            # Cancel heartbeat task
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
            
            # Remove from all groups
            for group in self.groups:
                try:
                    await self.channel_layer.group_discard(group, self.channel_name)
                except Exception as e:
                    logger.error(f"Error discarding group {group}: {str(e)}")
            
            logger.info(
                f"User {self.user.email if hasattr(self.user, 'email') else self.user} "
                f"disconnected (code: {close_code})"
            )
        except Exception as e:
            logger.error(f"Error in disconnect: {str(e)}", exc_info=True)

    async def receive_json(self, content: Dict[str, Any], **kwargs):
        """Handle incoming WebSocket messages"""
        try:
            message_type = content.get('type')
            
            if message_type == 'ping':
                await self.send_json({'type': 'pong', 'timestamp': datetime.now().isoformat()})
            
            elif message_type == 'mark_as_read':
                await self._handle_mark_as_read(content)
            
            elif message_type == 'mark_as_unread':
                await self._handle_mark_as_unread(content)
            
            elif message_type == 'fetch_unread':
                await self._handle_fetch_unread(content)
            
            elif message_type == 'fetch_recent':
                await self._handle_fetch_recent(content)
            
            elif message_type == 'archive':
                await self._handle_archive(content)
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
                await self.send_json({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                })
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {str(e)}")
            await self.send_json({
                'type': 'error',
                'message': 'Invalid JSON format'
            })
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)
            await self.send_json({
                'type': 'error',
                'message': 'Error processing message'
            })

    async def send_notification(self, event: Dict[str, Any]):
        """
        Receive notification from group and send to WebSocket.
        Called by group_send.
        """
        try:
            notification_data = event.get('notification')
            
            await self.send_json({
                'type': 'notification',
                'data': notification_data,
                'timestamp': datetime.now().isoformat()
            })
            
            # Log successful delivery
            notification_id = event.get('notification_id')
            if notification_id:
                await self._log_notification_event(
                    notification_id, 'delivered', 'websocket', 'success'
                )
        
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}", exc_info=True)

    async def send_error(self, event: Dict[str, Any]):
        """Send error message to client"""
        try:
            await self.send_json({
                'type': 'error',
                'message': event.get('message'),
                'error_code': event.get('error_code', 'UNKNOWN_ERROR'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

    async def broadcast_message(self, event: Dict[str, Any]):
        """Send broadcast message to all users in group"""
        try:
            await self.send_json({
                'type': 'broadcast',
                'data': event.get('message'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending broadcast: {str(e)}")

    # ============== Private Helper Methods ==============

    async def _assign_user_groups(self):
        """Assign user to appropriate notification groups based on role"""
        try:
            # Personal notifications
            personal_group = f"user_{self.user.pk}"
            await self.channel_layer.group_add(personal_group, self.channel_name)
            self.groups.append(personal_group)
            
            # Role-based notifications
            if self.user.is_authenticated:
                if self.user.is_staff or hasattr(self.user, 'is_superuser') and self.user.is_superuser:
                    role_group = "admin_notifications"
                else:
                    role = getattr(self.user, 'role', 'CUSTOMER')
                    role_group = f"{role}_notifications"
                
                await self.channel_layer.group_add(role_group, self.channel_name)
                self.groups.append(role_group)
                
                logger.debug(f"User {self.user.email if hasattr(self.user, 'email') else self.user} "
                           f"added to groups: {self.groups}")
        except Exception as e:
            logger.error(f"Error assigning groups: {str(e)}", exc_info=True)
            raise

    async def _send_heartbeat(self):
        """Send periodic heartbeat to keep connection alive"""
        try:
            while True:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                try:
                    await self.send_json({
                        'type': 'heartbeat',
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.warning(f"Failed to send heartbeat: {str(e)}")
                    break
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Heartbeat error: {str(e)}", exc_info=True)

    async def _handle_mark_as_read(self, content: Dict[str, Any]):
        """Handle mark as read request"""
        try:
            notification_id = content.get('notification_id')
            if notification_id:
                notification = await self._get_notification(notification_id)
                if notification and notification.user_id == self.user.pk:
                    await self._mark_notification_as_read(notification_id)
                    await self.send_json({
                        'type': 'notification_read',
                        'notification_id': notification_id,
                        'success': True
                    })
                else:
                    await self.send_json({
                        'type': 'error',
                        'message': 'Notification not found or unauthorized'
                    })
        except Exception as e:
            logger.error(f"Error marking as read: {str(e)}")
            await self.send_json({'type': 'error', 'message': str(e)})

    async def _handle_mark_as_unread(self, content: Dict[str, Any]):
        """Handle mark as unread request"""
        try:
            notification_id = content.get('notification_id')
            if notification_id:
                notification = await self._get_notification(notification_id)
                if notification and notification.user_id == self.user.pk:
                    await self._mark_notification_as_unread(notification_id)
                    await self.send_json({
                        'type': 'notification_unread',
                        'notification_id': notification_id,
                        'success': True
                    })
        except Exception as e:
            logger.error(f"Error marking as unread: {str(e)}")

    async def _handle_fetch_unread(self, content: Dict[str, Any]):
        """Fetch unread notifications"""
        try:
            limit = min(content.get('limit', 20), 100)
            notifications = await self._get_unread_notifications(limit)
            await self.send_json({
                'type': 'unread_notifications',
                'count': len(notifications),
                'notifications': notifications
            })
        except Exception as e:
            logger.error(f"Error fetching unread: {str(e)}")

    async def _handle_fetch_recent(self, content: Dict[str, Any]):
        """Fetch recent notifications"""
        try:
            limit = min(content.get('limit', 20), 100)
            notifications = await self._get_recent_notifications(limit)
            await self.send_json({
                'type': 'recent_notifications',
                'count': len(notifications),
                'notifications': notifications
            })
        except Exception as e:
            logger.error(f"Error fetching recent: {str(e)}")

    async def _handle_archive(self, content: Dict[str, Any]):
        """Archive notification"""
        try:
            notification_id = content.get('notification_id')
            if notification_id:
                notification = await self._get_notification(notification_id)
                if notification and notification.user_id == self.user.pk:
                    await self._archive_notification(notification_id)
                    await self.send_json({
                        'type': 'notification_archived',
                        'notification_id': notification_id,
                        'success': True
                    })
        except Exception as e:
            logger.error(f"Error archiving notification: {str(e)}")

    @database_sync_to_async
    def _get_notification(self, notification_id: str) -> Optional[Notification]:
        """Fetch notification from database"""
        try:
            return Notification.objects.get(id=notification_id, is_deleted=False)
        except Notification.DoesNotExist:
            return None

    @database_sync_to_async
    def _mark_notification_as_read(self, notification_id: str):
        """Mark notification as read"""
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_read()

    @database_sync_to_async
    def _mark_notification_as_unread(self, notification_id: str):
        """Mark notification as unread"""
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_unread()

    @database_sync_to_async
    def _archive_notification(self, notification_id: str):
        """Archive notification"""
        notification = Notification.objects.get(id=notification_id)
        notification.archive()

    @database_sync_to_async
    def _get_unread_notifications(self, limit: int) -> list:
        """Get unread notifications for current user"""
        notifications = Notification.objects.filter(
            user_id=self.user.pk,
            is_read=False,
            is_deleted=False
        ).values(
            'id', 'title', 'message', 'priority', 'category',
            'created_at', 'action_url', 'action_text'
        )[:limit]
        return list(notifications)

    @database_sync_to_async
    def _get_recent_notifications(self, limit: int) -> list:
        """Get recent notifications for current user"""
        notifications = Notification.objects.filter(
            user_id=self.user.pk,
            is_deleted=False
        ).values(
            'id', 'title', 'message', 'priority', 'category',
            'is_read', 'created_at', 'action_url', 'action_text'
        )[:limit]
        return list(notifications)

    @database_sync_to_async
    def _log_notification_event(self, notification_id: str, event_type: str, channel: str, status: str):
        """Log notification event"""
        try:
            notification = Notification.objects.get(id=notification_id)
            NotificationLog.objects.create(
                notification=notification,
                event_type=event_type,
                channel=channel,
                status=status
            )
        except Exception as e:
            logger.error(f"Error logging notification event: {str(e)}")