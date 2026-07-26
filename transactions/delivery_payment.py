"""
Paying an order's delivery fee - a second payment, made after the goods are paid and the
admin has set the fee.

Same shape as split checkout: the fee can come from the wallet, a card, or both. The wallet
portion is held (WalletHold purpose=DELIVERY) so an abandoned card leg returns it via the
same expiry sweeper that guards checkout; the card leg goes through Paystack and is captured
on verify. Once the whole fee is settled, Order.delivery_fee_paid flips true and the order
becomes shippable.

Only one charge is ever in flight per order: starting a new payment releases and cancels any
pending one, so a retry never stacks wallet holds or leaves a stale Paystack link payable.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from transactions import references, wallet_checkout
from transactions.models import DeliveryCharge, Order, WalletHold, money
from transactions.paystack import Paystack

logger = logging.getLogger(__name__)

EXPECTED_CURRENCY = "NGN"


class DeliveryPaymentError(Exception):
    """A delivery-fee payment that cannot be honoured. The message is safe to show the user."""


# ---------------------------------------------------------------------------
# "Needs attention" queries - shared by the admin endpoint and the daily reminder
# so the badge on screen and the email an admin gets can never describe different sets.
# ---------------------------------------------------------------------------

def unscheduled_orders():
    """Paid orders the admin has not yet given a delivery window + fee. Admin-actionable."""
    return Order.objects.filter(
        status=Order.Status.PAID, expected_delivery_latest__isnull=True,
    )


def orders_awaiting_delivery_fee():
    """Scheduled orders waiting on the customer to pay a positive delivery fee. Informational."""
    return Order.objects.filter(
        status=Order.Status.PAID, delivery_fee_paid=False,
        delivery_fee__gt=0, expected_delivery_latest__isnull=False,
    )


def orders_ready_to_ship():
    """
    Paid, scheduled orders whose delivery fee is settled - ready for the admin to ship.

    Requires a window so the three buckets stay disjoint: an order with no window is
    "unscheduled", never "ready", even if its fee flag is somehow already set.
    """
    return Order.objects.filter(
        status=Order.Status.PAID, delivery_fee_paid=True,
        expected_delivery_latest__isnull=False,
    )


def _open_charge(order):
    return order.delivery_charges.filter(status=DeliveryCharge.Status.PENDING).first()


def initialize_delivery_payment(order, callback_url, use_wallet=False, requested_wallet=None):
    """
    Start paying an order's delivery fee. Returns a dict; requires_payment is False when the
    wallet covered it all (already settled), otherwise an authorization_url is returned.
    """
    user = order.customer

    if str(order.payment_status).upper() != 'PAID':
        raise DeliveryPaymentError("The order's goods must be paid before its delivery fee.")

    fee = money(order.delivery_fee)
    if order.delivery_fee_paid or fee <= 0:
        raise DeliveryPaymentError("No delivery fee is due on this order.")

    with transaction.atomic():
        # One charge in flight: drop any prior pending one and return its held wallet money,
        # so a restart neither stacks holds nor leaves an old card link payable.
        existing = _open_charge(order)
        if existing is not None:
            wallet_checkout.release_for_order(
                order, reason="Delivery payment restarted", purpose=WalletHold.Purpose.DELIVERY
            )
            existing.status = DeliveryCharge.Status.CANCELLED
            existing.save(update_fields=['status', 'updated_at'])

        wallet_amount = Decimal('0.00')
        card_amount = fee
        if use_wallet:
            wallet_amount, card_amount = wallet_checkout.plan_split(
                fee, wallet_checkout.available_balance(user), requested_wallet,
            )

        charge = DeliveryCharge.objects.create(
            order=order,
            reference=references.new_delivery_reference(order.order_id),
            amount=fee,
            wallet_amount=wallet_amount,
            card_amount=card_amount,
        )
        if wallet_amount > 0:
            wallet_checkout.place_hold(user, order, wallet_amount, purpose=WalletHold.Purpose.DELIVERY)

    # Wallet covered the whole fee: settle now, no card leg.
    if use_wallet and card_amount <= 0:
        settle_delivery_charge(charge)
        return {
            'requires_payment': False,
            'reference': charge.reference,
            'wallet_amount': float(wallet_amount),
            'card_amount': 0.0,
            'order_id': str(order.order_id),
        }

    # Card leg (possibly after a partial wallet debit). The network call is outside the atomic
    # block; if it fails the hold is committed and the sweeper will return it.
    resp = Paystack().initialize_payment(
        email=user.email,
        amount=card_amount,
        reference=charge.reference,
        callback_url=callback_url,
    )
    logger.info(f"Delivery payment initialized for order {order.order_id} ({charge.reference})")
    return {
        'requires_payment': True,
        'authorization_url': resp['data']['authorization_url'],
        'reference': charge.reference,
        'wallet_amount': float(wallet_amount),
        'card_amount': float(card_amount),
        'order_id': str(order.order_id),
    }


def settle_delivery_charge(charge, paystack_transaction_id=''):
    """Capture the wallet leg (if any), mark the charge paid, and let the order ship. Idempotent."""
    order = charge.order
    with transaction.atomic():
        charge = DeliveryCharge.objects.select_for_update().get(pk=charge.pk)
        if charge.status == DeliveryCharge.Status.PAID:
            return charge

        if charge.wallet_amount > 0:
            wallet_checkout.capture_for_order(order, purpose=WalletHold.Purpose.DELIVERY)

        charge.status = DeliveryCharge.Status.PAID
        charge.verified = True
        charge.paid_at = timezone.now()
        if paystack_transaction_id and not charge.paystack_transaction_id:
            charge.paystack_transaction_id = str(paystack_transaction_id)
        charge.save(update_fields=[
            'status', 'verified', 'paid_at', 'paystack_transaction_id', 'updated_at',
        ])

        order.delivery_fee_paid = True
        order.save(update_fields=['delivery_fee_paid', 'updated_at'])

    logger.info(f"Delivery fee settled for order {order.order_id} ({charge.reference})")
    try:
        from users.notification_helpers import send_order_notification
        send_order_notification(
            order.customer,
            "Delivery fee paid",
            "Your delivery fee is paid - your order is now being prepared for shipping.",
            order_id=str(order.order_id),
        )
    except Exception:
        logger.exception("Failed to send delivery-paid notification for order %s", order.order_id)
    return charge


def verify_delivery_payment(reference):
    """Verify a delivery card leg with Paystack and settle it. Idempotent on an already-paid charge."""
    charge = DeliveryCharge.objects.filter(reference=reference).select_related('order').first()
    if charge is None:
        raise DeliveryPaymentError("Delivery payment not found.")
    if charge.status == DeliveryCharge.Status.PAID:
        return charge
    if charge.status == DeliveryCharge.Status.CANCELLED:
        raise DeliveryPaymentError("This delivery payment was cancelled. Please start a new one.")

    # No card leg to verify (wallet-only that never settled): settle straight away.
    if money(charge.card_amount) <= 0:
        return settle_delivery_charge(charge)

    data = Paystack().verify_payment(reference).get('data') or {}
    if data.get('status') != 'success':
        raise DeliveryPaymentError("The delivery payment was not successful.")
    if data.get('currency') and data.get('currency') != EXPECTED_CURRENCY:
        raise DeliveryPaymentError("The delivery payment used an unexpected currency.")

    paid = money(Decimal(str(data.get('amount', 0))) / 100)
    if paid != money(charge.card_amount):
        raise DeliveryPaymentError("The amount paid does not match the delivery fee due.")

    return settle_delivery_charge(charge, paystack_transaction_id=data.get('id') or '')


def settle_delivery_webhook(data):
    """Settle a delivery charge from a charge.success webhook. Returns (handled, detail)."""
    reference = data.get('reference')
    charge = DeliveryCharge.objects.filter(reference=reference).select_related('order').first()
    if charge is None:
        return False, f"no delivery charge for {reference}"
    if charge.status == DeliveryCharge.Status.PAID:
        return True, None
    if charge.status == DeliveryCharge.Status.CANCELLED:
        return False, f"delivery charge {reference} was cancelled"

    if money(charge.card_amount) > 0:
        paid = money(Decimal(str(data.get('amount', 0))) / 100)
        if paid != money(charge.card_amount):
            return False, f"delivery charge amount mismatch for {reference}"

    settle_delivery_charge(charge, paystack_transaction_id=data.get('id') or '')
    return True, None
