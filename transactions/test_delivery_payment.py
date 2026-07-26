"""
Paying an order's delivery fee - the second payment - from wallet, card, or both.

Mirrors the split-checkout guarantees: the wallet leg is held and reversible, the card leg is
captured on verify, and only when the whole fee settles does the order become shippable.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from transactions import delivery_payment
from transactions.models import (
    DeliveryCharge, LedgerEntry, Order, Wallet, WalletHold,
)
from users.models import Customer

User = get_user_model()


@patch('transactions.delivery_payment.Paystack')
class DeliveryPaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            email='dpc@test.com', password='pass12345', role='CUSTOMER', full_name='DP',
        )
        Customer.objects.get_or_create(user=self.customer)
        self.wallet, _ = Wallet.objects.get_or_create(user=self.customer)
        self.order = Order.objects.create(
            customer=self.customer, total_price=Decimal('5000.00'),
            status=Order.Status.PAID, payment_status='PAID',
            delivery_fee=Decimal('2500.00'), delivery_fee_paid=False,
        )
        self.client.force_authenticate(user=self.customer)

    def _fund(self, spendable=Decimal('0'), withdrawable=Decimal('0')):
        if spendable > 0:
            self.wallet.credit(spendable, source='t', bucket=LedgerEntry.Bucket.SPENDABLE,
                               entry_type=LedgerEntry.EntryType.DEPOSIT)
        if withdrawable > 0:
            self.wallet.credit(withdrawable, source='t', bucket=LedgerEntry.Bucket.WITHDRAWABLE,
                               entry_type=LedgerEntry.EntryType.VENDOR_EARNING)
        self.wallet.refresh_from_db()

    def _init_url(self):
        return reverse('init-delivery-payment', kwargs={'order_id': self.order.order_id})

    def _verify_url(self):
        return reverse('verify-delivery-payment')

    def _mock_init(self, Paystack):
        Paystack.return_value.initialize_payment.return_value = {
            'data': {'authorization_url': 'https://paystack.test/x'}
        }

    def _mock_verify(self, Paystack, card_amount, txn_id=777):
        Paystack.return_value.verify_payment.return_value = {
            'data': {'status': 'success', 'currency': 'NGN',
                     'amount': int(Decimal(str(card_amount)) * 100), 'id': txn_id}
        }

    def test_wallet_covers_the_whole_fee_settles_immediately(self, Paystack):
        self._fund(spendable=Decimal('3000'))
        resp = self.client.post(self._init_url(), {'use_wallet': True}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['data']['requires_payment'])
        self.order.refresh_from_db()
        self.assertTrue(self.order.delivery_fee_paid)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('500.00'))  # 3000 - 2500
        charge = DeliveryCharge.objects.get(order=self.order)
        self.assertEqual(charge.status, DeliveryCharge.Status.PAID)

    def test_card_only_when_no_wallet_used(self, Paystack):
        self._mock_init(Paystack)
        resp = self.client.post(self._init_url(), {}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['requires_payment'])
        self.assertEqual(resp.data['data']['card_amount'], 2500.0)
        charge = DeliveryCharge.objects.get(order=self.order)
        self.assertEqual(charge.card_amount, Decimal('2500.00'))
        self.assertEqual(charge.status, DeliveryCharge.Status.PENDING)
        self.order.refresh_from_db()
        self.assertFalse(self.order.delivery_fee_paid)  # not paid until verify

    def test_split_holds_wallet_and_settles_on_verify(self, Paystack):
        self._fund(spendable=Decimal('1000'))
        self._mock_init(Paystack)
        resp = self.client.post(self._init_url(), {'use_wallet': True}, format='json')

        self.assertEqual(resp.data['data']['wallet_amount'], 1000.0)
        self.assertEqual(resp.data['data']['card_amount'], 1500.0)
        # Wallet debited and held; balance now zero.
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        hold = WalletHold.objects.get(order=self.order, purpose=WalletHold.Purpose.DELIVERY)
        self.assertEqual(hold.status, WalletHold.Status.HELD)

        reference = resp.data['data']['reference']
        self._mock_verify(Paystack, Decimal('1500'))
        vresp = self.client.get(self._verify_url(), {'reference': reference})

        self.assertEqual(vresp.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.delivery_fee_paid)
        hold.refresh_from_db()
        self.assertEqual(hold.status, WalletHold.Status.CAPTURED)

    def test_verify_rejects_amount_mismatch(self, Paystack):
        self._mock_init(Paystack)
        resp = self.client.post(self._init_url(), {}, format='json')
        reference = resp.data['data']['reference']

        self._mock_verify(Paystack, Decimal('999'))  # wrong amount
        vresp = self.client.get(self._verify_url(), {'reference': reference})

        self.assertEqual(vresp.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.delivery_fee_paid)

    def test_restarting_releases_the_previous_wallet_hold(self, Paystack):
        self._fund(spendable=Decimal('1000'))
        self._mock_init(Paystack)
        self.client.post(self._init_url(), {'use_wallet': True}, format='json')
        # First attempt held 1000.
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))

        # Restart without wallet: the old hold is released, money returns to spendable.
        self.client.post(self._init_url(), {}, format='json')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1000.00'))
        self.assertEqual(
            WalletHold.objects.filter(order=self.order, status=WalletHold.Status.RELEASED).count(), 1
        )
        self.assertEqual(
            DeliveryCharge.objects.filter(order=self.order, status=DeliveryCharge.Status.PENDING).count(), 1
        )

    def test_no_fee_due_is_rejected(self, Paystack):
        self.order.delivery_fee = Decimal('0.00')
        self.order.save(update_fields=['delivery_fee'])
        resp = self.client.post(self._init_url(), {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_already_paid_is_rejected(self, Paystack):
        self.order.delivery_fee_paid = True
        self.order.save(update_fields=['delivery_fee_paid'])
        resp = self.client.post(self._init_url(), {}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_is_idempotent(self, Paystack):
        self._mock_init(Paystack)
        resp = self.client.post(self._init_url(), {}, format='json')
        reference = resp.data['data']['reference']
        self._mock_verify(Paystack, Decimal('2500'))

        self.client.get(self._verify_url(), {'reference': reference})
        second = self.client.get(self._verify_url(), {'reference': reference})

        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            DeliveryCharge.objects.filter(order=self.order, status=DeliveryCharge.Status.PAID).count(), 1
        )

    def test_another_customer_cannot_pay_your_delivery_fee(self, Paystack):
        self._mock_init(Paystack)
        resp = self.client.post(self._init_url(), {}, format='json')
        reference = resp.data['data']['reference']

        other = User.objects.create_user(email='other@test.com', password='pass12345', role='CUSTOMER')
        self.client.force_authenticate(user=other)
        vresp = self.client.get(self._verify_url(), {'reference': reference})
        self.assertEqual(vresp.status_code, 404)

    def test_paying_a_replaced_link_refunds_to_source(self, Paystack):
        """Restart cancels the old charge; paying its stale link is refunded, not stranded."""
        self._mock_init(Paystack)
        first = self.client.post(self._init_url(), {}, format='json')
        old_ref = first.data['data']['reference']

        # Restart: the old charge is cancelled, a new one is created.
        self.client.post(self._init_url(), {}, format='json')
        old_charge = DeliveryCharge.objects.get(reference=old_ref)
        self.assertEqual(old_charge.status, DeliveryCharge.Status.CANCELLED)

        # The customer pays the OLD (replaced) link. Verify must refund it to source.
        self._mock_verify(Paystack, Decimal('2500'), txn_id=4242)
        Paystack.return_value.refund.return_value = {'data': {'id': 9001, 'status': 'pending'}}
        vresp = self.client.get(self._verify_url(), {'reference': old_ref})

        self.assertEqual(vresp.status_code, 400)  # told to use the current payment
        Paystack.return_value.refund.assert_called_once()
        self.assertEqual(Paystack.return_value.refund.call_args.kwargs['amount'], Decimal('2500.00'))
        old_charge.refresh_from_db()
        self.assertEqual(old_charge.status, DeliveryCharge.Status.REFUNDED)
        # The order is NOT marked paid off a refunded, stranded payment.
        self.order.refresh_from_db()
        self.assertFalse(self.order.delivery_fee_paid)
