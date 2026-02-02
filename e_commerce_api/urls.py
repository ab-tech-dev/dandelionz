
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

    # Swagger
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
] + static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)
