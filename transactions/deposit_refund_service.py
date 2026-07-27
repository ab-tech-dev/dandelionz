"""
Returning deposited wallet funds to the card they came from.

Deposits land in the SPENDABLE bucket: usable at checkout, never withdrawable to a bank.
That asymmetry is deliberate - it is what stops the wallet turning a stolen card into a
bank transfer - but it also means a normal withdrawal cannot return this money. A refund to
source is the only exit, which is why account closure blocks on a spendable balance and
tells the user to refund to their card.

Ordering: deposits are consumed newest first. Paystack will not refund arbitrarily old
transactions, so spending the most recent ones gives the request the best chance of being
accepted. FIFO would burn the oldest, most refund-resistant deposits first and strand the
user with a balance they cannot get out.

Timing: the wallet is debited when the refund is *requested*, before Paystack is called.
Debiting on settlement instead would leave the money spendable at checkout while the refund
was in flight, and we would pay it out twice.
"""

import logging
from decimal import Decimal

from django.db import transaction

from transactions import references
from transactions.models import (
    DepositRefund,
    LedgerEntry,
    Wallet,
    WalletDeposit,
    money,
)
from transactions.paystack import Paystack

logger = logging.getLogger(__name__)


class RefundError(Exception):
    """A refund that cannot be honoured. The message is safe to show the user."""


def refundable_deposits(user):
    """
    Successful deposits that still have money on them, newest first.

    Deposits without a paystack_transaction_id are excluded: that id is what the refund
    call needs, and it has only been captured since deposits shipped. A deposit missing it
    cannot be refunded to source and needs an operator.
    """
    deposits = (
        WalletDeposit.objects
        .filter(user=user, status=WalletDeposit.Status.SUCCESS, verified=True)
        .exclude(paystack_transaction_id='')
        .order_by('-paid_at', '-created_at')
        .prefetch_related('refunds')
    )
    return [d for d in deposits if d.refundable_amount > 0]


def total_refundable(user):
    """The most that could be refunded to source right now."""
    total = sum((d.refundable_amount for d in refundable_deposits(user)), Decimal('0.00'))
    return money(total)


def plan_refund(user, amount):
    """
    Split `amount` across deposits, newest first.

    Returns [(deposit, amount)]. Raises RefundError if the deposits cannot cover it - which
    happens when a spendable balance came from somewhere other than a refundable deposit,
    or from deposits too old to have a transaction id recorded.
    """
    amount = money(amount)
    remaining = amount
    plan = []

    for deposit in refundable_deposits(user):
        if remaining <= 0:
            break
        take = min(deposit.refundable_amount, remaining)
        if take <= 0:
            continue
        plan.append((deposit, money(take)))
        remaining = money(remaining - take)

    if remaining > 0:
        raise RefundError(
            f"Only ₦{money(amount - remaining):,.2f} of that can be refunded to your card. "
            f"The rest of your deposited balance is from top-ups that can no longer be "
            f"returned to source - please contact support."
        )

    return plan


def request_refund(user, amount, requested_by=None):
    """
    Debit the spendable bucket and ask Paystack to return the money to source.

    The debit and the DepositRefund rows commit together, before any network call. Paystack
    is then called per allocation; a rejection reverses that allocation's debit via
    mark_as_failed, so a partial failure leaves the user's balance correct rather than
    silently short.

    Returns (refunds, errors).
    """
    amount = money(amount)
    if amount <= 0:
        raise RefundError("Refund amount must be greater than zero.")

    with transaction.atomic():
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)

        if wallet.spendable_balance < amount:
            raise RefundError(
                f"You have ₦{wallet.spendable_balance:,.2f} in deposited funds. "
                f"Only deposited funds can be refunded to a card - earnings and refunds "
                f"are withdrawn to your bank instead."
            )

        # Built inside the lock: another refund committing between the plan and the debit
        # would otherwise let both allocate the same deposit.
        plan = plan_refund(user, amount)

        refunds = []
        for deposit, part in plan:
            refund = DepositRefund.objects.create(
                user=user,
                deposit=deposit,
                reference=references.new_refund_reference(),
                amount=part,
                requested_by=requested_by,
            )
            wallet.debit(
                part,
                source=f"Refund to card {refund.reference}",
                bucket=LedgerEntry.Bucket.SPENDABLE,
                entry_type=LedgerEntry.EntryType.DEPOSIT_REVERSAL,
                idempotency_key=f"deposit-refund-{refund.reference}",
                reference=refund.reference,
            )
            refunds.append(refund)

    # Network calls happen after the money has been accounted for, never inside the lock.
    errors = []
    for refund in refunds:
        try:
            paystack = Paystack()
            resp = paystack.refund(
                transaction=refund.deposit.paystack_transaction_id,
                amount=refund.amount,
                merchant_note=f"Wallet deposit refund {refund.reference}",
            )
        except Exception as exc:
            logger.error(
                f"Paystack refund failed for {refund.reference} "
                f"(deposit {refund.deposit.reference}): {exc}",
                exc_info=True,
            )
            refund.mark_as_failed(f"Could not start the refund: {exc}")
            errors.append(str(exc))
            continue

        data = resp.get("data") or {}
        refund.status = DepositRefund.Status.PROCESSING
        refund.paystack_refund_id = str(data.get("id") or "")
        refund.save(update_fields=['status', 'paystack_refund_id', 'updated_at'])
        logger.info(
            f"Refund {refund.reference} accepted by Paystack for deposit "
            f"{refund.deposit.reference} ({refund.amount})"
        )

    return refunds, errors


def settle_refund_webhook(event, data):
    """
    Apply a refund.processed / refund.failed webhook.

    Paystack's refund payloads quote the *original transaction's* reference, not ours, and
    carry no refund reference we issued - so the refund is located by the deposit it came
    from. Where a deposit has several refunds in flight, the one matching this amount and
    still unsettled is chosen; that is the narrowest match the payload supports.

    Returns (handled, detail). `detail` is set when nothing was applied, so the webhook
    view can mark the event IGNORED rather than silently PROCESSED.
    """
    # Paystack sends transaction_reference on refund events, but nests the transaction
    # object on some payload versions. Check the flat field first, then the nested one.
    transaction_reference = data.get("transaction_reference")
    if not transaction_reference:
        nested = data.get("transaction")
        if isinstance(nested, dict):
            transaction_reference = nested.get("reference")

    if not transaction_reference:
        return False, "refund webhook carried no transaction reference"

    deposit = WalletDeposit.objects.filter(reference=transaction_reference).first()
    if deposit is None:
        return False, f"no wallet deposit for refunded transaction {transaction_reference}"

    amount = data.get("amount")
    candidates = deposit.refunds.filter(
        status__in=[DepositRefund.Status.PENDING, DepositRefund.Status.PROCESSING]
    ).order_by('created_at')

    refund = None
    if amount is not None:
        naira = money(Decimal(str(amount)) / 100)
        refund = candidates.filter(amount=naira).first()
    if refund is None:
        refund = candidates.first()

    if refund is None:
        return False, f"no unsettled refund for deposit {deposit.reference}"

    if event == "refund.processed":
        refund.mark_as_processed(data.get("id") or "")
        logger.info(f"Refund {refund.reference} settled by Paystack")
        return True, None

    if event in ("refund.failed", "refund.pending"):
        if event == "refund.pending":
            return True, None
        refund.mark_as_failed(data.get("message") or "Paystack could not complete the refund.")
        logger.warning(f"Refund {refund.reference} failed; spendable balance restored")
        return True, None

    return False, f"unhandled refund event {event}"
