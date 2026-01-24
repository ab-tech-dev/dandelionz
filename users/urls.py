from django.urls import path, re_path
from .views import (
    CustomerProfileViewSet,
    VendorViewSet,
    AdminProfileViewSet,
    AdminVendorViewSet,
    AdminMarketplaceViewSet,
    AdminOrdersViewSet,
    AdminFinanceViewSet,
    AdminAnalyticsViewSet,
    DeliveryAgentViewSet,
    AdminDeliveryAgentViewSet,
    AdminNotificationViewSet,
    NotificationsListView,
    NotificationDetailView,
    UnreadNotificationsCountView,
    MarkAllNotificationsReadView,
)
from authentication.views_admin import (
    AdminUserListView,
    AdminUserDetailView,
    AdminUserSuspendView,
    AdminOrderListView,
    AdminOrderDetailView,
    AdminOrderCancelView,
    AdminProfileView,
    AdminPhotoUploadView,
    AdminPasswordVerifyView,
    AdminPasswordChangeView,
    AdminAuditLogView,
)

# =========================
# CUSTOMER
# =========================
customer_profile = CustomerProfileViewSet.as_view({
    "get": "list",
    "put": "update",
    "patch": "partial_update",
})
customer_change_password = CustomerProfileViewSet.as_view({"post": "change_password"})

# =========================
# VENDOR
# =========================
vendor_profile = VendorViewSet.as_view({
    "get": "retrieve",
    "put": "update",
    "patch": "partial_update",
})
vendor_change_password = VendorViewSet.as_view({"post": "change_password"})

# =========================
# ADMIN
# =========================
admin_profile = AdminProfileViewSet.as_view({"get": "retrieve"})
admin_change_password = AdminProfileViewSet.as_view({"post": "change_password"})

admin_list_vendors = AdminVendorViewSet.as_view({"get": "list_vendors"})
admin_vendor_details = AdminVendorViewSet.as_view({"get": "get_vendor_details"})
admin_approve_vendor = AdminVendorViewSet.as_view({"post": "approve_vendor"})
admin_suspend_user = AdminVendorViewSet.as_view({"post": "suspend_user"})
admin_verify_kyc = AdminVendorViewSet.as_view({"post": "verify_kyc"})

admin_list_products = AdminMarketplaceViewSet.as_view({"get": "list_products"})
admin_update_product = AdminMarketplaceViewSet.as_view({"put": "update_product", "patch": "update_product"})

admin_orders_summary = AdminOrdersViewSet.as_view({"get": "summary"})
admin_assign_logistics = AdminOrdersViewSet.as_view({"post": "assign_logistics"})
admin_process_refund = AdminOrdersViewSet.as_view({"post": "process_refund"})

admin_payments = AdminFinanceViewSet.as_view({"get": "payments"})
admin_trigger_payout = AdminFinanceViewSet.as_view({"post": "trigger_payout"})

admin_analytics = AdminAnalyticsViewSet.as_view({"get": "overview"})

# =========================
# DELIVERY AGENT
# =========================
delivery_profile = DeliveryAgentViewSet.as_view({
    "get": "list",
    "patch": "partial_update",
})
delivery_assigned_orders = DeliveryAgentViewSet.as_view({"get": "assigned_orders"})
delivery_mark_delivered = DeliveryAgentViewSet.as_view({"patch": "mark_delivered"})
delivery_stats = DeliveryAgentViewSet.as_view({"get": "stats"})
delivery_notifications = DeliveryAgentViewSet.as_view({"get": "notifications"})
delivery_pending = DeliveryAgentViewSet.as_view({"get": "pending_deliveries"})

# =========================
# ADMIN DELIVERY AGENT MANAGEMENT
# =========================
admin_list_agents = AdminDeliveryAgentViewSet.as_view({"get": "list_agents"})
admin_create_agent = AdminDeliveryAgentViewSet.as_view({"post": "create_agent"})
admin_update_agent = AdminDeliveryAgentViewSet.as_view({"patch": "update_agent_status"})
admin_agent_details = AdminDeliveryAgentViewSet.as_view({"get": "get_agent_details"})

