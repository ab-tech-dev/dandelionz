"""
Tests for Paystack wallet top-ups.

The properties that matter here are security ones: a deposit must credit only what was
actually paid, must land in the bucket that cannot be withdrawn to a bank, and must not
credit twice when the verify endpoint and the webhook race - which they routinely do.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from transactions.models import LedgerEntry, Wallet, WalletDeposit

User = get_user_model()

TEST_SECRET = 'sk_test_dummy_secret'


def paystack_success(amount_naira, reference='DEP-TEST1', transaction_id='999'):
    return {
        'data': {
            'id': transaction_id,
            'status': 'success',
            'currency': 'NGN',
            'amount': int(Decimal(str(amount_naira)) * 100),
            'reference': reference,
        }
    }


class InitializeDepositTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='dep@test.com', password='test123', full_name='Dep User',
        )
        Wallet.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('transactions.views.Paystack.initialize_payment')
    def test_initializing_creates_a_pending_deposit_and_credits_nothing(self, mock_init):
        """Money must not move until the payment is actually verified."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack/x'}}

        response = self.client.post('/transactions/wallet/deposit/', {'amount': '2000.00'}, format='json')

        self.assertEqual(response.status_code, 201)
        deposit = WalletDeposit.objects.get(user=self.user)
        self.assertEqual(deposit.status, WalletDeposit.Status.PENDING)

        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, Decimal('0.00'))
        self.assertEqual(LedgerEntry.objects.filter(wallet=wallet).count(), 0)

    @patch('transactions.views.Paystack.initialize_payment')
    def test_reference_carries_the_deposit_prefix(self, mock_init):
        """The webhook routes on this prefix; without it a top-up looks like an order."""
        mock_init.return_value = {'data': {'authorization_url': 'https://paystack/x'}}

        self.client.post('/transactions/wallet/deposit/', {'amount': '2000.00'}, format='json')

        deposit = WalletDeposit.objects.get(user=self.user)
        self.assertTrue(deposit.reference.startswith('DEP-'))

    @patch('transactions.views.Paystack.initialize_payment')
    def test_amount_below_the_minimum_is_refused(self, mock_init):
        response = self.client.post('/transactions/wallet/deposit/', {'amount': '50.00'}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(WalletDeposit.objects.exists())
        mock_init.assert_not_called()

    @patch('transactions.views.Paystack.initialize_payment')
    def test_amount_above_the_maximum_is_refused(self, mock_init):
        response = self.client.post('/transactions/wallet/deposit/', {'amount': '9000000.00'}, format='json')

        self.assertEqual(response.status_code, 400)
        mock_init.assert_not_called()

    @patch('transactions.views.Paystack.initialize_payment')
    def test_a_paystack_failure_marks_the_deposit_failed(self, mock_init):
        mock_init.side_effect = Exception('paystack down')

        response = self.client.post('/transactions/wallet/deposit/', {'amount': '2000.00'}, format='json')

        self.assertEqual(response.status_code, 400)
        deposit = WalletDeposit.objects.get(user=self.user)
        self.assertEqual(deposit.status, WalletDeposit.Status.FAILED)

    def test_anonymous_users_cannot_start_a_deposit(self):
        client = APIClient()
        response = client.post('/transactions/wallet/deposit/', {'amount': '2000.00'}, format='json')
        self.assertIn(response.status_code, (401, 403))


class VerifyDepositTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='ver@test.com', password='test123', full_name='Ver User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.deposit = WalletDeposit.objects.create(
            user=self.user, reference='DEP-VERIFY1', amount=Decimal('3000.00'),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_verified_deposit_credits_the_spendable_bucket(self, mock_verify):
        """
        The core rule: deposited money is spendable at checkout but must never be
        withdrawable, or the wallet becomes a way to cash out a stolen card.
        """
        mock_verify.return_value = paystack_success('3000.00', 'DEP-VERIFY1')

        response = self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('3000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_deposited_funds_cannot_be_withdrawn(self, mock_verify):
        mock_verify.return_value = paystack_success('3000.00', 'DEP-VERIFY1')
        self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.wallet.refresh_from_db()
        with self.assertRaises(ValueError):
            self.wallet.debit(
                Decimal('1000.00'),
                source='Withdrawal attempt',
                bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            )

    @patch('transactions.views.Paystack.verify_payment')
    def test_verifying_twice_credits_once(self, mock_verify):
        mock_verify.return_value = paystack_success('3000.00', 'DEP-VERIFY1')

        self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')
        self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('3000.00'))
        self.assertEqual(
            LedgerEntry.objects.filter(
                wallet=self.wallet, entry_type=LedgerEntry.EntryType.DEPOSIT
            ).count(),
            1,
        )

    @patch('transactions.views.Paystack.verify_payment')
    def test_paying_less_than_requested_credits_nothing(self, mock_verify):
        """
        Guards against initialising a large deposit and paying a small one. Crediting the
        requested amount rather than the paid amount would be free money.
        """
        mock_verify.return_value = paystack_success('10.00', 'DEP-VERIFY1')

        response = self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))
        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.status, WalletDeposit.Status.FAILED)

    @patch('transactions.views.Paystack.verify_payment')
    def test_an_unsuccessful_payment_credits_nothing(self, mock_verify):
        mock_verify.return_value = {'data': {'status': 'failed', 'currency': 'NGN', 'amount': 300000}}

        response = self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_foreign_currency_payment_credits_nothing(self, mock_verify):
        mock_verify.return_value = {
            'data': {'status': 'success', 'currency': 'USD', 'amount': 300000}
        }

        response = self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_another_user_cannot_verify_someone_elses_deposit(self, mock_verify):
        mock_verify.return_value = paystack_success('3000.00', 'DEP-VERIFY1')
        intruder = User.objects.create_user(
            email='intruder@test.com', password='test123', full_name='Intruder',
        )
        client = APIClient()
        client.force_authenticate(user=intruder)

        response = client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.assertEqual(response.status_code, 403)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_the_paystack_transaction_id_is_stored_for_later_refunds(self, mock_verify):
        """Refunding a deposit to source needs Paystack's id, not our reference."""
        mock_verify.return_value = paystack_success('3000.00', 'DEP-VERIFY1', transaction_id='42424')

        self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-VERIFY1')

        self.deposit.refresh_from_db()
        self.assertEqual(self.deposit.paystack_transaction_id, '42424')

    def test_an_unknown_reference_is_a_404(self):
        response = self.client.get('/transactions/wallet/deposit/verify/?reference=DEP-NOPE')
        self.assertEqual(response.status_code, 404)


