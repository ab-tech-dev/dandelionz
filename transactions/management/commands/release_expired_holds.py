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

from transactions import wallet_checkout


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

        def on_event(kind, hold, detail=''):
            label = (
                f"{hold.reference} {hold.amount} for {hold.wallet.user.email} "
                f"(expired {hold.expires_at:%Y-%m-%d %H:%M})"
            )
            if kind == 'would_release':
                self.stdout.write(f"  would release {label}")
            elif kind == 'released':
                self.stdout.write(self.style.SUCCESS(f"  released {label}"))
            elif kind == 'failed':
                self.stderr.write(self.style.ERROR(f"  FAILED {hold.reference}: {detail}"))

        # The sweep itself lives in wallet_checkout so the Celery task runs identical logic.
        result = wallet_checkout.sweep_expired_holds(dry_run=dry_run, on_event=on_event)

        if result['total'] == 0:
            self.stdout.write("No expired holds.")
            return

        if dry_run:
            self.stdout.write(f"\nDry run: {result['total']} hold(s) would be released.")
            return

        self.stdout.write(f"\nReleased {result['released']} hold(s).")
        if result['failed']:
            self.stderr.write(self.style.ERROR(
                f"{result['failed']} hold(s) could not be released and remain held. "
                f"They will be retried on the next run."
            ))
            raise SystemExit(1)
