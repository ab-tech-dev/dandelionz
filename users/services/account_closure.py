"""
Account closure: what has to be true before an account can go, and what "gone" means.

Two rules drive this module.

**Money must leave before the account does.** Closing an account used to hard-delete the
user, which cascaded to the wallet and destroyed the balance along with every record of it.
A user with money in their wallet could close their account and the funds would simply
vanish - no refund, nothing to reconcile. So closure is now blocked while funds remain, and
the message tells the user which route out applies to their balance.

**The money trail outlives the account.** Closure anonymises the user row rather than
deleting it, so LedgerEntry rows survive for auditing. LedgerEntry.wallet is PROTECT, so a
stray hard delete fails loudly instead of silently erasing history.

Those two rules pull against each other on personal data, and the split is: the ledger keeps
*amounts and references*, the profile keeps *nothing identifying*. LedgerEntry references no
bank data at all, and PayoutRequest snapshots its own copy of the destination account at the
time of payout, so scrubbing the live profile costs the audit trail nothing.
"""

import logging
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework import status as http_status
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)

# Every closed account gets an email on this domain (see close_account). It doubles as the
# marker for "this account was closed", because the user table has no closed flag and
# is_active is also False for accounts an admin merely suspended.
CLOSED_EMAIL_SUFFIX = '@removed.invalid'

# Reasons closure can be refused. The client shows `message` directly.
BLOCKED_WITHDRAWABLE = 'withdrawable_balance'
BLOCKED_SPENDABLE = 'spendable_balance'
BLOCKED_PENDING_WITHDRAWAL = 'pending_withdrawal'
BLOCKED_ACTIVE_HOLD = 'active_hold'
BLOCKED_PENDING_REFUND = 'pending_refund'
BLOCKED_OPEN_ORDER = 'open_order'
BLOCKED_VENDOR_OPEN_ORDER = 'vendor_open_order'


class AccountClosureBlocked(APIException):
    """
    Raised by close_account when the guards fail on the re-check under the row lock.

    The closure views already call check_can_close first, so this only fires when
    something changed in the few milliseconds between that check and the closure. The body
    carries every key the existing clients read (error, message, detail, reason), so the
    web and mobile apps show the text without any change.
    """
    status_code = http_status.HTTP_400_BAD_REQUEST
    default_code = 'account_closure_blocked'

    def __init__(self, blocker):
        body = {
            'success': False,
            'error': blocker['message'],
            'message': blocker['message'],
            'detail': blocker['message'],
            'reason': blocker['reason'],
        }
        if blocker.get('amount') is not None:
            body['amount'] = blocker['amount']
        super().__init__(body)


def exclude_closed_vendors(queryset):
    """
    Drop products whose vendor closed their account.

    Closure moves those products to draft, but an admin list that does not filter on
    publish_status would still show them, and the approve and reject endpoints would act on
    them. Accepts a queryset or a manager.
    """
    return queryset.exclude(store__user__email__endswith=CLOSED_EMAIL_SUFFIX)


def check_can_close(user):
    """
    Decide whether this account may be closed.

    Returns (True, None) or (False, {"reason": ..., "message": ..., "amount": ...}).
    """
    from transactions.models import Wallet, WalletHold
    from users.models import PayoutRequest

    wallet = Wallet.objects.filter(user=user).first()

    if wallet:
        if wallet.withdrawable_balance > 0:
            return False, {
                'reason': BLOCKED_WITHDRAWABLE,
                'amount': str(wallet.withdrawable_balance),
                'message': (
                    f"You have ₦{wallet.withdrawable_balance:,.2f} available in your "
                    f"wallet. Withdraw it to your bank account before closing your account."
                ),
            }

        if wallet.spendable_balance > 0:
            # Deposited funds cannot be withdrawn to a bank by design - that is the rule
            # that stops the wallet being a cash-out route for a stolen card, and closure
            # is exactly when someone would try to use it. The safe way out is a refund to
            # the card the money came from.
            return False, {
                'reason': BLOCKED_SPENDABLE,
                'amount': str(wallet.spendable_balance),
                'message': (
                    f"You have ₦{wallet.spendable_balance:,.2f} in deposited funds. "
                    f"Deposits cannot be withdrawn to a bank, so either spend the balance "
                    f"on an order or refund it to your original payment card, then close "
                    f"your account."
                ),
                'refund_endpoint': '/transactions/wallet/deposit/refund/',
            }

        live_hold = WalletHold.objects.filter(
            wallet=wallet, status=WalletHold.Status.HELD
        ).first()
        if live_hold:
            return False, {
                'reason': BLOCKED_ACTIVE_HOLD,
                'amount': str(live_hold.amount),
                'message': (
                    "You have a checkout in progress using your wallet balance. "
                    "Complete or cancel it before closing your account."
                ),
            }

    # A refund in flight has already left the wallet but has not reached the card yet. If
    # it fails, mark_as_failed credits the money back - to a wallet that would no longer
    # have an owner who can reach it.
    from transactions.models import DepositRefund

    refund_in_flight = DepositRefund.objects.filter(
        user=user,
        status__in=[DepositRefund.Status.PENDING, DepositRefund.Status.PROCESSING],
    ).exists()
    if refund_in_flight:
        return False, {
            'reason': BLOCKED_PENDING_REFUND,
            'amount': None,
            'message': (
                "You have a refund on its way back to your card. Wait for it to complete "
                "before closing your account."
            ),
        }

    pending = PayoutRequest.objects.filter(
        user=user, status__in=['pending', 'processing']
    ).exists()
    if not pending and hasattr(user, 'vendor_profile'):
        pending = PayoutRequest.objects.filter(
            vendor=user.vendor_profile, status__in=['pending', 'processing']
        ).exists()

    if pending:
        return False, {
            'reason': BLOCKED_PENDING_WITHDRAWAL,
            'amount': None,
            'message': (
                "You have a withdrawal still being processed. Wait for it to complete "
                "before closing your account."
            ),
        }

    return _check_open_orders(user)


