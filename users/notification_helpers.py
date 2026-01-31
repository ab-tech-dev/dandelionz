"""
Notification Helpers - Centralized functions for sending notifications across the system.
This module replaces direct Notification.objects.create() calls with the new NotificationService.

Usage:
    from users.notification_helpers import send_order_notification, send_product_notification
    
    send_order_notification(user, "Order Confirmed", "Your order has been confirmed")
    send_product_notification(vendor, "Product Approved", "Your product has been approved")
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from django.contrib.auth import get_user_model

from e_commerce_api import settings
from .notification_service import NotificationService
from .notification_models import NotificationType

if TYPE_CHECKING:
    from authentication.models import CustomUser as User
else:
    User = get_user_model()

logger = logging.getLogger(__name__)


def send_order_notification(
    recipient: 'User',
    title: str,
    message: str,
    order_id: Optional[str] = None,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> bool:
    """
    Send order-related notification to a user.
    
    Args:
        recipient: User to receive notification
        title: Notification title
        message: Notification message
        order_id: Order ID for context (optional)
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        bool: Success status
    """
    try:
        notification_data = {
            'recipient': recipient,
            'title': title,
            'message': message,
            'send_email': send_email,
            'send_websocket': send_websocket,
        }
        
        # Add metadata
        metadata = {'order_id': order_id, **kwargs}
        notification_data['metadata'] = {k: v for k, v in metadata.items() if v is not None}
        
        if action_url:
            notification_data['action_url'] = action_url
        
        NotificationService.create_notification(**notification_data)
        return True
    except Exception as e:
        logger.error(f"Failed to send order notification to {recipient.email}: {str(e)}", exc_info=True)
        return False


def send_product_notification(
    recipient: 'User',
    title: str,
    message: str,
    product_name: Optional[str] = None,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> bool:
    """
    Send product-related notification to a vendor.
    
    Args:
        recipient: Vendor user to receive notification
        title: Notification title
        message: Notification message
        product_name: Product name for context (optional)
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        bool: Success status
    """
    try:
        notification_data = {
            'recipient': recipient,
            'title': title,
            'message': message,
            'send_email': send_email,
            'send_websocket': send_websocket,
        }
        
        # Add metadata
        metadata = {'product_name': product_name, **kwargs}
        notification_data['metadata'] = {k: v for k, v in metadata.items() if v is not None}
        
        if action_url:
            notification_data['action_url'] = action_url
        
        NotificationService.create_notification(**notification_data)
        return True
    except Exception as e:
        logger.error(f"Failed to send product notification to {recipient.email}: {str(e)}", exc_info=True)
        return False


def send_payment_notification(
    recipient: 'User',
    title: str,
    message: str,
    transaction_id: Optional[str] = None,
    amount: Optional[float] = None,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> bool:
    """
    Send payment/transaction-related notification.
    
    Args:
        recipient: User to receive notification
        title: Notification title
        message: Notification message
        transaction_id: Transaction ID for context
        amount: Transaction amount
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        bool: Success status
    """
    try:
        notification_data = {
            'recipient': recipient,
            'title': title,
            'message': message,
            'send_email': send_email,
            'send_websocket': send_websocket,
        }
        
        # Add metadata
        metadata = {
            'transaction_id': transaction_id,
            'amount': amount,
            **kwargs
        }
        notification_data['metadata'] = {k: v for k, v in metadata.items() if v is not None}
        
        if action_url:
            notification_data['action_url'] = action_url
        
        NotificationService.create_notification(**notification_data)
        return True
    except Exception as e:
        logger.error(f"Failed to send payment notification to {recipient.email}: {str(e)}", exc_info=True)
        return False


def send_delivery_notification(
    recipient: 'User',
    title: str,
    message: str,
    order_id: Optional[str] = None,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> bool:
    """
    Send delivery-related notification to delivery agent.
    
    Args:
        recipient: Delivery agent user
        title: Notification title
        message: Notification message
        order_id: Order ID for context
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        bool: Success status
    """
    try:
        notification_data = {
            'recipient': recipient,
            'title': title,
            'message': message,
            'send_email': send_email,
            'send_websocket': send_websocket,
        }
        
        # Add metadata
        metadata = {'order_id': order_id, **kwargs}
        notification_data['metadata'] = {k: v for k, v in metadata.items() if v is not None}
        
        if action_url:
            notification_data['action_url'] = action_url
        
        NotificationService.create_notification(**notification_data)
        return True
    except Exception as e:
        logger.error(f"Failed to send delivery notification to {recipient.email}: {str(e)}", exc_info=True)
        return False


def send_user_notification(
    recipient: 'User',
    title: str,
    message: str,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> bool:
    """
    Send generic user notification.
    
    Args:
        recipient: User to receive notification
        title: Notification title
        message: Notification message
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        bool: Success status
    """
    try:
        notification_data = {
            'recipient': recipient,
            'title': title,
            'message': message,
            'send_email': send_email,
            'send_websocket': send_websocket,
            'metadata': kwargs,
        }
        
        if action_url:
            notification_data['action_url'] = action_url
        
        NotificationService.create_notification(**notification_data)
        return True
    except Exception as e:
        logger.error(f"Failed to send user notification to {recipient.email}: {str(e)}", exc_info=True)
        return False


def send_bulk_notification(
    users: list,
    title: str,
    message: str,
    action_url: Optional[str] = None,
    send_email: bool = False,
    send_websocket: bool = True,
    **kwargs
) -> int:
    """
    Send notification to multiple users (for broadcasts).
    
    Args:
        users: List of User objects
        title: Notification title
        message: Notification message
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: False for bulk)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        int: Number of notifications sent successfully
    """
    try:
        sent_count = 0
        
        for user in users:
            try:
                notification_data = {
                    'recipient': user,
                    'title': title,
                    'message': message,
                    'send_email': send_email,
                    'send_websocket': send_websocket,
                    'metadata': kwargs,
                }
                
                if action_url:
                    notification_data['action_url'] = action_url
                
                NotificationService.create_notification(**notification_data)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send bulk notification to {user.email}: {str(e)}")
                continue
        
        logger.info(f"Sent bulk notification to {sent_count}/{len(users)} users")
        return sent_count
    except Exception as e:
        logger.error(f"Error in send_bulk_notification: {str(e)}", exc_info=True)
        return 0


def notify_admin(
    title: str,
    message: str,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> int:
    """
    Broadcast notification to all admins.
    
    Args:
        title: Notification title
        message: Notification message
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        int: Number of admins notified
    """
    try:
        admin_users = User.objects.filter(role='admin', is_active=True)
        return send_bulk_notification(
            list(admin_users),
            title,
            message,
            action_url=action_url,
            send_email=send_email,
            send_websocket=send_websocket,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Error notifying admins: {str(e)}", exc_info=True)
        return 0


def notify_all_users(
    title: str,
    message: str,
    action_url: Optional[str] = None,
    send_email: bool = False,
    send_websocket: bool = True,
    **kwargs
) -> int:
    """
    Broadcast notification to all active users.
    
    Args:
        title: Notification title
        message: Notification message
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: False for large broadcasts)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        int: Number of users notified
    """
    try:
        all_users = User.objects.filter(is_active=True, status='ACTIVE')
        return send_bulk_notification(
            list(all_users),
            title,
            message,
            action_url=action_url,
            send_email=send_email,
            send_websocket=send_websocket,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Error notifying all users: {str(e)}", exc_info=True)
        return 0


def notify_all_vendors(
    title: str,
    message: str,
    action_url: Optional[str] = None,
    send_email: bool = True,
    send_websocket: bool = True,
    **kwargs
) -> int:
    """
    Broadcast notification to all vendors.
    
    Args:
        title: Notification title
        message: Notification message
        action_url: URL to navigate to (optional)
        send_email: Send via email (default: True)
        send_websocket: Send via WebSocket (default: True)
        **kwargs: Additional metadata
        
    Returns:
        int: Number of vendors notified
    """
    try:
        from store.models import Vendor
        
        vendor_users = User.objects.filter(
            uuid__in=Vendor.objects.filter(
                vendor_status='approved'
            ).values_list('user_id', flat=True),
            is_active=True,
            status='ACTIVE'
        )
        
        return send_bulk_notification(
            list(vendor_users),
            title,
            message,
            action_url=action_url,
            send_email=send_email,
            send_websocket=send_websocket,
            **kwargs
        )
    except Exception as e:
        logger.error(f"Error notifying vendors: {str(e)}", exc_info=True)
        return 0
