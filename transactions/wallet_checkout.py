"""
Paying for an order with wallet balance, in full or split with a card.

The wallet is debited when checkout starts, not when the card leg completes. Those two legs
cannot be made atomic - one is a local transaction, the other is a network call to Paystack -
so something has to give, and holding the money up front is the only order that is safe. The
alternative, debiting after the card succeeds, lets the same balance be spent on two
checkouts opened in adjacent tabs.

WalletHold is what makes that reversible: it records how much came from each bucket, so an
abandoned or failed checkout returns every naira to where it came from. A release that
credited everything to one bucket would quietly convert deposits into withdrawable funds,
which is the exact laundering route the two-bucket split exists to prevent.

Bucket order is deliberate. Wallet.debit() with no bucket spends SPENDABLE first, so a
split payment consumes the customer's own deposits - the money that can only ever be spent
here - before touching refunds and earnings they could otherwise withdraw. Spending the
withdrawable half first would strand the restricted half.
"""

import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from transactions.models import LedgerEntry, Wallet, WalletHold, money

logger = logging.getLogger(__name__)

# How long a hold survives an abandoned checkout before the sweeper returns the money.
# Long enough to finish a card payment including a bank OTP round trip; short enough that a
# customer who wandered off is not locked out of their own balance for the rest of the day.
HOLD_TTL_MINUTES = 30


class WalletPaymentError(Exception):
    """A wallet payment that cannot be honoured. The message is safe to show the user."""


class SettlementBlocked(Exception):
    """
    A card payment arrived for an order that must not be settled.

    Raised rather than returned so no caller can ignore it by accident - the whole failure
    mode this guards against was a capture that quietly returned False.
    """


def settlement_blocker(order, payment):
    """
    Why this order must not be marked paid, or None if it may be.

    Guards the gap between the two legs of a split payment. The wallet leg can be returned
    to the customer - by cancelling, or by the expiry sweeper - while the card leg's Paystack
    link is still live and payable. Settling then would fulfil the order having collected
    only the card half, with the wallet half back in the customer's balance.

    Both variants are reachable without any race:
      cancel  - cancel a PENDING split order, take the wallet money back, then pay the card
      expiry  - abandon checkout for longer than HOLD_TTL_MINUTES, then pay the card

    A cancelled order is refused outright. Otherwise the order is refused when a hold was
    released and the card leg alone does not cover the total.
    """
    from transactions.models import Order, WalletHold

    if order.status == Order.Status.CANCELED:
        return f"order {order.order_id} was cancelled"

    released = WalletHold.objects.filter(
        order=order, status=WalletHold.Status.RELEASED
    ).first()
    if released is not None and not active_hold_for(order):
        if money(payment.amount) < money(order.total_price):
            return (
                f"wallet hold {released.reference} was released, so the card leg "
                f"({payment.amount}) no longer covers the order total ({order.total_price})"
            )

    return None


def available_balance(user):
    """Total the wallet can put towards an order: both buckets are spendable at checkout."""
    wallet = Wallet.objects.filter(user=user).first()
    if wallet is None:
        return Decimal('0.00')
    return money(wallet.spendable_balance + wallet.withdrawable_balance)


def plan_split(total, wallet_available, requested=None):
    """
    Decide how an order total is divided between wallet and card.

    `requested` lets the client ask for less than the full balance; None means "as much as
    the wallet can cover". Either way the wallet portion is capped at both the balance and
    the order total, so the card leg is never negative and the wallet is never overdrawn.

    Returns (wallet_amount, card_amount).
    """
    total = money(total)
    wallet_available = money(wallet_available)

    if requested is None:
        wallet_amount = min(wallet_available, total)
    else:
        requested = money(requested)
        if requested <= 0:
            raise WalletPaymentError("Wallet amount must be greater than zero.")
        if requested > wallet_available:
            raise WalletPaymentError(
                f"You only have ₦{wallet_available:,.2f} in your wallet."
            )
        wallet_amount = min(requested, total)

    return money(wallet_amount), money(total - wallet_amount)


def place_hold(user, order, amount):
    """
    Debit the wallet and record a hold against this order.

    Runs under a row lock on the wallet: the balance check and the debit have to be one
    step, or two checkouts started together both see enough money and both succeed.

    Returns the WalletHold, or None when there is nothing to hold.
    """
    amount = money(amount)
    if amount <= 0:
        return None

    with transaction.atomic():
        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)

        spendable = money(wallet.spendable_balance)
        withdrawable = money(wallet.withdrawable_balance)
        if spendable + withdrawable < amount:
            raise WalletPaymentError(
                f"Your wallet balance changed. Available: ₦{spendable + withdrawable:,.2f}."
            )

        # Mirrors Wallet._plan_debit's ordering so the hold records what the debit actually
        # did. Deriving it here rather than reading it back keeps the two in step by
        # construction; if they ever disagreed, a release would credit the wrong bucket.
        from_spendable = min(spendable, amount)
        from_withdrawable = money(amount - from_spendable)

        reference = f"HLD-{uuid.uuid4().hex[:16].upper()}"
        hold = WalletHold.objects.create(
            wallet=wallet,
            order=order,
            reference=reference,
            amount=amount,
            spendable_amount=from_spendable,
            withdrawable_amount=from_withdrawable,
            expires_at=timezone.now() + timezone.timedelta(minutes=HOLD_TTL_MINUTES),
        )

        wallet.debit(
            amount,
            source=f"Order payment {order.order_id}",
            entry_type=LedgerEntry.EntryType.ORDER_PAYMENT,
            idempotency_key=f"order-hold-{reference}",
            order=order,
        )

    logger.info(
        f"Wallet hold {reference} placed for order {order.order_id}: {amount} "
        f"(spendable {from_spendable}, withdrawable {from_withdrawable})"
    )
    return hold


