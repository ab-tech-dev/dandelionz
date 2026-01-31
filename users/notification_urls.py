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
router.register(r'preferences', NotificationPreferenceViewSet, basename='notification-preference')

urlpatterns = [
    path('', include(router.urls)),
]
