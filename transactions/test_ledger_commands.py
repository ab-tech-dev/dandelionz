"""
Tests for the ledger management commands.

These run against the state the VPS will actually be in at deploy time: wallets holding a
balance with no ledger entries behind it.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from transactions.models import LedgerEntry, Wallet

User = get_user_model()


def make_legacy_wallet(email, balance):
    """A wallet in pre-ledger shape: balance set, buckets empty, no entries."""
    user = User.objects.create_user(email=email, password='test123', full_name='Legacy')
    wallet, _ = Wallet.objects.get_or_create(user=user)
    Wallet.objects.filter(pk=wallet.pk).update(
        balance=Decimal(balance),
        spendable_balance=Decimal('0.00'),
        withdrawable_balance=Decimal('0.00'),
    )
    wallet.refresh_from_db()
    return wallet


class BackfillLedgerTests(TestCase):

    def test_adopts_legacy_balances_into_the_withdrawable_bucket(self):
        wallet = make_legacy_wallet('a@test.com', '2500.00')

        call_command('backfill_ledger', stdout=StringIO())

        wallet.refresh_from_db()
        self.assertEqual(wallet.withdrawable_balance, Decimal('2500.00'))
        self.assertEqual(wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(wallet.balance, Decimal('2500.00'))

    def test_writes_one_opening_entry_per_wallet(self):
        make_legacy_wallet('b@test.com', '100.00')
        make_legacy_wallet('c@test.com', '200.00')

        call_command('backfill_ledger', stdout=StringIO())

        openings = LedgerEntry.objects.filter(
            entry_type=LedgerEntry.EntryType.OPENING_BALANCE
        )
        self.assertEqual(openings.count(), 2)

    def test_is_safe_to_run_twice(self):
        """The user runs this by hand on the VPS; a double-run must not double the money."""
        wallet = make_legacy_wallet('d@test.com', '900.00')

        call_command('backfill_ledger', stdout=StringIO())
        call_command('backfill_ledger', stdout=StringIO())

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal('900.00'))
        self.assertEqual(
            LedgerEntry.objects.filter(
                wallet=wallet, entry_type=LedgerEntry.EntryType.OPENING_BALANCE
            ).count(),
            1,
        )

    def test_dry_run_writes_nothing(self):
        wallet = make_legacy_wallet('e@test.com', '400.00')

        out = StringIO()
        call_command('backfill_ledger', '--dry-run', stdout=out)

        wallet.refresh_from_db()
        self.assertEqual(wallet.withdrawable_balance, Decimal('0.00'))
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertIn('Dry run', out.getvalue())

    def test_skips_zero_balance_wallets(self):
        make_legacy_wallet('f@test.com', '0.00')

        call_command('backfill_ledger', stdout=StringIO())

        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_leaves_already_ledgered_wallets_alone(self):
        """A wallet credited after the ledger shipped is already consistent."""
        user = User.objects.create_user(
            email='g@test.com', password='test123', full_name='Modern',
        )
        wallet, _ = Wallet.objects.get_or_create(user=user)
        wallet.credit(Decimal('300.00'), source='Refund')

        call_command('backfill_ledger', stdout=StringIO())

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal('300.00'))
        self.assertEqual(
            LedgerEntry.objects.filter(
                entry_type=LedgerEntry.EntryType.OPENING_BALANCE
            ).count(),
            0,
        )


class ReconcileWalletsTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='rec@test.com', password='test123', full_name='Reconcile',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_reports_success_when_caches_agree(self):
        self.wallet.credit(Decimal('500.00'), source='Refund')

        out = StringIO()
        call_command('reconcile_wallets', stdout=out)

        self.assertIn('agree with the ledger', out.getvalue())

    def test_detects_a_cache_written_behind_the_ledgers_back(self):
        """Someone setting wallet.balance directly is exactly what this must catch."""
        self.wallet.credit(Decimal('500.00'), source='Refund')
        Wallet.objects.filter(pk=self.wallet.pk).update(balance=Decimal('9999.00'))

        with self.assertRaises(SystemExit):
            call_command('reconcile_wallets', stdout=StringIO(), stderr=StringIO())

    def test_fix_rewrites_caches_from_the_ledger(self):
        self.wallet.credit(Decimal('500.00'), source='Refund')
        Wallet.objects.filter(pk=self.wallet.pk).update(
            balance=Decimal('9999.00'),
            withdrawable_balance=Decimal('9999.00'),
        )

        call_command('reconcile_wallets', '--fix', stdout=StringIO(), stderr=StringIO())

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('500.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('500.00'))

    def test_fix_exits_cleanly_after_repairing(self):
        """A repair run must not exit non-zero, or a cron --fix would page every time."""
        self.wallet.credit(Decimal('100.00'), source='Refund')
        Wallet.objects.filter(pk=self.wallet.pk).update(balance=Decimal('7.00'))

        call_command('reconcile_wallets', '--fix', stdout=StringIO(), stderr=StringIO())
