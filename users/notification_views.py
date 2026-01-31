"""
Notification API Views and Viewsets
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
import logging

from .notification_models import (
    Notification, NotificationType, NotificationPreference
)
from .notification_serializers import (
    NotificationListSerializer, NotificationDetailSerializer,
    NotificationCreateSerializer, NotificationBulkCreateSerializer,
    NotificationMarkAsReadSerializer, NotificationPreferenceSerializer,
    NotificationStatsSerializer, NotificationTypeSerializer
)
from .notification_service import NotificationService, BulkNotificationService

logger = logging.getLogger(__name__)


class NotificationPagination(PageNumberPagination):
    """Pagination for notification lists"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class IsNotificationOwner(permissions.BasePermission):
    """Permission to only access own notifications"""
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notifications.
    
    Endpoints:
    - GET /api/notifications/ - List all notifications
    - GET /api/notifications/{id}/ - Get notification detail
    - DELETE /api/notifications/{id}/ - Delete notification
    - POST /api/notifications/mark_as_read/ - Mark as read
    - POST /api/notifications/mark_all_as_read/ - Mark all as read
    - POST /api/notifications/archive/ - Archive notification
    - POST /api/notifications/unarchive/ - Restore notification
    - GET /api/notifications/stats/ - Get notification stats
    - GET /api/notifications/unread_count/ - Get unread count
    - GET /api/notifications/bulk_delete/ - Delete multiple
    """
    
    permission_classes = [permissions.IsAuthenticated, IsNotificationOwner]
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        """Filter notifications for current user"""
        return Notification.objects.filter(
            user=self.request.user,
            is_deleted=False
        ).select_related('notification_type')

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return NotificationListSerializer
        elif self.action == 'create':
            return NotificationCreateSerializer
        elif self.action == 'bulk_create':
            return NotificationBulkCreateSerializer
        elif self.action in ['mark_as_read', 'mark_all_as_read']:
            return NotificationMarkAsReadSerializer
        return NotificationDetailSerializer

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get unread notification count"""
        try:
            count = NotificationService.get_unread_count(request.user)
            return Response({
                'unread_count': count,
                'status': 'success'
            })
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            return Response(
                {'error': 'Failed to get unread count'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get notification statistics"""
        try:
            stats = NotificationService.get_stats(request.user)
            serializer = NotificationStatsSerializer(stats)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return Response(
                {'error': 'Failed to get stats'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def mark_as_read(self, request):
        """Mark single notification as read"""
        try:
            notification_id = request.data.get('notification_id')
            if not notification_id:
                return Response(
                    {'error': 'notification_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            success = NotificationService.mark_as_read(request.user, notification_id)
            if success:
                return Response({
                    'status': 'success',
                    'message': 'Notification marked as read'
                })
            return Response(
                {'error': 'Notification not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error marking as read: {str(e)}")
            return Response(
                {'error': 'Failed to mark as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all unread notifications as read"""
        try:
            count = NotificationService.mark_all_as_read(request.user)
            return Response({
                'status': 'success',
                'message': f'{count} notifications marked as read',
                'count': count
            })
        except Exception as e:
            logger.error(f"Error marking all as read: {str(e)}")
            return Response(
                {'error': 'Failed to mark all as read'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive a notification"""
        try:
            notification = self.get_object()
            NotificationService.archive_notification(request.user, str(pk))
            return Response({
                'status': 'success',
                'message': 'Notification archived'
            })
        except Exception as e:
            logger.error(f"Error archiving: {str(e)}")
            return Response(
                {'error': 'Failed to archive'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        """Unarchive a notification"""
        try:
            notification = self.get_object()
            notification.unarchive()
            return Response({
                'status': 'success',
                'message': 'Notification unarchived'
            })
        except Exception as e:
            logger.error(f"Error unarchiving: {str(e)}")
            return Response(
                {'error': 'Failed to unarchive'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """Delete multiple notifications"""
        try:
            notification_ids = request.data.get('notification_ids', [])
            if not notification_ids:
                return Response(
                    {'error': 'notification_ids is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            count = BulkNotificationService.delete_bulk_notifications(
                request.user,
                notification_ids
            )
            return Response({
                'status': 'success',
                'message': f'{count} notifications deleted',
                'count': count
            })
        except Exception as e:
            logger.error(f"Error bulk deleting: {str(e)}")
            return Response(
                {'error': 'Failed to delete notifications'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def destroy(self, request, *args, **kwargs):
        """Soft delete a notification"""
        try:
            notification = self.get_object()
            NotificationService.delete_notification(request.user, str(notification.id))
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting: {str(e)}")
            return Response(
                {'error': 'Failed to delete'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NotificationTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for notification types (read-only).
    
    Endpoints:
    - GET /api/notification-types/ - List all types
    - GET /api/notification-types/{id}/ - Get type detail
    """
    queryset = NotificationType.objects.filter(is_active=True)
    serializer_class = NotificationTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination


class NotificationPreferenceViewSet(viewsets.ViewSet):
    """
    ViewSet for user notification preferences.
    
    Endpoints:
    - GET /api/notification-preferences/ - Get current user preferences
    - PUT /api/notification-preferences/ - Update preferences
    - POST /api/notification-preferences/enable_quiet_hours/ - Enable quiet hours
    - POST /api/notification-preferences/disable_quiet_hours/ - Disable quiet hours
    - POST /api/notification-preferences/enable_dnd/ - Enable do not disturb
    - POST /api/notification-preferences/disable_dnd/ - Disable do not disturb
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def list(self, request):
        """Get current user's notification preferences"""
        try:
            preference = NotificationService.get_or_create_preference(request.user)
            serializer = NotificationPreferenceSerializer(preference)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting preference: {str(e)}")
            return Response(
                {'error': 'Failed to get preferences'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['put'])
    def update(self, request):
        """Update notification preferences"""
        try:
            preference = NotificationService.get_or_create_preference(request.user)
            serializer = NotificationPreferenceSerializer(
                preference,
                data=request.data,
                partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response({
                    'status': 'success',
                    'message': 'Preferences updated',
                    'data': serializer.data
                })
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating preference: {str(e)}")
            return Response(
                {'error': 'Failed to update preferences'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def enable_quiet_hours(self, request):
        """Enable quiet hours for notifications"""
        try:
            preference = NotificationService.get_or_create_preference(request.user)
            start_time = request.data.get('start_time')
            end_time = request.data.get('end_time')

            if not start_time or not end_time:
                return Response(
                    {'error': 'start_time and end_time are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            preference.quiet_hours_enabled = True
            preference.quiet_hours_start = start_time
            preference.quiet_hours_end = end_time
            preference.save()

            return Response({
                'status': 'success',
                'message': 'Quiet hours enabled'
            })
        except Exception as e:
            logger.error(f"Error enabling quiet hours: {str(e)}")
            return Response(
                {'error': 'Failed to enable quiet hours'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def disable_quiet_hours(self, request):
        """Disable quiet hours"""
        try:
            preference = NotificationService.get_or_create_preference(request.user)
            preference.quiet_hours_enabled = False
            preference.save()

            return Response({
                'status': 'success',
                'message': 'Quiet hours disabled'
            })
        except Exception as e:
            logger.error(f"Error disabling quiet hours: {str(e)}")
            return Response(
                {'error': 'Failed to disable quiet hours'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def enable_dnd(self, request):
        """Enable do not disturb mode"""
        try:
            preference = NotificationService.get_or_create_preference(request.user)
            duration_minutes = request.data.get('duration_minutes', 60)

            from django.utils import timezone
            from datetime import timedelta

            preference.do_not_disturb_enabled = True
            preference.do_not_disturb_until = timezone.now() + timedelta(minutes=duration_minutes)
            preference.save()

            return Response({
                'status': 'success',
                'message': 'Do not disturb enabled',
                'until': preference.do_not_disturb_until
            })
        except Exception as e:
            logger.error(f"Error enabling DND: {str(e)}")
            return Response(
                {'error': 'Failed to enable DND'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def disable_dnd(self, request):
        """Disable do not disturb mode"""
        try:
            preference = NotificationService.get_or_create_preference(request.user)
            preference.do_not_disturb_enabled = False
            preference.do_not_disturb_until = None
            preference.save()

            return Response({
                'status': 'success',
                'message': 'Do not disturb disabled'
            })
        except Exception as e:
            logger.error(f"Error disabling DND: {str(e)}")
            return Response(
                {'error': 'Failed to disable DND'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
