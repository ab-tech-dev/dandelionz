"""
ASGI config for e_commerce_api project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from django.core.asgi import get_asgi_application

import users
from users.notification_auth import JwtAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_commerce_api.settings')

# Initialize Django ASGI application early to ensure apps are loaded
django_asgi_app = get_asgi_application()

# WebSocket URLRouter configuration
ws_urlpatterns = users.routing.websocket_urlpatterns

# ASGI application with proper middleware stack
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JwtAuthMiddleware(
            URLRouter(
                ws_urlpatterns
            )
        )
    )
})
