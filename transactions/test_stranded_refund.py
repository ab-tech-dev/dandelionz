"""
Option A: refunding a card leg to source when its order can no longer be settled.

A split payment's two legs are separable. The wallet leg can be handed back to the customer
- by cancelling, or by the abandonment sweeper - while the card leg's Paystack link is still
payable. If the customer then pays the card leg, settlement is refused, which leaves real
money collected at Paystack for an order that will never ship. This returns it to the card
automatically and records the refund so it stays reconcilable.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from store.models import Cart, CartItem, Product
from transactions import wallet_checkout
from transactions.models import LedgerEntry, Order, OrderPaymentRefund, Wallet
from users.models import Customer, Vendor

User = get_user_model()

PAYSTACK_REFUND_OK = {"status": True, "data": {"id": 555111, "status": "pending"}}


@patch('transactions.tasks.notify_stakeholders_order_paid.delay')
@patch('transactions.views._notify_checkout')
@patch('transactions.views.Paystack.initialize_payment')
class StrandedCardLegRefundTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email='str@test.com', password='pass12345', role='CUSTOMER', full_name='Str',
        )
        self.vendor_user = User.objects.create_user(
            email='strvendor@test.com', password='pass12345', role='VENDOR',
        )
        Customer.objects.get_or_create(user=self.customer)
        self.vendor, _ = Vendor.objects.get_or_create(
            user=self.vendor_user, defaults={'store_name': 'Str Store'},
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.customer)
        self.cart = Cart.objects.create(customer=self.customer)
        self.product = Product.objects.create(
            store=self.vendor, name='Widget', price=Decimal('1000.00'), stock=100,
        )
        self.client.force_authenticate(user=self.customer)

    def _fund_spendable(self, amount):
        self.wallet.credit(
            amount, source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
            entry_type=LedgerEntry.EntryType.DEPOSIT,
        )
        self.wallet.refresh_from_db()

    def _paid_then_stranded(self, mock_init):
        """Split checkout (8000 order, 5000 wallet, 3000 card), then cancel so the wallet
        money returns and the card leg becomes unsettleable."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=8)
        self._fund_spendable(Decimal('5000'))
        response = self.client.post(
            '/transactions/checkout/', {'use_wallet': True}, format='json'
        )
        order = Order.objects.get(order_id=response.data['data']['order_id'])
        self.client.post(f'/transactions/orders/{order.order_id}/cancel/')
        return order

    @patch('transactions.views.Paystack.verify_payment')
    @patch('transactions.paystack.Paystack.refund')
    def test_a_stranded_card_leg_is_refunded_to_source(
        self, mock_refund, mock_verify, mock_init, _notify, _task
    ):
        mock_refund.return_value = PAYSTACK_REFUND_OK
        order = self._paid_then_stranded(mock_init)
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 300000, 'id': 987}
        }

        resp = self.client.post(
            '/transactions/verify-payment/', {'reference': order.payment.reference},
            format='json',
        )

        self.assertEqual(resp.status_code, 400)
        mock_refund.assert_called_once()
        self.assertEqual(mock_refund.call_args.kwargs['amount'], Decimal('3000.00'))
        refund = OrderPaymentRefund.objects.get(payment=order.payment)
        self.assertEqual(refund.status, OrderPaymentRefund.Status.PROCESSING)
        self.assertEqual(refund.amount, Decimal('3000.00'))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELED)

    @patch('transactions.views.Paystack.verify_payment')
    @patch('transactions.paystack.Paystack.refund')
    def test_the_refund_uses_paystacks_transaction_id(
        self, mock_refund, mock_verify, mock_init, _notify, _task
    ):
        mock_refund.return_value = PAYSTACK_REFUND_OK
        order = self._paid_then_stranded(mock_init)
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 300000, 'id': 424242}
        }

        self.client.post(
            '/transactions/verify-payment/', {'reference': order.payment.reference},
            format='json',
        )

        self.assertEqual(mock_refund.call_args.kwargs['transaction'], '424242')
        order.payment.refresh_from_db()
        self.assertEqual(order.payment.paystack_transaction_id, '424242')

    @patch('transactions.views.Paystack.verify_payment')
    @patch('transactions.paystack.Paystack.refund')
    def test_refund_is_not_issued_twice_for_the_same_card_leg(
        self, mock_refund, mock_verify, mock_init, _notify, _task
    ):
        """A verify/webhook retry must not refund the same charge twice."""
        mock_refund.return_value = PAYSTACK_REFUND_OK
        order = self._paid_then_stranded(mock_init)
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 300000, 'id': 987}
        }

        self.client.post('/transactions/verify-payment/',
                         {'reference': order.payment.reference}, format='json')
        self.client.post('/transactions/verify-payment/',
                         {'reference': order.payment.reference}, format='json')

        self.assertEqual(mock_refund.call_count, 1)
        self.assertEqual(
            OrderPaymentRefund.objects.filter(payment=order.payment).count(), 1
        )

    @patch('transactions.paystack.Paystack.refund')
    def test_a_failed_paystack_refund_is_recorded_for_retry(
        self, mock_refund, mock_init, _notify, _task
    ):
        mock_refund.side_effect = Exception('Paystack down')
        order = self._paid_then_stranded(mock_init)

        refund = wallet_checkout.refund_stranded_card_leg(order.payment)

        self.assertEqual(refund.status, OrderPaymentRefund.Status.FAILED)
        self.assertIn('Paystack down', refund.failure_reason)

    @patch('transactions.paystack.Paystack.refund')
    def test_a_failed_refund_can_be_retried_but_a_live_one_cannot_double(
        self, mock_refund, mock_init, _notify, _task
    ):
        """
        The partial unique constraint allows a fresh attempt after a failure, but never two
        live refunds for one charge.
        """
        order = self._paid_then_stranded(mock_init)

        mock_refund.side_effect = Exception('down')
        first = wallet_checkout.refund_stranded_card_leg(order.payment)
        self.assertEqual(first.status, OrderPaymentRefund.Status.FAILED)

        # Retry after the failure: a new row is created and succeeds.
        mock_refund.side_effect = None
        mock_refund.return_value = PAYSTACK_REFUND_OK
        second = wallet_checkout.refund_stranded_card_leg(order.payment)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.status, OrderPaymentRefund.Status.PROCESSING)

        # A further call with a live refund present short-circuits to it.
        third = wallet_checkout.refund_stranded_card_leg(order.payment)
        self.assertEqual(third.pk, second.pk)
        self.assertEqual(
            OrderPaymentRefund.objects.filter(
                payment=order.payment
            ).exclude(status=OrderPaymentRefund.Status.FAILED).count(),
            1,
        )

    @patch('transactions.paystack.Paystack.refund')
    def test_refund_settles_on_the_refund_processed_webhook(
        self, mock_refund, mock_init, _notify, _task
    ):
        from transactions.deposit_refund_service import settle_refund_webhook

        mock_refund.return_value = PAYSTACK_REFUND_OK
        order = self._paid_then_stranded(mock_init)
        refund = wallet_checkout.refund_stranded_card_leg(order.payment)

        handled, _ = settle_refund_webhook('refund.processed', {
            'transaction_reference': order.payment.reference,
            'amount': 300000,
            'id': 555111,
        })

        self.assertTrue(handled)
        refund.refresh_from_db()
        self.assertEqual(refund.status, OrderPaymentRefund.Status.PROCESSED)
        self.assertIsNotNone(refund.settled_at)

    @patch('transactions.paystack.Paystack.refund')
    def test_refund_failed_webhook_marks_the_record_failed(
        self, mock_refund, mock_init, _notify, _task
    ):
        from transactions.deposit_refund_service import settle_refund_webhook

        mock_refund.return_value = PAYSTACK_REFUND_OK
        order = self._paid_then_stranded(mock_init)
        refund = wallet_checkout.refund_stranded_card_leg(order.payment)

        handled, _ = settle_refund_webhook('refund.failed', {
            'transaction_reference': order.payment.reference,
            'amount': 300000,
            'message': 'card expired',
        })

        self.assertTrue(handled)
        refund.refresh_from_db()
        self.assertEqual(refund.status, OrderPaymentRefund.Status.FAILED)

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_normal_card_leg_records_the_transaction_id_when_it_settles(
        self, mock_verify, mock_init, _notify, _task
    ):
        """The id is captured on the ordinary success path too, for future admin refunds,
        and no refund is created."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack.test/a'}}
        CartItem.objects.create(cart=self.cart, product=self.product, quantity=5)
        response = self.client.post('/transactions/checkout/', {}, format='json')
        order = Order.objects.get(order_id=response.data['data']['order_id'])
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'NGN', 'amount': 500000, 'id': 111222}
        }

        self.client.post('/transactions/verify-payment/',
                         {'reference': order.payment.reference}, format='json')

        order.payment.refresh_from_db()
        self.assertTrue(order.payment.verified)
        self.assertEqual(order.payment.paystack_transaction_id, '111222')
        self.assertFalse(
            OrderPaymentRefund.objects.filter(payment=order.payment).exists()
        )
