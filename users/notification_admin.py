"""
Django Admin configuration for Notification models
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Q
from .notification_models import (
    Notification, NotificationType, NotificationPreference, NotificationLog
)


@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'name', 'icon_display', 'color_display', 'is_active', 'notification_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'name', 'display_name', 'description')
        }),
        ('Appearance', {
            'fields': ('icon', 'color')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def icon_display(self, obj):
        return f"{obj.icon} {obj.name}"
    icon_display.short_description = 'Icon'
    
    def color_display(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border-radius: 4px; display: inline-block;"></div> {}',
            obj.color,
            obj.color
        )
    color_display.short_description = 'Color'
    
    def notification_count(self, obj):
        count = obj.notifications.count()
        return format_html(
            '<span style="background-color: #667eea; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            count
        )
    notification_count.short_description = 'Total Notifications'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title_short', 'user_email', 'priority_badge', 'read_status', 'category', 'created_at_short', 'delivery_status']
    list_filter = ['priority', 'category', 'is_read', 'is_archived', 'is_deleted', 'created_at', 'notification_type']
    search_fields = ['title', 'message', 'user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['id', 'created_at', 'read_at', 'updated_at', 'delivery_status_detail', 'related_object_display']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Recipient', {
            'fields': ('id', 'user', 'notification_type')
        }),
        ('Content', {
            'fields': ('title', 'message', 'description', 'metadata')
        }),
        ('Settings', {
            'fields': ('priority', 'category', 'expires_at')
        }),
        ('Action', {
            'fields': ('action_url', 'action_text'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_read', 'is_archived', 'is_deleted', 'read_at')
        }),
        ('Delivery', {
            'fields': ('delivery_status_detail', 'was_sent_websocket', 'was_sent_email', 'was_sent_push', 'send_attempts'),
            'classes': ('collapse',)
        }),
        ('Related Object', {
            'fields': ('related_object_type', 'related_object_id', 'related_object_display'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_read', 'mark_as_unread', 'archive_selected', 'delete_selected']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'notification_type')
    
    def title_short(self, obj):
        return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
    title_short.short_description = 'Title'
    
    def user_email(self, obj):
        return obj.user.email if hasattr(obj.user, 'email') else str(obj.user)
    user_email.short_description = 'User'
    
    def priority_badge(self, obj):
        colors = {
            'low': '#34d399',
            'normal': '#667eea',
            'high': '#ff9f40',
            'urgent': '#ff6b6b',
        }
        color = colors.get(obj.priority, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: 600;">{}</span>',
            color,
            obj.get_priority_display().upper()
        )
    priority_badge.short_description = 'Priority'
    
    def read_status(self, obj):
        status = '✓ Read' if obj.is_read else '○ Unread'
        color = '#34d399' if obj.is_read else '#ff9f40'
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            status
        )
    read_status.short_description = 'Read Status'
    
    def created_at_short(self, obj):
        return obj.created_at.strftime('%Y-%m-%d %H:%M')
    created_at_short.short_description = 'Created'
    
    def delivery_status(self, obj):
        channels = []
        if obj.was_sent_websocket:
            channels.append('<span style="background: #34d399; color: white; padding: 2px 6px; border-radius: 2px; font-size: 11px; margin-right: 4px;">📡 WS</span>')
        if obj.was_sent_email:
            channels.append('<span style="background: #667eea; color: white; padding: 2px 6px; border-radius: 2px; font-size: 11px; margin-right: 4px;">📧 Email</span>')
        if obj.was_sent_push:
            channels.append('<span style="background: #ff9f40; color: white; padding: 2px 6px; border-radius: 2px; font-size: 11px; margin-right: 4px;">📱 Push</span>')
        return format_html(' '.join(channels)) if channels else '-'
    delivery_status.short_description = 'Delivery'
    
    def delivery_status_detail(self, obj):
        return f"""
        <table style="width: 100%; border-collapse: collapse;">
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 8px;"><strong>WebSocket:</strong></td>
                <td style="padding: 8px;">{'✓ Sent' if obj.was_sent_websocket else '✗ Not sent'}</td>
            </tr>
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 8px;"><strong>Email:</strong></td>
                <td style="padding: 8px;">{'✓ Sent' if obj.was_sent_email else '✗ Not sent'}</td>
            </tr>
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 8px;"><strong>Push:</strong></td>
                <td style="padding: 8px;">{'✓ Sent' if obj.was_sent_push else '✗ Not sent'}</td>
            </tr>
            <tr>
                <td style="padding: 8px;"><strong>Attempts:</strong></td>
                <td style="padding: 8px;">{obj.send_attempts}</td>
            </tr>
        </table>
        """
    delivery_status_detail.short_description = 'Delivery Status'
    
    def related_object_display(self, obj):
        if obj.related_object_type and obj.related_object_id:
            return f"{obj.related_object_type}: {obj.related_object_id}"
        return '-'
    related_object_display.short_description = 'Related Object'
    
    def mark_as_read(self, request, queryset):
        count = 0
        for notification in queryset:
            notification.mark_as_read()
            count += 1
        self.message_user(request, f'{count} notification(s) marked as read.')
    mark_as_read.short_description = 'Mark selected as read'
    
    def mark_as_unread(self, request, queryset):
        count = 0
        for notification in queryset:
            notification.mark_as_unread()
            count += 1
        self.message_user(request, f'{count} notification(s) marked as unread.')
    mark_as_unread.short_description = 'Mark selected as unread'
    
    def archive_selected(self, request, queryset):
        count = queryset.update(is_archived=True)
        self.message_user(request, f'{count} notification(s) archived.')
    archive_selected.short_description = 'Archive selected'


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'channels_enabled', 'quiet_hours_status', 'dnd_status']
    list_filter = ['websocket_enabled', 'email_enabled', 'push_enabled', 'quiet_hours_enabled', 'do_not_disturb_enabled']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['id', 'user', 'created_at', 'updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('id', 'user')
        }),
        ('Notification Channels', {
            'fields': ('websocket_enabled', 'email_enabled', 'push_enabled'),
            'description': 'Select which notification channels are enabled for this user'
        }),
        ('Frequency Settings', {
            'fields': ('email_frequency', 'push_frequency'),
            'description': 'Set the frequency for different notification types'
        }),
        ('Category Preferences', {
            'fields': ('enabled_categories', 'disabled_categories'),
            'description': 'Select which notification categories this user wants to receive'
        }),
        ('Quiet Hours', {
            'fields': ('quiet_hours_enabled', 'quiet_hours_start', 'quiet_hours_end'),
            'description': 'Define time range when notifications should not be sent'
        }),
        ('Do Not Disturb', {
            'fields': ('do_not_disturb_enabled', 'do_not_disturb_until'),
            'description': 'Temporarily mute notifications until specified time'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')
    
    def user_email(self, obj):
        return obj.user.email if hasattr(obj.user, 'email') else str(obj.user)
    user_email.short_description = 'User'
    
    def channels_enabled(self, obj):
        channels = []
        if obj.websocket_enabled:
            channels.append('<span style="background: #34d399; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px; margin-right: 4px;">📡 WebSocket</span>')
        if obj.email_enabled:
            channels.append('<span style="background: #667eea; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px; margin-right: 4px;">📧 Email</span>')
        if obj.push_enabled:
            channels.append('<span style="background: #ff9f40; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px; margin-right: 4px;">📱 Push</span>')
        return format_html(' '.join(channels)) if channels else '<span style="color: #999;">None enabled</span>'
    channels_enabled.short_description = 'Enabled Channels'
    
    def quiet_hours_status(self, obj):
        if obj.quiet_hours_enabled:
            return format_html(
                '<span style="background: #ff9f40; color: white; padding: 3px 8px; border-radius: 3px;">🕐 {} - {}</span>',
                obj.quiet_hours_start.strftime('%H:%M') if obj.quiet_hours_start else '--:--',
                obj.quiet_hours_end.strftime('%H:%M') if obj.quiet_hours_end else '--:--'
            )
        return '-'
    quiet_hours_status.short_description = 'Quiet Hours'
    
    def dnd_status(self, obj):
        if obj.do_not_disturb_enabled and obj.do_not_disturb_until:
            return format_html(
                '<span style="background: #ff6b6b; color: white; padding: 3px 8px; border-radius: 3px;">🔕 Until {}</span>',
                obj.do_not_disturb_until.strftime('%Y-%m-%d %H:%M')
            )
        return '-'
    dnd_status.short_description = 'Do Not Disturb'


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['notification_title', 'event_type_badge', 'channel_badge', 'status_badge', 'created_at_short']
    list_filter = ['event_type', 'channel', 'status', 'created_at']
    search_fields = ['notification__title', 'notification__message', 'status', 'error_message']
    readonly_fields = ['id', 'notification', 'created_at', 'metadata_display']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Notification', {
            'fields': ('id', 'notification')
        }),
        ('Event Details', {
            'fields': ('event_type', 'channel', 'status')
        }),
        ('Error Information', {
            'fields': ('error_message', 'metadata_display'),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('notification')
    
    def notification_title(self, obj):
        return obj.notification.title[:50] + '...' if len(obj.notification.title) > 50 else obj.notification.title
    notification_title.short_description = 'Notification'
    
    def event_type_badge(self, obj):
        colors = {
            'created': '#667eea',
            'sent': '#34d399',
            'delivered': '#10b981',
            'read': '#06b6d4',
            'failed': '#ff6b6b',
            'archived': '#a78bfa',
            'deleted': '#ef4444',
        }
        color = colors.get(obj.event_type, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: 600;">{}</span>',
            color,
            obj.get_event_type_display().upper()
        )
    event_type_badge.short_description = 'Event'
    
    def channel_badge(self, obj):
        colors = {
            'websocket': '#34d399',
            'email': '#667eea',
            'push': '#ff9f40',
        }
        color = colors.get(obj.channel, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_channel_display().upper()
        )
    channel_badge.short_description = 'Channel'
    
    def status_badge(self, obj):
        colors = {
            'success': '#34d399',
            'failed': '#ff6b6b',
            'pending': '#ff9f40',
        }
        color = colors.get(obj.status, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def created_at_short(self, obj):
        return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')
    created_at_short.short_description = 'Created'
    
    def metadata_display(self, obj):
        import json
        return format_html('<pre>{}</pre>', json.dumps(obj.metadata, indent=2))
    metadata_display.short_description = 'Metadata'
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
