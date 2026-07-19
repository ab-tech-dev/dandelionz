"""
Tests for Paystack webhook replay protection and reference routing.

Paystack retries webhooks until it gets a 200. Before the PaystackEvent table, the only
thing stopping a retry from being reprocessed was Payment.verified - which covers the order
charge path and nothing else.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from transactions import references
from transactions.models import Order, Payment, PaystackEvent, Wallet

User = get_user_model()

TEST_SECRET = 'sk_test_dummy_secret'


def sign(body_bytes):
    return hmac.new(TEST_SECRET.encode(), body_bytes, hashlib.sha512).hexdigest()


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class PaystackWebhookDedupTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='hook@test.com', password='test123', full_name='Hook User',
        )
        Wallet.objects.get_or_create(user=self.user)
        self.order = Order.objects.create(customer=self.user, total_price=Decimal('1000.00'))
        self.payment = Payment.objects.create(
            order=self.order,
            reference='ORD-test-ref-1',
            amount=Decimal('1000.00'),
        )
        self.url = '/transactions/webhook/'

        # A successful payment queues a Celery notification. There is no broker in tests,
        # and this suite is about replay handling, not notifications.
        notify_patcher = patch('transactions.tasks.notify_stakeholders_order_paid.delay')
        self.mock_notify = notify_patcher.start()
        self.addCleanup(notify_patcher.stop)

    def _post(self, payload):
        body = json.dumps(payload).encode()
        return self.client.post(
            self.url,
            data=body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=sign(body),
        )

    def test_rejects_a_bad_signature(self):
        body = json.dumps({'event': 'charge.success', 'data': {'reference': 'x'}}).encode()
        response = self.client.post(
            self.url,
            data=body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='not-the-right-signature',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PaystackEvent.objects.count(), 0)

    @patch('transactions.views.Paystack.verify_payment')
    def test_records_the_event_it_processed(self, mock_verify):
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 100000}
        }

        self._post({
            'id': 12345,
            'event': 'charge.success',
            'data': {'reference': 'ORD-test-ref-1'},
        })

        # Keyed by event type as well as object id - see the comment in the view.
        event = PaystackEvent.objects.get(event_id='charge.success:12345')
        self.assertEqual(event.event_type, 'charge.success')
        self.assertEqual(event.reference, 'ORD-test-ref-1')
        self.assertTrue(event.signature_valid)

    @patch('transactions.views.Paystack.verify_payment')
    def test_replayed_event_is_ignored(self, mock_verify):
        """The core guarantee: Paystack retrying must not reprocess anything."""
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 100000}
        }
        payload = {
            'id': 999,
            'event': 'charge.success',
            'data': {'reference': 'ORD-test-ref-1'},
        }

        first = self._post(payload)
        second = self._post(payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json().get('detail'), 'duplicate')
        self.assertEqual(PaystackEvent.objects.count(), 1)
        # The payment was verified once, not twice.
        self.assertEqual(mock_verify.call_count, 1)

    @patch('transactions.views.Paystack.verify_payment')
    def test_different_event_types_sharing_an_object_id_are_not_confused(self, mock_verify):
        """
        Regression: transaction ids and transfer ids are separate sequences that can
        collide numerically. Keying dedup on the bare id let a transfer.success be
        swallowed as a duplicate of an unrelated charge.success, stranding a payout in
        'processing' forever.
        """
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 100000}
        }

        self._post({
            'id': 777,
            'event': 'charge.success',
            'data': {'reference': 'ORD-test-ref-1'},
        })
        second = self._post({
            'id': 777,
            'event': 'transfer.success',
            'data': {'reference': 'WTH-SOMETHING'},
        })

        self.assertNotEqual(second.json().get('detail'), 'duplicate')
        self.assertEqual(PaystackEvent.objects.count(), 2)

    @patch('transactions.views.Paystack.verify_payment')
    def test_declined_events_are_marked_ignored_not_processed(self, mock_verify):
        """
        An event we returned 200 for without acting on must be findable on the admin
        failed-payments screen. Marking it PROCESSED would hide exactly the orphaned
        events an operator needs to see.
        """
        self._post({
            'id': 888,
            'event': 'charge.success',
            'data': {'reference': 'ORD-reference-that-does-not-exist'},
        })

        event = PaystackEvent.objects.get(event_id='charge.success:888')
        self.assertEqual(event.status, PaystackEvent.Status.IGNORED)
        self.assertEqual(event.error_message, 'payment not found')

    @patch('transactions.views.Paystack.verify_payment')
    def test_events_without_an_id_are_deduped_by_body_hash(self, mock_verify):
        """Paystack does not always send an id; identical bodies must still collapse."""
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 100000}
        }
        payload = {'event': 'charge.success', 'data': {'reference': 'ORD-test-ref-1'}}

        self._post(payload)
        second = self._post(payload)

        self.assertEqual(second.json().get('detail'), 'duplicate')
        self.assertEqual(PaystackEvent.objects.count(), 1)

    @patch('transactions.views.Paystack.verify_payment')
    def test_failure_during_processing_is_recorded_on_the_event(self, mock_verify):
        """A blown-up webhook should be visible on the admin screen, not just in logs."""
        mock_verify.side_effect = None
        with patch(
            'transactions.views.Payment.objects'
        ) as mock_objects:
            mock_objects.select_for_update.side_effect = RuntimeError('database exploded')
            with self.assertRaises(RuntimeError):
                self._post({
                    'id': 555,
                    'event': 'charge.success',
                    'data': {'reference': 'ORD-test-ref-1'},
                })

        event = PaystackEvent.objects.get(event_id='charge.success:555')
        self.assertEqual(event.status, PaystackEvent.Status.FAILED)
        self.assertIn('database exploded', event.error_message)


class ReferenceClassificationTests(TestCase):
    """Routing must not mistake a wallet deposit for an order payment."""

    def test_prefixes_route_to_their_own_kind(self):
        self.assertEqual(references.classify('ORD-abc-123'), references.ORDER)
        self.assertEqual(references.classify('DEP-ABC123'), references.DEPOSIT)
        self.assertEqual(references.classify('INS-abc-123'), references.INSTALLMENT)
        self.assertEqual(references.classify('WTH-ABC123'), references.TRANSFER)
        self.assertEqual(references.classify('ADM-ABC123'), references.TRANSFER)

    def test_legacy_unprefixed_references_are_treated_as_orders(self):
        """
        Every reference created before prefixes existed was an order payment. If these
        stopped resolving, payments in flight during the deploy would be orphaned.
        """
        legacy = '8cf2b8e8-02b2-45b9-95fe-b27e1ad59ff1-a1b2c3d4e5'
        self.assertEqual(references.classify(legacy), references.ORDER)

    def test_empty_reference_does_not_crash(self):
        self.assertEqual(references.classify(''), references.ORDER)
        self.assertEqual(references.classify(None), references.ORDER)

    def test_generated_references_carry_their_prefix(self):
        self.assertTrue(references.new_deposit_reference().startswith('DEP-'))
        self.assertTrue(references.new_order_reference('abc').startswith('ORD-'))
        self.assertTrue(references.new_installment_reference('7').startswith('INS-'))

    def test_generated_deposit_references_are_unique(self):
        refs = {references.new_deposit_reference() for _ in range(50)}
        self.assertEqual(len(refs), 50)