def _check_open_orders(user):
    """
    Money that is already in motion for an order has to land before the account goes.

    Unpaid (PENDING) orders deliberately do not block: every checkout creates one and nothing
    expires them, so an abandoned payment page would otherwise make deletion impossible.
    close_account cancels them instead (see _cancel_unpaid_orders).

    A customer who closes with a paid, undelivered order can no longer cancel it, pay its
    delivery fee, or be refunded to anything but the card. A vendor who closes with orders
    in flight has their earnings credited, at delivery, to a wallet nobody can reach.
    """
    from transactions.models import Order, OrderPaymentRefund, Refund

    shipped = Order.objects.filter(customer=user, status=Order.Status.SHIPPED).exists()
    if shipped:
        return False, {
            'reason': BLOCKED_OPEN_ORDER,
            'amount': None,
            'message': (
                "You have an order that is on its way. Wait for it to be delivered "
                "before closing your account."
            ),
        }

    paid = Order.objects.filter(customer=user, status=Order.Status.PAID).exists()
    if paid:
        return False, {
            'reason': BLOCKED_OPEN_ORDER,
            'amount': None,
            'message': (
                "You have a paid order that has not been delivered. Cancel it for a "
                "refund, or wait for it to arrive, before closing your account."
            ),
        }

    # A cancelled order's refund is only requested at cancellation. Until it is processed
    # the money has not reached the customer, and the account must stay reachable.
    refund_open = (
        Refund.objects.filter(
            payment__order__customer=user, status=Refund.Status.PENDING
        ).exists()
        or OrderPaymentRefund.objects.filter(
            payment__order__customer=user,
            status__in=[OrderPaymentRefund.Status.PENDING, OrderPaymentRefund.Status.PROCESSING],
        ).exists()
    )
    if refund_open:
        return False, {
            'reason': BLOCKED_PENDING_REFUND,
            'amount': None,
            'message': (
                "You have a refund that is still being processed. Wait for it to "
                "complete before closing your account."
            ),
        }

    vendor = getattr(user, 'vendor_profile', None)
    if vendor is not None:
        from transactions.models import OrderItem

        vendor_open = OrderItem.objects.filter(
            product__store=vendor,
            order__status__in=[Order.Status.PAID, Order.Status.SHIPPED],
        ).exists()
        if vendor_open:
            return False, {
                'reason': BLOCKED_VENDOR_OPEN_ORDER,
                'amount': None,
                'message': (
                    "You have orders that are paid but not yet delivered. Fulfil them, "
                    "and wait for delivery, before closing your account."
                ),
            }

    return True, None


# Personal data held on the role profiles rather than on the user row. Cleared at closure
# for the same reason the user fields are: none of it is referenced by the ledger, and bank
# details left on a closed account are the most sensitive thing we would be retaining.
_PROFILE_SCRUB = {
    'customer_profile': (
        ('shipping_address', ''),
        ('city', ''),
        ('postal_code', ''),
        ('shipping_latitude', None),
        ('shipping_longitude', None),
        ('bank_name', ''),
        ('bank_code', ''),
        ('account_number', ''),
        ('account_name', ''),
        ('recipient_code', ''),
    ),
    'vendor_profile': (
        ('address', ''),
        # The coordinates go with the address. For a sole trader the store location is
        # often their home, so clearing the free-text address while leaving metre-accurate
        # coordinates behind would defeat the point - the customer branch clears its
        # shipping coords for the same reason.
        ('store_latitude', None),
        ('store_longitude', None),
        ('bank_name', ''),
        ('bank_code', ''),
        ('account_number', ''),
        ('account_name', ''),
        ('recipient_code', ''),
    ),
    'admin_payout_profile': (
        ('bank_name', ''),
        ('bank_code', ''),
        ('account_number', ''),
        ('account_name', ''),
        ('recipient_code', ''),
    ),
}


