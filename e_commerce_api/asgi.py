import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_commerce_api.settings")

from django.core.asgi import get_asgi_application

# Initialize Django first
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from channels.middleware import BaseMiddleware
import logging

from users.notification_auth import JwtAuthMiddleware
from users.routing import websocket_urlpatterns

logger = logging.getLogger(__name__)


class TokenAwareOriginValidator(BaseMiddleware):
    """
    Custom WebSocket validator that allows token-authenticated connections
    to bypass strict origin validation while still enforcing it for browser connections.
    
    This allows WebSocket connections from curl, non-browser clients, and localhost
    when they provide a valid JWT token.
    """
    
    def __init__(self, inner):
        self.inner = inner
        self.allowed_hosts_validator = AllowedHostsOriginValidator(inner)
    
    async def __call__(self, scope, receive, send):
        """
        Check for token before validating origin
        
        Args:
            scope: WebSocket connection scope
            receive: Channel receive callable
            send: Channel send callable
        """
        try:
            # Only apply to WebSocket connections
            if scope['type'] != 'websocket':
                return await self.inner(scope, receive, send)
            
            client_addr = scope.get('client', ('unknown', 'unknown'))
            logger.info(f"WebSocket connection attempt from {client_addr[0]}:{client_addr[1]}")
            
            # Extract token from query string or headers
            query_string = scope.get('query_string', b'').decode()
            headers = dict(scope.get('headers', []))
            
            has_token = False
            
            # Check query params for token: ?token=xxx
            if 'token=' in query_string:
                has_token = True
                logger.debug(f"Found token in query string from {client_addr[0]}")
            
            # Check Authorization header for token: Authorization: Bearer xxx
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                has_token = True
                logger.debug(f"Found token in Authorization header from {client_addr[0]}")
            
            # If token is provided, bypass origin validation
            # The JWT middleware will validate the token
            if has_token:
                logger.info(f"Token detected, skipping origin validation for {client_addr[0]}")
                return await self.inner(scope, receive, send)
            
            # Otherwise, use strict origin validation for browser connections
            logger.info(f"No token provided, enforcing origin validation for {client_addr[0]}")
            return await self.allowed_hosts_validator(scope, receive, send)
            
        except Exception as e:
            logger.error(f"Error in TokenAwareOriginValidator: {str(e)}", exc_info=True)
            raise


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAwareOriginValidator(
        JwtAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    )
})
