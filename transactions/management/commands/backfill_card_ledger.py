"""
Write ledger rows for card money that moved before the card ledger existed.

Run once on the VPS after deploying it:

    python3 manage.py backfill_card_ledger --dry-run    # see what would be written
    python3 manage.py backfill_card_ledger

Covers card order payments, card installment payments, card delivery fees, and card refunds
(including payments that were refused settlement and returned to the card).

Safe to re-run, and safe to run alongside live traffic: every row has a unique idempotency key
shared with the live hooks (see transactions/external_ledger.py), so a movement is written
exactly once no matter which of them gets there first. A second run reports zero new rows.
It is also the repair tool for any row a live hook failed to write.

Timestamps: rows are dated to when the money actually moved, so date filters and exports
attribute it to the right day. They are never dated before the oldest existing ledger row,
though. The admin payout-retry check treats the oldest ledger row as "when the ledger
started" and refuses to retry payouts after it that have no ledger trail; moving that
boundary earlier would block retries for payouts that predate the ledger.
"""

from collections import Counter, defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand

from transactions import external_ledger as xl
from transactions.models import (
    DeliveryCharge, InstallmentCharge, LedgerEntry, OrderPaymentRefund, Payment, money,
)

Type = LedgerEntry.EntryType


class Command(BaseCommand):
    help = "Create ledger entries for card payments and refunds made before the card ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Report what would be written without writing anything.",
        )

    # -- candidate collection -----------------------------------------------------------

    def _jobs(self):
        """
        Yield (label, rows, record, when_in, when_out) for every card movement.

        `rows` is [(idempotency_key, entry_type, direction, amount), ...] - what the movement
        should have written. `record` writes any of them that are missing.
        """
        # Card order payments. Orders on an installment plan are excluded: their Payment row is
        # created at completion for the plan total and is a record, not a card charge.
        payments = (
            Payment.objects
            .filter(verified=True, status='SUCCESS', amount__gt=0,
                    order__installment_plan__isnull=True)
            .select_related('order__customer')
        )
        for p in payments.iterator():
            yield (
                f"order payment {p.reference}",
                [(xl.key_in(p.reference), Type.CARD_ORDER_PAYMENT, xl.CREDIT, p.amount)],
                lambda p=p: [xl.record_order_card_payment(p)],
                p.paid_at, None,
            )

        charges = (
            InstallmentCharge.objects
            .filter(method=InstallmentCharge.Method.CARD, status=InstallmentCharge.Status.PAID)
            .select_related('plan__order__customer')
        )
        for c in charges.iterator():
            yield (
                f"installment {c.reference}",
                [(xl.key_in(c.reference), Type.CARD_INSTALLMENT_PAYMENT, xl.CREDIT, c.amount)],
                lambda c=c: [xl.record_installment_card_payment(c)],
                c.paid_at, None,
            )

        delivery = (
            DeliveryCharge.objects
            .filter(status=DeliveryCharge.Status.PAID, card_amount__gt=0)
            .select_related('order__customer')
        )
        for d in delivery.iterator():
            yield (
                f"delivery fee {d.reference}",
                [(xl.key_in(d.reference), Type.CARD_DELIVERY_FEE, xl.CREDIT, d.card_amount)],
                lambda d=d: [xl.record_delivery_card_payment(d)],
                d.paid_at, None,
            )

        # Card legs refused settlement and returned to the card.
        refunds = (
            OrderPaymentRefund.objects
            .filter(status=OrderPaymentRefund.Status.PROCESSED)
            .select_related('payment__order__customer', 'order__customer')
        )
        for r in refunds.iterator():
            yield (
                f"order refund {r.reference}",
                [
                    (xl.key_in(r.payment.reference), Type.CARD_ORDER_PAYMENT, xl.CREDIT, r.payment.amount),
                    (xl.key_out(r.reference), Type.CARD_REFUND, xl.DEBIT, r.amount),
                ],
                lambda r=r: xl.record_order_payment_refund(r),
                r.payment.paid_at or r.payment.created_at, r.settled_at,
            )

        # Installment / delivery payments that could not be applied and were returned.
        stranded_i = (
            InstallmentCharge.objects
            .filter(status=InstallmentCharge.Status.REFUNDED)
            .select_related('plan__order__customer')
        )
        for c in stranded_i.iterator():
            order = c.plan.order
            yield (
                f"stranded installment {c.reference}",
                [
                    (xl.key_in(c.reference), Type.CARD_INSTALLMENT_PAYMENT, xl.CREDIT, c.amount),
                    (xl.key_out(c.reference), Type.CARD_REFUND, xl.DEBIT, c.amount),
                ],
                lambda c=c, order=order: xl.record_stranded_card_return(
                    user=order.customer, order=order, entry_type=Type.CARD_INSTALLMENT_PAYMENT,
                    reference=c.reference, amount=c.amount, label='installment'),
                c.created_at, c.updated_at,
            )

        stranded_d = (
            DeliveryCharge.objects
            .filter(status=DeliveryCharge.Status.REFUNDED)
            .select_related('order__customer')
        )
        for d in stranded_d.iterator():
            amount = d.card_amount if d.card_amount and d.card_amount > 0 else d.amount
            yield (
                f"stranded delivery fee {d.reference}",
                [
                    (xl.key_in(d.reference), Type.CARD_DELIVERY_FEE, xl.CREDIT, amount),
                    (xl.key_out(d.reference), Type.CARD_REFUND, xl.DEBIT, amount),
                ],
                lambda d=d, amount=amount: xl.record_stranded_card_return(
                    user=d.order.customer, order=d.order, entry_type=Type.CARD_DELIVERY_FEE,
                    reference=d.reference, amount=amount, label='delivery fee'),
                d.created_at, d.updated_at,
            )

    # -- run ----------------------------------------------------------------------------

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Oldest existing ledger row, read before anything is written. See module docstring.
        ledger_start = (
            LedgerEntry.objects.order_by('created_at')
            .values_list('created_at', flat=True).first()
        )

        scanned = failed = 0
        written = Counter()
        totals = defaultdict(lambda: Decimal('0.00'))

        for label, rows, record, when_in, when_out in self._jobs():
            scanned += 1
            keys = [k for k, *_ in rows]
            existing = set(
                LedgerEntry.objects.filter(idempotency_key__in=keys)
                .values_list('idempotency_key', flat=True)
            )
            missing = [r for r in rows if r[0] not in existing]
            if not missing:
                continue

            if dry_run:
                for _, entry_type, direction, amount in missing:
                    written[(entry_type, direction)] += 1
                    totals[(entry_type, direction)] += money(amount)
                continue

            try:
                entries = record()
            except Exception as exc:  # the recorders never raise; belt and braces
                failed += 1
                self.stderr.write(f"FAILED {label}: {exc}")
                continue

            created = [e for e in entries if e is not None and e.idempotency_key not in existing]
            if len(created) < len(missing):
                failed += 1
                self.stderr.write(f"Could not write every row for {label}")
            for entry in created:
                written[(entry.entry_type, entry.direction)] += 1
                totals[(entry.entry_type, entry.direction)] += entry.amount
                when = when_in if entry.direction == xl.CREDIT else when_out
                # update() bypasses the append-only save() guard; this only sets the date a
                # row is attributed to, once, at creation.
                if when is not None and ledger_start is not None:
                    LedgerEntry.objects.filter(pk=entry.pk).update(
                        created_at=max(when, ledger_start)
                    )

        verb = "Would write" if dry_run else "Wrote"
        self.stdout.write(f"Scanned {scanned} card movement(s).")
        if not written:
            self.stdout.write("Nothing to write - the card ledger is already complete.")
        for (entry_type, direction), count in sorted(written.items()):
            self.stdout.write(
                f"  {verb} {count:>4} x {entry_type} ({direction})  "
                f"total NGN {totals[(entry_type, direction)]:,.2f}"
            )
        if failed:
            self.stdout.write(self.style.WARNING(f"{failed} movement(s) could not be fully written."))