urlpatterns = [
    # CUSTOMER
    path("customer/profile/", customer_profile, name="customer-profile"),
    path("customer/change-password/", customer_change_password, name="customer-change-password"),

    # VENDOR
    path("vendor/profile/", vendor_profile, name="vendor-profile"),
    path("vendor/change-password/", vendor_change_password, name="vendor-change-password"),
    path("vendor/products/add/", VendorViewSet.as_view({"post": "add_product"}), name="vendor-add-product"),
    path("vendor/products/", VendorViewSet.as_view({"get": "list_products"}), name="vendor-list-products"),
    path("vendor/products/<slug:slug>/", VendorViewSet.as_view({"put": "update_product", "patch": "update_product", "delete": "delete_product"}), name="vendor-product-detail"),
    path("vendor/orders/", VendorViewSet.as_view({"get": "orders"}), name="vendor-orders"),
    path("vendor/analytics/", VendorViewSet.as_view({"get": "analytics"}), name="vendor-analytics"),
    path("vendor/notifications/", VendorViewSet.as_view({"get": "notifications"}), name="vendor-notifications"),

    # ADMIN PROFILE
    path("admin/profile/", admin_profile, name="admin-profile"),
    path("admin/change-password/", admin_change_password, name="admin-change-password"),

    # ADMIN VENDOR MANAGEMENT
    path("admin/vendors/", admin_list_vendors, name="admin-list-vendors"),
    re_path(r"^admin/vendors/(?P<vendor_uuid>[^/]+)/$", admin_vendor_details, name="admin-vendor-details"),
    path("admin/vendors/approve/", admin_approve_vendor, name="admin-approve-vendor"),
    path("admin/users/suspend/", admin_suspend_user, name="admin-suspend-user"),
    path("admin/vendors/verify-kyc/", admin_verify_kyc, name="admin-verify-kyc"),

    # ADMIN MARKETPLACE
    path("admin/products/", admin_list_products, name="admin-list-products"),
    path("admin/products/update/", admin_update_product, name="admin-update-product"),
    path("admin/products/<slug:slug>/delete/", AdminMarketplaceViewSet.as_view({"delete": "delete_product"}), name="admin-delete-product"),
    # ADMIN ORDERS
    path("admin/orders/summary/", admin_orders_summary, name="admin-orders-summary"),
    path("admin/orders/assign-logistics/", admin_assign_logistics, name="admin-assign-logistics"),
    path("admin/orders/refund/", admin_process_refund, name="admin-process-refund"),

    # ADMIN FINANCE
    path("admin/payments/", admin_payments, name="admin-payments"),
    path("admin/payouts/trigger/", admin_trigger_payout, name="admin-trigger-payout"),

    # ADMIN ANALYTICS
    path("admin/analytics/", admin_analytics, name="admin-analytics"),

    # DELIVERY AGENT
    path("delivery/profile/", delivery_profile, name="delivery-profile"),
    path("delivery/assigned-orders/", delivery_assigned_orders, name="delivery-assigned-orders"),
    path("delivery/mark-delivered/<str:order_id>/", delivery_mark_delivered, name="delivery-mark-delivered"),
    path("delivery/stats/", delivery_stats, name="delivery-stats"),
    path("delivery/notifications/", delivery_notifications, name="delivery-notifications"),
    path("delivery/pending-deliveries/", delivery_pending, name="delivery-pending-deliveries"),

    # ADMIN DELIVERY AGENT MANAGEMENT
    path("admin/delivery-agents/", admin_list_agents, name="admin-list-agents"),
    path("admin/delivery-agents/create/", admin_create_agent, name="admin-create-agent"),
    path("admin/delivery-agents/update-status/", admin_update_agent, name="admin-update-agent-status"),
    path("admin/delivery-agents/details/<int:agent_id>/", admin_agent_details, name="admin-agent-details"),

    # NOTIFICATIONS
    path("notifications/", NotificationsListView.as_view(), name="notifications-list"),
    path("notifications/<int:notification_id>/", NotificationDetailView.as_view(), name="notification-detail"),
    path("notifications/unread/count/", UnreadNotificationsCountView.as_view(), name="unread-count"),
    path("notifications/mark-all-read/", MarkAllNotificationsReadView.as_view(), name="mark-all-read"),

    # ADMIN NOTIFICATIONS
    path("admin/notifications/", AdminNotificationViewSet.as_view({"post": "create", "get": "list_notifications"}), name="admin-notifications"),

    # NEW ADMIN DASHBOARD ENDPOINTS (User & Order Management + Audit)
    # User Management
    path("admin/users/", AdminUserListView.as_view(), name="admin-users-list"),
    path("admin/users/<uuid:uuid>/", AdminUserDetailView.as_view(), name="admin-users-detail"),
    path("admin/users/<uuid:uuid>/suspend/", AdminUserSuspendView.as_view(), name="admin-users-suspend"),
    
    # Order Management (with status history)
    path("admin/orders/list/", AdminOrderListView.as_view(), name="admin-orders-list"),
    path("admin/orders/<uuid:order_id>/", AdminOrderDetailView.as_view(), name="admin-orders-detail"),
    path("admin/orders/<uuid:order_id>/cancel/", AdminOrderCancelView.as_view(), name="admin-orders-cancel"),
    
    # Admin Profile Management
    path("admin/account/profile/", AdminProfileView.as_view(), name="admin-account-profile"),
    path("admin/account/photo/", AdminPhotoUploadView.as_view(), name="admin-account-photo"),
    path("admin/account/password/verify/", AdminPasswordVerifyView.as_view(), name="admin-account-password-verify"),
    path("admin/account/password/change/", AdminPasswordChangeView.as_view(), name="admin-account-password-change"),
    
    # Audit Logs
    path("admin/audit-logs/", AdminAuditLogView.as_view(), name="admin-audit-logs"),
]
