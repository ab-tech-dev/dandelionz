# Django Channels Real-Time Notification System - Complete Implementation Guide

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [System Components](#system-components)
4. [Installation & Setup](#installation--setup)
5. [Database Models](#database-models)
6. [WebSocket Consumer Implementation](#websocket-consumer-implementation)
7. [Notification Service Layer](#notification-service-layer)
8. [API Views & Serializers](#api-views--serializers)
9. [Frontend Integration](#frontend-integration)
10. [Usage Examples](#usage-examples)
11. [Best Practices](#best-practices)

---

## Overview

This document explains a **production-ready real-time notification system** built with Django Channels, WebSockets, and Celery. The system supports:

- **Real-time delivery** via WebSocket connections
- **Multi-channel delivery** (WebSocket, Email, Push notifications)
- **Persistent storage** with database tracking
- **User preferences** and notification filtering
- **Audit logging** of all notification events
- **Bulk operations** for broadcasting to multiple users
- **Priority-based** notification management
- **Graceful degradation** when connections fail

### Key Features
✅ JWT-based WebSocket authentication  
✅ Automatic group-based routing (admin, vendor, customer)  
✅ Heartbeat mechanism for connection monitoring  
✅ Comprehensive error handling and logging  
✅ Notification status tracking  
✅ Message acknowledgment system  
✅ Batch notification delivery  
✅ Soft deletes and archiving  

---

## Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLIENT APPLICATIONS                          │
│  (Web Browser, Mobile App, Desktop Client)                       │
└──────────────────────┬──────────────────────────────────────────┘
                       │ WebSocket Connection (ws/wss)
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                   DJANGO ASGI SERVER                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  AllowedHostsOriginValidator                               │ │
│  │     ↓                                                        │ │
│  │  JwtAuthMiddleware (JWT Token Validation)                  │ │
│  │     ↓                                                        │ │
│  │  URLRouter (ws/notifications/)                             │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    ┌───▼────────┐ ┌───▼────────┐ ┌───▼────────┐
    │  Consumer  │ │  Consumer  │ │  Consumer  │
    │  User #1   │ │  User #2   │ │  User #N   │
    └────┬───────┘ └────┬───────┘ └────┬───────┘
         │              │              │
         └──────────────┼──────────────┘
                        │
            ┌───────────▼────────────┐
            │  CHANNEL LAYER         │
            │  (Redis Backend)       │
            │  ┌──────────────────┐  │
            │  │ Group: user_*    │  │
            │  │ Group: admin_*   │  │
            │  │ Group: vendor_*  │  │
            │  │ Group: customer_*│  │
            │  └──────────────────┘  │
            └───────────┬────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
    ┌───▼──────┐   ┌───▼──────┐   ┌───▼─────────┐
    │ Django   │   │  Celery  │   │ Notification│
    │ Database │   │  Worker  │   │ Service     │
    │          │   │ (Tasks)  │   │             │
    └──────────┘   └──────────┘   └─────────────┘
```

### Message Flow

```
1. Trigger Event
   └─► Order Created, Payment Received, etc.

2. Create Notification
   └─► NotificationService.create_notification()
       ├─► Create DB record
       ├─► Send WebSocket (sync)
       ├─► Queue Email (async - Celery)
       └─► Queue Push (async - Celery)

3. WebSocket Delivery
   └─► Get user's group: user_{user_id}
       └─► channel_layer.group_send()
           └─► Consumer.send_notification()
               └─► client.send_json(notification_data)

4. Email Delivery (Async)
   └─► Celery Task: send_notification_email.delay()
       └─► Render Template
           └─► Send Email
               └─► Log Event

5. Frontend Receives
   └─► Parse JSON
       └─► Update UI
           └─► Show Toast/Badge
               └─► Send ACK back (optional)
```

---

## System Components

### 1. **Channel Layer** (Redis)
- Message broker for WebSocket communication
- Stores group memberships
- Facilitates inter-process communication

### 2. **Django Channels Consumer**
- Handles WebSocket lifecycle
- Manages group subscriptions
- Processes incoming messages
- Sends notifications to clients

### 3. **Notification Service**
- Business logic for notification operations
- Creates, updates, and deletes notifications
- Manages multi-channel delivery
- Handles broadcast operations

### 4. **Celery Workers**
- Asynchronous task processing
- Email delivery
- Batch operations
- Scheduled maintenance tasks

### 5. **Database Models**
- Notification: Core notification data
- NotificationType: Categorization
- NotificationPreference: User settings
- NotificationLog: Audit trail

### 6. **REST API**
- HTTP endpoints for notification management
- Integration with Django REST Framework
- Custom actions for bulk operations
- Statistics and analytics

---

## Installation & Setup

### 1. Install Required Packages

```bash
pip install channels channels-redis daphne celery redis
```

### 2. Update Django Settings

```python
# e_commerce_api/settings.py

INSTALLED_APPS = [
    "channels",  # Must be before other apps
    "daphne",
    # ... other apps
]

# Channels Configuration
ASGI_APPLICATION = "e_commerce_api.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],  # Redis connection
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'

# Notification Settings
NOTIFICATION_EMAIL_FROM = os.getenv('NOTIFICATION_EMAIL_FROM', 'noreply@example.com')
```

### 3. Create ASGI Application

```python
# e_commerce_api/asgi.py

import os
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

import users
from users.notification_auth import JwtAuthMiddleware

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e_commerce_api.settings')

django_asgi_app = get_asgi_application()

# WebSocket URL patterns
ws_urlpatterns = users.routing.websocket_urlpatterns

# ASGI application configuration
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
```

### 4. WebSocket URL Routing

```python
# users/routing.py

from users.consumer import NotificationConsumer
from django.urls import re_path

websocket_urlpatterns = [
    re_path(r'ws/notifications/$', NotificationConsumer.as_asgi()),
]
```

### 5. Running the Application

```bash
# Terminal 1: Redis server
redis-server

# Terminal 2: ASGI server (Daphne)
daphne -b 0.0.0.0 -p 8000 e_commerce_api.asgi:application

# Terminal 3: Celery worker
celery -A e_commerce_api worker -l info

# Terminal 4: Celery Beat (for scheduled tasks)
celery -A e_commerce_api beat -l info
```

### 6. Using Docker Compose

```yaml
# docker-compose.yml

version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  web:
    build: .
    command: daphne -b 0.0.0.0 -p 8000 e_commerce_api.asgi:application
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CHANNEL_LAYERS_BACKEND=channels_redis.core.RedisChannelLayer

  celery:
    build: .
    command: celery -A e_commerce_api worker -l info
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0

  celery-beat:
    build: .
    command: celery -A e_commerce_api beat -l info
    depends_on:
      - redis
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0

volumes:
  redis_data:
```

---

## Database Models

### Notification Model

```python
# users/notification_models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

User = settings.AUTH_USER_MODEL


class NotificationType(models.Model):
    """Categorize notifications"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)  # emoji or icon name
    color = models.CharField(max_length=7, default="#000000")  # hex color
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notification_types'
        ordering = ['display_name']

    def __str__(self):
        return self.display_name


class Notification(models.Model):
    """Core notification model"""
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='notifications',
        db_index=True
    )
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    
    # Content
    title = models.CharField(max_length=255)
    message = models.TextField()
    description = models.TextField(blank=True)
    
    # Metadata
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
        db_index=True
    )
    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="e.g., 'order', 'payment', 'vendor_approval'"
    )
    
    # Action
    action_url = models.URLField(blank=True, null=True)
    action_text = models.CharField(max_length=100, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    
    # Related object
    related_object_type = models.CharField(max_length=50, blank=True)
    related_object_id = models.CharField(max_length=100, blank=True)
    
    # Additional data
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Delivery tracking
    was_sent_websocket = models.BooleanField(default=False)
    was_sent_email = models.BooleanField(default=False)
    was_sent_push = models.BooleanField(default=False)
    send_attempts = models.IntegerField(default=0)

    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['user', 'is_read', 'is_deleted', '-created_at']),
            models.Index(fields=['user', 'category', '-created_at']),
            models.Index(fields=['is_read', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.email}"

    def to_dict(self):
        """Convert to dictionary for WebSocket transmission"""
        return {
            'id': str(self.id),
            'title': self.title,
            'message': self.message,
            'description': self.description,
            'priority': self.priority,
            'category': self.category,
            'action_url': self.action_url,
            'action_text': self.action_text,
            'is_read': self.is_read,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'notification_type': {
                'name': self.notification_type.name,
                'display_name': self.notification_type.display_name,
                'icon': self.notification_type.icon,
                'color': self.notification_type.color,
            } if self.notification_type else None,
        }

    def mark_as_read(self):
        """Mark as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_unread(self):
        """Mark as unread"""
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at'])


class NotificationPreference(models.Model):
    """User preferences for notifications"""
    FREQUENCY_CHOICES = [
        ('instant', 'Instant'),
        ('daily', 'Daily Digest'),
        ('weekly', 'Weekly Digest'),
    ]

    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='notification_preferences'
    )
    
    # Channel preferences
    enable_websocket = models.BooleanField(default=True)
    enable_email = models.BooleanField(default=True)
    enable_push = models.BooleanField(default=False)
    
    # Frequency
    email_frequency = models.CharField(
        max_length=20, 
        choices=FREQUENCY_CHOICES, 
        default='instant'
    )
    
    # Categories to subscribe to
    subscribed_categories = models.JSONField(
        default=list,
        help_text="Categories to receive notifications for"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences for {self.user.email}"


class NotificationLog(models.Model):
    """Audit trail for notifications"""
    EVENT_TYPES = [
        ('created', 'Created'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    ]

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='logs'
    )
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    channel = models.CharField(
        max_length=20,
        choices=[
            ('websocket', 'WebSocket'),
            ('email', 'Email'),
            ('push', 'Push'),
        ]
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('failed', 'Failed'),
        ]
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} - {self.channel} - {self.status}"
```

### Database Schema

```sql
CREATE TABLE notification_types (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    color VARCHAR(7) DEFAULT '#000000',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP AUTO_NOW_ADD,
    updated_at TIMESTAMP AUTO_NOW
);

CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth_user(id),
    notification_type_id UUID REFERENCES notification_types(id),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    description TEXT,
    priority VARCHAR(10) DEFAULT 'normal',
    category VARCHAR(50),
    action_url VARCHAR(255),
    action_text VARCHAR(100),
    is_read BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    related_object_type VARCHAR(50),
    related_object_id VARCHAR(100),
    metadata JSON,
    created_at TIMESTAMP AUTO_NOW_ADD,
    read_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    updated_at TIMESTAMP AUTO_NOW,
    was_sent_websocket BOOLEAN DEFAULT FALSE,
    was_sent_email BOOLEAN DEFAULT FALSE,
    was_sent_push BOOLEAN DEFAULT FALSE,
    send_attempts INT DEFAULT 0,
    INDEX idx_user_read_deleted (user_id, is_read, is_deleted, created_at DESC),
    INDEX idx_user_category (user_id, category, created_at DESC),
    INDEX idx_read_created (is_read, created_at)
);

CREATE TABLE notification_preferences (
    id UUID PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL REFERENCES auth_user(id),
    enable_websocket BOOLEAN DEFAULT TRUE,
    enable_email BOOLEAN DEFAULT TRUE,
    enable_push BOOLEAN DEFAULT FALSE,
    email_frequency VARCHAR(20) DEFAULT 'instant',
    subscribed_categories JSON,
    created_at TIMESTAMP AUTO_NOW_ADD,
    updated_at TIMESTAMP AUTO_NOW
);

CREATE TABLE notification_logs (
    id UUID PRIMARY KEY,
    notification_id UUID NOT NULL REFERENCES notifications(id),
    event_type VARCHAR(20) NOT NULL,
    channel VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP AUTO_NOW_ADD,
    INDEX idx_notification_created (notification_id, created_at DESC)
);
```

---

## WebSocket Consumer Implementation

### Authentication Middleware

```python
# users/notification_auth.py

import logging
from typing import Optional
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
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
        token: JWT access token from query string
    
    Returns:
        User instance or None if invalid
    """
    try:
        if not token:
            return None
        
        access_token = AccessToken(token)
        user_id = access_token['user_uuid']  # Adjust based on your token structure
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
    Custom JWT authentication middleware for WebSocket
    
    Supports both:
    1. Django session authentication
    2. JWT token from query string: ?token=xxx
    3. Bearer token from Authorization header
    """

    async def __call__(self, scope, receive, send):
        """Process WebSocket connection with JWT auth"""
        close_old_connections()
        
        # Try Django session auth first (development)
        if 'user' in scope and scope['user'].is_authenticated:
            return await super().__call__(scope, receive, send)
        
        # Extract token from query string
        query_string = scope.get('query_string', b'').decode()
        token = None
        
        # Parse query params: ?token=xxx
        if 'token=' in query_string:
            try:
                token = query_string.split('token=')[1].split('&')[0]
            except IndexError:
                pass
        
        # Try Authorization header as fallback
        if not token:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
        
        # Get user from token
        if token:
            user = await get_user(token)
            scope['user'] = user if user else AnonymousUser()
        else:
            scope['user'] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)
```

### WebSocket Consumer

```python
# users/consumer.py

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from .notification_models import Notification, NotificationPreference, NotificationLog
from django.utils import timezone

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    Real-time notification consumer with:
    - JWT authentication
    - Group-based routing (admin, vendor, customer)
    - Heartbeat monitoring
    - Message acknowledgment
    - Comprehensive error handling
    """
    
    HEARTBEAT_INTERVAL = 30  # seconds
    MAX_MESSAGE_SIZE = 10240  # 10 KB
    
    async def connect(self):
        """Handle WebSocket connection"""
        try:
            self.user = self.scope["user"]
            self.groups = []
            self.heartbeat_task = None
            
            # Validate authentication
            if not self.user.is_authenticated:
                await self.close(code=4001, reason="Unauthenticated")
                logger.warning(f"Unauthorized connection: {self.scope.get('client')}")
                return
            
            # Assign user to groups based on role
            await self._assign_user_groups()
            
            # Accept connection
            await self.accept()
            logger.info(f"User {self.user.email} connected to notifications")
            
            # Send connection confirmation
            await self.send_json({
                'type': 'connection_established',
                'timestamp': datetime.now().isoformat(),
                'user_id': str(self.user.pk),
                'message': 'Connected to notification service'
            })
            
            # Start heartbeat task
            self.heartbeat_task = asyncio.create_task(self._send_heartbeat())
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}", exc_info=True)
            await self.close(code=4000, reason="Connection failed")

    async def disconnect(self, close_code: int):
        """Handle disconnection"""
        try:
            # Cancel heartbeat
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
            
            # Remove from groups
            for group in self.groups:
                try:
                    await self.channel_layer.group_discard(group, self.channel_name)
                except Exception as e:
                    logger.error(f"Error discarding group {group}: {str(e)}")
            
            logger.info(f"User {self.user.email} disconnected (code: {close_code})")
        except Exception as e:
            logger.error(f"Disconnection error: {str(e)}", exc_info=True)

    async def receive_json(self, content: Dict[str, Any], **kwargs):
        """
        Handle incoming messages from client
        
        Supported message types:
        - ping: Connection test
        - mark_as_read: Mark notification as read
        - mark_as_unread: Mark notification as unread
        - fetch_unread: Get unread notifications
        - fetch_recent: Get recent notifications
        - archive: Archive notification
        """
        try:
            message_type = content.get('type')
            
            if message_type == 'ping':
                # Respond to ping
                await self.send_json({
                    'type': 'pong',
                    'timestamp': datetime.now().isoformat()
                })
            
            elif message_type == 'mark_as_read':
                # Mark single notification as read
                await self._handle_mark_as_read(content)
            
            elif message_type == 'mark_as_unread':
                # Mark as unread
                await self._handle_mark_as_unread(content)
            
            elif message_type == 'fetch_unread':
                # Fetch unread notifications
                await self._handle_fetch_unread(content)
            
            elif message_type == 'fetch_recent':
                # Fetch recent notifications
                await self._handle_fetch_recent(content)
            
            elif message_type == 'archive':
                # Archive notification
                await self._handle_archive(content)
            
            else:
                logger.warning(f"Unknown message type: {message_type}")
                await self.send_json({
                    'type': 'error',
                    'message': f'Unknown message type: {message_type}'
                })
        
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
            await self.send_json({
                'type': 'error',
                'message': 'Invalid JSON format'
            })
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}", exc_info=True)
            await self.send_json({
                'type': 'error',
                'message': 'Error processing message'
            })

    # ============ Channel Layer Handlers ============

    async def send_notification(self, event: Dict[str, Any]):
        """
        Receive and send notification to client
        Called by channel_layer.group_send()
        """
        try:
            notification_data = event.get('notification')
            
            await self.send_json({
                'type': 'notification',
                'data': notification_data,
                'timestamp': datetime.now().isoformat()
            })
            
            # Log delivery
            notification_id = event.get('notification_id')
            if notification_id:
                await self._log_notification_event(
                    notification_id, 'delivered', 'websocket', 'success'
                )
        
        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}", exc_info=True)

    async def send_error(self, event: Dict[str, Any]):
        """Send error message"""
        try:
            await self.send_json({
                'type': 'error',
                'message': event.get('message'),
                'error_code': event.get('error_code', 'UNKNOWN_ERROR'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

    async def broadcast_message(self, event: Dict[str, Any]):
        """Send broadcast to all users in group"""
        try:
            await self.send_json({
                'type': 'broadcast',
                'data': event.get('message'),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error sending broadcast: {str(e)}")

    # ============ Private Helper Methods ============

    async def _assign_user_groups(self):
        """Assign user to groups based on role"""
        try:
            # Personal group for direct notifications
            personal_group = f"user_{self.user.pk}"
            await self.channel_layer.group_add(personal_group, self.channel_name)
            self.groups.append(personal_group)
            
            # Role-based group for broadcasts
            if self.user.is_authenticated:
                if self.user.is_staff or self.user.is_superuser:
                    role_group = "admin_notifications"
                else:
                    # Adjust based on your user model
                    role = getattr(self.user, 'role', 'CUSTOMER')
                    role_group = f"{role}_notifications"
                
                await self.channel_layer.group_add(role_group, self.channel_name)
                self.groups.append(role_group)
                
                logger.debug(f"User {self.user.email} added to groups: {self.groups}")
        except Exception as e:
            logger.error(f"Error assigning groups: {str(e)}", exc_info=True)
            raise

    async def _send_heartbeat(self):
        """Send periodic heartbeat to keep connection alive"""
        try:
            while True:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                try:
                    await self.send_json({
                        'type': 'heartbeat',
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.warning(f"Failed to send heartbeat: {str(e)}")
                    break
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Heartbeat error: {str(e)}", exc_info=True)

    async def _handle_mark_as_read(self, content: Dict[str, Any]):
        """Handle mark as read"""
        try:
            notification_id = content.get('notification_id')
            if notification_id:
                notification = await self._get_notification(notification_id)
                if notification and notification.user_id == self.user.pk:
                    await self._mark_notification_as_read(notification_id)
                    await self.send_json({
                        'type': 'notification_read',
                        'notification_id': notification_id,
                        'success': True
                    })
                else:
                    await self.send_json({
                        'type': 'error',
                        'message': 'Notification not found'
                    })
        except Exception as e:
            logger.error(f"Error marking as read: {str(e)}")
            await self.send_json({'type': 'error', 'message': str(e)})

    async def _handle_mark_as_unread(self, content: Dict[str, Any]):
        """Handle mark as unread"""
        try:
            notification_id = content.get('notification_id')
            if notification_id:
                notification = await self._get_notification(notification_id)
                if notification and notification.user_id == self.user.pk:
                    await self._mark_notification_as_unread(notification_id)
                    await self.send_json({
                        'type': 'notification_unread',
                        'notification_id': notification_id,
                        'success': True
                    })
        except Exception as e:
            logger.error(f"Error marking as unread: {str(e)}")

    async def _handle_fetch_unread(self, content: Dict[str, Any]):
        """Fetch unread notifications"""
        try:
            limit = min(content.get('limit', 20), 100)
            notifications = await self._get_unread_notifications(limit)
            await self.send_json({
                'type': 'unread_notifications',
                'count': len(notifications),
                'notifications': notifications
            })
        except Exception as e:
            logger.error(f"Error fetching unread: {str(e)}")

    async def _handle_fetch_recent(self, content: Dict[str, Any]):
        """Fetch recent notifications"""
        try:
            limit = min(content.get('limit', 20), 100)
            notifications = await self._get_recent_notifications(limit)
            await self.send_json({
                'type': 'recent_notifications',
                'count': len(notifications),
                'notifications': notifications
            })
        except Exception as e:
            logger.error(f"Error fetching recent: {str(e)}")

    async def _handle_archive(self, content: Dict[str, Any]):
        """Archive notification"""
        try:
            notification_id = content.get('notification_id')
            if notification_id:
                notification = await self._get_notification(notification_id)
                if notification and notification.user_id == self.user.pk:
                    await self._archive_notification(notification_id)
                    await self.send_json({
                        'type': 'notification_archived',
                        'notification_id': notification_id,
                        'success': True
                    })
        except Exception as e:
            logger.error(f"Error archiving notification: {str(e)}")

    @database_sync_to_async
    def _get_notification(self, notification_id: str) -> Optional[Notification]:
        """Get notification from DB"""
        try:
            return Notification.objects.get(id=notification_id, is_deleted=False)
        except Notification.DoesNotExist:
            return None

    @database_sync_to_async
    def _mark_notification_as_read(self, notification_id: str):
        """Update notification status"""
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_read()

    @database_sync_to_async
    def _mark_notification_as_unread(self, notification_id: str):
        """Unmark notification"""
        notification = Notification.objects.get(id=notification_id)
        notification.mark_as_unread()

    @database_sync_to_async
    def _archive_notification(self, notification_id: str):
        """Archive notification"""
        notification = Notification.objects.get(id=notification_id)
        notification.archive()

    @database_sync_to_async
    def _get_unread_notifications(self, limit: int) -> list:
        """Get unread notifications"""
        notifications = Notification.objects.filter(
            user_id=self.user.pk,
            is_read=False,
            is_deleted=False
        ).values(
            'id', 'title', 'message', 'priority', 'category',
            'created_at', 'action_url', 'action_text'
        )[:limit]
        return list(notifications)

    @database_sync_to_async
    def _get_recent_notifications(self, limit: int) -> list:
        """Get recent notifications"""
        notifications = Notification.objects.filter(
            user_id=self.user.pk,
            is_deleted=False
        ).values(
            'id', 'title', 'message', 'priority', 'category',
            'is_read', 'created_at', 'action_url', 'action_text'
        )[:limit]
        return list(notifications)

    @database_sync_to_async
    def _log_notification_event(self, notification_id: str, event_type: str, channel: str, status: str):
        """Log notification event"""
        try:
            notification = Notification.objects.get(id=notification_id)
            NotificationLog.objects.create(
                notification=notification,
                event_type=event_type,
                channel=channel,
                status=status
            )
        except Exception as e:
            logger.error(f"Error logging event: {str(e)}")
```

---

## Notification Service Layer

### Main Service

```python
# users/notification_service.py

import logging
from typing import List, Dict, Any, Optional
from django.db.models import Q, Count
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta
import uuid

from .notification_models import (
    Notification, NotificationType, NotificationPreference, NotificationLog
)
from django.conf import settings

User = settings.AUTH_USER_MODEL
logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


class NotificationService:
    """Core service for managing notifications"""

    @staticmethod
    def create_notification(
        user: User,
        title: str,
        message: str,
        notification_type: Optional[NotificationType] = None,
        category: str = '',
        priority: str = 'normal',
        description: str = '',
        action_url: str = '',
        action_text: str = '',
        metadata: Dict[str, Any] = None,
        related_object_type: str = '',
        related_object_id: str = '',
        expires_at: Optional[timezone.datetime] = None,
        send_websocket: bool = True,
        send_email: bool = False,
        send_push: bool = False,
    ) -> Optional[Notification]:
        """
        Create and send notification
        
        Args:
            user: Target user
            title: Notification title
            message: Main message
            notification_type: NotificationType instance
            category: Category for filtering (order, payment, etc.)
            priority: low, normal, high, urgent
            description: Detailed description
            action_url: Deep link for action
            action_text: Button text
            metadata: Additional JSON data
            related_object_type: Related resource type
            related_object_id: Related resource ID
            expires_at: Auto-delete timestamp
            send_websocket: Send via WebSocket
            send_email: Send via email
            send_push: Send via push notification
        
        Returns:
            Created Notification or None
        """
        try:
            if metadata is None:
                metadata = {}

            # Create notification record
            notification = Notification.objects.create(
                user=user,
                title=title,
                message=message,
                notification_type=notification_type,
                category=category,
                priority=priority,
                description=description,
                action_url=action_url,
                action_text=action_text,
                metadata=metadata,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                expires_at=expires_at,
            )

            # Log creation
            NotificationLog.objects.create(
                notification=notification,
                event_type='created',
                status='success',
                channel='websocket'
            )

            # Send through different channels
            if send_websocket:
                NotificationService.send_websocket_notification(notification)
            
            if send_email:
                NotificationService.send_email_notification(notification)
            
            if send_push:
                NotificationService.send_push_notification(notification)

            logger.info(f"Notification {notification.id} created for user {user.email}")
            return notification

        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def send_websocket_notification(notification: Notification) -> bool:
        """
        Send notification via WebSocket in real-time
        
        Args:
            notification: Notification instance
        
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Get user's personal group
            group_name = f"user_{notification.user.pk}"
            
            # Prepare notification data
            notification_data = notification.to_dict()
            
            # Send through channel layer
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'notification': notification_data,
                    'notification_id': str(notification.id),
                }
            )

            # Update flag
            notification.was_sent_websocket = True
            notification.save(update_fields=['was_sent_websocket'])

            # Log
            NotificationLog.objects.create(
                notification=notification,
                event_type='sent',
                channel='websocket',
                status='success'
            )

            logger.debug(f"Notification {notification.id} sent via WebSocket")
            return True

        except Exception as e:
            logger.error(f"Error sending WebSocket notification: {str(e)}", exc_info=True)
            NotificationLog.objects.create(
                notification=notification,
                event_type='sent',
                channel='websocket',
                status='failed',
                error_message=str(e)
            )
            return False

    @staticmethod
    def send_email_notification(notification: Notification) -> bool:
        """Send notification via email (async via Celery)"""
        try:
            from users.notification_tasks import send_notification_email
            
            # Queue async task
            send_notification_email.delay(str(notification.id))
            
            notification.was_sent_email = True
            notification.save(update_fields=['was_sent_email'])

            logger.debug(f"Email notification {notification.id} queued")
            return True

        except Exception as e:
            logger.error(f"Error queuing email: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def send_push_notification(notification: Notification) -> bool:
        """Send push notification (FCM/APNs integration placeholder)"""
        try:
            # TODO: Implement FCM or APNs integration
            logger.debug(f"Push notification {notification.id} would be sent")
            return False
        except Exception as e:
            logger.error(f"Error sending push: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def broadcast_notification(
        title: str,
        message: str,
        notification_type: Optional[NotificationType] = None,
        group_filter: Optional[str] = None,
        **kwargs
    ) -> int:
        """
        Send notification to multiple users
        
        Args:
            title: Notification title
            message: Message text
            notification_type: NotificationType
            group_filter: 'admin', 'vendor', 'customer'
            **kwargs: Additional notification args
        
        Returns:
            Number of notifications created
        """
        try:
            # Determine target users
            if group_filter == 'admin':
                users = User.objects.filter(is_staff=True)
            elif group_filter == 'vendor':
                users = User.objects.filter(role='VENDOR')
            elif group_filter == 'customer':
                users = User.objects.filter(role='CUSTOMER')
            else:
                users = User.objects.filter(is_active=True)

            count = 0
            for user in users:
                if NotificationService.create_notification(
                    user=user,
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    **kwargs
                ):
                    count += 1

            logger.info(f"Broadcast sent to {count} users")
            return count

        except Exception as e:
            logger.error(f"Error in broadcast: {str(e)}", exc_info=True)
            return 0

    @staticmethod
    def get_user_notifications(
        user: User,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[Notification], int]:
        """
        Fetch user notifications with filtering
        
        Args:
            user: Target user
            filters: Filter dict (is_read, category, priority, is_archived)
            limit: Pagination limit
            offset: Pagination offset
        
        Returns:
            Tuple of (notifications, total_count)
        """
        try:
            query = Notification.objects.filter(
                user=user,
                is_deleted=False
            )

            if filters:
                if 'is_read' in filters:
                    query = query.filter(is_read=filters['is_read'])
                if 'category' in filters:
                    query = query.filter(category=filters['category'])
                if 'priority' in filters:
                    query = query.filter(priority=filters['priority'])
                if 'is_archived' in filters:
                    query = query.filter(is_archived=filters['is_archived'])

            total_count = query.count()
            notifications = query[offset:offset + limit]

            return list(notifications), total_count

        except Exception as e:
            logger.error(f"Error fetching notifications: {str(e)}", exc_info=True)
            return [], 0

    @staticmethod
    def get_unread_count(user: User) -> int:
        """Get unread notification count"""
        try:
            return Notification.objects.filter(
                user=user,
                is_read=False,
                is_deleted=False
            ).count()
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            return 0

    @staticmethod
    def mark_as_read(user: User, notification_id: str) -> bool:
        """Mark notification as read"""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=user
            )
            notification.mark_as_read()

            NotificationLog.objects.create(
                notification=notification,
                event_type='read',
                status='success'
            )

            return True
        except Exception as e:
            logger.error(f"Error marking as read: {str(e)}")
            return False

    @staticmethod
    def get_stats(user: User) -> Dict[str, Any]:
        """Get notification statistics for user"""
        try:
            base_query = Notification.objects.filter(
                user=user,
                is_deleted=False
            )

            total = base_query.count()
            unread = base_query.filter(is_read=False).count()
            read = base_query.filter(is_read=True).count()
            archived = base_query.filter(is_archived=True).count()

            return {
                'total_notifications': total,
                'unread_count': unread,
                'read_count': read,
                'archived_count': archived,
            }

        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {}

    @staticmethod
    def cleanup_expired_notifications() -> int:
        """Remove expired notifications"""
        try:
            now = timezone.now()
            expired = Notification.objects.filter(
                expires_at__lt=now,
                is_deleted=False
            )
            count, _ = expired.delete()
            logger.info(f"Cleaned up {count} expired notifications")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up: {str(e)}")
            return 0


class BulkNotificationService:
    """Service for bulk notification operations"""

    @staticmethod
    def create_bulk_notifications(
        user_ids: List[str],
        title: str,
        message: str,
        **kwargs
    ) -> int:
        """Create notifications for multiple users"""
        try:
            users = User.objects.filter(pk__in=user_ids)
            count = 0

            for user in users:
                if NotificationService.create_notification(
                    user=user,
                    title=title,
                    message=message,
                    **kwargs
                ):
                    count += 1

            return count
        except Exception as e:
            logger.error(f"Error in bulk create: {str(e)}")
            return 0

    @staticmethod
    def mark_bulk_as_read(user: User, notification_ids: List[str]) -> int:
        """Mark multiple notifications as read"""
        try:
            notifications = Notification.objects.filter(
                user=user,
                id__in=notification_ids,
                is_deleted=False
            )
            count = notifications.count()
            now = timezone.now()
            notifications.update(is_read=True, read_at=now)

            return count
        except Exception as e:
            logger.error(f"Error in bulk mark as read: {str(e)}")
            return 0

    @staticmethod
    def delete_bulk_notifications(user: User, notification_ids: List[str]) -> int:
        """Soft delete multiple notifications"""
        try:
            notifications = Notification.objects.filter(
                user=user,
                id__in=notification_ids
            )
            count = notifications.count()
            notifications.update(is_deleted=True)

            return count
        except Exception as e:
            logger.error(f"Error in bulk delete: {str(e)}")
            return 0
```

### Celery Tasks

```python
# users/notification_tasks.py

from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

from .notification_models import Notification, NotificationLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_notification_email(self, notification_id: str):
    """
    Send notification via email asynchronously
    
    Args:
        notification_id: UUID of notification
    """
    try:
        notification = Notification.objects.get(id=notification_id)
        user = notification.user
        
        if not notification.was_sent_email:
            # Prepare email context
            context = {
                'user_name': getattr(user, 'first_name', user.email.split('@')[0]),
                'title': notification.title,
                'message': notification.message,
                'description': notification.description,
                'action_url': notification.action_url,
                'action_text': notification.action_text,
                'priority': notification.priority,
                'created_at': notification.created_at,
            }

            # Render HTML template
            html_message = render_to_string(
                'emails/notification_email.html',
                context
            )

            # Send email
            send_mail(
                subject=f"[{notification.priority.upper()}] {notification.title}",
                message=notification.message,
                from_email=settings.NOTIFICATION_EMAIL_FROM,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False,
            )

            # Update notification
            notification.was_sent_email = True
            notification.send_attempts += 1
            notification.save(update_fields=['was_sent_email', 'send_attempts'])

            # Log success
            NotificationLog.objects.create(
                notification=notification,
                event_type='sent',
                channel='email',
                status='success'
            )

            logger.info(f"Email sent for notification {notification_id}")

    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
    except Exception as exc:
        logger.error(f"Error sending email: {str(exc)}", exc_info=True)
        
        # Retry with exponential backoff
        try:
            self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            # Log final failure
            try:
                notification = Notification.objects.get(id=notification_id)
                NotificationLog.objects.create(
                    notification=notification,
                    event_type='sent',
                    channel='email',
                    status='failed',
                    error_message=str(exc)
                )
            except:
                pass


@shared_task
def cleanup_expired_notifications():
    """
    Periodic task to clean up expired notifications
    Scheduled via Celery Beat (every 24 hours)
    """
    try:
        from .notification_service import NotificationService
        
        count = NotificationService.cleanup_expired_notifications()
        logger.info(f"Cleanup completed: removed {count} expired notifications")
        
        return {
            'status': 'success',
            'cleaned_up': count
        }
    except Exception as e:
        logger.error(f"Error in cleanup: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task
def send_batch_notifications(notification_ids: list):
    """
    Send multiple notifications asynchronously
    
    Args:
        notification_ids: List of notification UUIDs
    """
    try:
        from .notification_service import NotificationService
        
        count = 0
        errors = []
        
        for notification_id in notification_ids:
            try:
                notification = Notification.objects.get(id=notification_id)
                if NotificationService.send_websocket_notification(notification):
                    count += 1
            except Exception as e:
                logger.error(f"Error sending {notification_id}: {str(e)}")
                errors.append({
                    'notification_id': notification_id,
                    'error': str(e)
                })
        
        logger.info(f"Batch send: {count} sent, {len(errors)} failed")
        
        return {
            'sent': count,
            'failed': len(errors),
            'errors': errors
        }
    except Exception as e:
        logger.error(f"Error in batch send: {str(e)}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e)
        }
```

### Celery Beat Configuration

```python
# e_commerce_api/settings.py

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-notifications': {
        'task': 'users.notification_tasks.cleanup_expired_notifications',
        'schedule': crontab(hour=0, minute=0),  # Run at midnight daily
    },
}
```

---

## API Views & Serializers

### Serializers

```python
# users/notification_serializers.py

from rest_framework import serializers
from .notification_models import Notification, NotificationType, NotificationPreference
from django.conf import settings

User = settings.AUTH_USER_MODEL


class NotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationType
        fields = ['id', 'name', 'display_name', 'description', 'icon', 'color', 'is_active']
        read_only_fields = ['id', 'created_at', 'updated_at']


class NotificationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for lists"""
    notification_type_display = serializers.CharField(
        source='notification_type.display_name',
        read_only=True
    )
    notification_type_icon = serializers.CharField(
        source='notification_type.icon',
        read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'priority', 'category',
            'is_read', 'is_archived', 'created_at', 'read_at',
            'notification_type_display', 'notification_type_icon',
            'action_url', 'action_text'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'read_at', 'updated_at'
        ]


class NotificationDetailSerializer(serializers.ModelSerializer):
    """Full details"""
    notification_type = NotificationTypeSerializer(read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'user_email', 'notification_type', 'title', 'message',
            'description', 'priority', 'category', 'action_url', 'action_text',
            'is_read', 'is_archived', 'is_deleted', 'metadata',
            'related_object_type', 'related_object_id',
            'was_sent_websocket', 'was_sent_email', 'was_sent_push',
            'created_at', 'read_at', 'expires_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'user', 'created_at', 'updated_at', 'read_at',
            'was_sent_websocket', 'was_sent_email', 'was_sent_push'
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'user', 'enable_websocket', 'enable_email', 'enable_push',
            'email_frequency', 'subscribed_categories'
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class NotificationStatsSerializer(serializers.Serializer):
    """Notification statistics"""
    total_notifications = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    archived_count = serializers.IntegerField()
```

### ViewSets

```python
# users/notification_views.py (excerpt)

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .notification_models import Notification
from .notification_serializers import NotificationListSerializer, NotificationDetailSerializer
from .notification_service import NotificationService


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class NotificationViewSet(viewsets.ModelViewSet):
    """
    NotificationViewSet - API endpoints for notifications
    
    GET    /api/notifications/              - List user's notifications
    GET    /api/notifications/{id}/         - Get notification details
    DELETE /api/notifications/{id}/         - Delete notification
    POST   /api/notifications/mark_as_read/ - Mark as read
    POST   /api/notifications/archive/      - Archive notification
    GET    /api/notifications/unread_count/ - Get unread count
    GET    /api/notifications/stats/        - Get statistics
    """
    
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NotificationPagination
    
    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user,
            is_deleted=False
        ).select_related('notification_type')

    def get_serializer_class(self):
        if self.action == 'list':
            return NotificationListSerializer
        return NotificationDetailSerializer

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get unread notification count"""
        try:
            count = NotificationService.get_unread_count(request.user)
            return Response({
                'unread_count': count,
                'status': 'success'
            })
        except Exception as e:
            return Response(
                {'error': 'Failed to get unread count'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get notification statistics"""
        try:
            stats = NotificationService.get_stats(request.user)
            return Response(stats)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Mark notification as read"""
        success = NotificationService.mark_as_read(request.user, pk)
        return Response({
            'success': success,
            'notification_id': pk
        })

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        """Mark all notifications as read"""
        count = NotificationService.mark_all_as_read(request.user)
        return Response({
            'marked_as_read': count
        })

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive notification"""
        success = NotificationService.archive_notification(request.user, pk)
        return Response({
            'success': success,
            'notification_id': pk
        })
```

---

## Frontend Integration

### JavaScript/React Client

```javascript
// Frontend WebSocket client example

class NotificationManager {
    constructor(token) {
        this.token = token;
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.listeners = {};
    }

    /**
     * Connect to WebSocket server
     */
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/notifications/?token=${this.token}`;

        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
            console.log('Connected to notification service');
            this.reconnectAttempts = 0;
            this.emit('connected', {});
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.emit('error', { message: 'Connection error' });
        };

        this.socket.onclose = () => {
            console.log('Disconnected from notification service');
            this.emit('disconnected', {});
            this.attemptReconnect();
        };
    }

    /**
     * Attempt to reconnect with exponential backoff
     */
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            console.log(`Reconnecting in ${delay}ms...`);
            setTimeout(() => this.connect(), delay);
        }
    }

    /**
     * Handle incoming message
     */
    handleMessage(message) {
        const type = message.type;

        switch (type) {
            case 'connection_established':
                console.log('Connection established');
                this.emit('connection_established', message);
                break;

            case 'notification':
                console.log('Received notification:', message.data);
                this.emit('notification', message.data);
                break;

            case 'heartbeat':
                // Respond to heartbeat
                this.send({ type: 'pong' });
                break;

            case 'error':
                console.error('Server error:', message.message);
                this.emit('error', message);
                break;

            case 'notification_read':
                this.emit('notification_read', message);
                break;

            case 'unread_notifications':
                this.emit('unread_notifications', message.notifications);
                break;

            default:
                console.log('Unknown message type:', type);
        }
    }

    /**
     * Send message to server
     */
    send(message) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        } else {
            console.error('WebSocket not connected');
        }
    }

    /**
     * Mark notification as read
     */
    markAsRead(notificationId) {
        this.send({
            type: 'mark_as_read',
            notification_id: notificationId
        });
    }

    /**
     * Fetch unread notifications
     */
    fetchUnread(limit = 20) {
        this.send({
            type: 'fetch_unread',
            limit: limit
        });
    }

    /**
     * Archive notification
     */
    archive(notificationId) {
        this.send({
            type: 'archive',
            notification_id: notificationId
        });
    }

    /**
     * Register event listener
     */
    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    /**
     * Emit event
     */
    emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => callback(data));
        }
    }

    /**
     * Disconnect
     */
    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }
}

// Usage Example
const notificationManager = new NotificationManager(jwtToken);

notificationManager.on('connected', () => {
    console.log('Ready to receive notifications');
});

notificationManager.on('notification', (notification) => {
    // Show toast or update UI
    showNotificationToast(notification);
});

notificationManager.on('error', (error) => {
    console.error('Notification error:', error);
});

notificationManager.connect();

// Mark notification as read when user clicks it
function handleNotificationClick(notificationId) {
    notificationManager.markAsRead(notificationId);
}

// Disconnect when user leaves the app
window.addEventListener('beforeunload', () => {
    notificationManager.disconnect();
});
```

### React Component Example

```jsx
// NotificationCenter.jsx

import React, { useEffect, useState } from 'react';
import NotificationManager from './NotificationManager';

const NotificationCenter = ({ token }) => {
    const [notifications, setNotifications] = useState([]);
    const [isConnected, setIsConnected] = useState(false);
    const [unreadCount, setUnreadCount] = useState(0);

    useEffect(() => {
        const notificationManager = new NotificationManager(token);

        // Handle connection
        notificationManager.on('connected', () => {
            setIsConnected(true);
            notificationManager.fetchUnread();
        });

        // Handle new notification
        notificationManager.on('notification', (notification) => {
            setNotifications(prev => [notification, ...prev]);
            setUnreadCount(prev => prev + 1);
            
            // Show browser notification
            if (Notification.permission === 'granted') {
                new Notification(notification.title, {
                    body: notification.message,
                    icon: '/static/logo.png'
                });
            }
        });

        // Handle disconnection
        notificationManager.on('disconnected', () => {
            setIsConnected(false);
        });

        notificationManager.connect();

        return () => notificationManager.disconnect();
    }, [token]);

    const handleMarkAsRead = (notificationId) => {
        setNotifications(prev =>
            prev.map(n =>
                n.id === notificationId ? { ...n, is_read: true } : n
            )
        );
        notificationManager.markAsRead(notificationId);
        setUnreadCount(prev => Math.max(0, prev - 1));
    };

    return (
        <div className="notification-center">
            <div className="notification-header">
                <h2>Notifications</h2>
                <span className="unread-badge">{unreadCount}</span>
                <div className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
                    {isConnected ? '●' : '○'} {isConnected ? 'Connected' : 'Disconnected'}
                </div>
            </div>
            <div className="notification-list">
                {notifications.map(notification => (
                    <div
                        key={notification.id}
                        className={`notification-item ${notification.is_read ? 'read' : 'unread'}`}
                        onClick={() => handleMarkAsRead(notification.id)}
                    >
                        <div className="notification-content">
                            <h3>{notification.title}</h3>
                            <p>{notification.message}</p>
                            <small>{new Date(notification.created_at).toLocaleString()}</small>
                        </div>
                        {notification.action_url && (
                            <a href={notification.action_url} className="notification-action">
                                {notification.action_text}
                            </a>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default NotificationCenter;
```

---

## Usage Examples

### Example 1: Order Notification

```python
# In orders/signals.py or tasks

from django.db.models.signals import post_save
from django.dispatch import receiver
from users.notification_service import NotificationService
from store.models import Order, NotificationType

@receiver(post_save, sender=Order)
def send_order_notification(sender, instance, created, **kwargs):
    """Send notification when order is created or updated"""
    if created:
        # Get or create notification type
        notif_type, _ = NotificationType.objects.get_or_create(
            name='order_created',
            defaults={
                'display_name': 'Order Created',
                'icon': '📦',
                'color': '#4CAF50'
            }
        )

        # Create notification
        NotificationService.create_notification(
            user=instance.user,
            title='Order Placed',
            message=f'Your order #{instance.id} has been placed successfully',
            description=f'Total: ₦{instance.total_amount}',
            notification_type=notif_type,
            category='order',
            priority='normal',
            action_url=f'/orders/{instance.id}/',
            action_text='View Order',
            metadata={
                'order_id': str(instance.id),
                'total_amount': float(instance.total_amount),
                'items_count': instance.items.count()
            },
            related_object_type='order',
            related_object_id=str(instance.id),
            send_websocket=True,
            send_email=True
        )
```

### Example 2: Payment Notification

```python
# In transactions/signals.py

from users.notification_service import NotificationService
from transactions.models import Payment, NotificationType

def send_payment_notification(payment):
    """Send payment notification"""
    notif_type, _ = NotificationType.objects.get_or_create(
        name='payment_received',
        defaults={
            'display_name': 'Payment Received',
            'icon': '💳',
            'color': '#2196F3'
        }
    )

    if payment.status == 'completed':
        NotificationService.create_notification(
            user=payment.user,
            title='Payment Successful',
            message=f'Payment of ₦{payment.amount} received successfully',
            notification_type=notif_type,
            category='payment',
            priority='high',
            action_url=f'/payments/{payment.id}/',
            action_text='View Receipt',
            metadata={
                'payment_id': str(payment.id),
                'amount': float(payment.amount),
                'method': payment.method
            },
            send_websocket=True,
            send_email=True
        )
```

### Example 3: Broadcast Notification

```python
# In admin views

from users.notification_service import NotificationService
from store.models import NotificationType

def send_broadcast(request):
    """Send broadcast notification to all admin users"""
    notif_type, _ = NotificationType.objects.get_or_create(
        name='admin_broadcast',
        defaults={
            'display_name': 'Admin Alert',
            'icon': '🔔',
            'color': '#FF9800'
        }
    )

    count = NotificationService.broadcast_notification(
        title='System Maintenance',
        message='System will be down for maintenance on 2024-02-15',
        notification_type=notif_type,
        category='admin',
        priority='urgent',
        group_filter='admin'  # Send only to admin users
    )

    return Response({
        'status': 'success',
        'notifications_sent': count
    })
```

### Example 4: Bulk Notifications

```python
# Notify multiple users about a promotion

from users.notification_service import BulkNotificationService
from store.models import NotificationType

def notify_users_about_promotion(promo_id, user_ids):
    """Send promotion notification to multiple users"""
    notif_type, _ = NotificationType.objects.get_or_create(
        name='promotion',
        defaults={
            'display_name': 'Special Offer',
            'icon': '🎉',
            'color': '#FF5722'
        }
    )

    count = BulkNotificationService.create_bulk_notifications(
        user_ids=user_ids,
        title='Special Promotion',
        message='Check out our latest exclusive offers!',
        notification_type=notif_type,
        category='promotion',
        priority='normal',
        action_url=f'/promotions/{promo_id}/',
        action_text='View Offer',
        send_websocket=True
    )

    return count
```

---

## Best Practices

### 1. **Error Handling & Logging**
```python
# Always use try-except and log errors
try:
    notification = NotificationService.create_notification(...)
except Exception as e:
    logger.error(f"Failed to create notification: {str(e)}", exc_info=True)
    # Gracefully handle the error
```

### 2. **Asynchronous Operations**
```python
# Use Celery for email/heavy operations
@shared_task
def send_bulk_email_notifications(notification_ids):
    # Don't block the main request
    pass
```

### 3. **Rate Limiting**
```python
# Prevent notification spam
from rest_framework.throttling import UserRateThrottle

class NotificationThrottle(UserRateThrottle):
    scope = 'notifications'
    THROTTLE_RATES = {
        'notifications': '100/hour'
    }
```

### 4. **Notification Expiration**
```python
# Set expiration for temporary notifications
from datetime import timedelta
from django.utils import timezone

expires_at = timezone.now() + timedelta(days=7)
NotificationService.create_notification(
    ...
    expires_at=expires_at
)
```

### 5. **User Preferences**
```python
# Respect user notification preferences
user_prefs = NotificationService.get_or_create_preference(user)
if user_prefs.enable_email:
    send_email = True
```

### 6. **Connection Pooling**
```python
# In settings.py for production
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
            "capacity": 10000,
            "expiry": 10,
            "connection_kwargs": {
                "max_connections": 50
            },
        },
    },
}
```

### 7. **Security**
- ✅ Always validate JWT tokens
- ✅ Check user permissions before sending
- ✅ Sanitize notification content
- ✅ Use HTTPS/WSS in production
- ✅ Implement rate limiting
- ✅ Log all notification events

### 8. **Monitoring & Metrics**
```python
# Track notification statistics
class NotificationMetrics:
    @staticmethod
    def get_delivery_rate(user):
        """Calculate notification delivery rate"""
        total = Notification.objects.filter(user=user).count()
        delivered = Notification.objects.filter(
            user=user,
            was_sent_websocket=True
        ).count()
        return (delivered / total * 100) if total > 0 else 0
```

---

## Summary

This Django Channels notification system provides:

✅ **Real-time delivery** via WebSocket  
✅ **Multi-channel support** (WebSocket, Email, Push)  
✅ **Persistent storage** with full audit trail  
✅ **JWT authentication** for secure connections  
✅ **Automatic group management** based on user roles  
✅ **Scalable architecture** using Redis & Celery  
✅ **Comprehensive error handling** and logging  
✅ **RESTful API** for HTTP operations  
✅ **Production-ready** code with best practices  

For questions or improvements, refer to the official documentation:
- [Django Channels](https://channels.readthedocs.io/)
- [Redis](https://redis.io/documentation)
- [Celery](https://docs.celeryproject.io/)
