
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
        terms_of_service="https://danelionz.net/terms/",
        contact=openapi.Contact(email="support@danelionz.net"),
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

def healthz(request):
    data = {"django": "ok"}
    # DB check
    try:
        db_conn = connections['default']
        db_conn.cursor()
        data['db'] = 'ok'
    except OperationalError:
        data['db'] = 'error'

    # Redis check
    try:
        r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/1"))
        if r.ping():
            data['redis'] = 'ok'
        else:
            data['redis'] = 'error'
    except Exception:
        data['redis'] = 'error'

    status = 200 if data.get('db')=='ok' and data.get('redis')=='ok' else 500
    return JsonResponse(data, status=status)




urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('authentication.urls')),
    path('api/store/', include('store.urls')),
    path('api/transactions/', include('transactions.urls')),

    path("health/", healthz),

    # Swagger
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
] + static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)
