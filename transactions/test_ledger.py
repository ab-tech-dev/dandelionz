"""
Tests for the append-only ledger that backs every wallet movement.

The invariant these protect: Wallet.balance / spendable_balance / withdrawable_balance are
caches, and they must always agree with the sum of LedgerEntry rows. Anything that can make
those disagree is a money bug.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, models
from django.test import TestCase
from django.utils import timezone

from transactions.models import LedgerEntry, Wallet, WalletHold, WalletTransaction

User = get_user_model()


def bucket_sum(wallet, bucket):
    """Recompute a bucket balance from ledger entries alone, ignoring the cached column."""
    entries = LedgerEntry.objects.filter(wallet=wallet, bucket=bucket)
    total = Decimal('0.00')
    for entry in entries:
        total += entry.signed_amount
    return total.quantize(Decimal('0.01'))


class LedgerCreditDebitTests(TestCase):
    """Core credit/debit behaviour and bucket routing."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='ledger@test.com',
            password='test123',
            full_name='Ledger User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_credit_defaults_to_withdrawable_bucket(self):
        """Historical callers pass no bucket; their money must stay withdrawable."""
        self.wallet.credit(Decimal('500.00'), source='Refund abc123')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('500.00'))
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(self.wallet.balance, Decimal('500.00'))

    def test_deposit_credits_spendable_and_never_withdrawable(self):
        """A Paystack deposit must not become cash-out-able."""
        self.wallet.credit(
            Decimal('2000.00'),
            source='Wallet deposit DEP-1',
            bucket=LedgerEntry.Bucket.SPENDABLE,
            entry_type=LedgerEntry.EntryType.DEPOSIT,
        )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('2000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('0.00'))

    def test_withdrawal_cannot_touch_deposited_funds(self):
        """
        The core anti-laundering guarantee: money that arrived as a card deposit cannot
        leave as a bank transfer, even when the total balance looks sufficient.
        """
        self.wallet.credit(
            Decimal('5000.00'),
            source='Wallet deposit DEP-2',
            bucket=LedgerEntry.Bucket.SPENDABLE,
        )

        with self.assertRaises(ValueError) as ctx:
            self.wallet.debit(
                Decimal('1000.00'),
                source='Withdrawal WTH-1',
                bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            )

        self.assertIn('withdrawable', str(ctx.exception).lower())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('5000.00'))

    def test_unbucketed_debit_spends_deposits_before_earnings(self):
        """Checkout drains SPENDABLE first so the withdrawable pool stays as small as possible."""
        self.wallet.credit(Decimal('300.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('700.00'), source='Refund', bucket=LedgerEntry.Bucket.WITHDRAWABLE)

        self.wallet.debit(Decimal('500.00'), source='Order payment ORD-1')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('0.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('500.00'))
        self.assertEqual(self.wallet.balance, Decimal('500.00'))

    def test_debit_spanning_both_buckets_writes_one_entry_per_bucket(self):
        """A split debit must be traceable to each bucket it drew from."""
        self.wallet.credit(Decimal('300.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('700.00'), source='Refund', bucket=LedgerEntry.Bucket.WITHDRAWABLE)

        entries = self.wallet.debit(Decimal('500.00'), source='Order payment ORD-2')

        self.assertEqual(len(entries), 2)
        by_bucket = {e.bucket: e.amount for e in entries}
        self.assertEqual(by_bucket[LedgerEntry.Bucket.SPENDABLE], Decimal('300.00'))
        self.assertEqual(by_bucket[LedgerEntry.Bucket.WITHDRAWABLE], Decimal('200.00'))

    def test_debit_beyond_total_balance_raises_and_changes_nothing(self):
        self.wallet.credit(Decimal('100.00'), source='Refund')

        with self.assertRaises(ValueError):
            self.wallet.debit(Decimal('250.00'), source='Order payment')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('100.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('100.00'))

    def test_negative_movement_is_rejected(self):
        with self.assertRaises(ValueError):
            self.wallet.credit(Decimal('-50.00'), source='Nonsense')

    def test_zero_movement_is_a_silent_no_op(self):
        """
        credit_vendors_for_order computes a zero vendor share for a free or fully
        discounted order item. Raising here would blow up the delivery signal and leave
        the order stuck undelivered, which is what the old tolerant behaviour avoided.
        """
        entries = self.wallet.credit(Decimal('0.00'), source='Zero share')

        self.assertEqual(entries, [])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))
        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), 0)

    def test_balance_always_equals_sum_of_buckets(self):
        """The cached total must never drift from its parts."""
        self.wallet.credit(Decimal('1234.56'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('765.44'), source='Refund')
        self.wallet.debit(Decimal('900.00'), source='Order payment')

        self.wallet.refresh_from_db()
        self.assertEqual(
            self.wallet.balance,
            self.wallet.spendable_balance + self.wallet.withdrawable_balance,
        )

    def test_cached_balances_agree_with_ledger_entries(self):
        """The whole point of the ledger: caches are reproducible from entries alone."""
        self.wallet.credit(Decimal('400.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('600.00'), source='Refund')
        self.wallet.debit(Decimal('550.00'), source='Order payment')

        self.wallet.refresh_from_db()
        self.assertEqual(
            self.wallet.spendable_balance,
            bucket_sum(self.wallet, LedgerEntry.Bucket.SPENDABLE),
        )
        self.assertEqual(
            self.wallet.withdrawable_balance,
            bucket_sum(self.wallet, LedgerEntry.Bucket.WITHDRAWABLE),
        )

    def test_balance_after_snapshot_tracks_the_running_bucket_total(self):
        self.wallet.credit(Decimal('100.00'), source='Refund one')
        self.wallet.credit(Decimal('250.00'), source='Refund two')

        entries = LedgerEntry.objects.filter(
            wallet=self.wallet, bucket=LedgerEntry.Bucket.WITHDRAWABLE
        ).order_by('id')
        self.assertEqual(
            [e.balance_after for e in entries],
            [Decimal('100.00'), Decimal('350.00')],
        )

    def test_legacy_wallet_transaction_row_still_written(self):
        """Existing admin screens and source__icontains dedup checks read this table."""
        self.wallet.credit(Decimal('75.00'), source='Referral bonus for x@y.com')

        txn = WalletTransaction.objects.get(wallet=self.wallet)
        self.assertEqual(txn.transaction_type, WalletTransaction.TransactionType.CREDIT)
        self.assertEqual(txn.amount, Decimal('75.00'))
        self.assertEqual(txn.source, 'Referral bonus for x@y.com')


class LegacyBalanceAdoptionTests(TestCase):
    """
    Wallets that already held money before the ledger existed.

    These simulate the real production state at deploy time: `balance` is populated but both
    bucket columns are still zero, because no ledger entry has ever been written for them.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='legacy@test.com', password='test123', full_name='Legacy User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        # Write the pre-ledger state directly, bypassing credit() - exactly what the old
        # code left behind.
        Wallet.objects.filter(pk=self.wallet.pk).update(
            balance=Decimal('5000.00'),
            spendable_balance=Decimal('0.00'),
            withdrawable_balance=Decimal('0.00'),
        )
        self.wallet.refresh_from_db()

    def test_first_credit_does_not_destroy_a_pre_ledger_balance(self):
        """
        The regression this guards: balance is recomputed as spendable + withdrawable, so
        without adoption a 5,000 wallet earning 100 would end up holding 100.
        """
        self.wallet.credit(Decimal('100.00'), source='Refund')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('5100.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('5100.00'))

    def test_legacy_balance_is_adopted_as_withdrawable(self):
        """Existing balances are all refunds and earnings, so they stay cash-out-able."""
        self.wallet.credit(Decimal('100.00'), source='Refund')

        opening = LedgerEntry.objects.get(
            wallet=self.wallet, entry_type=LedgerEntry.EntryType.OPENING_BALANCE
        )
        self.assertEqual(opening.amount, Decimal('5000.00'))
        self.assertEqual(opening.bucket, LedgerEntry.Bucket.WITHDRAWABLE)

    def test_adoption_happens_only_once(self):
        self.wallet.credit(Decimal('100.00'), source='Refund one')
        self.wallet.credit(Decimal('100.00'), source='Refund two')

        self.assertEqual(
            LedgerEntry.objects.filter(
                wallet=self.wallet, entry_type=LedgerEntry.EntryType.OPENING_BALANCE
            ).count(),
            1,
        )
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('5200.00'))

    def test_legacy_balance_is_withdrawable_immediately(self):
        """A user with pre-existing money must not be blocked from withdrawing it."""
        self.wallet.debit(
            Decimal('5000.00'),
            source='Withdrawal WTH-legacy',
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
        )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('0.00'))

    def test_adoption_survives_an_idempotent_no_op_call(self):
        """
        Adoption must persist even when the triggering credit is skipped as a duplicate.
        The early return path is easy to get wrong: it can drop the adopted balance on the
        floor, leaving the wallet reading zero.
        """
        # Burn the key on a different wallet so the call below short-circuits.
        other_user = User.objects.create_user(
            email='other@test.com', password='test123', full_name='Other User',
        )
        other_wallet, _ = Wallet.objects.get_or_create(user=other_user)
        other_wallet.credit(Decimal('10.00'), source='Refund', idempotency_key='shared-key')

        self.wallet.credit(Decimal('100.00'), source='Refund', idempotency_key='shared-key')

        self.wallet.refresh_from_db()
        # The 100 credit was skipped as a duplicate, but the 5,000 was still adopted.
        self.assertEqual(self.wallet.balance, Decimal('5000.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('5000.00'))


class LedgerIdempotencyTests(TestCase):
    """Repeat delivery of the same event must not move money twice."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='idem@test.com', password='test123', full_name='Idem User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)

    def test_repeat_credit_with_same_key_is_a_no_op(self):
        """This is what protects against a replayed Paystack webhook double-crediting."""
        self.wallet.credit(Decimal('1000.00'), source='Deposit DEP-9', idempotency_key='dep-9')
        self.wallet.credit(Decimal('1000.00'), source='Deposit DEP-9', idempotency_key='dep-9')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('1000.00'))
        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), 1)

    def test_repeat_credit_returns_no_entries_on_the_second_call(self):
        first = self.wallet.credit(Decimal('50.00'), source='Refund', idempotency_key='ref-1')
        second = self.wallet.credit(Decimal('50.00'), source='Refund', idempotency_key='ref-1')

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_movements_without_a_key_are_independent(self):
        """Un-keyed callers must still be able to credit the same amount twice legitimately."""
        self.wallet.credit(Decimal('20.00'), source='Refund')
        self.wallet.credit(Decimal('20.00'), source='Refund')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('40.00'))
        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), 2)

    def test_split_debit_keys_do_not_collide(self):
        """A two-bucket debit writes two rows, so their keys must be distinct."""
        self.wallet.credit(Decimal('100.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('100.00'), source='Refund')

        self.wallet.debit(Decimal('150.00'), source='Order', idempotency_key='order-77')

        keys = list(
            LedgerEntry.objects.filter(direction=LedgerEntry.Direction.DEBIT)
            .values_list('idempotency_key', flat=True)
        )
        self.assertEqual(len(keys), 2)
        self.assertEqual(len(set(keys)), 2)

    def test_replayed_split_debit_does_not_debit_twice(self):
        """
        Regression: the replay guard used to match on idempotency_key, but a split debit
        stores per-leg suffixed keys and never the bare caller key - so the guard never
        matched and a replayed two-bucket debit ran a second time. It now matches on
        operation_key, which every leg shares.
        """
        self.wallet.credit(Decimal('100.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('100.00'), source='Refund')

        self.wallet.debit(Decimal('150.00'), source='Order', idempotency_key='order-88')
        self.wallet.debit(Decimal('150.00'), source='Order', idempotency_key='order-88')

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('50.00'))
        self.assertEqual(
            LedgerEntry.objects.filter(direction=LedgerEntry.Direction.DEBIT).count(), 2
        )

    def test_every_leg_of_one_operation_shares_an_operation_key(self):
        """The admin ledger needs to group a split payment back into a single operation."""
        self.wallet.credit(Decimal('100.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('100.00'), source='Refund')

        self.wallet.debit(Decimal('150.00'), source='Order', idempotency_key='order-99')

        keys = set(
            LedgerEntry.objects.filter(direction=LedgerEntry.Direction.DEBIT)
            .values_list('operation_key', flat=True)
        )
        self.assertEqual(keys, {'order-99'})

    def test_debit_covered_by_one_bucket_produces_a_single_leg(self):
        """A zero-amount leg would inflate the leg count and re-suffix the keys."""
        self.wallet.credit(Decimal('500.00'), source='Refund')

        entries = self.wallet.debit(Decimal('200.00'), source='Order', idempotency_key='single-1')

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].idempotency_key, 'single-1')

    def test_reference_is_recorded_on_the_entry(self):
        self.wallet.credit(Decimal('50.00'), source='Refund', reference='ORD-abc-123')

        entry = LedgerEntry.objects.get(wallet=self.wallet)
        self.assertEqual(entry.reference, 'ORD-abc-123')


class LedgerImmutabilityTests(TestCase):
    """Entries are append-only. Corrections happen by writing a compensating entry."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='immutable@test.com', password='test123', full_name='Immutable User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('100.00'), source='Refund')
        self.entry = LedgerEntry.objects.get(wallet=self.wallet)

    def test_saving_an_existing_entry_raises(self):
        self.entry.amount = Decimal('999.00')
        with self.assertRaises(ValueError) as ctx:
            self.entry.save()
        self.assertIn('append-only', str(ctx.exception))

    def test_deleting_an_entry_raises(self):
        with self.assertRaises(ValueError) as ctx:
            self.entry.delete()
        self.assertIn('append-only', str(ctx.exception))

    def test_negative_amounts_are_rejected_at_the_database(self):
        """Direction carries the sign; a negative amount would corrupt every running total."""
        with self.assertRaises(IntegrityError):
            LedgerEntry.objects.create(
                wallet=self.wallet,
                direction=LedgerEntry.Direction.CREDIT,
                bucket=LedgerEntry.Bucket.WITHDRAWABLE,
                entry_type=LedgerEntry.EntryType.OTHER,
                amount=Decimal('-10.00'),
                balance_after=Decimal('90.00'),
                idempotency_key='negative-test',
            )


class LedgerRetentionTests(TestCase):
    """
    The money trail must outlive the account.

    LedgerEntry.wallet is PROTECT so a hard delete fails loudly rather than silently
    erasing financial history. Account closure anonymises the user instead - see the
    account deletion guards in users/views.py.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='retain@test.com', password='test123', full_name='Retain User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('250.00'), source='Refund')

    def test_hard_deleting_a_user_with_ledger_history_is_refused(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.user.delete()

        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), 1)

    def test_ledger_entries_survive_when_the_user_is_anonymised(self):
        """Anonymising keeps the row, so the entries and their wallet link stay intact."""
        self.user.email = f'deleted-{self.user.pk}@removed.invalid'
        self.user.full_name = 'Deleted User'
        self.user.is_active = False
        self.user.save(update_fields=['email', 'full_name', 'is_active'])

        self.wallet.refresh_from_db()
        self.assertEqual(LedgerEntry.objects.filter(wallet=self.wallet).count(), 1)
        self.assertEqual(self.wallet.balance, Decimal('250.00'))


class WalletHoldTests(TestCase):
    """Holds make split payment safe: reserve up front, release if the card leg never lands."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='hold@test.com', password='test123', full_name='Hold User',
        )
        self.wallet, _ = Wallet.objects.get_or_create(user=self.user)
        self.wallet.credit(Decimal('400.00'), source='Deposit', bucket=LedgerEntry.Bucket.SPENDABLE)
        self.wallet.credit(Decimal('600.00'), source='Refund')

    def _place_hold(self, spendable, withdrawable, reference='HOLD-1'):
        total = spendable + withdrawable
        self.wallet.debit(total, source=f'Order payment {reference}')
        return WalletHold.objects.create(
            wallet=self.wallet,
            reference=reference,
            amount=total,
            spendable_amount=spendable,
            withdrawable_amount=withdrawable,
            expires_at=timezone.now() + timezone.timedelta(minutes=30),
        )

    def test_release_returns_funds_to_their_original_buckets(self):
        """
        An abandoned checkout must not launder deposited money into withdrawable money.
        If it did, a user could deposit, abandon a checkout, and cash out.
        """
        hold = self._place_hold(Decimal('400.00'), Decimal('100.00'))

        hold.release()

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.spendable_balance, Decimal('400.00'))
        self.assertEqual(self.wallet.withdrawable_balance, Decimal('600.00'))

    def test_release_is_idempotent(self):
        hold = self._place_hold(Decimal('100.00'), Decimal('0.00'))

        self.assertTrue(hold.release())
        self.assertFalse(hold.release())

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('1000.00'))

    def test_capture_is_idempotent_and_keeps_the_money_spent(self):
        hold = self._place_hold(Decimal('400.00'), Decimal('100.00'))

        self.assertTrue(hold.capture())
        self.assertFalse(hold.capture())

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('500.00'))

    def test_captured_hold_cannot_later_be_released(self):
        """Otherwise a late webhook could refund money for an order that was really paid."""
        hold = self._place_hold(Decimal('400.00'), Decimal('100.00'))
        hold.capture()

        self.assertFalse(hold.release())

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal('500.00'))

    def test_held_amount_reports_only_live_holds(self):
        self._place_hold(Decimal('100.00'), Decimal('0.00'), reference='HOLD-A')
        captured = self._place_hold(Decimal('50.00'), Decimal('0.00'), reference='HOLD-B')
        captured.capture()

        self.assertEqual(self.wallet.held_amount, Decimal('100.00'))
