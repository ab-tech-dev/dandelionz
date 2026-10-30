"""
Push / in-app alerts to every admin when money moves.

Order payments already alert admins ("New Paid Order", sent by notify_stakeholders_order_paid)
and withdrawal requests already alert them ("New Withdrawal Request"). This covers the rest:
installment payments, delivery fees, wallet top-ups, and refunds going back to a card.

Design points:

  * Sent only after the surrounding transaction commits (on_commit), so an alert never
    announces money that a rollback then removes.
  * Sent through Celery, so a slow push provider never delays a payment response or a webhook;
    if the broker is unavailable it falls back to sending inline.
  * De-duplicated per payment, twice: here (the webhook and the verify endpoint routinely both
    settle the same payment) and again inside the task, so that if queueing raises after the
    task already ran, the inline fallback cannot send a second copy. cache.add() is atomic.
  * Best-effort: nothing here can raise into, or fail, a payment.
  * Push + in-app only. Email is off on purpose: admins would otherwise get one email per
    payment, on top of the Paystack receipts they already receive.

An admin only gets the push on a device where they are logged in to the app with notifications
allowed; otherwise the alert still appears in-app.
"""

import logging
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

DEDUPE_TTL_SECONDS = 60 * 60 * 24


def claim_send(dedupe_key):
    """True if this payment's alert has not been sent yet (and marks it sent). Fails open."""
    try:
        return cache.add(f"admin-payment-alert-sent:{dedupe_key}", 1, DEDUPE_TTL_SECONDS)
    except Exception:
        return True


def naira(amount):
    return f"₦{Decimal(str(amount)):,.2f}"


def alert_admins(*, title, message, dedupe_key, **metadata):
    """
    Queue an admin alert for after the current transaction commits. Never raises.

    `dedupe_key` identifies the payment (e.g. "installment-INS-2-abc"); a repeat settlement of
    the same payment produces no second alert. `metadata` values must be JSON-serialisable
    strings/numbers.
    """
    try:
        payload = {
            'title': title, 'message': message, 'dedupe_key': dedupe_key,
            'kind': metadata.pop('kind', 'payment'), **metadata,
        }
        transaction.on_commit(lambda: _dispatch(dedupe_key, payload))
    except Exception:
        logger.exception("Could not queue admin payment alert %s", dedupe_key)


def _dispatch(dedupe_key, payload):
    try:
        if not cache.add(f"admin-payment-alert:{dedupe_key}", 1, DEDUPE_TTL_SECONDS):
            return  # already alerted for this payment
    except Exception:
        # Cache down: better a rare duplicate alert than a missed one.
        logger.warning("Admin alert de-dupe cache unavailable for %s", dedupe_key)

    try:
        from transactions.tasks import send_admin_payment_alert
        send_admin_payment_alert.delay(**payload)
    except Exception:
        logger.exception("Could not queue admin alert %s; sending inline", dedupe_key)
        try:
            from transactions.tasks import send_admin_payment_alert
            send_admin_payment_alert(**payload)
        except Exception:
            logger.exception("Admin payment alert %s failed", dedupe_key)
