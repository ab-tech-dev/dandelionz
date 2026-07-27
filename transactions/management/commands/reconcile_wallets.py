"""
Assert that cached wallet balances still agree with the ledger.

    python3 manage.py reconcile_wallets           # report only
    python3 manage.py reconcile_wallets --fix     # rewrite caches from the ledger

The ledger is the source of truth; Wallet.balance / spendable_balance / withdrawable_balance
are caches maintained alongside it. If they ever diverge, something wrote to a balance
column without going through Wallet.credit/debit, and that is worth knowing about before it
compounds.

Exits non-zero when drift is found, so it can be wired to a cron alert.
"""

from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from transactions.models import LedgerEntry, Wallet

TWO_PLACES = Decimal('0.01')


def all_ledger_totals():
    """
    Recompute every wallet's bucket balances from the ledger in a single query.

    Returns {wallet_id: {bucket: Decimal}}. Done as one grouped aggregate rather than a
    per-wallet scan: the ledger is append-only and never pruned, so a per-wallet Python
    loop gets steadily slower forever and this command is meant to be safe to cron.
    """
    rows = (
        LedgerEntry.objects
        .values('wallet_id', 'bucket', 'direction')
        .annotate(total=Sum('amount'))
    )

    totals = defaultdict(lambda: {
        LedgerEntry.Bucket.SPENDABLE: Decimal('0.00'),
        LedgerEntry.Bucket.WITHDRAWABLE: Decimal('0.00'),
    })
    for row in rows:
        amount = row['total'] or Decimal('0.00')
        if row['direction'] == LedgerEntry.Direction.DEBIT:
            amount = -amount
        totals[row['wallet_id']][row['bucket']] += amount
    return totals


class Command(BaseCommand):
    help = "Check cached wallet balances against the ledger, and optionally repair them."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help="Rewrite cached balances from the ledger where they disagree.",
        )

    def handle(self, *args, **options):
        fix = options['fix']

        checked = 0
        drifted = 0
        repaired = 0

        wallets = Wallet.objects.select_related('user').order_by('id')
        self.stdout.write(f"Reconciling {wallets.count()} wallet(s)...")

        totals = all_ledger_totals()

        for wallet in wallets.iterator():
            checked += 1
            wallet_totals = totals.get(wallet.pk)
            if wallet_totals is None:
                spendable = Decimal('0.00')
                withdrawable = Decimal('0.00')
            else:
                spendable = wallet_totals[LedgerEntry.Bucket.SPENDABLE].quantize(TWO_PLACES)
                withdrawable = wallet_totals[LedgerEntry.Bucket.WITHDRAWABLE].quantize(TWO_PLACES)
            expected_total = (spendable + withdrawable).quantize(TWO_PLACES)

            cached_spendable = Decimal(wallet.spendable_balance).quantize(TWO_PLACES)
            cached_withdrawable = Decimal(wallet.withdrawable_balance).quantize(TWO_PLACES)
            cached_total = Decimal(wallet.balance).quantize(TWO_PLACES)

            agrees = (
                cached_spendable == spendable
                and cached_withdrawable == withdrawable
                and cached_total == expected_total
            )
            if agrees:
                continue

            drifted += 1
            self.stderr.write(self.style.WARNING(
                f"  wallet {wallet.pk} ({wallet.user.email}) drift:\n"
                f"    spendable    cached {cached_spendable} vs ledger {spendable}\n"
                f"    withdrawable cached {cached_withdrawable} vs ledger {withdrawable}\n"
                f"    total        cached {cached_total} vs ledger {expected_total}"
            ))

            if not fix:
                continue

            with transaction.atomic():
                locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
                locked.spendable_balance = spendable
                locked.withdrawable_balance = withdrawable
                locked.balance = expected_total
                locked.save(update_fields=[
                    'balance', 'spendable_balance', 'withdrawable_balance', 'updated_at',
                ])
            repaired += 1
            self.stdout.write(f"    repaired wallet {wallet.pk}")

        self.stdout.write("")
        if drifted == 0:
            self.stdout.write(self.style.SUCCESS(
                f"All {checked} wallet(s) agree with the ledger."
            ))
            return

        if fix:
            self.stdout.write(self.style.SUCCESS(
                f"Repaired {repaired} of {drifted} drifted wallet(s) out of {checked}."
            ))
            return

        self.stdout.write(self.style.ERROR(
            f"{drifted} of {checked} wallet(s) disagree with the ledger. "
            f"Re-run with --fix to rewrite the caches."
        ))
        # Non-zero exit so a scheduled run surfaces as a failure.
        raise SystemExit(1)
