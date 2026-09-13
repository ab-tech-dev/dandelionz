"""
notification_text.py
Helpers for building human-readable notification messages.

Usage:
    from transactions.notification_text import format_product_names

    msg = f"Payment confirmed for order for {format_product_names(cart_items)}."
"""

import logging

logger = logging.getLogger(__name__)


def format_product_names(items, max_items: int = 3, fallback: str = "") -> str:
    """
    Return a comma-separated list of product names from an order/cart item
    queryset or iterable.

    Examples
    --------
    3 items  → "Apple Watch, Nike Shoe & 1 other"
    2 items  → "Apple Watch & Nike Shoe"
    1 item   → "Apple Watch"
    0 items  → fallback value (empty string by default)

    The function is intentionally defensive: if the product name is missing,
    empty, or any attribute access fails, that item is silently skipped so a
    single corrupted row never crashes the notification path.

    Args:
        items:      QuerySet or iterable of cart/order items that have a
                    ``product`` attribute with a ``name`` field.
        max_items:  Maximum number of names to spell out before collapsing the
                    rest into "& N other(s)".  Defaults to 3.
        fallback:   String returned when no names can be extracted.
    """
    names = []
    try:
        for item in items:
            try:
                name = getattr(getattr(item, "product", None), "name", None)
                if name and str(name).strip():
                    names.append(str(name).strip())
            except Exception:
                continue
    except Exception:
        logger.exception("format_product_names: error iterating items")

    if not names:
        return fallback

    unique_names = list(dict.fromkeys(names))  # deduplicate, preserve order

    if len(unique_names) == 1:
        return unique_names[0]

    if len(unique_names) <= max_items:
        return ", ".join(unique_names[:-1]) + " & " + unique_names[-1]

    shown = unique_names[:max_items]
    remaining = len(unique_names) - max_items
    other_label = "other" if remaining == 1 else "others"
    return ", ".join(shown) + f" & {remaining} {other_label}"
