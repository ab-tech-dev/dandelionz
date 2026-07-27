"""
Seed the ledger with opening balances for wallets that predate it.

Run once on the VPS after deploying the ledger:

    python3 manage.py backfill_ledger --dry-run    # see what would happen
    python3 manage.py backfill_ledger

Safe to re-run: each wallet gets at most one OPENING_BALANCE entry, enforced by a unique
idempotency key, so a second run reports zero adopted.

Note this is a convenience, not a correctness requirement. Wallet._adopt_legacy_balance
does the same thing lazily on first touch, so a wallet that gets credited before this runs
is still correct. What the command buys you is doing it all at once, up front, where you can
see the totals - rather than discovering a stale balance months later.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from transactions.models import LedgerEntry, Wallet


class Command(BaseCommand):
    help = "Create OPENING_BALANCE ledger entries for wallets funded before the ledger existed."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Report what would be adopted without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        adopted_count = 0
        skipped_count = 0
        negative_count = 0
        adopted_total = Decimal('0.00')

        wallets = Wallet.objects.select_related('user').order_by('id')
        total = wallets.count()
        self.stdout.write(f"Scanning {total} wallet(s)...")

        for wallet in wallets.iterator():
            key = f"opening-balance-{wallet.pk}"
            if LedgerEntry.objects.filter(idempotency_key=key).exists():
                skipped_count += 1
                continue

            legacy = (
                Decimal(wallet.balance)
                - Decimal(wallet.spendable_balance)
                - Decimal(wallet.withdrawable_balance)
            ).quantize(Decimal('0.01'))

            if legacy < 0:
                # Cached columns already exceed the recorded total. Not something this
                # command should paper over - reconcile_wallets explains it properly.
                negative_count += 1
                self.stderr.write(self.style.WARNING(
                    f"  wallet {wallet.pk} ({wallet.user.email}): buckets exceed balance "
                    f"by {abs(legacy)} - skipped, run reconcile_wallets"
                ))
                continue

            if legacy == 0:
                skipped_count += 1
                continue

            adopted_count += 1
            adopted_total += legacy

            if dry_run:
                self.stdout.write(
                    f"  would adopt {legacy} for {wallet.user.email} (wallet {wallet.pk})"
                )
                continue

            with transaction.atomic():
                locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
                locked._adopt_legacy_balance()

            self.stdout.write(f"  adopted {legacy} for {wallet.user.email}")

        self.stdout.write("")
        verb = "Would adopt" if dry_run else "Adopted"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {adopted_count} wallet(s), total {adopted_total}. "
            f"Skipped {skipped_count} (already done or zero balance)."
        ))
        if negative_count:
            self.stdout.write(self.style.WARNING(
                f"{negative_count} wallet(s) skipped with buckets exceeding balance - "
                f"investigate with: python3 manage.py reconcile_wallets"
            ))
        if dry_run:
            self.stdout.write("Dry run - nothing was written.")
