"""
Notification URLs configuration
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .notification_views import (
    NotificationViewSet, NotificationTypeViewSet, NotificationPreferenceViewSet
)

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')
router.register(r'types', NotificationTypeViewSet, basename='notification-type')

# Manually configure NotificationPreferenceViewSet routes
preference_list = NotificationPreferenceViewSet.as_view({'get': 'list', 'put': 'update'})
preference_enable_quiet = NotificationPreferenceViewSet.as_view({'post': 'enable_quiet_hours'})
preference_disable_quiet = NotificationPreferenceViewSet.as_view({'post': 'disable_quiet_hours'})
preference_enable_dnd = NotificationPreferenceViewSet.as_view({'post': 'enable_dnd'})
preference_disable_dnd = NotificationPreferenceViewSet.as_view({'post': 'disable_dnd'})

urlpatterns = [
    path('', include(router.urls)),
    
    # Notification Preferences
    path('preferences/', preference_list, name='notification-preferences'),
    path('preferences/enable-quiet-hours/', preference_enable_quiet, name='notification-preferences-enable-quiet'),
    path('preferences/disable-quiet-hours/', preference_disable_quiet, name='notification-preferences-disable-quiet'),
    path('preferences/enable-dnd/', preference_enable_dnd, name='notification-preferences-enable-dnd'),
    path('preferences/disable-dnd/', preference_disable_dnd, name='notification-preferences-disable-dnd'),
]
