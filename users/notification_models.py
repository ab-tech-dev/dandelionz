from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL


class NotificationType(models.Model):
    """
    Define notification types for categorization and filtering.
    Examples: order_update, payment_received, vendor_approval, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Icon name or emoji")
    color = models.CharField(max_length=7, default="#000000", help_text="Hex color code")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_types'
        verbose_name = 'Notification Type'
        verbose_name_plural = 'Notification Types'
        ordering = ['display_name']

    def __str__(self):
        return self.display_name


class Notification(models.Model):
    """
    Store all notifications with metadata for persistence and history.
    Supports multiple recipient types (users, roles, groups).
    """
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='notifications',
        db_index=True,
        null=True,  # Allow null for migrations
        blank=True
    )
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    
    # Core content
    title = models.CharField(max_length=255)
    message = models.TextField()
    description = models.TextField(blank=True, help_text="Detailed description (optional)")
    
    # Metadata
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
        db_index=True
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="e.g., 'order', 'payment', 'vendor_approval'"
    )
    
    # Action links
    action_url = models.URLField(blank=True, null=True, help_text="Deep link for in-app action")
    action_text = models.CharField(max_length=100, blank=True, help_text="Button text for action")
    
    # Status
    is_read = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    
    # Related objects
    related_object_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Content type of related object (e.g., 'order', 'payment')"
    )
    related_object_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="ID of related object"
    )
    
    # Additional data
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional JSON data (images, stats, etc.)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_for = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Schedule notification for future delivery"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Notification will be auto-deleted after this time"
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    # Delivery tracking
    was_sent_websocket = models.BooleanField(default=False)
    was_sent_email = models.BooleanField(default=False, help_text="Optional email delivery")
    was_sent_push = models.BooleanField(default=False, help_text="Optional push notification")
    send_attempts = models.IntegerField(default=0, help_text="Track retry attempts")
    is_draft = models.BooleanField(default=False, db_index=True, help_text="Draft notification not yet sent")

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        indexes = [
            models.Index(fields=['user', 'is_read', 'is_deleted', '-created_at']),
            models.Index(fields=['user', 'category', '-created_at']),
            models.Index(fields=['is_read', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.email if hasattr(self.user, 'email') else self.user}"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_unread(self):
        """Mark notification as unread"""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at'])

    def archive(self):
        """Archive notification"""
        self.is_archived = True
        self.save(update_fields=['is_archived'])

    def unarchive(self):
        """Unarchive notification"""
        self.is_archived = False
        self.save(update_fields=['is_archived'])

    def soft_delete(self):
        """Soft delete notification"""
        self.is_deleted = True
        self.save(update_fields=['is_deleted'])

    def restore(self):
        """Restore soft-deleted notification"""
        self.is_deleted = False
        self.save(update_fields=['is_deleted'])

    def to_dict(self):
        """Convert notification to dictionary for WebSocket transmission"""
        return {
            'id': str(self.id),
            'title': self.title,
            'message': self.message,
            'description': self.description,
            'priority': self.priority,
            'category': self.category,
            'action_url': self.action_url,
            'action_text': self.action_text,
            'is_read': self.is_read,
            'is_draft': self.is_draft,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'notification_type': {
                'name': self.notification_type.name,
                'display_name': self.notification_type.display_name,
                'icon': self.notification_type.icon,
                'color': self.notification_type.color,
            } if self.notification_type else None,
        }


class NotificationPreference(models.Model):
    """
    User preferences for notifications (channels, frequency, categories).
    """
    FREQUENCY_CHOICES = [
        ('instant', 'Instant'),
        ('hourly', 'Hourly Digest'),
        ('daily', 'Daily Digest'),
        ('weekly', 'Weekly Digest'),
        ('never', 'Never'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preference'
    )
    
    # Channel preferences
    websocket_enabled = models.BooleanField(default=True, help_text="Real-time WebSocket notifications")
    email_enabled = models.BooleanField(default=True, help_text="Email notifications")
    push_enabled = models.BooleanField(default=False, help_text="Push notifications")
    
    # Frequency preferences
    email_frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily'
    )
    push_frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='instant'
    )
    
    # Category preferences
    enabled_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of enabled notification categories"
    )
    disabled_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of disabled notification categories"
    )
    
    # Quiet hours (no notifications outside business hours if enabled)
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(null=True, blank=True, help_text="HH:MM format")
    quiet_hours_end = models.TimeField(null=True, blank=True, help_text="HH:MM format")
    
    # Do not disturb
    do_not_disturb_enabled = models.BooleanField(default=False)
    do_not_disturb_until = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_preferences'
        verbose_name = 'Notification Preference'
        verbose_name_plural = 'Notification Preferences'

    def __str__(self):
        return f"Preferences for {self.user.email if hasattr(self.user, 'email') else self.user}"

    def is_notification_allowed(self, category=None):
        """Check if notification category is allowed"""
        if self.do_not_disturb_enabled and self.do_not_disturb_until > timezone.now():
            return False
        
        if category:
            if category in self.disabled_categories:
                return False
            if self.enabled_categories and category not in self.enabled_categories:
                return False
        
        if self.quiet_hours_enabled:
            now = timezone.now().time()
            if self.quiet_hours_start <= now <= self.quiet_hours_end:
                return False
        
        return True


class NotificationLog(models.Model):
    """
    Log all notification events for auditing and debugging.
    """
    EVENT_TYPES = [
        ('created', 'Created'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('archived', 'Archived'),
        ('deleted', 'Deleted'),
        ('resent', 'Resent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    channel = models.CharField(
        max_length=20,
        choices=[('websocket', 'WebSocket'), ('email', 'Email'), ('push', 'Push')],
        default='websocket'
    )
    status = models.CharField(max_length=50, help_text="Status details")
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'notification_logs'
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} - {self.notification.title}"