def active_hold_for(order):
    """The hold still reserving money for this order, if any."""
    return WalletHold.objects.filter(order=order, status=WalletHold.Status.HELD).first()


def captured_hold_for(order):
    """The hold whose money was actually spent on this order, if any."""
    return WalletHold.objects.filter(order=order, status=WalletHold.Status.CAPTURED).first()


def wallet_amount_paid(order):
    """
    How much of this order was settled from the wallet.

    Reads the captured hold rather than a field on Order: the hold is where the per-bucket
    split lives, and a refund has to put each part back where it came from.
    """
    hold = captured_hold_for(order)
    return money(hold.amount) if hold else Decimal('0.00')


def capture_for_order(order):
    """Confirm the wallet spend once the rest of the payment has landed. Idempotent."""
    hold = active_hold_for(order)
    if hold is None:
        return False
    captured = hold.capture()
    if captured:
        logger.info(f"Wallet hold {hold.reference} captured for order {order.order_id}")
    return captured


def release_for_order(order, reason="Checkout not completed"):
    """Return held wallet money to its original buckets. Idempotent."""
    hold = active_hold_for(order)
    if hold is None:
        return False
    released = hold.release(reason)
    if released:
        logger.info(f"Wallet hold {hold.reference} released for order {order.order_id}: {reason}")
    return released


def refund_to_source_buckets(wallet, order, amount, *, source, idempotency_prefix,
                             payment=None, entry_type=None):
    """
    Credit a refund back to the buckets the money actually came from.

    The part paid from the wallet returns to its originating buckets; the part paid by card
    lands in WITHDRAWABLE, which is what a card refund into a wallet has always done here.

    Without this split, refunding a split payment would credit the whole order total to
    WITHDRAWABLE - so paying with deposited funds and then cancelling would turn money that
    can only be spent into money that can be paid out to a bank. That is the laundering
    route the two-bucket design exists to close, and it opens the moment checkout can spend
    from SPENDABLE.

    A partial refund is allocated **proportionally** to how the order was paid. Returning
    the wallet share first would be safer for the platform but wrong for the customer: on
    an order paid ₦500 from deposits and ₦4,500 by card, a ₦500 partial refund would come
    back entirely as spend-only money when 90% of what they paid could have returned as
    withdrawable.

    Returns {'spendable': Decimal, 'withdrawable': Decimal}.
    """
    amount = money(amount)
    applied = {'spendable': Decimal('0.00'), 'withdrawable': Decimal('0.00')}
    if amount <= 0:
        return applied

    entry_type = entry_type or LedgerEntry.EntryType.ORDER_REFUND
    hold = captured_hold_for(order)

    from_spendable = Decimal('0.00')
    if hold is not None and hold.spendable_amount > 0:
        card_amount = money(payment.amount) if payment is not None else Decimal('0.00')
        total_paid = money(hold.amount + card_amount)
        if total_paid > 0:
            share = (money(hold.spendable_amount) / total_paid)
            from_spendable = money(amount * share)
        # Never return more spendable than was actually paid from that bucket, and never
        # more than the refund itself.
        from_spendable = min(from_spendable, money(hold.spendable_amount), amount)

    if from_spendable > 0:
        wallet.credit(
            from_spendable,
            source=source,
            bucket=LedgerEntry.Bucket.SPENDABLE,
            entry_type=entry_type,
            idempotency_key=f"{idempotency_prefix}-spendable",
            order=order,
            payment=payment,
        )
        applied['spendable'] = from_spendable

    remaining = money(amount - from_spendable)
    if remaining > 0:
        # The wallet's withdrawable share plus the card leg. Both are money the customer
        # could already have taken to a bank, so returning them as withdrawable changes
        # nothing about what they can do with it.
        wallet.credit(
            remaining,
            source=source,
            bucket=LedgerEntry.Bucket.WITHDRAWABLE,
            entry_type=entry_type,
            idempotency_key=f"{idempotency_prefix}-withdrawable",
            order=order,
            payment=payment,
        )
        applied['withdrawable'] = remaining

    return applied
