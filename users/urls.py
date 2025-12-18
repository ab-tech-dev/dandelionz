from django.urls import path
from .views import (
    CustomerProfileViewSet,
    VendorViewSet,
    AdminProfileViewSet,
    AdminVendorViewSet,
    AdminMarketplaceViewSet,
    AdminOrdersViewSet,
    AdminFinanceViewSet,
    AdminAnalyticsViewSet,
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
]
