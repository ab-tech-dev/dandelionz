"""
Platform commission on vendor sales.

One place decides what cut the platform takes on an order item, so that every site that
touches commission - the credit at delivery, the reversal on refund, the pending/earnings
estimates, and the analytics - agrees on the rate by construction rather than by four
copies of ``* 0.10`` that can drift apart. Before this module the rate lived as a literal
in six places; a per-vendor rate would have silently disagreed with itself.

The rate is *layered*, most-specific wins:

    product.commission_rate  ->  vendor.commission_rate  ->  platform default

and hard-capped at the platform ceiling, so a mis-set field can never charge a vendor more
than the maximum. 10% is both the default and the ceiling; a vendor or product may be given
a *lower* negotiated rate but never a higher one.

Money correctness note: this resolver reflects the *current* configured rate. The credit at
delivery uses it once and writes the resulting amount to the append-only ledger; the reversal
must read that ledger entry back, NOT re-resolve, because an admin may have changed the rate
in between. See ``credit_vendors_for_order`` and the refund-approval reversal in views.py.
"""

from decimal import Decimal

from django.conf import settings

# The platform's default take, and simultaneously the hard maximum any vendor- or
# product-level override may set. Exposed in settings so it can be tuned per environment;
# the model-field validators pin the same 0.10 ceiling independently.
DEFAULT_COMMISSION_RATE = Decimal("0.10")
MAX_COMMISSION_RATE = Decimal("0.10")


def platform_commission_rate():
    """The platform default rate (also the ceiling). Reads settings, falling back to 0.10."""
    return Decimal(str(getattr(settings, "PLATFORM_COMMISSION_RATE", DEFAULT_COMMISSION_RATE)))


def _clamp(rate):
    """Pin a configured rate into [0, ceiling]; defends against a bad DB value."""
    ceiling = MAX_COMMISSION_RATE
    rate = Decimal(str(rate))
    if rate < Decimal("0"):
        return Decimal("0")
    if rate > ceiling:
        return ceiling
    return rate


def resolve_commission_rate(item=None, *, product=None, vendor=None):
    """
    The commission rate for one order item as a Decimal, most-specific wins.

    Pass an ``OrderItem`` (its ``product`` and ``product.store`` are read), or a ``product``
    and/or ``vendor`` directly. An unset override falls through to the next level; nothing
    set anywhere yields the platform default.
    """
    if item is not None:
        product = getattr(item, "product", None)
    if product is not None and vendor is None:
        vendor = getattr(product, "store", None)

    product_rate = getattr(product, "commission_rate", None) if product is not None else None
    if product_rate is not None:
        return _clamp(product_rate)

    vendor_rate = getattr(vendor, "commission_rate", None) if vendor is not None else None
    if vendor_rate is not None:
        return _clamp(vendor_rate)

    return platform_commission_rate()


def vendor_share_rate(item=None, *, product=None, vendor=None):
    """The vendor's fraction of an item subtotal, i.e. ``1 - commission``."""
    return Decimal("1.00") - resolve_commission_rate(item, product=product, vendor=vendor)


def format_rate_label(rate):
    """Human percentage for logs/metadata, e.g. Decimal('0.08') -> '8%'. Trims trailing zeros."""
    percent = Decimal(str(rate)) * Decimal("100")
    text = format(percent, "f")  # e.g. '10.00', '7.50', '8.00'
    # Strip only *fractional* trailing zeros - rstrip('0') alone would turn '10' into '1'.
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text + "%"
