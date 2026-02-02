"""
Notification authentication and middleware utilities
"""

import logging
from typing import Optional, Dict, Any
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.auth import AuthMiddlewareStack
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings

logger = logging.getLogger(__name__)
User = settings.AUTH_USER_MODEL


@database_sync_to_async
def get_user(token: str) -> Optional[User]:
    """
    Extract user from JWT token
    
    Args:
        token: JWT access token
    
    Returns:
        User instance or None
    """
    try:
        if not token:
            return None
        
        access_token = AccessToken(token)
        user_id = access_token['user_uuid']
        user = User.objects.get(uuid=user_id)
        return user
    
    except (InvalidToken, TokenError, User.DoesNotExist) as e:
        logger.warning(f"Token validation failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error extracting user from token: {str(e)}")
        return None


class JwtAuthMiddleware(BaseMiddleware):
    """
    Custom JWT authentication middleware for WebSocket.
    Allows both Django session auth and JWT token auth.
    """

    async def __call__(self, scope, receive, send):
        """
        Process WebSocket connection with JWT authentication
        
        Args:
            scope: Connection scope
            receive: ASGI receive channel
            send: ASGI send channel
        """
        try:
            close_old_connections()
            
            client_addr = scope.get('client', ('unknown', 'unknown'))
            logger.info(f"JwtAuthMiddleware processing connection from {client_addr[0]}:{client_addr[1]}")
            
            # Try Django session auth first
            if 'user' in scope and scope['user'].is_authenticated:
                logger.info(f"Using Django session auth for {client_addr[0]}")
                return await super().__call__(scope, receive, send)
            
            # Try JWT token from query string
            query_string = scope.get('query_string', b'').decode()
            token = None
            
            # Extract token from query params: ?token=xxx
            if 'token=' in query_string:
                try:
                    token = query_string.split('token=')[1].split('&')[0]
                    logger.debug(f"Extracted token from query string for {client_addr[0]}")
                except IndexError:
                    logger.warning(f"Failed to parse token from query string for {client_addr[0]}")
                    pass
            
            # Extract token from headers if present
            if not token:
                headers = dict(scope.get('headers', []))
                auth_header = headers.get(b'authorization', b'').decode()
                if auth_header.startswith('Bearer '):
                    token = auth_header[7:]
                    logger.debug(f"Extracted token from Authorization header for {client_addr[0]}")
            
            if token:
                logger.debug(f"Attempting to validate token for {client_addr[0]}")
                user = await get_user(token)
                if user:
                    scope['user'] = user
                    logger.info(f"Successfully authenticated user {user.email if hasattr(user, 'email') else user.uuid} from {client_addr[0]}")
                else:
                    scope['user'] = AnonymousUser()
                    logger.warning(f"Token validation failed for {client_addr[0]}, using AnonymousUser")
            else:
                scope['user'] = AnonymousUser()
                logger.info(f"No token provided for {client_addr[0]}, using AnonymousUser")
            
            return await super().__call__(scope, receive, send)
            
        except Exception as e:
            logger.error(f"Error in JwtAuthMiddleware: {str(e)}", exc_info=True)
            raise


def get_jwt_auth_middleware():
    """
    Factory function to get configured JWT auth middleware
    """
    return JwtAuthMiddleware(AuthMiddlewareStack)


# Additional helper functions

@database_sync_to_async
def user_has_role(user: User, role: str) -> bool:
    """Check if user has specific role"""
    if not user.is_authenticated:
        return False
    return getattr(user, 'role', None) == role


@database_sync_to_async
def user_is_admin(user: User) -> bool:
    """Check if user is admin"""
    if not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser


@database_sync_to_async
def user_is_vendor(user: User) -> bool:
    """Check if user is vendor"""
    if not user.is_authenticated:
        return False
    return getattr(user, 'role', None) == 'VENDOR'


@database_sync_to_async
def user_is_delivery_agent(user: User) -> bool:
    """Check if user is delivery agent"""
    if not user.is_authenticated:
        return False
    return getattr(user, 'role', None) == 'DELIVERY_AGENT'


class NotificationAuthPermission:
    """
    Permission checker for notification operations
    """

    @staticmethod
    async def can_receive_notifications(user: User) -> bool:
        """Check if user can receive notifications"""
        return user.is_authenticated

    @staticmethod
    async def can_modify_notification(user: User, notification) -> bool:
        """Check if user can modify notification"""
        return notification.user == user

    @staticmethod
    async def can_broadcast_notifications(user: User) -> bool:
        """Check if user can send broadcast notifications (admin only)"""
        return await user_is_admin(user)

    @staticmethod
    async def can_view_other_notifications(user: User) -> bool:
        """Check if user can view other users' notifications (admin only)"""
        return await user_is_admin(user)


