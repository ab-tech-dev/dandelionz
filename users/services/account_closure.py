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
"""

import logging
import uuid

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Reasons closure can be refused. The client shows `message` directly.
BLOCKED_WITHDRAWABLE = 'withdrawable_balance'
BLOCKED_SPENDABLE = 'spendable_balance'
BLOCKED_PENDING_WITHDRAWAL = 'pending_withdrawal'
BLOCKED_ACTIVE_HOLD = 'active_hold'


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
                    f"on an order or request a refund to your original payment card, then "
                    f"close your account."
                ),
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

    return True, None


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
    placeholder = f"closed-{uuid.uuid4().hex[:16]}@removed.invalid"
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

    logger.info(f"Account closed and anonymised: {original_email} -> {placeholder}")
    return user
