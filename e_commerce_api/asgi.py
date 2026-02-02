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


class TokenAwareOriginValidator:
    """
    Custom WebSocket validator that allows token-authenticated connections
    to bypass strict origin validation while still enforcing it for browser connections.
    
    This allows WebSocket connections from curl, non-browser clients, and localhost
    when they provide a valid JWT token.
    """
    
    def __init__(self, inner):
        self.inner = inner
    
    async def __call__(self, scope, receive, send):
        """
        Check for token before validating origin
        
        Args:
            scope: WebSocket connection scope
            receive: Channel receive callable
            send: Channel send callable
        """
        # Only apply to WebSocket connections
        if scope['type'] != 'websocket':
            return await self.inner(scope, receive, send)
        
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
        
        # If token is provided, bypass origin validation but continue through middleware
        # The JWT middleware will validate the token
        if has_token:
            logger.info(f"Token detected in WebSocket connection from {scope.get('client')}, skipping origin validation")
            return await self.inner(scope, receive, send)
        
        # Otherwise, check origin for browser connections
        origin = dict(scope.get('headers', [])).get(b'origin', b'').decode()
        if origin:
            logger.debug(f"No token provided, validating origin: {origin}")
            # Validate origin - let AllowedHostsOriginValidator handle this
            validator = AllowedHostsOriginValidator(self.inner)
            return await validator(scope, receive, send)
        
        # No origin header (likely non-browser), allow through with token or JWT validation
        return await self.inner(scope, receive, send)


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": TokenAwareOriginValidator(
        JwtAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    )
})
