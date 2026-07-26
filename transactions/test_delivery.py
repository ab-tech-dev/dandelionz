"""
Admin-set delivery window (a range) and delivery fee, and the ship gate that depends on it.

Dandelionz runs logistics, so the admin schedules each paid order - setting when it will
arrive and what delivery costs - and the order cannot ship until that fee is settled.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from transactions.models import Order
from users.models import Customer

User = get_user_model()


@patch('authentication.views_admin.send_order_notification', lambda *a, **k: True)
class AdminSetDeliveryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='dadmin@test.com', password='pass12345', role=User.Role.BUSINESS_ADMIN,
        )
        self.customer = User.objects.create_user(
            email='dcust@test.com', password='pass12345', role='CUSTOMER',
        )
        Customer.objects.get_or_create(user=self.customer)
        self.order = Order.objects.create(
            customer=self.customer, total_price=Decimal('5000.00'),
            status=Order.Status.PAID, payment_status='PAID',
        )
        self.client.force_authenticate(user=self.admin)

    def _delivery_url(self):
        return reverse('admin-orders-set-delivery', kwargs={'order_id': self.order.order_id})

    def _status_url(self):
        return reverse('admin-orders-detail', kwargs={'order_id': self.order.order_id})

    def test_admin_sets_explicit_window_and_fee(self):
        earliest = timezone.now() + timedelta(days=3)
        latest = timezone.now() + timedelta(days=6)
        resp = self.client.patch(self._delivery_url(), {
            'expected_delivery_earliest': earliest.isoformat(),
            'expected_delivery_latest': latest.isoformat(),
            'delivery_fee': '1500.00',
        }, format='json')

        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_fee, Decimal('1500.00'))
        self.assertFalse(self.order.delivery_fee_paid)  # positive fee is not yet paid
        self.assertIsNotNone(self.order.expected_delivery_earliest)
        self.assertIsNotNone(self.order.expected_delivery_latest)

    def test_use_default_applies_the_configured_window(self):
        resp = self.client.patch(self._delivery_url(), {
            'use_default': True,
            'delivery_fee': '2000.00',
        }, format='json')

        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        # Default window is DELIVERY_ETA_MIN_DAYS..MAX_DAYS out (7..14 by default).
        days_out = (self.order.expected_delivery_latest - timezone.now()).days
        self.assertGreaterEqual(days_out, 12)
        self.assertLessEqual(days_out, 14)

    def test_zero_fee_is_marked_paid_immediately(self):
        resp = self.client.patch(self._delivery_url(), {
            'use_default': True,
            'delivery_fee': '0.00',
        }, format='json')

        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.delivery_fee_paid)

    def test_window_without_dates_or_default_is_rejected(self):
        resp = self.client.patch(self._delivery_url(), {'delivery_fee': '1000.00'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_earliest_after_latest_is_rejected(self):
        earliest = timezone.now() + timedelta(days=9)
        latest = timezone.now() + timedelta(days=4)
        resp = self.client.patch(self._delivery_url(), {
            'expected_delivery_earliest': earliest.isoformat(),
            'expected_delivery_latest': latest.isoformat(),
            'delivery_fee': '1000.00',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_shipping_is_blocked_until_the_fee_is_paid(self):
        # Fee set, not yet paid -> cannot ship.
        self.client.patch(self._delivery_url(), {
            'use_default': True, 'delivery_fee': '1500.00',
        }, format='json')

        resp = self.client.patch(self._status_url(), {'status': 'SHIPPED'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PAID)

    def test_shipping_allowed_once_the_fee_is_paid(self):
        self.client.patch(self._delivery_url(), {
            'use_default': True, 'delivery_fee': '1500.00',
        }, format='json')
        self.order.refresh_from_db()
        self.order.delivery_fee_paid = True  # simulate the customer having paid
        self.order.save(update_fields=['delivery_fee_paid'])

        resp = self.client.patch(self._status_url(), {'status': 'SHIPPED'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    def test_free_delivery_order_can_ship_without_a_second_payment(self):
        self.client.patch(self._delivery_url(), {
            'use_default': True, 'delivery_fee': '0.00',
        }, format='json')

        resp = self.client.patch(self._status_url(), {'status': 'SHIPPED'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    def test_only_paid_orders_can_be_scheduled(self):
        self.order.payment_status = 'UNPAID'
        self.order.save(update_fields=['payment_status'])
        resp = self.client.patch(self._delivery_url(), {
            'use_default': True, 'delivery_fee': '1000.00',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_non_admin_is_forbidden(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.patch(self._delivery_url(), {
            'use_default': True, 'delivery_fee': '1000.00',
        }, format='json')
        self.assertIn(resp.status_code, (401, 403))
