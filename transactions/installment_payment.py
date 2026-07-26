"""
Flexible installment payments: pay any amount toward a plan's running balance, from the wallet
or by card.

The plan carries a running amount_paid; balance_remaining is what is owed. A payment may be any
positive amount, subject to two rules: it may never exceed the balance, and once a scheduled due
date has passed it must be at least the scheduled-to-date shortfall (plan.minimum_due_now) - so a
customer can dribble money in before a due date, must cover at least the instalment on the date,
and can clear the whole balance whenever they like.

Wallet payments are a simple atomic debit (the wallet must cover the whole amount - there is no
part-wallet/part-card split, so no hold machinery is needed). Card payments go through Paystack
and are applied on verify. Each payment is an InstallmentCharge, applied to the plan exactly once.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from transactions import references
from transactions.models import (
    InstallmentCharge, InstallmentPlan, LedgerEntry, Wallet, money,
)
from transactions.paystack import Paystack

logger = logging.getLogger(__name__)

EXPECTED_CURRENCY = "NGN"


class InstallmentPaymentError(Exception):
    """An installment payment that cannot be honoured. The message is safe to show the user."""


def _available_wallet(user):
    wallet = Wallet.objects.filter(user=user).first()
    if wallet is None:
        return Decimal('0.00')
    return money(wallet.spendable_balance + wallet.withdrawable_balance)


def _resolve_amount(plan, amount, clear_balance):
    """Validate and settle on the amount to charge, applying the min/max rules."""
    balance = plan.balance_remaining
    if balance <= 0:
        raise InstallmentPaymentError("This plan is already fully paid.")

    if clear_balance or amount is None:
        return balance

    amount = money(amount)
    if amount <= 0:
        raise InstallmentPaymentError("Enter an amount greater than zero.")
    if amount > balance:
        raise InstallmentPaymentError(
            f"That is more than the ₦{balance:,.2f} outstanding. Use 'clear balance' to pay it off."
        )
    minimum = plan.minimum_due_now()
    if amount < minimum:
        raise InstallmentPaymentError(
            f"At least ₦{minimum:,.2f} is due now. Pay that or more, or clear the balance."
        )
    return amount


def initialize_installment_payment(plan, callback_url, amount=None, clear_balance=False, use_wallet=False):
    """
    Start a payment toward the plan. Returns a dict; requires_payment is False when the wallet
    settled it immediately, otherwise an authorization_url is returned for the card leg.
    """
    if plan.status != 'ACTIVE':
        raise InstallmentPaymentError("This installment plan is not active.")

    user = plan.order.customer
    charge_amount = _resolve_amount(plan, amount, clear_balance)

    # One card charge in flight: cancel any prior pending one so its stale Paystack link cannot
    # settle onto a superseded charge. If it is later paid, verify/webhook refund it to source.
    with transaction.atomic():
        existing = plan.charges.filter(status=InstallmentCharge.Status.PENDING).first()
        if existing is not None:
            existing.status = InstallmentCharge.Status.CANCELLED
            existing.save(update_fields=['status', 'updated_at'])

    reference = references.new_installment_reference(plan.id)

    if use_wallet:
        # Wallet must cover the whole amount - no split. Debit and settle atomically.
        with transaction.atomic():
            wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
            available = money(wallet.spendable_balance + wallet.withdrawable_balance)
            if available < charge_amount:
                raise InstallmentPaymentError(
                    f"Your wallet balance is ₦{available:,.2f}. Pay a smaller amount or use a card."
                )
            charge = InstallmentCharge.objects.create(
                plan=plan, reference=reference, amount=charge_amount,
                method=InstallmentCharge.Method.WALLET,
            )
            wallet.debit(
                charge_amount,
                source=f"Installment payment {plan.order.order_id}",
                entry_type=LedgerEntry.EntryType.ORDER_PAYMENT,
                idempotency_key=f"installment-charge-{reference}",
                order=plan.order,
            )
            _settle_locked(charge)
        return {
            'requires_payment': False,
            'reference': reference,
            'method': 'WALLET',
            'amount': float(charge_amount),
            'plan_id': plan.id,
            'order_id': str(plan.order.order_id),
        }

    charge = InstallmentCharge.objects.create(
        plan=plan, reference=reference, amount=charge_amount, method=InstallmentCharge.Method.CARD,
    )
    resp = Paystack().initialize_payment(
        email=user.email, amount=charge_amount, reference=reference, callback_url=callback_url,
    )
    logger.info(f"Installment payment initialized for plan {plan.id} ({reference})")
    return {
        'requires_payment': True,
        'authorization_url': resp['data']['authorization_url'],
        'reference': reference,
        'method': 'CARD',
        'amount': float(charge_amount),
        'plan_id': plan.id,
        'order_id': str(plan.order.order_id),
    }


def _settle_locked(charge):
    """Apply an already-locked charge to its plan. Caller holds the row lock / transaction."""
    charge.status = InstallmentCharge.Status.PAID
    charge.verified = True
    charge.paid_at = timezone.now()
    charge.save(update_fields=['status', 'verified', 'paid_at', 'paystack_transaction_id', 'updated_at'])
    charge.plan.apply_payment(charge.amount)


def settle_installment_charge(charge, paystack_transaction_id=''):
    """Mark a charge paid and apply it to the plan's balance. Idempotent."""
    with transaction.atomic():
        charge = (
            InstallmentCharge.objects.select_for_update()
            .select_related('plan', 'plan__order')
            .get(pk=charge.pk)
        )
        if charge.status == InstallmentCharge.Status.PAID:
            return charge
        if paystack_transaction_id and not charge.paystack_transaction_id:
            charge.paystack_transaction_id = str(paystack_transaction_id)
        _settle_locked(charge)
    logger.info(f"Installment charge settled for plan {charge.plan_id} ({charge.reference})")
    return charge


