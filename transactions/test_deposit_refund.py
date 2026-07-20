"""
Tests for refunding deposited wallet funds to their original card.

The behaviour being protected: deposits are spendable but never withdrawable to a bank, so
a refund to source is the only way this money leaves the wallet without being spent. That
makes it the escape hatch account closure depends on - and it must not become a second way
to cash out, or a way to spend the same money twice.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from transactions.deposit_refund_service import (
    RefundError,
    plan_refund,
    refundable_deposits,
    request_refund,
    settle_refund_webhook,
    total_refundable,
)
from transactions.models import DepositRefund, LedgerEntry, Wallet, WalletDeposit

User = get_user_model()

PAYSTACK_OK = {"status": True, "data": {"id": 987654, "status": "pending"}}


class DepositRefundServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='refund@test.com', password='test123', full_name='Refund User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def _deposit(self, amount, txn_id='123456', paid_days_ago=0):
        deposit = WalletDeposit.objects.create(
            user=self.user,
            reference=f"DEP-{txn_id}",
            amount=Decimal(str(amount)),
        )
        deposit.mark_as_successful(txn_id)
        deposit.paid_at = timezone.now() - timezone.timedelta(days=paid_days_ago)
        deposit.save(update_fields=['paid_at'])
        return deposit

    def test_refundable_total_matches_deposits(self):
        self._deposit('2000.00', txn_id='111')
        self._deposit('1500.00', txn_id='222')

        self.assertEqual(total_refundable(self.user), Decimal('3500.00'))

    def test_a_deposit_with_no_paystack_transaction_id_is_not_refundable(self):
        """The id is what the refund call needs; without it there is nothing to refund to."""
        deposit = WalletDeposit.objects.create(
            user=self.user, reference='DEP-NOID', amount=Decimal('1000.00'),
        )
        deposit.mark_as_successful()  # no transaction id captured

        self.assertEqual(refundable_deposits(self.user), [])
        self.assertEqual(total_refundable(self.user), Decimal('0.00'))

    def test_newest_deposits_are_consumed_first(self):
        """
        Paystack will not refund arbitrarily old transactions, so the most recent top-up is
        the one most likely to be accepted. FIFO would strand the user.
        """
        self._deposit('1000.00', txn_id='OLD', paid_days_ago=100)
        newest = self._deposit('1000.00', txn_id='NEW', paid_days_ago=1)

        plan = plan_refund(self.user, Decimal('600.00'))

        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][0].pk, newest.pk)
        self.assertEqual(plan[0][1], Decimal('600.00'))

    def test_a_refund_spans_several_deposits_when_it_has_to(self):
        self._deposit('1000.00', txn_id='OLD', paid_days_ago=100)
        self._deposit('1000.00', txn_id='NEW', paid_days_ago=1)

        plan = plan_refund(self.user, Decimal('1500.00'))

        self.assertEqual(len(plan), 2)
        self.assertEqual(sum(part for _, part in plan), Decimal('1500.00'))

    @patch('transactions.paystack.Paystack.refund')
    def test_requesting_a_refund_debits_the_spendable_bucket_immediately(self, mock_refund):
        """
        Not on settlement: leaving it spendable while the refund is in flight would let the
        user spend the same money at checkout and be paid twice.
        """
        mock_refund.return_value = PAYSTACK_OK
        self._deposit('2000.00')

        request_refund(self.user, Decimal('800.00'))

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1200.00'))

    @patch('transactions.paystack.Paystack.refund')
    def test_a_refund_never_touches_the_withdrawable_bucket(self, mock_refund):
        mock_refund.return_value = PAYSTACK_OK
        self._deposit('2000.00')
        self.wallet.credit(Decimal('5000.00'), source='Referral bonus')

        request_refund(self.user, Decimal('2000.00'))

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('5000.00'))

    @patch('transactions.paystack.Paystack.refund')
    def test_withdrawable_funds_cannot_be_refunded_to_a_card(self, mock_refund):
        """
        The mirror of the withdrawal rule. Earnings go to a bank; only deposits go back to
        a card. Allowing either direction to cross would defeat the split.
        """
        mock_refund.return_value = PAYSTACK_OK
        self.wallet.credit(Decimal('5000.00'), source='Referral bonus')

        with self.assertRaises(RefundError):
            request_refund(self.user, Decimal('1000.00'))

        mock_refund.assert_not_called()

    @patch('transactions.paystack.Paystack.refund')
    def test_refunding_more_than_the_balance_is_refused(self, mock_refund):
        mock_refund.return_value = PAYSTACK_OK
        self._deposit('1000.00')

        with self.assertRaises(RefundError):
            request_refund(self.user, Decimal('1500.00'))

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1000.00'))
        mock_refund.assert_not_called()

    @patch('transactions.paystack.Paystack.refund')
    def test_a_deposit_cannot_be_refunded_twice(self, mock_refund):
        mock_refund.return_value = PAYSTACK_OK
        self._deposit('1000.00')

        request_refund(self.user, Decimal('1000.00'))

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(total_refundable(self.user), Decimal('0.00'))
        with self.assertRaises(RefundError):
            request_refund(self.user, Decimal('1000.00'))

    @patch('transactions.paystack.Paystack.refund')
    def test_a_paystack_rejection_puts_the_money_back(self, mock_refund):
        mock_refund.side_effect = Exception('Transaction too old to refund')
        self._deposit('1000.00')

        refunds, errors = request_refund(self.user, Decimal('1000.00'))

        self.assertEqual(len(errors), 1)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1000.00'))
        self.assertEqual(refunds[0].status, DepositRefund.Status.FAILED)

    @patch('transactions.paystack.Paystack.refund')
    def test_the_ledger_records_the_refund_as_a_deposit_reversal(self, mock_refund):
        mock_refund.return_value = PAYSTACK_OK
        self._deposit('1000.00')

        refunds, _ = request_refund(self.user, Decimal('400.00'))

        entry = LedgerEntry.objects.get(
            entry_type=LedgerEntry.EntryType.DEPOSIT_REVERSAL,
            reference=refunds[0].reference,
        )
        self.assertEqual(entry.direction, LedgerEntry.Direction.DEBIT)
        self.assertEqual(entry.bucket, LedgerEntry.Bucket.SPENDABLE)
        self.assertEqual(entry.amount, Decimal('400.00'))


class RefundWebhookTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='hook@test.com', password='test123', full_name='Hook User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.deposit = WalletDeposit.objects.create(
            user=self.user, reference='DEP-HOOK', amount=Decimal('1000.00'),
        )
        self.deposit.mark_as_successful('555555')

        with patch('transactions.paystack.Paystack.refund', return_value=PAYSTACK_OK):
            self.refunds, _ = request_refund(self.user, Decimal('1000.00'))
        self.refund = self.refunds[0]

    def test_processed_webhook_settles_the_refund(self):
        handled, detail = settle_refund_webhook('refund.processed', {
            'transaction_reference': 'DEP-HOOK',
            'amount': 100000,
            'id': 987654,
        })

        self.assertTrue(handled)
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.status, DepositRefund.Status.PROCESSED)
        self.assertIsNotNone(self.refund.settled_at)

    def test_a_settled_refund_does_not_return_the_money(self):
        """The debit happened at request time; settling must not credit anything back."""
        settle_refund_webhook('refund.processed', {
            'transaction_reference': 'DEP-HOOK', 'amount': 100000,
        })

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))

    def test_failed_webhook_restores_the_spendable_balance(self):
        handled, _ = settle_refund_webhook('refund.failed', {
            'transaction_reference': 'DEP-HOOK',
            'amount': 100000,
            'message': 'Card no longer valid',
        })

        self.assertTrue(handled)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1000.00'))
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.status, DepositRefund.Status.FAILED)

    def test_a_late_failure_cannot_un_settle_a_processed_refund(self):
        """Paystack already paid the card out; crediting the wallet would double it."""
        settle_refund_webhook('refund.processed', {
            'transaction_reference': 'DEP-HOOK', 'amount': 100000,
        })
        settle_refund_webhook('refund.failed', {
            'transaction_reference': 'DEP-HOOK', 'amount': 100000,
        })

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.status, DepositRefund.Status.PROCESSED)

    def test_a_repeated_failure_webhook_credits_only_once(self):
        settle_refund_webhook('refund.failed', {
            'transaction_reference': 'DEP-HOOK', 'amount': 100000,
        })
        settle_refund_webhook('refund.failed', {
            'transaction_reference': 'DEP-HOOK', 'amount': 100000,
        })

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1000.00'))

    def test_an_unknown_transaction_is_reported_not_swallowed(self):
        handled, detail = settle_refund_webhook('refund.processed', {
            'transaction_reference': 'DEP-NOTOURS', 'amount': 100000,
        })

        self.assertFalse(handled)
        self.assertIn('no wallet deposit', detail)

    def test_the_nested_transaction_payload_shape_is_understood(self):
        handled, _ = settle_refund_webhook('refund.processed', {
            'transaction': {'reference': 'DEP-HOOK'},
            'amount': 100000,
        })

        self.assertTrue(handled)


class DepositRefundEndpointTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='api@test.com', password='test123', full_name='Api User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.deposit = WalletDeposit.objects.create(
            user=self.user, reference='DEP-API', amount=Decimal('2000.00'),
        )
        self.deposit.mark_as_successful('777777')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_reports_the_refundable_amount(self):
        response = self.client.get('/transactions/wallet/deposit/refund/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['refundable_amount'], '2000.00')
        self.assertEqual(len(response.data['data']['deposits']), 1)

    @patch('transactions.paystack.Paystack.refund')
    def test_post_starts_a_refund(self, mock_refund):
        mock_refund.return_value = PAYSTACK_OK

        response = self.client.post(
            '/transactions/wallet/deposit/refund/', {'amount': '500.00'}, format='json'
        )

        self.assertEqual(response.status_code, 201)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('1500.00'))

    @patch('transactions.paystack.Paystack.refund')
    def test_post_reports_a_total_failure_as_an_error(self, mock_refund):
        mock_refund.side_effect = Exception('Paystack down')

        response = self.client.post(
            '/transactions/wallet/deposit/refund/', {'amount': '500.00'}, format='json'
        )

        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))

    def test_post_rejects_more_than_the_balance(self):
        response = self.client.post(
            '/transactions/wallet/deposit/refund/', {'amount': '9999.00'}, format='json'
        )

        self.assertEqual(response.status_code, 400)

    def test_a_user_only_sees_their_own_refunds(self):
        other = User.objects.create_user(
            email='other@test.com', password='test123', full_name='Other User',
        )
        other_deposit = WalletDeposit.objects.create(
            user=other, reference='DEP-OTHER', amount=Decimal('500.00'),
        )
        other_deposit.mark_as_successful('888888')
        with patch('transactions.paystack.Paystack.refund', return_value=PAYSTACK_OK):
            request_refund(other, Decimal('500.00'))

        response = self.client.get('/transactions/wallet/deposit/refunds/')

        self.assertEqual(response.status_code, 200)
        results = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 0)
        # And the other user's refund does exist - the list is empty because it is scoped,
        # not because nothing was created.
        self.assertEqual(DepositRefund.objects.filter(user=other).count(), 1)

    def test_the_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get('/transactions/wallet/deposit/refund/')

        self.assertIn(response.status_code, (401, 403))