@override_settings(PAYSTACK_SECRET_KEY=TEST_SECRET)
class DepositWebhookTests(TestCase):
    """The webhook and the verify endpoint race; both must be safe."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='hookdep@test.com', password='test123', full_name='Hook Dep',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.deposit = WalletDeposit.objects.create(
            user=self.user, reference='DEP-HOOK1', amount=Decimal('4000.00'),
        )

    def _post(self, payload):
        body = json.dumps(payload).encode()
        signature = hmac.new(TEST_SECRET.encode(), body, hashlib.sha512).hexdigest()
        return self.client.post(
            '/transactions/webhook/',
            data=body,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

    @patch('transactions.views.Paystack.verify_payment')
    def test_webhook_credits_a_deposit_to_the_spendable_bucket(self, mock_verify):
        mock_verify.return_value = paystack_success('4000.00', 'DEP-HOOK1')

        self._post({
            'id': 5001,
            'event': 'charge.success',
            'data': {'reference': 'DEP-HOOK1', 'id': 5001},
        })

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('4000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('0.00'))

    @patch('transactions.views.Paystack.verify_payment')
    def test_webhook_after_verify_does_not_double_credit(self, mock_verify):
        """The realistic race: the user returns to the app as the webhook lands."""
        mock_verify.return_value = paystack_success('4000.00', 'DEP-HOOK1')

        client = APIClient()
        client.force_authenticate(user=self.user)
        client.get('/transactions/wallet/deposit/verify/?reference=DEP-HOOK1')

        self._post({
            'id': 5002,
            'event': 'charge.success',
            'data': {'reference': 'DEP-HOOK1', 'id': 5002},
        })

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('4000.00'))
        self.assertEqual(
            LedgerEntry.objects.filter(
                wallet=self.wallet, entry_type=LedgerEntry.EntryType.DEPOSIT
            ).count(),
            1,
        )

    @patch('transactions.views.Paystack.verify_payment')
    def test_a_deposit_webhook_is_not_treated_as_an_order_payment(self, mock_verify):
        """
        Before reference routing, any non-transfer event was looked up in the Payment
        table - a top-up would have been reported as an unknown payment and dropped.
        """
        mock_verify.return_value = paystack_success('4000.00', 'DEP-HOOK1')

        response = self._post({
            'id': 5003,
            'event': 'charge.success',
            'data': {'reference': 'DEP-HOOK1', 'id': 5003},
        })

        self.assertNotEqual(response.json().get('detail'), 'payment not found')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('4000.00'))
