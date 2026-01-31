from rest_framework import serializers
from .notification_models import Notification, NotificationType, NotificationPreference, NotificationLog
from django.conf import settings

User = settings.AUTH_USER_MODEL


class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationType
        fields = ['id', 'name', 'display_name', 'description', 'icon', 'color', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for notification lists"""
    notification_type_display = serializers.CharField(
        source='notification_type.display_name',
        read_only=True
    )
    notification_type_icon = serializers.CharField(
        source='notification_type.icon',
        read_only=True
    )
    notification_type_color = serializers.CharField(
        source='notification_type.color',
        read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'priority', 'category',
            'is_read', 'is_archived', 'created_at', 'read_at',
            'notification_type_display', 'notification_type_icon', 'notification_type_color',
            'action_url', 'action_text'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'read_at', 'updated_at'
        ]


class NotificationDetailSerializer(serializers.ModelSerializer):
    """Full serializer for notification details"""
    notification_type = NotificationTypeSerializer(read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_email', 'notification_type', 'title', 'message',
            'description', 'priority', 'category', 'action_url', 'action_text',
            'is_read', 'is_archived', 'is_deleted', 'metadata',
            'related_object_type', 'related_object_id',
            'was_sent_websocket', 'was_sent_email', 'was_sent_push',
            'created_at', 'read_at', 'expires_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at', 'read_at',
            'was_sent_websocket', 'was_sent_email', 'was_sent_push'
        ]


class NotificationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating notifications (admin use)"""
    
    class Meta:
        model = Notification
        fields = [
            'user', 'notification_type', 'title', 'message', 'description',
            'priority', 'category', 'action_url', 'action_text',
            'metadata', 'related_object_type', 'related_object_id', 'expires_at'
        ]

    def validate_priority(self, value):
        if value not in dict(Notification.PRIORITY_CHOICES):
            raise serializers.ValidationError(
                f"Invalid priority. Choose from {list(dict(Notification.PRIORITY_CHOICES).keys())}"
            )
        return value

    def create(self, validated_data):
        notification = Notification.objects.create(**validated_data)
        return notification


class NotificationBulkCreateSerializer(serializers.Serializer):
    """Serializer for bulk creating notifications"""
    users = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        many=True
    )
    notification_type = serializers.PrimaryKeyRelatedField(
        queryset=NotificationType.objects.all()
    )
    title = serializers.CharField(max_length=255)
    message = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=['low', 'normal', 'high', 'urgent'])
    category = serializers.CharField(max_length=50, required=False, allow_blank=True)
    action_url = serializers.URLField(required=False, allow_blank=True)
    action_text = serializers.CharField(max_length=100, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)

    def create(self, validated_data):
        users = validated_data.pop('users')
        notifications = [
            Notification(user=user, **validated_data)
            for user in users
        ]
        return Notification.objects.bulk_create(notifications, batch_size=100)


class NotificationMarkAsReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read"""
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False
    )
    mark_all = serializers.BooleanField(default=False)


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'id', 'user', 'websocket_enabled', 'email_enabled', 'push_enabled',
            'email_frequency', 'push_frequency', 'enabled_categories', 'disabled_categories',
            'quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end',
            'do_not_disturb_enabled', 'do_not_disturb_until'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def validate(self, data):
        if data.get('quiet_hours_enabled'):
            if not data.get('quiet_hours_start') or not data.get('quiet_hours_end'):
                raise serializers.ValidationError(
                    "quiet_hours_start and quiet_hours_end are required when quiet_hours_enabled is True"
                )
        return data


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = ['id', 'notification', 'event_type', 'channel', 'status', 'error_message', 'metadata', 'created_at']
        read_only_fields = ['id', 'notification', 'created_at']


class NotificationStatsSerializer(serializers.Serializer):
    """Serializer for notification statistics"""
    total_notifications = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    archived_count = serializers.IntegerField()
    by_category = serializers.DictField(child=serializers.IntegerField())
    by_priority = serializers.DictField(child=serializers.IntegerField())
    last_notification_time = serializers.DateTimeField()
