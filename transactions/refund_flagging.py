"""
Flagging customers who refund a suspicious share of their orders, for admin review.

This never blocks anyone - it surfaces a customer for a human to look at. A customer is flagged
only when all three gates are met: enough paid orders to judge them on, enough refunds to be a
pattern rather than a one-off, and a high enough refund rate. So a new account or the occasional
refund is never flagged. Thresholds live in settings and are tunable without a deploy (industry
rule-of-thumb: serial returners sit around a 50%+ return rate).

"Refund" here means any non-rejected Refund on one of the customer's orders - a rejected refund
was already reviewed and denied, so counting it would penalise the customer for the platform's
own decision. One Refund exists per order, so the count is also the number of refunded orders.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from transactions.models import Order, Refund

# A refund still "counts" while pending or once approved; a rejected one does not.
NON_REJECTED = [Refund.Status.PENDING, Refund.Status.APPROVED]


def _min_orders():
    return int(getattr(settings, 'REFUND_FLAG_MIN_ORDERS', 4))


def _min_refunds():
    return int(getattr(settings, 'REFUND_FLAG_MIN_REFUNDS', 3))


def _rate_threshold():
    return Decimal(str(getattr(settings, 'REFUND_FLAG_RATE', '0.5')))


def is_flagged(paid_orders, refund_count, rate):
    """All three gates must hold. Kept separate so the endpoint and the list agree exactly."""
    return (
        paid_orders >= _min_orders()
        and refund_count >= _min_refunds()
        and rate >= _rate_threshold()
    )


def refund_profile(user):
    """A customer's refund history and whether it currently warrants review."""
    paid_orders = Order.objects.filter(
        customer=user, payment_status__iexact='PAID',
    ).count()
    refund_count = Refund.objects.filter(
        payment__order__customer=user, status__in=NON_REJECTED,
    ).count()
    rate = (Decimal(refund_count) / Decimal(paid_orders)) if paid_orders else Decimal('0')
    flagged = is_flagged(paid_orders, refund_count, rate)

    customer = getattr(user, 'customer_profile', None)
    reviewed_count = customer.refund_flag_reviewed_count if customer else 0
    # Needs review only if flagged AND they have refunded more since an admin last cleared them.
    needs_review = flagged and refund_count > reviewed_count

    return {
        'paid_orders': paid_orders,
        'refund_count': refund_count,
        'refund_rate': float(round(rate, 4)),
        'flagged': flagged,
        'needs_review': needs_review,
        'reviewed_count': reviewed_count,
        'thresholds': {
            'min_orders': _min_orders(),
            'min_refunds': _min_refunds(),
            'rate': float(_rate_threshold()),
        },
    }


def flagged_customers():
    """
    Customers currently warranting refund review, most-refunded first.

    One annotated query rather than a per-customer loop; the rate gate and the review-snooze are
    applied in Python because both are per-row derived values. Both counts descend the same
    orders relation, so the join does not fan out and the counts stay exact.
    """
    User = get_user_model()

    rows = (
        User.objects.filter(role=User.Role.CUSTOMER)
        .annotate(
            paid_orders=Count(
                'orders', filter=Q(orders__payment_status__iexact='PAID'), distinct=True,
            ),
            refunds=Count(
                'orders__payment__refund',
                filter=Q(orders__payment__refund__status__in=NON_REJECTED),
                distinct=True,
            ),
        )
        .filter(paid_orders__gte=_min_orders(), refunds__gte=_min_refunds())
        .select_related('customer_profile')
    )

    rate_threshold = _rate_threshold()
    result = []
    for u in rows:
        rate = Decimal(u.refunds) / Decimal(u.paid_orders) if u.paid_orders else Decimal('0')
        if rate < rate_threshold:
            continue
        reviewed = getattr(getattr(u, 'customer_profile', None), 'refund_flag_reviewed_count', 0)
        if u.refunds <= reviewed:
            continue
        result.append({
            'user': u,
            'paid_orders': u.paid_orders,
            'refund_count': u.refunds,
            'refund_rate': float(round(rate, 4)),
        })
    result.sort(key=lambda r: r['refund_count'], reverse=True)
    return result
