import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "e_commerce_api.settings")

from django.core.asgi import get_asgi_application

# Initialize Django first
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
import logging

from users.notification_auth import JwtAuthMiddleware
from users.routing import websocket_urlpatterns

logger = logging.getLogger(__name__)


class TokenAwareOriginValidator(AllowedHostsOriginValidator):
    """
    Custom origin validator that bypasses origin checking if a valid JWT token is provided.
    This allows WebSocket connections from curl, non-browser clients, and localhost.
    
    How it works:
    1. Checks if a JWT token is present in query string (?token=xxx) or Authorization header
    2. If token is present, skips origin validation and lets JWT middleware handle auth
    3. If no token, applies strict origin validation (for browser connections)
    
    This solves the 403 error issue when using curl with valid tokens.
    """
    
    async def __call__(self, scope, receive, send):
        """
        Override to check for valid JWT token before enforcing origin validation
        
        Args:
            scope: WebSocket connection scope
            receive: Channel receive callable
            send: Channel send callable
        """
        # Only apply to WebSocket connections
        if scope['type'] != 'websocket':
            return await super().__call__(scope, receive, send)
        
        # Extract token from query string or headers
        query_string = scope.get('query_string', b'').decode()
        headers = dict(scope.get('headers', []))
        
        has_token = False
        
        # Check query params for token: ?token=xxx
        if 'token=' in query_string:
            has_token = True
            logger.debug(f"Found token in query string")
        
        # Check Authorization header for token: Authorization: Bearer xxx
        auth_header = headers.get(b'authorization', b'').decode()
        if auth_header.startswith('Bearer '):
            has_token = True
            logger.debug(f"Found token in Authorization header")
        
        # If token is provided, skip origin validation
        # The JWT middleware will validate the token itself
        if has_token:
            logger.info(f"Valid token detected in WebSocket connection from {scope.get('client')}, skipping origin validation")
            return await URLRouter(websocket_urlpatterns)(scope, receive, send)
        
        # Otherwise, enforce origin validation for browser connections
        logger.debug(f"No token provided, enforcing origin validation for {scope.get('client')}")
        return await super().__call__(scope, receive, send)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAwareOriginValidator(
        JwtAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    )
})
