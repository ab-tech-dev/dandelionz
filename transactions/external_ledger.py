"""
Recording card money in the finance ledger.

The ledger is built around wallets: every row moves one of a user's two wallet buckets and
carries the bucket's balance afterwards. A card payment moves no wallet - the money goes from
the customer's card to Paystack and never enters a balance - so it used to leave no trace in
the ledger at all, and the finance screen could not account for a naira that came in by card.

This module writes those movements as rows in the same table, in a third bucket,
LedgerEntry.Bucket.EXTERNAL:

    CREDIT  card order payment / card installment / card delivery fee   (money in)
    DEBIT   card refund                                                  (money out)

An EXTERNAL row is attached to the payer's wallet so it has an owner to show, search and
export, but it NEVER changes a balance. That is why this is a separate writer rather than
Wallet.credit()/debit(): those mutate balances, these must not. Consequences, all
deliberate:

  * balance_after is 0.00 - a wallet balance is meaningless for money that never entered one.
  * reconcile_wallets ignores the bucket, so cached wallet balances still agree with the ledger.
  * Wallet deposits, wallet-paid orders, withdrawals and refunds-to-wallet are NOT duplicated
    here. They already write ordinary wallet rows; only money that bypasses wallets is added.

Every write is idempotent (a unique key per movement) and best-effort: a payment can be
reported twice, by the webhook and by the verify endpoint, and a failure to write a ledger
row must never fail or roll back the payment itself. A row that could not be written is
repaired by `manage.py backfill_card_ledger`.
"""

import logging

from django.db import transaction

from transactions.models import LedgerEntry, Wallet, money

logger = logging.getLogger(__name__)

CREDIT = LedgerEntry.Direction.CREDIT
DEBIT = LedgerEntry.Direction.DEBIT
EXTERNAL = LedgerEntry.Bucket.EXTERNAL
Type = LedgerEntry.EntryType


def key_in(reference):
    """Idempotency key for the money-in row of a Paystack reference."""
    return f"card-in-{reference}"


def key_out(reference):
    """Idempotency key for the money-out row of a refund (or stranded charge) reference."""
    return f"card-out-{reference}"


def _record(*, user, direction, entry_type, amount, reference, description,
            idempotency_key, order=None, payment=None, metadata=None):
    """
    Write one EXTERNAL row, once. Returns the entry (new or existing), or None if there was
    nothing to record or the write failed. Never raises.
    """
    amount = money(amount or 0)
    if user is None or amount <= 0 or not idempotency_key:
        return None
    try:
        # A savepoint when called inside a payment transaction, so a failure here cannot
        # poison the surrounding atomic block.
        with transaction.atomic():
            wallet, _ = Wallet.objects.get_or_create(user=user)
            entry, _ = LedgerEntry.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults=dict(
                    wallet=wallet,
                    direction=direction,
                    bucket=EXTERNAL,
                    entry_type=entry_type,
                    amount=amount,
                    balance_after=money(0),
                    operation_key=idempotency_key,
                    reference=str(reference or '')[:100],
                    description=str(description or '')[:255],
                    order=order,
                    payment=payment,
                    metadata={'channel': 'CARD', 'gateway': 'Paystack', **(metadata or {})},
                ),
            )
        return entry
    except Exception:
        logger.exception("Could not record card movement %s in the ledger", idempotency_key)
        return None


# ---------------------------------------------------------------------------------------
# Money in
# ---------------------------------------------------------------------------------------

def record_order_card_payment(payment):
    """The card leg of an order. A fully wallet-funded order has a zero card leg: no row."""
    order = payment.order
    return _record(
        user=order.customer,
        direction=CREDIT,
        entry_type=Type.CARD_ORDER_PAYMENT,
        amount=payment.amount,
        reference=payment.reference,
        description=f"Card payment for order {order.order_id}",
        idempotency_key=key_in(payment.reference),
        order=order,
        payment=payment,
        metadata={'kind': 'order'},
    )


def record_installment_card_payment(charge):
    """A card installment payment (the wallet-paid ones already write an ORDER_PAYMENT row)."""
    order = charge.plan.order
    return _record(
        user=order.customer,
        direction=CREDIT,
        entry_type=Type.CARD_INSTALLMENT_PAYMENT,
        amount=charge.amount,
        reference=charge.reference,
        description=f"Card installment payment for order {order.order_id}",
        idempotency_key=key_in(charge.reference),
        order=order,
        metadata={'kind': 'installment', 'plan_id': charge.plan_id},
    )


def record_delivery_card_payment(charge):
    """The card leg of a delivery fee. The wallet leg is already a wallet row."""
    order = charge.order
    return _record(
        user=order.customer,
        direction=CREDIT,
        entry_type=Type.CARD_DELIVERY_FEE,
        amount=charge.card_amount,
        reference=charge.reference,
        description=f"Card payment of delivery fee for order {order.order_id}",
        idempotency_key=key_in(charge.reference),
        order=order,
        metadata={'kind': 'delivery'},
    )


# ---------------------------------------------------------------------------------------
# Money out (card refunds)
# ---------------------------------------------------------------------------------------

def record_order_payment_refund(refund):
    """
    A card order leg returned to the card (OrderPaymentRefund, once Paystack settles it).

    The inbound side is written too: the payment was refused settlement, so the normal
    "card in" row was never created, and a refund with no matching payment would show money
    leaving that never arrived.
    """
    payment = refund.payment
    order = refund.order or payment.order
    entries = [
        record_order_card_payment(payment),
        _record(
            user=order.customer,
            direction=DEBIT,
            entry_type=Type.CARD_REFUND,
            amount=refund.amount,
            reference=refund.reference,
            description=f"Card refund for order {order.order_id}: {refund.reason or 'order could not be completed'}",
            idempotency_key=key_out(refund.reference),
            order=order,
            payment=payment,
            metadata={'kind': 'order', 'payment_reference': payment.reference},
        ),
    ]
    return [e for e in entries if e is not None]


def record_stranded_card_return(*, user, order, entry_type, reference, amount, label):
    """
    A payment that landed on a charge we could no longer honour and was returned to the card
    (installment or delivery). Writes the money that arrived and the refund that sent it back.
    `reference` is the charge's Paystack reference; `label` reads "installment" / "delivery fee".
    """
    entries = [
        _record(
            user=user,
            direction=CREDIT,
            entry_type=entry_type,
            amount=amount,
            reference=reference,
            description=f"Card payment of {label} for order {order.order_id} (could not be applied)",
            idempotency_key=key_in(reference),
            order=order,
            metadata={'kind': label, 'stranded': True},
        ),
        _record(
            user=user,
            direction=DEBIT,
            entry_type=Type.CARD_REFUND,
            amount=amount,
            reference=reference,
            description=f"Card refund of {label} for order {order.order_id} (returned to card)",
            idempotency_key=key_out(reference),
            order=order,
            metadata={'kind': label, 'stranded': True},
        ),
    ]
    return [e for e in entries if e is not None]