def _unpublish_vendor_store(user):
    """
    Take a closing vendor's products off sale.

    This has to happen here rather than in one of the two closure endpoints, because the
    store address is scrubbed a moment later: a published product whose vendor has no
    address and no coordinates fails geocoding at checkout, so the customer gets an
    unactionable "Unable to calculate shipping fee" instead of simply not seeing the item.
    """
    vendor = getattr(user, 'vendor_profile', None)
    if vendor is None:
        return

    from store.models import CartItem, Favourite, Product
    Product.objects.filter(store=vendor).update(publish_status='draft')

    # A product already sitting in a cart would still check out, because checkout reads the
    # cart and never looks at publish_status. Remove it from carts and wishlists here, so the
    # customer sees an empty slot instead of paying for something the vendor can no longer ship.
    CartItem.objects.filter(product__store=vendor).delete()
    Favourite.objects.filter(product__store=vendor).delete()


def _scrub_profiles(user):
    """Clear payout and address data from whichever role profiles this user has."""
    for relation, fields in _PROFILE_SCRUB.items():
        profile = getattr(user, relation, None)
        if profile is None:
            continue

        updated = []
        for field, value in fields:
            if hasattr(profile, field):
                setattr(profile, field, value)
                updated.append(field)

        if updated:
            profile.save(update_fields=updated)


def _cancel_unpaid_orders(user):
    """
    Cancel the customer's unpaid checkouts the same way CustomerCancelOrderView does.

    They hold no money (a wallet hold is its own blocker in check_can_close), but a Paystack
    link left open on one could be paid after the account is gone and settle an order that
    nobody can cancel or pay the delivery fee for. Voiding the payment closes that door.
    """
    from transactions import wallet_checkout
    from transactions.models import Order, OrderStatusHistory

    for order in Order.objects.select_for_update().filter(
        customer=user, status=Order.Status.PENDING
    ):
        order.status = Order.Status.CANCELED
        order.save(update_fields=['status'])
        OrderStatusHistory.objects.create(
            order=order,
            status=Order.Status.CANCELED,
            changed_by='SYSTEM',
            reason="Cancelled automatically because the customer closed their account",
        )
        wallet_checkout.release_for_order(order, reason="Account closed")

        payment = getattr(order, 'payment', None)
        if payment is not None and not payment.verified:
            payment.status = 'CANCELLED'
            payment.save(update_fields=['status'])


@transaction.atomic
def close_account(user):
    """
    Anonymise the account in place.

    Deliberately not `user.delete()`: the wallet cascades from the user, and the ledger is
    PROTECTed by the wallet, so a hard delete would either fail or destroy the financial
    record. Overwriting the identifying fields removes the personal data while leaving the
    rows that the money trail hangs off.

    The email is replaced with a unique unusable address so the original can never be
    recovered and the uniqueness constraint still holds if the same person signs up again.
    """
    # Lock the user row, then ask again. The views check first, but an order can be placed
    # between that check and this write. Two concurrent closures also queue here instead of
    # both running.
    type(user).objects.select_for_update().get(pk=user.pk)
    allowed, blocker = check_can_close(user)
    if not allowed:
        raise AccountClosureBlocked(blocker)

    _cancel_unpaid_orders(user)

    placeholder = f"closed-{uuid.uuid4().hex[:16]}{CLOSED_EMAIL_SUFFIX}"
    original_email = user.email

    user.email = placeholder
    user.full_name = 'Closed Account'
    user.is_active = False
    user.set_unusable_password()

    updated = ['email', 'full_name', 'is_active', 'password']

    # These are optional across roles, so only touch what this user actually has.
    for field, value in (
        ('phone_number', ''),
        ('profile_image', None),
        ('address', ''),
    ):
        if hasattr(user, field):
            setattr(user, field, value)
            updated.append(field)

    if hasattr(user, 'closed_at'):
        user.closed_at = timezone.now()
        updated.append('closed_at')

    user.save(update_fields=list(dict.fromkeys(updated)))

    _unpublish_vendor_store(user)
    _scrub_profiles(user)

    # The PIN hash is a live credential. The account cannot authenticate any more, but there
    # is no reason to keep it, and nothing in the ledger refers to it.
    from users.models import PaymentPIN
    PaymentPIN.objects.filter(user=user).delete()

    logger.info(f"Account closed and anonymised: {original_email} -> {placeholder}")
    return user
