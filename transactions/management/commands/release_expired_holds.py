"""
Return wallet money held for checkouts that were never completed.

A hold is placed when a split payment starts and resolved when the card leg succeeds or
fails. Neither happens if the customer simply closes the payment page - so without this the
money sits reserved indefinitely, and the customer is locked out of their own balance with
no way to get it back and nothing on screen explaining why.

Idempotent: WalletHold.release() is a no-op on anything already captured or released, and
the ledger credits carry per-hold idempotency keys, so running this twice cannot double-pay.

Intended to run on a schedule (every 10 minutes or so). Safe to run by hand.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from transactions.models import WalletHold


class Command(BaseCommand):
    help = "Release wallet holds whose checkout was abandoned"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Report what would be released without moving any money.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        expired = (
            WalletHold.objects
            .filter(status=WalletHold.Status.HELD, expires_at__lt=now)
            .select_related('wallet', 'wallet__user', 'order')
            .order_by('expires_at')
        )

        total = expired.count()
        if total == 0:
            self.stdout.write("No expired holds.")
            return

        self.stdout.write(f"Found {total} expired hold(s).")

        released = 0
        failed = 0
        for hold in expired.iterator():
            label = (
                f"  {hold.reference} {hold.amount} for {hold.wallet.user.email} "
                f"(expired {hold.expires_at:%Y-%m-%d %H:%M})"
            )

            if dry_run:
                self.stdout.write(f"  would release {label.strip()}")
                continue

            try:
                if hold.release("Checkout abandoned"):
                    released += 1
                    self.stdout.write(self.style.SUCCESS(f"  released {label.strip()}"))
            except Exception as exc:
                # One bad hold must not strand the rest. Report and continue: the next run
                # picks this one up again, since a failed release leaves it HELD.
                failed += 1
                self.stderr.write(self.style.ERROR(
                    f"  FAILED {hold.reference}: {exc}"
                ))

        if dry_run:
            self.stdout.write(f"\nDry run: {total} hold(s) would be released.")
            return

        self.stdout.write(f"\nReleased {released} hold(s).")
        if failed:
            self.stderr.write(self.style.ERROR(
                f"{failed} hold(s) could not be released and remain held. "
                f"They will be retried on the next run."
            ))
            raise SystemExit(1)
