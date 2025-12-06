from django.urls import path
from .views import CustomerProfileViewSet, VendorViewSet, BusinessAdminViewSet

# -------------------------
# CUSTOMER
# -------------------------
customer_profile = CustomerProfileViewSet.as_view({
    "get": "list",
    "put": "update",
    "patch": "partial_update",
})
customer_change_password = CustomerProfileViewSet.as_view({
    "post": "change_password",
})

# -------------------------
# VENDOR
# -------------------------
vendor_profile = VendorViewSet.as_view({
    "get": "retrieve",
    "put": "update",
    "patch": "partial_update",
})
vendor_change_password = VendorViewSet.as_view({
    "post": "change_password",
})

# -------------------------
# BUSINESS ADMIN
# -------------------------
business_admin_profile = BusinessAdminViewSet.as_view({
    "get": "retrieve",
})
business_admin_change_password = BusinessAdminViewSet.as_view({
    "post": "change_password",
})

urlpatterns = [
    # =============================
    # CUSTOMER ROUTES
    # =============================
    path("customer/profile/", customer_profile, name="customer-profile"),
    path("customer/change-password/", customer_change_password, name="customer-change-password"),

    # =============================
    # VENDOR ROUTES
    # =============================
    path("vendor/profile/", vendor_profile, name="vendor-profile"),
    path("vendor/change-password/", vendor_change_password, name="vendor-change-password"),
    path("vendor/add-product/", VendorViewSet.as_view({"post": "add_product"})),
    path("vendor/list-products/", VendorViewSet.as_view({"get": "list_products"})),
    path("vendor/update-product/<int:pk>/", VendorViewSet.as_view({"put": "update_product", "patch": "update_product"})),
    path("vendor/delete-product/<int:pk>/", VendorViewSet.as_view({"delete": "delete_product"})),
    path("vendor/orders/", VendorViewSet.as_view({"get": "orders"})),
    path("vendor/analytics/", VendorViewSet.as_view({"get": "analytics"})),
    path("vendor/notifications/", VendorViewSet.as_view({"get": "notifications"})),

    # =============================
    # BUSINESS ADMIN ROUTES
    # =============================
    path("admin/profile/", business_admin_profile, name="business-admin-profile"),
    path("admin/change-password/", business_admin_change_password, name="business-admin-change-password"),

    path("admin/notifications/", BusinessAdminViewSet.as_view({"get": "notifications"})),

    path("admin/vendors/", BusinessAdminViewSet.as_view({"get": "list_vendors"})),
    path("admin/vendors/<int:pk>/approve/", BusinessAdminViewSet.as_view({"post": "approve_vendor"})),
    path("admin/users/<int:pk>/suspend/", BusinessAdminViewSet.as_view({"post": "suspend_user"})),
    path("admin/vendors/<int:pk>/verify-kyc/", BusinessAdminViewSet.as_view({"post": "verify_kyc"})),

    path("admin/products/", BusinessAdminViewSet.as_view({"get": "list_products"})),
    path("admin/products/<int:pk>/update/", BusinessAdminViewSet.as_view({"put": "update_product", "patch": "update_product"})),

    path("admin/orders/", BusinessAdminViewSet.as_view({"get": "orders"})),
    path("admin/orders/<int:pk>/assign-logistics/", BusinessAdminViewSet.as_view({"post": "assign_logistics"})),
    path("admin/orders/<int:pk>/refund/", BusinessAdminViewSet.as_view({"post": "process_refund"})),

    path("admin/payments/", BusinessAdminViewSet.as_view({"get": "payments"})),
    path("admin/vendors/<int:pk>/trigger-payout/", BusinessAdminViewSet.as_view({"post": "trigger_payout"})),
    path("admin/settlements/", BusinessAdminViewSet.as_view({"get": "settlements"})),
]