def _refund_stranded_installment(charge, paystack_data, reason):
    """A payment landed on a superseded (cancelled) charge - return it to source. Idempotent."""
    if charge.status == InstallmentCharge.Status.REFUNDED:
        return charge
    amount = money(Decimal(str(paystack_data.get('amount', 0))) / 100)
    if amount <= 0:
        return charge
    handle = str(paystack_data.get('id') or '') or charge.reference
    try:
        resp = Paystack().refund(
            transaction=handle, amount=amount,
            merchant_note=f"Stranded installment payment {charge.reference}: {reason}",
        )
    except Exception as exc:
        logger.error(f"Failed to refund stranded installment {charge.reference}: {exc}", exc_info=True)
        return charge
    charge.status = InstallmentCharge.Status.REFUNDED
    charge.paystack_refund_id = str((resp.get('data') or {}).get('id') or '')
    charge.save(update_fields=['status', 'paystack_refund_id', 'updated_at'])
    logger.info(f"Refunded stranded installment payment {charge.reference} ({amount}) to source")
    return charge


def verify_installment_payment(reference):
    """Verify a card installment charge with Paystack and settle it. Idempotent when already paid."""
    charge = InstallmentCharge.objects.filter(reference=reference).select_related('plan__order').first()
    if charge is None:
        raise InstallmentPaymentError("Installment payment not found.")
    if charge.status == InstallmentCharge.Status.PAID:
        return charge
    if charge.status == InstallmentCharge.Status.REFUNDED:
        raise InstallmentPaymentError(
            "That payment link was replaced and any payment on it has been refunded. "
            "Please use the current payment."
        )
    if charge.status == InstallmentCharge.Status.CANCELLED:
        data = Paystack().verify_payment(reference).get('data') or {}
        if data.get('status') == 'success':
            _refund_stranded_installment(charge, data, "payment link was replaced")
            raise InstallmentPaymentError(
                "That payment link had expired and your payment has been refunded. "
                "Please use the current payment."
            )
        raise InstallmentPaymentError("This payment was cancelled. Please start a new one.")

    data = Paystack().verify_payment(reference).get('data') or {}
    if data.get('status') != 'success':
        raise InstallmentPaymentError("The payment was not successful.")
    if data.get('currency') and data.get('currency') != EXPECTED_CURRENCY:
        raise InstallmentPaymentError("The payment used an unexpected currency.")
    paid = money(Decimal(str(data.get('amount', 0))) / 100)
    if paid != money(charge.amount):
        raise InstallmentPaymentError("The amount paid does not match the payment requested.")

    return settle_installment_charge(charge, paystack_transaction_id=data.get('id') or '')


def settle_installment_webhook(data):
    """Settle a card installment charge from a charge.success webhook. Returns (handled, detail)."""
    reference = data.get('reference')
    charge = InstallmentCharge.objects.filter(reference=reference).select_related('plan__order').first()
    if charge is None:
        return False, f"no installment charge for {reference}"
    if charge.status == InstallmentCharge.Status.PAID:
        return True, None
    if charge.status == InstallmentCharge.Status.REFUNDED:
        return True, None
    if charge.status == InstallmentCharge.Status.CANCELLED:
        if data.get('status') == 'success':
            _refund_stranded_installment(charge, data, "payment link was replaced")
            return True, f"installment charge {reference} cancelled; payment refunded"
        return False, f"installment charge {reference} was cancelled"

    paid = money(Decimal(str(data.get('amount', 0))) / 100)
    if paid != money(charge.amount):
        return False, f"installment charge amount mismatch for {reference}"

    settle_installment_charge(charge, paystack_transaction_id=data.get('id') or '')
    return True, None
