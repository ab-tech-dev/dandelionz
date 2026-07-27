"""
Tests for the admin wallet withdrawal path.

Two defects are pinned here, both found by the security review of the ledger work:

1. The balance check read wallet.balance (the total) while the debit targeted the
   WITHDRAWABLE bucket, so a request funded by spendable deposits passed the gate and then
   died inside debit().
2. The PayoutRequest row and its ledger debit were written outside a transaction, so when
   the debit did fail the request stayed committed in 'processing' with no matching entry -
   an obligation on paper that reconcile_wallets cannot see and retry_payouts would pay.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from transactions.models import LedgerEntry, Wallet
from users.models import AdminPayoutProfile, BusinessAdmin, PaymentPIN, PayoutRequest

User = get_user_model()


class AdminWithdrawalBucketTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='admin@test.com',
            password='test123',
            full_name='Admin User',
            role=User.Role.BUSINESS_ADMIN,
        )
        BusinessAdmin.objects.get_or_create(user=self.user)
        AdminPayoutProfile.objects.create(
            user=self.user,
            bank_name='GTBank',
            bank_code='058',
            account_number='0123456789',
            account_name='Admin User',
        )
        pin = PaymentPIN(user=self.user)
        pin.set_pin('1234')

        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _withdraw(self, amount):
        return self.client.post(
            '/user/admin/wallet/withdraw/',
            {'amount': str(amount), 'pin': '1234'},
            format='json',
        )

    def test_spendable_balance_cannot_fund_a_withdrawal(self):
        """
        The wallet holds ₦5,000, but all of it is deposited funds. wallet.balance says 5000
        and withdrawable_balance says 0 - the gate must read the latter.
        """
        self.wallet.credit(
            Decimal('5000.00'),
            source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        response = self._withdraw(Decimal('1000.00'))

        self.assertEqual(response.status_code, 400)
        self.assertIn('Insufficient balance', response.data['message'])

    @patch('transactions.models.Wallet.debit')
    def test_a_failing_debit_leaves_no_payout_request_behind(self, mock_debit):
        """
        Pins the atomic block rather than the balance gate: the debit is forced to fail
        after the gate has already passed, which is what a concurrent withdrawal draining
        the bucket looks like. Without the transaction the PayoutRequest stays committed in
        'processing' with nothing debited against it.
        """
        mock_debit.side_effect = ValueError('Insufficient withdrawable balance')
        self.wallet.credit(Decimal('5000.00'), source='Commission')

        response = self._withdraw(Decimal('1000.00'))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PayoutRequest.objects.filter(user=self.user).exists())

    @patch('users.services.payout_service.PayoutService.process_external_transfer')
    def test_withdrawable_balance_funds_a_withdrawal(self, mock_transfer):
        mock_transfer.return_value = (True, 'TRF_test')
        self.wallet.credit(Decimal('5000.00'), source='Commission')

        response = self._withdraw(Decimal('1000.00'))

        self.assertEqual(response.status_code, 200)
        payout = PayoutRequest.objects.get(user=self.user)
        self.assertEqual(payout.amount, Decimal('1000.00'))
        self.assertTrue(
            LedgerEntry.objects.filter(
                payout_request=payout, direction=LedgerEntry.Direction.DEBIT
            ).exists()
        )
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('4000.00'))

    @patch('users.services.payout_service.PayoutService.process_external_transfer')
    def test_a_mixed_wallet_can_only_withdraw_the_withdrawable_part(self, mock_transfer):
        """
        The case the old check got wrong: ₦6,000 total, only ₦1,000 of it withdrawable.
        wallet.balance would have waved through anything up to ₦6,000.
        """
        mock_transfer.return_value = (True, 'TRF_test')
        self.wallet.credit(
            Decimal('5000.00'),
            source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )
        self.wallet.credit(Decimal('1000.00'), source='Commission')
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('6000.00'))

        too_much = self._withdraw(Decimal('2000.00'))
        self.assertEqual(too_much.status_code, 400)
        # Specifically the gate's message: reaching debit() and being rejected there would
        # also give a 400, so asserting the status alone would not pin the gate.
        self.assertIn('Insufficient balance', too_much.data['message'])
        self.assertFalse(PayoutRequest.objects.filter(user=self.user).exists())

        allowed = self._withdraw(Decimal('1000.00'))
        self.assertEqual(allowed.status_code, 200)


class RetryPayoutLedgerGuardTests(TestCase):
    """
    Defence in depth behind the transaction: if a payout row somehow exists with no ledger
    debit, retrying it would send money the wallet still believes it holds.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='retry@test.com', password='test123', full_name='Retry User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('5000.00'), source='Commission')

    def _run_retry(self, queryset):
        from django.contrib.admin.sites import AdminSite
        from users.admin import PayoutRequestAdmin

        payout_admin = PayoutRequestAdmin(PayoutRequest, AdminSite())
        request = type('R', (), {})()
        messages = []
        payout_admin.message_user = lambda req, msg, level=None: messages.append((level, msg))
        payout_admin.retry_payouts(request, queryset)
        return messages

    def _debit_for(self, payout):
        self.wallet.debit(
            payout.amount,
            source=f'Withdrawal {payout.reference}',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            entry_type=LedgerEntry.EntryType.WITHDRAWAL,
            idempotency_key=f'withdrawal-{payout.reference}',
            payout_request=payout,
        )

    @patch('users.services.payout_service.PayoutService.process_external_transfer')
    def test_a_payout_with_no_ledger_debit_is_not_retried(self, mock_transfer):
        orphan = PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            reference='ADM-ORPHAN',
            status='processing',
        )

        messages = self._run_retry(PayoutRequest.objects.filter(pk=orphan.pk))

        mock_transfer.assert_not_called()
        self.assertTrue(any('no outstanding ledger debit' in msg for _, msg in messages))

    @patch('users.services.payout_service.PayoutService.process_external_transfer')
    def test_an_already_reversed_payout_is_not_retried(self, mock_transfer):
        """
        The case an existence check waves through: Paystack rejected the transfer, the
        wallet was refunded, and the row was left in 'processing'. It has a debit, but the
        money is back - retrying would send it twice.
        """
        payout = PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            reference='ADM-REVERSED',
            status='processing',
        )
        self._debit_for(payout)
        self.wallet.credit(
            Decimal('1000.00'),
            source=f'Refund for failed withdrawal {payout.reference}',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            entry_type=LedgerEntry.EntryType.WITHDRAWAL_REVERSAL,
            idempotency_key=f'withdrawal-reversal-{payout.reference}',
            payout_request=payout,
        )

        messages = self._run_retry(PayoutRequest.objects.filter(pk=payout.pk))

        mock_transfer.assert_not_called()
        self.assertTrue(any('already been refunded' in msg for _, msg in messages))

    @patch('users.services.payout_service.PayoutService.process_external_transfer')
    def test_a_payout_older_than_the_ledger_is_still_retryable(self, mock_transfer):
        """
        backfill_ledger never reconstructs per-payout entries, so historical payouts have
        nothing linked to them. Blocking those would disable the retry action for exactly
        the old failures it exists to fix.
        """
        mock_transfer.return_value = (True, 'TRF_test')
        legacy = PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            reference='ADM-LEGACY',
            status='failed',
        )
        # created_at is auto_now_add, so push it behind the ledger explicitly.
        earliest = LedgerEntry.objects.order_by('created_at').first().created_at
        PayoutRequest.objects.filter(pk=legacy.pk).update(
            created_at=earliest - timedelta(days=30)
        )
        legacy.refresh_from_db()

        self._run_retry(PayoutRequest.objects.filter(pk=legacy.pk))

        mock_transfer.assert_called_once()

    @patch('users.services.payout_service.PayoutService.process_external_transfer')
    def test_a_properly_debited_payout_is_retried(self, mock_transfer):
        mock_transfer.return_value = (True, 'TRF_test')
        payout = PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            reference='ADM-GOOD',
            status='failed',
        )
        self.wallet.debit(
            Decimal('1000.00'),
            source=f'Withdrawal {payout.reference}',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            entry_type=LedgerEntry.EntryType.WITHDRAWAL,
            idempotency_key=f'withdrawal-{payout.reference}',
            payout_request=payout,
        )

        self._run_retry(PayoutRequest.objects.filter(pk=payout.pk))

        mock_transfer.assert_called_once()
