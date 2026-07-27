"""
Flagging customers who refund a suspicious share of their orders - for admin review, never a block.

Pins the three gates (enough orders, enough refunds, high enough rate), that rejected refunds do
not count, and the review-snooze that stops a cleared customer re-appearing until they refund more.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from transactions import refund_flagging
from transactions.models import Order, Payment, Refund
from users.models import Customer

User = get_user_model()


def _paid_order(customer, refunded=False, refund_status=Refund.Status.PENDING):
    order = Order.objects.create(
        customer=customer, total_price=Decimal('1000.00'),
        status=Order.Status.PAID, payment_status='PAID',
    )
    payment = Payment.objects.create(
        order=order, amount=Decimal('1000.00'), status='SUCCESS', verified=True,
    )
    if refunded:
        Refund.objects.create(
            payment=payment, refunded_amount=Decimal('1000.00'), status=refund_status,
        )
    return order


class RefundProfileTests(TestCase):
    def _customer(self, email):
        u = User.objects.create_user(email=email, password='pass12345', role='CUSTOMER')
        Customer.objects.get_or_create(user=u)
        return u

    def test_serial_refunder_is_flagged(self):
        u = self._customer('a@test.com')
        for _ in range(1):
            _paid_order(u)                 # 1 clean
        for _ in range(3):
            _paid_order(u, refunded=True)  # 3 refunded -> 4 paid, rate 0.75
        p = refund_flagging.refund_profile(u)
        self.assertEqual(p['paid_orders'], 4)
        self.assertEqual(p['refund_count'], 3)
        self.assertTrue(p['flagged'])
        self.assertTrue(p['needs_review'])

    def test_low_rate_is_not_flagged(self):
        u = self._customer('b@test.com')
        for _ in range(9):
            _paid_order(u)
        for _ in range(1):
            _paid_order(u, refunded=True)  # 10 paid, 1 refund, rate 0.1
        p = refund_flagging.refund_profile(u)
        self.assertFalse(p['flagged'])

    def test_too_few_orders_is_not_flagged(self):
        u = self._customer('c@test.com')
        for _ in range(3):
            _paid_order(u, refunded=True)  # 3 paid all refunded, but < min orders (4)
        p = refund_flagging.refund_profile(u)
        self.assertEqual(p['refund_count'], 3)
        self.assertFalse(p['flagged'])

    def test_rejected_refunds_do_not_count(self):
        u = self._customer('d@test.com')
        _paid_order(u)
        for _ in range(3):
            _paid_order(u, refunded=True, refund_status=Refund.Status.REJECTED)
        p = refund_flagging.refund_profile(u)
        self.assertEqual(p['refund_count'], 0)
        self.assertFalse(p['flagged'])


class RefundFlagEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='fadmin@test.com', password='pass12345', role=User.Role.BUSINESS_ADMIN,
        )
        self.customer = User.objects.create_user(
            email='flagged@test.com', password='pass12345', role='CUSTOMER', full_name='Flag Me',
        )
        Customer.objects.get_or_create(user=self.customer)
        _paid_order(self.customer)
        for _ in range(3):
            _paid_order(self.customer, refunded=True)  # 4 paid, 3 refunds -> flagged
        self.client.force_authenticate(user=self.admin)

    def test_flagged_list_contains_the_serial_refunder(self):
        # A second customer below the rate threshold must NOT appear.
        clean = User.objects.create_user(email='clean@test.com', password='pass12345', role='CUSTOMER')
        Customer.objects.get_or_create(user=clean)
        for _ in range(9):
            _paid_order(clean)
        _paid_order(clean, refunded=True)  # 10 paid, 1 refund -> rate 0.1

        resp = self.client.get(reverse('admin-customer-refund-flags'))
        self.assertEqual(resp.status_code, 200)
        rows = {r['email']: r for r in resp.data['data']['results']}
        self.assertIn('flagged@test.com', rows)
        self.assertNotIn('clean@test.com', rows)
        # Guard the annotated counts directly, so dropping distinct=True (which would inflate
        # them via the order->payment->refund join fan-out) fails here.
        row = rows['flagged@test.com']
        self.assertEqual(row['paid_orders'], 4)
        self.assertEqual(row['refund_count'], 3)

    def test_profile_endpoint(self):
        url = reverse('admin-customer-refund-profile', kwargs={'uuid': self.customer.uuid})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['flagged'])
        self.assertEqual(resp.data['data']['refund_count'], 3)

    def test_marking_reviewed_snoozes_then_reraises_when_worse(self):
        review_url = reverse('admin-customer-refund-flag-review', kwargs={'uuid': self.customer.uuid})
        resp = self.client.post(review_url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['data']['needs_review'])

        # No longer in the review queue.
        flags = self.client.get(reverse('admin-customer-refund-flags'))
        self.assertNotIn('flagged@test.com', [r['email'] for r in flags.data['data']['results']])

        # They refund another order: the flag re-raises.
        _paid_order(self.customer, refunded=True)
        profile = self.client.get(
            reverse('admin-customer-refund-profile', kwargs={'uuid': self.customer.uuid})
        )
        self.assertTrue(profile.data['data']['needs_review'])
        flags2 = self.client.get(reverse('admin-customer-refund-flags'))
        self.assertIn('flagged@test.com', [r['email'] for r in flags2.data['data']['results']])

    def test_non_admin_is_forbidden(self):
        self.client.force_authenticate(user=self.customer)
        resp = self.client.get(reverse('admin-customer-refund-flags'))
        self.assertIn(resp.status_code, (401, 403))
