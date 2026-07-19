"""
Tests for account closure guards and anonymisation.

The behaviour being protected: a user must not be able to close their account while money
is still in their wallet, and closing must not destroy the ledger.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from transactions.models import LedgerEntry, Wallet, WalletHold
from django.utils import timezone
from users.models import PayoutRequest
from users.services.account_closure import (
    BLOCKED_ACTIVE_HOLD,
    BLOCKED_PENDING_WITHDRAWAL,
    BLOCKED_SPENDABLE,
    BLOCKED_WITHDRAWABLE,
    check_can_close,
    close_account,
)

User = get_user_model()


class AccountClosureGuardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='closing@test.com', password='test123', full_name='Closing User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_empty_wallet_can_close(self):
        allowed, blocker = check_can_close(self.user)

        self.assertTrue(allowed)
        self.assertIsNone(blocker)

    def test_withdrawable_balance_blocks_closure_and_says_to_withdraw(self):
        self.wallet.credit(Decimal('4500.00'), source='Refund')

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_WITHDRAWABLE)
        self.assertIn('Withdraw it to your bank', blocker['message'])
        self.assertIn('4,500.00', blocker['message'])

    def test_deposited_balance_blocks_closure_and_does_not_offer_a_bank_withdrawal(self):
        """
        Deposits must never be routed to a bank, and account closure is the most
        attractive moment to try it - the message must not suggest that route.
        """
        self.wallet.credit(
            Decimal('2000.00'),
            source='Wallet deposit',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_SPENDABLE)
        self.assertIn('refund to your original payment card', blocker['message'])
        self.assertNotIn('Withdraw it to your bank', blocker['message'])

    def test_withdrawable_is_reported_before_spendable(self):
        """With both, the actionable one the user can resolve themselves comes first."""
        self.wallet.credit(Decimal('100.00'), source='Refund')
        self.wallet.credit(
            Decimal('100.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_WITHDRAWABLE)

    def test_live_wallet_hold_blocks_closure(self):
        """An in-flight checkout is holding funds that are not yet spent or released."""
        WalletHold.objects.create(
            wallet=self.wallet,
            reference='HOLD-CLOSE-1',
            amount=Decimal('300.00'),
            spendable_amount=Decimal('300.00'),
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_ACTIVE_HOLD)

    def test_released_hold_does_not_block_closure(self):
        hold = WalletHold.objects.create(
            wallet=self.wallet,
            reference='HOLD-CLOSE-2',
            amount=Decimal('300.00'),
            status=WalletHold.Status.RELEASED,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

        allowed, _ = check_can_close(self.user)

        self.assertTrue(allowed)

    def test_pending_withdrawal_blocks_closure(self):
        """Money already on its way out still belongs to them until it lands or fails."""
        PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            account_name='Closing User',
            reference='WTH-CLOSING1',
            status='pending',
        )

        allowed, blocker = check_can_close(self.user)

        self.assertFalse(allowed)
        self.assertEqual(blocker['reason'], BLOCKED_PENDING_WITHDRAWAL)

    def test_completed_withdrawal_does_not_block_closure(self):
        PayoutRequest.objects.create(
            user=self.user,
            amount=Decimal('1000.00'),
            bank_name='GTBank',
            account_number='0123456789',
            account_name='Closing User',
            reference='WTH-CLOSING2',
            status='successful',
        )

        allowed, _ = check_can_close(self.user)

        self.assertTrue(allowed)


class AccountAnonymisationTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='anon@test.com', password='test123', full_name='Anon User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('500.00'), source='Refund')
        self.wallet.debit(
            Decimal('500.00'),
            source='Withdrawal WTH-X',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
        )

    def test_closing_keeps_the_ledger_intact(self):
        """The whole point of anonymising rather than deleting."""
        entry_count = LedgerEntry.objects.filter(wallet=self.wallet).count()

        close_account(self.user)

        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), entry_count)

    def test_closing_removes_identifying_data(self):
        close_account(self.user)

        self.user.refresh_from_db()
        self.assertNotIn('anon@test.com', self.user.email)
        self.assertTrue(self.user.email.endswith('@removed.invalid'))
        self.assertEqual(self.user.full_name, 'Closed Account')
        self.assertFalse(self.user.is_active)

    def test_closed_account_cannot_log_in_with_the_old_password(self):
        close_account(self.user)

        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('test123'))
        self.assertFalse(self.user.has_usable_password())

    def test_two_closed_accounts_do_not_collide_on_email(self):
        other = User.objects.create_user(
            email='anon2@test.com', password='test123', full_name='Anon Two',
        )

        close_account(self.user)
        close_account(other)

        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertNotEqual(self.user.email, other.email)

    def test_the_original_email_can_be_reused_after_closure(self):
        """Someone closing their account should be able to sign up again later."""
        close_account(self.user)

        reused = User.objects.create_user(
            email='anon@test.com', password='new123', full_name='Returning User',
        )
        self.assertEqual(reused.email, 'anon@test.com')
