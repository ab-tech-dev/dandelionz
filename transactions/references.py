"""
Paystack reference prefixes, and the routing they enable.

Every reference we hand to Paystack is prefixed by what it is paying for. Without this the
webhook has to guess: the original handler treated *any* non-transfer event as an order
payment and looked the reference up in the Payment table, which was fine when orders were
the only thing being charged. Adding wallet deposits breaks that assumption, so the prefix
makes the intent explicit.

Existing references in the wild have no prefix. `classify` treats anything unrecognised as
ORDER, which is what those legacy references are, so in-flight payments keep working across
the deploy.
"""

import uuid

ORDER = 'ORDER'
DEPOSIT = 'DEPOSIT'
INSTALLMENT = 'INSTALLMENT'
TRANSFER = 'TRANSFER'

PREFIXES = {
    'ORD-': ORDER,
    'DEP-': DEPOSIT,
    'INS-': INSTALLMENT,
    'WTH-': TRANSFER,
    'ADM-': TRANSFER,
}


def classify(reference):
    """
    Map a Paystack reference to the kind of thing it pays for.

    Unprefixed references are treated as ORDER: that is what every reference created before
    this module existed was, and they must keep resolving after deploy.
    """
    if not reference:
        return ORDER
    for prefix, kind in PREFIXES.items():
        if reference.startswith(prefix):
            return kind
    return ORDER


def new_deposit_reference():
    return f"DEP-{uuid.uuid4().hex[:16].upper()}"


def new_order_reference(order_id):
    """Order references keep embedding the order id, as the existing checkout does."""
    return f"ORD-{order_id}-{uuid.uuid4().hex[:10]}"


def new_installment_reference(plan_id):
    return f"INS-{plan_id}-{uuid.uuid4().hex[:10]}"
