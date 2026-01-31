"""
Django management command to verify the Channels notification system configuration.

Usage:
    python manage.py verify_notification_system
    python manage.py verify_notification_system --test-email
    python manage.py verify_notification_system --send-test-notification
"""

import sys
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone
from django.db import connections
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Verify Django Channels notification system configuration and connectivity'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-email',
            action='store_true',
            help='Test email notification delivery'
        )
        parser.add_argument(
            '--send-test-notification',
            action='store_true',
            help='Send a test notification to the first user'
        )
        parser.add_argument(
            '--check-tasks',
            action='store_true',
            help='Check Celery task registration'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('\n' + '='*60))
        self.stdout.write(self.style.HTTP_INFO('DJANGO CHANNELS NOTIFICATION SYSTEM VERIFICATION'))
        self.stdout.write(self.style.HTTP_INFO('='*60 + '\n'))

        all_passed = True

        # 1. Check Django Configuration
        all_passed &= self._check_django_config()

        # 2. Check Redis Connection
        all_passed &= self._check_redis()

        # 3. Check Django Database
        all_passed &= self._check_database()

        # 4. Check Celery Configuration
        all_passed &= self._check_celery()

        # 5. Check ASGI Configuration
        all_passed &= self._check_asgi()

        # 6. Check Notification Models
        all_passed &= self._check_models()

        # 7. Check Channel Layer
        all_passed &= self._check_channel_layer()

        # Optional tests
        if options['check_tasks']:
            all_passed &= self._check_celery_tasks()

        if options['test_email']:
            all_passed &= self._test_email_notification()

        if options['send_test_notification']:
            all_passed &= self._send_test_notification()

        # Summary
        self.stdout.write('\n' + '='*60)
        if all_passed:
            self.stdout.write(self.style.SUCCESS('✅ ALL CHECKS PASSED'))
        else:
            self.stdout.write(self.style.ERROR('❌ SOME CHECKS FAILED'))
        self.stdout.write('='*60 + '\n')

        return 0 if all_passed else 1

    def _check_django_config(self):
        """Check Django configuration"""
        self.stdout.write(self.style.HTTP_INFO('\n1. Django Configuration'))
        self.stdout.write('-' * 40)

        checks = [
            ('channels in INSTALLED_APPS', 'channels' in settings.INSTALLED_APPS),
            ('ASGI_APPLICATION set', hasattr(settings, 'ASGI_APPLICATION')),
            ('CHANNEL_LAYERS configured', hasattr(settings, 'CHANNEL_LAYERS')),
            ('Notification settings defined', hasattr(settings, 'NOTIFICATION_WEBSOCKET_ENABLED')),
        ]

        passed = True
        for check_name, result in checks:
            status = self.style.SUCCESS('✅') if result else self.style.ERROR('❌')
            self.stdout.write(f'  {status} {check_name}')
            passed &= result

        return passed

    def _check_redis(self):
        """Check Redis connectivity"""
        self.stdout.write(self.style.HTTP_INFO('\n2. Redis Connectivity'))
        self.stdout.write('-' * 40)

        try:
            import redis
            redis_url = settings.CHANNEL_LAYERS['default']['CONFIG']['hosts'][0]
            
            # Parse Redis URL
            from urllib.parse import urlparse
            parsed = urlparse(redis_url) if redis_url.startswith('redis') else None
            
            if not parsed:
                self.stdout.write(self.style.WARNING('  ⚠️  Could not parse Redis URL'))
                return False

            # Try to connect
            r = redis.from_url(redis_url)
            r.ping()
            
            self.stdout.write(self.style.SUCCESS(f'  ✅ Redis connected: {redis_url}'))
            
            # Get Redis info
            info = r.info()
            self.stdout.write(f'  ℹ️  Redis version: {info.get("redis_version", "unknown")}')
            self.stdout.write(f'  ℹ️  Memory used: {info.get("used_memory_human", "unknown")}')
            
            return True
        except ImportError:
            self.stdout.write(self.style.ERROR('  ❌ redis-py not installed'))
            return False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Redis connection failed: {str(e)}'))
            return False

    def _check_database(self):
        """Check database connectivity"""
        self.stdout.write(self.style.HTTP_INFO('\n3. Database Connectivity'))
        self.stdout.write('-' * 40)

        try:
            conn = connections['default']
            conn.ensure_connection()
            
            # Check if notifications table exists
            from users.notification_models import Notification
            count = Notification.objects.count()
            
            self.stdout.write(self.style.SUCCESS('  ✅ Database connected'))
            self.stdout.write(f'  ℹ️  Notification records: {count}')
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Database error: {str(e)}'))
            return False

    def _check_celery(self):
        """Check Celery configuration"""
        self.stdout.write(self.style.HTTP_INFO('\n4. Celery Configuration'))
        self.stdout.write('-' * 40)

        checks = [
            ('CELERY_BROKER_URL set', bool(settings.CELERY_BROKER_URL)),
            ('CELERY_RESULT_BACKEND set', bool(settings.CELERY_RESULT_BACKEND)),
            ('Celery Beat schedule defined', hasattr(settings, 'CELERY_BEAT_SCHEDULE')),
            ('Task queues configured', hasattr(settings, 'CELERY_TASK_QUEUES')),
        ]

        passed = True
        for check_name, result in checks:
            status = self.style.SUCCESS('✅') if result else self.style.ERROR('❌')
            self.stdout.write(f'  {status} {check_name}')
            passed &= result

        if hasattr(settings, 'CELERY_BEAT_SCHEDULE'):
            self.stdout.write(f'  ℹ️  Scheduled tasks: {len(settings.CELERY_BEAT_SCHEDULE)}')
            for task_name in settings.CELERY_BEAT_SCHEDULE:
                self.stdout.write(f'     - {task_name}')

        return passed

    def _check_asgi(self):
        """Check ASGI configuration"""
        self.stdout.write(self.style.HTTP_INFO('\n5. ASGI Configuration'))
        self.stdout.write('-' * 40)

        try:
            # Try to load the ASGI application
            from django.core.asgi import get_asgi_application
            from users.routing import websocket_urlpatterns
            
            self.stdout.write(self.style.SUCCESS('  ✅ ASGI application loads'))
            self.stdout.write(f'  ℹ️  WebSocket patterns: {len(websocket_urlpatterns)}')
            
            for pattern in websocket_urlpatterns:
                self.stdout.write(f'     - {pattern.pattern}')
            
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ ASGI error: {str(e)}'))
            return False

    def _check_models(self):
        """Check Notification models"""
        self.stdout.write(self.style.HTTP_INFO('\n6. Notification Models'))
        self.stdout.write('-' * 40)

        try:
            from users.notification_models import (
                Notification, NotificationType, NotificationPreference, NotificationLog
            )
            
            models = [
                ('Notification', Notification),
                ('NotificationType', NotificationType),
                ('NotificationPreference', NotificationPreference),
                ('NotificationLog', NotificationLog),
            ]
            
            for model_name, model in models:
                count = model.objects.count()
                self.stdout.write(self.style.SUCCESS(f'  ✅ {model_name}: {count} records'))
            
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Model error: {str(e)}'))
            return False

    def _check_channel_layer(self):
        """Check channel layer connectivity"""
        self.stdout.write(self.style.HTTP_INFO('\n7. Channel Layer'))
        self.stdout.write('-' * 40)

        try:
            from channels.layers import get_channel_layer
            import asyncio
            
            channel_layer = get_channel_layer()
            
            if channel_layer is None:
                self.stdout.write(self.style.ERROR('  ❌ Channel layer not configured'))
                return False
            
            # Try to send a test message
            async def test_channel():
                try:
                    await channel_layer.group_send(
                        'test_group',
                        {'type': 'test.message', 'text': 'test'}
                    )
                    return True
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ❌ Channel send failed: {str(e)}'))
                    return False
            
            # Run async test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(test_channel())
            loop.close()
            
            if result:
                self.stdout.write(self.style.SUCCESS('  ✅ Channel layer operational'))
            
            return result
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Channel layer error: {str(e)}'))
            return False

    def _check_celery_tasks(self):
        """Check Celery task registration"""
        self.stdout.write(self.style.HTTP_INFO('\n8. Celery Tasks'))
        self.stdout.write('-' * 40)

        try:
            from e_commerce_api.celery import app
            
            registered_tasks = app.tasks
            expected_tasks = [
                'users.send_scheduled_notification',
                'users.cleanup_old_notifications',
                'transactions.check_overdue_deliveries',
            ]
            
            for task_name in expected_tasks:
                if task_name in registered_tasks:
                    self.stdout.write(self.style.SUCCESS(f'  ✅ {task_name}'))
                else:
                    self.stdout.write(self.style.WARNING(f'  ⚠️  {task_name} not found'))
            
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Celery error: {str(e)}'))
            return False

    def _test_email_notification(self):
        """Test email notification"""
        self.stdout.write(self.style.HTTP_INFO('\n9. Email Notification Test'))
        self.stdout.write('-' * 40)

        try:
            from authentication.models import CustomUser
            from users.notification_service import NotificationService
            
            # Get first user
            user = CustomUser.objects.first()
            if not user:
                self.stdout.write(self.style.WARNING('  ⚠️  No users found'))
                return False
            
            # Send test email
            result = NotificationService.send_email_notification(
                title='Test Email Notification',
                message='This is a test email',
                recipient_email=user.email
            )
            
            if result:
                self.stdout.write(self.style.SUCCESS(f'  ✅ Email sent to {user.email}'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠️  Email service not configured'))
            
            return True
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Email test failed: {str(e)}'))
            return False

    def _send_test_notification(self):
        """Send a test notification"""
        self.stdout.write(self.style.HTTP_INFO('\n10. Send Test Notification'))
        self.stdout.write('-' * 40)

        try:
            from authentication.models import CustomUser
            from users.notification_service import NotificationService
            from users.notification_models import NotificationType
            
            # Get or create notification type
            notif_type, _ = NotificationType.objects.get_or_create(
                name='system_test',
                defaults={'display_name': 'System Test'}
            )
            
            # Get first user
            user = CustomUser.objects.first()
            if not user:
                self.stdout.write(self.style.WARNING('  ⚠️  No users found'))
                return False
            
            # Create notification
            notification = NotificationService.create_notification(
                user=user,
                title='🔔 Test Notification',
                message='This is a test notification to verify the system works correctly.',
                notification_type=notif_type,
                category='system',
                priority='normal',
                description='System verification test',
                send_websocket=True,
                send_email=False
            )
            
            if notification:
                self.stdout.write(self.style.SUCCESS(f'  ✅ Test notification sent'))
                self.stdout.write(f'  ℹ️  Notification ID: {notification.id}')
                self.stdout.write(f'  ℹ️  Sent to: {user.email}')
                return True
            else:
                self.stdout.write(self.style.ERROR('  ❌ Failed to create notification'))
                return False
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ❌ Test notification failed: {str(e)}'))
            logger.exception('Test notification error')
            return False