class NotificationErrorHandler:
    """
    Centralized error handling for notifications
    """
    
    ERRORS = {
        'UNAUTHORIZED': {
            'code': 4001,
            'message': 'Unauthorized access'
        },
        'INVALID_MESSAGE': {
            'code': 4002,
            'message': 'Invalid message format'
        },
        'NOTIFICATION_NOT_FOUND': {
            'code': 4004,
            'message': 'Notification not found'
        },
        'PERMISSION_DENIED': {
            'code': 4003,
            'message': 'Permission denied'
        },
        'INTERNAL_ERROR': {
            'code': 5000,
            'message': 'Internal server error'
        },
        'TOO_MANY_REQUESTS': {
            'code': 4029,
            'message': 'Too many requests'
        },
    }

    @staticmethod
    def get_error(error_type: str, details: str = '') -> Dict[str, Any]:
        """Get error response"""
        error = NotificationErrorHandler.ERRORS.get(
            error_type,
            NotificationErrorHandler.ERRORS['INTERNAL_ERROR']
        )
        return {
            'code': error['code'],
            'message': error['message'],
            'details': details,
        }


# Rate limiting utilities

class NotificationRateLimiter:
    """
    Rate limiter for notification operations
    """
    
    # Store: {user_id: {operation: count}}
    _limits = {}
    
    LIMITS = {
        'mark_as_read': {'calls': 100, 'period': 60},  # 100 calls per minute
        'send': {'calls': 50, 'period': 60},  # 50 sends per minute
        'websocket_message': {'calls': 500, 'period': 60},  # 500 messages per minute
    }

    @staticmethod
    def is_allowed(user_id: str, operation: str) -> bool:
        """
        Check if operation is allowed for user
        
        Args:
            user_id: User identifier
            operation: Operation name
        
        Returns:
            True if allowed, False otherwise
        """
        import time
        
        now = time.time()
        limit = NotificationRateLimiter.LIMITS.get(operation)
        
        if not limit:
            return True

        if user_id not in NotificationRateLimiter._limits:
            NotificationRateLimiter._limits[user_id] = {}

        op_data = NotificationRateLimiter._limits[user_id].get(operation, {
            'count': 0,
            'reset_at': now + limit['period']
        })

        # Reset if period expired
        if now > op_data['reset_at']:
            op_data = {
                'count': 0,
                'reset_at': now + limit['period']
            }

        # Check limit
        if op_data['count'] >= limit['calls']:
            return False

        # Increment counter
        op_data['count'] += 1
        NotificationRateLimiter._limits[user_id][operation] = op_data

        return True


# Validation utilities

class NotificationValidator:
    """
    Validation utilities for notifications
    """
    
    MAX_TITLE_LENGTH = 255
    MAX_MESSAGE_LENGTH = 5000
    MAX_DESCRIPTION_LENGTH = 10000
    
    VALID_PRIORITIES = ['low', 'normal', 'high', 'urgent']
    VALID_CATEGORIES = [
        'order', 'payment', 'vendor_approval', 'delivery',
        'product_update', 'system', 'promotion', 'support'
    ]

    @staticmethod
    def validate_notification_data(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate notification data
        
        Args:
            data: Notification data
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        title = data.get('title', '')
        message = data.get('message', '')
        priority = data.get('priority', 'normal')
        category = data.get('category', '')

        # Validate title
        if not title or len(title) > NotificationValidator.MAX_TITLE_LENGTH:
            return False, f"Title must be 1-{NotificationValidator.MAX_TITLE_LENGTH} characters"

        # Validate message
        if not message or len(message) > NotificationValidator.MAX_MESSAGE_LENGTH:
            return False, f"Message must be 1-{NotificationValidator.MAX_MESSAGE_LENGTH} characters"

        # Validate priority
        if priority not in NotificationValidator.VALID_PRIORITIES:
            return False, f"Invalid priority. Must be one of {NotificationValidator.VALID_PRIORITIES}"

        # Validate category
        if category and category not in NotificationValidator.VALID_CATEGORIES:
            return False, f"Invalid category. Must be one of {NotificationValidator.VALID_CATEGORIES}"

        return True, None

    @staticmethod
    def sanitize_notification_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize notification data"""
        return {
            'title': str(data.get('title', '')).strip()[:NotificationValidator.MAX_TITLE_LENGTH],
            'message': str(data.get('message', '')).strip()[:NotificationValidator.MAX_MESSAGE_LENGTH],
            'description': str(data.get('description', '')).strip()[:NotificationValidator.MAX_DESCRIPTION_LENGTH],
            'priority': data.get('priority', 'normal').lower(),
            'category': str(data.get('category', '')).lower().strip(),
            'action_url': str(data.get('action_url', '')).strip(),
            'action_text': str(data.get('action_text', '')).strip()[:100],
        }
