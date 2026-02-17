
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


from django.urls import path, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Dandelionz Ecommerce API",
        default_version='v1',
        description="API documentation for Multi-Vendor Ecommerce Platform",
        terms_of_service="https://dandelionz.com.ng/terms/",
        contact=openapi.Contact(email="support@dandelionz.com.ng"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError
import redis
import os

# Vendor wallet quick-access aliases (legacy frontend paths)
from users.views import VendorWalletViewSet, VendorPaymentSettingsViewSet

vendor_wallet_balance = VendorWalletViewSet.as_view({"get": "wallet_balance"})
vendor_wallet_transactions = VendorWalletViewSet.as_view({"get": "wallet_transactions"})
vendor_wallet_withdraw = VendorWalletViewSet.as_view({"post": "request_withdrawal"})
vendor_payment_settings = VendorPaymentSettingsViewSet.as_view({"get": "payment_settings", "put": "update_payment_settings"})
vendor_payment_pin = VendorPaymentSettingsViewSet.as_view({"post": "set_payment_pin"})
vendor_payment_pin_forgot = VendorPaymentSettingsViewSet.as_view({"post": "forgot_payment_pin"})


def api_root(request):
    """Root API endpoint - provides API information and health check"""
    return JsonResponse({
        'success': True,
        'message': 'Welcome to Dandelionz Ecommerce API',
        'version': '1.0.0',
        'status': 'operational',
        'endpoints': {
            'auth': '/auth/',
            'store': '/store/',
            'user': '/user/',
            'transactions': '/transactions/',
            'api_docs': '/swagger/',
            'redoc': '/redoc/',
        }
    })



urlpatterns = [
    # Root API endpoint
    path('', api_root, name='api-root'),
    
    # Fake admin traps
    path('admin/', include('django_admin_trap.urls')),
    path('wp-admin/', include('django_admin_trap.urls')),
    path('administrator/', include('django_admin_trap.urls')),

    # Real admin (hidden)
    path('abtechdev/', admin.site.urls),

    # App URLs
    path('auth/', include('authentication.urls')),
    path('store/', include('store.urls')),
    path('user/', include('users.urls')),
    path('transactions/', include('transactions.urls')),

    # Legacy vendor wallet endpoints (frontend uses /vendor/*)
    path('vendor/wallet/', vendor_wallet_balance, name='vendor-wallet-balance-legacy'),
    path('vendor/wallet/transactions/', vendor_wallet_transactions, name='vendor-wallet-transactions-legacy'),
    path('vendor/wallet/withdraw/', vendor_wallet_withdraw, name='vendor-request-withdrawal-legacy'),
    path('vendor/payment-settings/', vendor_payment_settings, name='vendor-payment-settings-legacy'),
    path('vendor/payment-settings/pin/', vendor_payment_pin, name='vendor-payment-settings-pin-legacy'),
    path('vendor/payment-settings/pin/forgot/', vendor_payment_pin_forgot, name='vendor-payment-settings-pin-forgot-legacy'),

    # Swagger
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
] + static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)
