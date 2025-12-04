# users/urls.py
from django.urls import path
from .views import CustomerProfileViewSet, VendorViewSet

from django.urls import path
from users.views import BusinessAdminViewSet

business_admin_retrieve = BusinessAdminViewSet.as_view({
    "get": "retrieve",
})

business_admin_change_password = BusinessAdminViewSet.as_view({
    "post": "change_password",
})

business_admin_notifications = BusinessAdminViewSet.as_view({
    "get": "notifications",
})

business_admin_list_vendors = BusinessAdminViewSet.as_view({
    "get": "list_vendors",
})

business_admin_approve_vendor = BusinessAdminViewSet.as_view({
    "post": "approve_vendor",
})

business_admin_suspend_user = BusinessAdminViewSet.as_view({
    "post": "suspend_user",
})

business_admin_verify_kyc = BusinessAdminViewSet.as_view({
    "post": "verify_kyc",
})

business_admin_list_products = BusinessAdminViewSet.as_view({
    "get": "list_products",
})

business_admin_update_product = BusinessAdminViewSet.as_view({
    "put": "update_product",
    "patch": "update_product",
})

business_admin_orders = BusinessAdminViewSet.as_view({
    "get": "orders",
})

business_admin_assign_logistics = BusinessAdminViewSet.as_view({
    "post": "assign_logistics",
})

business_admin_process_refund = BusinessAdminViewSet.as_view({
    "post": "process_refund",
})

business_admin_payments = BusinessAdminViewSet.as_view({
    "get": "payments",
})

business_admin_trigger_payout = BusinessAdminViewSet.as_view({
    "post": "trigger_payout",
})

business_admin_settlements = BusinessAdminViewSet.as_view({
    "get": "settlements",
})

customer_profile = CustomerProfileViewSet.as_view({
    'get': 'list',
    'put': 'update',
    'patch': 'partial_update'
})

change_password = CustomerProfileViewSet.as_view({
    'post': 'change_password'
})

urlpatterns = [
    path('profile/', customer_profile, name='customer-profile'),
    path('change-password/', change_password, name='change-password'),
    path("profile/", VendorViewSet.as_view({"get": "retrieve", "put": "update", "patch": "partial_update"})),
    path("change-password/", VendorViewSet.as_view({"post": "change_password"})),
    path("add-product/", VendorViewSet.as_view({"post": "add_product"})),
    path("list-products/", VendorViewSet.as_view({"get": "list_products"})),
    path("update-product/<int:pk>/", VendorViewSet.as_view({"put": "update_product", "patch": "update_product"})),
    path("delete-product/<int:pk>/", VendorViewSet.as_view({"delete": "delete_product"})),
    path("orders/", VendorViewSet.as_view({"get": "orders"})),
    path("analytics/", VendorViewSet.as_view({"get": "analytics"})),
    path("vendor-notifications/", VendorViewSet.as_view({"get": "notifications"})),
    path("profile/", business_admin_retrieve, name="business-admin-profile"),
    path("change-password/", business_admin_change_password, name="business-admin-change-password"),

    path("admin-notifications/", business_admin_notifications, name="business-admin-notifications"),

    path("vendors/", business_admin_list_vendors, name="business-admin-list-vendors"),
    path("vendors/<int:pk>/approve/", business_admin_approve_vendor, name="business-admin-approve-vendor"),
    path("users/<int:pk>/suspend/", business_admin_suspend_user, name="business-admin-suspend-user"),
    path("vendors/<int:pk>/verify-kyc/", business_admin_verify_kyc, name="business-admin-verify-kyc"),

    path("products/", business_admin_list_products, name="business-admin-list-products"),
    path("products/<int:pk>/update/", business_admin_update_product, name="business-admin-update-product"),

    path("orders/", business_admin_orders, name="business-admin-orders"),
    path("orders/<int:pk>/assign-logistics/", business_admin_assign_logistics, name="business-admin-assign-logistics"),
    path("orders/<int:pk>/refund/", business_admin_process_refund, name="business-admin-process-refund"),

    path("payments/", business_admin_payments, name="business-admin-payments"),
    path("vendors/<int:pk>/trigger-payout/", business_admin_trigger_payout, name="business-admin-trigger-payout"),
    path("settlements/", business_admin_settlements, name="business-admin-settlements"),    
]


