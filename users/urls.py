from django.urls import path, re_path, include
from .views import (
    CustomerProfileViewSet,
    VendorViewSet,
    VendorWalletViewSet,
    VendorPaymentSettingsViewSet,
    VendorAccountViewSet,
    AdminProfileViewSet,
    AdminVendorViewSet,
    AdminMarketplaceViewSet,
    AdminOrdersViewSet,
    AdminFinanceViewSet,
    AdminAnalyticsViewSet,
    DeliveryAgentViewSet,
    AdminDeliveryAgentViewSet,
    AdminNotificationViewSet,
    AdminWalletViewSet,
    AdminPaymentSettingsViewSet,
    AdminSettlementsViewSet,
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
customer_close_account = CustomerProfileViewSet.as_view({"delete": "close_account"})

# =========================
# VENDOR
# =========================
vendor_profile = VendorViewSet.as_view({
    "get": "retrieve",
    "put": "update",
    "patch": "partial_update",
})
vendor_change_password = VendorViewSet.as_view({"post": "change_password"})
vendor_close_account = VendorViewSet.as_view({"delete": "close_account"})

# =========================
# ADMIN
# =========================
admin_profile = AdminProfileViewSet.as_view({"get": "retrieve"})
admin_change_password = AdminProfileViewSet.as_view({"post": "change_password"})

admin_list_vendors = AdminVendorViewSet.as_view({"get": "list_vendors"})
admin_vendor_details = AdminVendorViewSet.as_view({"get": "get_vendor_details"})
admin_approve_vendor = AdminVendorViewSet.as_view({"post": "approve_vendor", "put": "approve_vendor"})
admin_suspend_user = AdminVendorViewSet.as_view({"post": "suspend_user", "put": "suspend_user"})
admin_verify_kyc = AdminVendorViewSet.as_view({"post": "verify_kyc", "put": "verify_kyc"})

admin_list_products = AdminMarketplaceViewSet.as_view({"get": "list_products"})
admin_update_product = AdminMarketplaceViewSet.as_view({"put": "update_product", "patch": "update_product"})

admin_orders_summary = AdminOrdersViewSet.as_view({"get": "summary"})
admin_assign_logistics = AdminOrdersViewSet.as_view({"post": "assign_logistics"})
admin_process_refund = AdminOrdersViewSet.as_view({"post": "process_refund"})

admin_payments = AdminFinanceViewSet.as_view({"get": "payments"})
admin_trigger_payout = AdminFinanceViewSet.as_view({"post": "trigger_payout"})
admin_finance_summary = AdminFinanceViewSet.as_view({"get": "summary"})
admin_finance_transactions = AdminFinanceViewSet.as_view({"get": "transactions"})
admin_finance_payouts = AdminFinanceViewSet.as_view({"get": "payouts"})
admin_finance_withdrawals = AdminFinanceViewSet.as_view({"get": "list_withdrawals"})
admin_finance_withdrawal_detail = AdminFinanceViewSet.as_view({"get": "withdrawal_detail"})
admin_finance_withdrawal_approve = AdminFinanceViewSet.as_view({"post": "approve_withdrawal"})
admin_finance_withdrawal_reject = AdminFinanceViewSet.as_view({"post": "reject_withdrawal"})

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
    path("customer/account/", customer_close_account, name="customer-close-account"),
    
    # CUSTOMER WALLET & PAYMENT
    path("customer/wallet/", CustomerProfileViewSet.as_view({"get": "wallet_balance"}), name="customer-wallet-balance"),
    path("customer/wallet/transactions/", CustomerProfileViewSet.as_view({"get": "wallet_transactions"}), name="customer-wallet-transactions"),
    path("customer/wallet/withdraw/", CustomerProfileViewSet.as_view({"post": "request_withdrawal"}), name="customer-request-withdrawal"),
    
    # CUSTOMER PAYMENT SETTINGS & PIN
    path("customer/payment-settings/pin/", CustomerProfileViewSet.as_view({"post": "set_payment_pin"}), name="customer-set-pin"),

    # VENDOR
    path("vendor/profile/", vendor_profile, name="vendor-profile"),
    path("vendor/change-password/", vendor_change_password, name="vendor-change-password"),
    path("vendor/account/", vendor_close_account, name="vendor-close-account"),
    path("vendor/products/add/", VendorViewSet.as_view({"post": "add_product"}), name="vendor-add-product"),
    path("vendor/products/", VendorViewSet.as_view({"get": "list_products"}), name="vendor-list-products"),
    path(
        "vendor/products/<slug:slug>/",
        VendorViewSet.as_view(
            {
                "get": "product_detail",
                "put": "update_product",
                "patch": "update_product",
                "delete": "delete_product",
            }
        ),
        name="vendor-product-detail",
    ),
    path("vendor/orders/", VendorViewSet.as_view({"get": "orders"}), name="vendor-orders"),
    path("vendor/orders/list/", VendorViewSet.as_view({"get": "list_orders"}), name="vendor-orders-list"),
    re_path(r"^vendor/orders/(?P<order_uuid>[^/]+)/$", VendorViewSet.as_view({"get": "order_detail"}), name="vendor-order-detail"),
    path("vendor/analytics/", VendorViewSet.as_view({"get": "analytics"}), name="vendor-analytics"),
    path("vendor/notifications/", VendorViewSet.as_view({"get": "notifications"}), name="vendor-notifications"),
    
    # VENDOR WALLET & PAYMENT
    path("vendor/wallet/", VendorWalletViewSet.as_view({"get": "wallet_balance"}), name="vendor-wallet-balance"),
    path("vendor/wallet/transactions/", VendorWalletViewSet.as_view({"get": "wallet_transactions"}), name="vendor-wallet-transactions"),
    path("vendor/wallet/withdraw/", VendorWalletViewSet.as_view({"post": "request_withdrawal"}), name="vendor-request-withdrawal"),
    
    # VENDOR PAYMENT SETTINGS & PIN
    path("vendor/payment-settings/", VendorPaymentSettingsViewSet.as_view({"get": "payment_settings", "put": "update_payment_settings"}), name="vendor-payment-settings"),
    path("vendor/payment-settings/pin/", VendorPaymentSettingsViewSet.as_view({"post": "set_payment_pin"}), name="vendor-set-pin"),
    path("vendor/payment-settings/pin/forgot/", VendorPaymentSettingsViewSet.as_view({"post": "forgot_payment_pin"}), name="vendor-forgot-pin"),
    
    # VENDOR ACCOUNT
    path("vendor/account/", VendorAccountViewSet.as_view({"delete": "delete_account"}), name="vendor-delete-account"),

    # ADMIN PROFILE
    path("admin/profile/", admin_profile, name="admin-profile"),
    path("admin/change-password/", admin_change_password, name="admin-change-password"),

    # ADMIN VENDOR MANAGEMENT
    path("admin/vendors/", admin_list_vendors, name="admin-list-vendors"),
    path("admin/vendors/approve/", admin_approve_vendor, name="admin-approve-vendor"),
    path("admin/vendors/<uuid:vendor_uuid>/approve/", admin_approve_vendor, name="admin-approve-vendor-by-uuid"),
    path("admin/vendors/verify-kyc/", admin_verify_kyc, name="admin-verify-kyc"),
    path("admin/vendors/<uuid:vendor_uuid>/verify-kyc/", admin_verify_kyc, name="admin-verify-kyc-by-uuid"),
    path("admin/vendors/<uuid:vendor_uuid>/suspend/", admin_suspend_user, name="admin-vendor-suspend"),
    path("admin/users/suspend/", admin_suspend_user, name="admin-suspend-user"),
    re_path(r"^admin/vendors/(?P<vendor_uuid>[^/]+)/$", admin_vendor_details, name="admin-vendor-details"),

    # ADMIN MARKETPLACE
    path("admin/products/", admin_list_products, name="admin-list-products"),
    path("admin/products/update/", admin_update_product, name="admin-update-product"),
    path("admin/products/<slug:slug>/delete/", AdminMarketplaceViewSet.as_view({"delete": "delete_product"}), name="admin-delete-product"),
    # ADMIN ORDERS
    path("admin/orders/", AdminOrderListView.as_view(), name="admin-orders"),
    path("admin/orders/summary/", admin_orders_summary, name="admin-orders-summary"),
    path("admin/orders/assign-logistics/", admin_assign_logistics, name="admin-assign-logistics"),
    path("admin/orders/refund/", admin_process_refund, name="admin-process-refund"),

    # ADMIN FINANCE
    path("admin/payments/", admin_payments, name="admin-payments"),
    path("admin/payouts/trigger/", admin_trigger_payout, name="admin-trigger-payout"),
    path("admin/finance/summary/", admin_finance_summary, name="admin-finance-summary"),
    path("admin/finance/transactions/", admin_finance_transactions, name="admin-finance-transactions"),
    path("admin/finance/payouts/", admin_finance_payouts, name="admin-finance-payouts"),
    path("admin/finance/withdrawals/", admin_finance_withdrawals, name="admin-finance-withdrawals"),
    path("admin/finance/withdrawals/detail/", admin_finance_withdrawal_detail, name="admin-finance-withdrawal-detail"),
    path("admin/finance/withdrawals/approve/", admin_finance_withdrawal_approve, name="admin-finance-withdrawal-approve"),
    path("admin/finance/withdrawals/reject/", admin_finance_withdrawal_reject, name="admin-finance-withdrawal-reject"),

    # ADMIN ANALYTICS
    path("admin/analytics/", admin_analytics, name="admin-analytics"),
    path("admin/analytics/detailed/", AdminAnalyticsViewSet.as_view({"get": "detailed"}), name="admin-analytics-detailed"),

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

    # NOTIFICATIONS (Deprecated - Use new REST API endpoints instead)
    # path("notifications/", NotificationsListView.as_view(), name="notifications-list"),  # Use GET /api/notifications/
    # path("notifications/<int:notification_id>/", NotificationDetailView.as_view(), name="notification-detail"),  # Use GET /api/notifications/{id}/
    # path("notifications/unread/count/", UnreadNotificationsCountView.as_view(), name="unread-count"),  # Use GET /api/notifications/unread_count/
    # path("notifications/mark-all-read/", MarkAllNotificationsReadView.as_view(), name="mark-all-read"),  # Use POST /api/notifications/mark_all_as_read/

    # ADMIN NOTIFICATIONS
    path("admin/notifications/", AdminNotificationViewSet.as_view({"post": "create", "get": "list_notifications"}), name="admin-notifications"),
    path("admin/notifications/publish/<uuid:notification_id>/", AdminNotificationViewSet.as_view({"post": "publish_notification"}), name="admin-notification-publish"),

    # ADMIN WALLET & EARNINGS
    path("admin/wallet/", AdminWalletViewSet.as_view({"get": "balance"}), name="admin-wallet-balance"),
    path("admin/wallet/transactions/", AdminWalletViewSet.as_view({"get": "transactions"}), name="admin-wallet-transactions"),
    path("admin/wallet/withdraw/", AdminWalletViewSet.as_view({"post": "withdraw"}), name="admin-withdraw"),

    # ADMIN PAYMENT SETTINGS & PIN
    path("admin/payment-settings/", AdminPaymentSettingsViewSet.as_view({"get": "retrieve_settings", "put": "update_settings"}), name="admin-payment-settings"),
    path("admin/payment-settings/pin/", AdminPaymentSettingsViewSet.as_view({"post": "set_pin"}), name="admin-set-pin"),

    # ADMIN SETTLEMENTS & DISPUTES
    path("admin/settlements/summary/", AdminSettlementsViewSet.as_view({"get": "summary"}), name="admin-settlements-summary"),
    path("admin/settlements/vendor/", AdminSettlementsViewSet.as_view({"get": "vendor"}), name="admin-vendor-settlements"),
    path("admin/settlements/disputes/", AdminSettlementsViewSet.as_view({"get": "disputes"}), name="admin-disputes"),
    re_path(r"^admin/settlements/disputes/(?P<dispute_id>[^/]+)/resolve/$", AdminSettlementsViewSet.as_view({"post": "resolve_dispute"}), name="admin-resolve-dispute"),

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

    # ========================================
    # NOTIFICATION SYSTEM
    # ========================================
    path("notifications/", include("users.notification_urls")),
]
