"""
Admin Dashboard API URLs

All routes require BUSINESS_ADMIN or ADMIN authentication.
All admin actions are logged for audit trail.
"""

from django.urls import path
from authentication.views_admin import (
    AdminUserListView,
    AdminUserDetailView,
    AdminUserSuspendView,
    AdminUserActivateView,
    AdminOrderListView,
    AdminOrderDetailView,
    AdminOrderCancelView,
    AdminProfileView,
    AdminPhotoUploadView,
    AdminPasswordVerifyView,
    AdminPasswordChangeView,
    AdminAuditLogView,
)

app_name = 'admin'

urlpatterns = [
    # =====================================================
    # USER MANAGEMENT ENDPOINTS
    # =====================================================
    path('users/', AdminUserListView.as_view(), name='user-list'),
    path('users/<uuid:uuid>/', AdminUserDetailView.as_view(), name='user-detail'),
    path('users/<uuid:uuid>/suspend/', AdminUserSuspendView.as_view(), name='user-suspend'),
    path('users/<uuid:uuid>/activate/', AdminUserActivateView.as_view(), name='user-activate'),
    
    # =====================================================
    # ORDER MANAGEMENT ENDPOINTS
    # =====================================================
    path('orders/', AdminOrderListView.as_view(), name='order-list'),
    path('orders/<uuid:order_id>/', AdminOrderDetailView.as_view(), name='order-detail'),
    path('orders/<uuid:order_id>/cancel/', AdminOrderCancelView.as_view(), name='order-cancel'),
    
    # =====================================================
    # ADMIN PROFILE MANAGEMENT ENDPOINTS
    # =====================================================
    path('profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('profile/photo/', AdminPhotoUploadView.as_view(), name='admin-photo-upload'),
    path('password/verify/', AdminPasswordVerifyView.as_view(), name='admin-password-verify'),
    path('password/change/', AdminPasswordChangeView.as_view(), name='admin-password-change'),
    
    # =====================================================
    # AUDIT LOG ENDPOINTS
    # =====================================================
    path('audit-logs/', AdminAuditLogView.as_view(), name='audit-logs'),
]
