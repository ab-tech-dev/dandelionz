"""
Lightweight product recommendations.

Four entry points -- :func:`related_products`, :func:`personalized_products`,
:func:`trending_products` and :func:`recommend` -- all sit on one scoring core:
build a *profile* (a set of categories, tags and brands with weights), then rank
candidate products by how much they overlap it. ``related_products`` profiles a
single product; ``personalized_products`` profiles a user's history. Nothing
else differs.

Scoring runs in Python over a bounded candidate pool rather than in SQL. That
keeps the weights readable and portable across SQLite and Postgres, and the pool
cap (:data:`CANDIDATE_POOL_LIMIT`) keeps the cost flat as the catalogue grows.
This is meant to be replaced by something better later; it is intentionally not
clever.

Trending is the cold-start floor: every other entry point falls back to it when
it has no signal, so it must work with an empty InteractionEvent table.
"""
import hashlib
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, FloatField, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Favourite, InteractionEvent, Product, Review

# ---------------------------
# Content-similarity weights
# ---------------------------
# Used by related_products. Category is the strongest single signal because it
# is curated; tags are noisier but more specific, so a full tag match can beat a
# bare category match while a partial one cannot.
WEIGHT_SAME_CATEGORY = 40.0
WEIGHT_TAG_OVERLAP = 45.0
WEIGHT_SAME_BRAND = 20.0
WEIGHT_PRICE_BAND = 10.0

# ---------------------------
# Personalization weights
# ---------------------------
# Affinity scores are normalized to 0..1 before these multipliers apply, so the
# three axes stay comparable no matter how lopsided a user's history is.
WEIGHT_CATEGORY_AFFINITY = 40.0
WEIGHT_TAG_AFFINITY = 35.0
WEIGHT_BRAND_AFFINITY = 20.0

# How much each kind of history contributes to the profile. A purchase is a
# far stronger statement of taste than a page view.
SIGNAL_PURCHASE = 5.0
SIGNAL_FAVOURITE = 3.0
SIGNAL_REVIEW = 3.0
SIGNAL_CART_ADD = 2.0
SIGNAL_VIEW = 1.0

# ---------------------------
# Trending weights
# ---------------------------
# Order volume dominates; rating and freshness break ties between products that
# sold comparably. Ratings are 1..5 and recency is 0..1, so the multipliers put
# all three on a similar scale.
WEIGHT_ORDER_VOLUME = 10.0
WEIGHT_AVG_RATING = 4.0
WEIGHT_RECENCY = 8.0

# ---------------------------
# Tuning knobs
# ---------------------------
TRENDING_WINDOW_DAYS = 30
INTERACTION_WINDOW_DAYS = 30
RECENT_INTERACTION_LIMIT = 100

# Every history query is bounded. Without these a long-standing customer pulls
# their entire order, favourite and review history into memory on each uncached
# for-you request, and taste from three years ago counts as much as last week's.
HISTORY_WINDOW_DAYS = 365
RECENT_PURCHASE_LIMIT = 100
RECENT_FAVOURITE_LIMIT = 100
RECENT_REVIEW_LIMIT = 100

# The prefilter emits one unindexable LIKE per tag and one per brand, so the
# profile is trimmed to its strongest entries before the query is built.
PROFILE_TAG_LIMIT = 25
PROFILE_BRAND_LIMIT = 15

# Extra rows a fallback asks trending for, so filtering out excluded products
# does not return limit-1. Bounded so a customer with a long purchase history
# cannot turn one fallback into a request for hundreds of rows.
FALLBACK_OVER_FETCH = 24

# Two products are "similarly priced" within this fraction of each other.
PRICE_BAND_RATIO = 0.30

# Ceiling on how many rows we pull into Python to score. Well above any
# realistic ``limit``, low enough that a huge catalogue cannot blow up a request.
CANDIDATE_POOL_LIMIT = 200

MAX_LIMIT = 24
DEFAULT_LIMIT = 8

TRENDING_CACHE_SECONDS = 900  # 15 minutes


# ---------------------------
# Helpers
# ---------------------------
def _visible_products():
    """Every product a shopper is allowed to see. The universe for all scoring."""
    return Product.objects.filter(
        approval_status='approved',
        publish_status='submitted',
    ).select_related('category', 'store')


def parse_tags(raw):
    """
    Split a Product.tags blob into a normalized set.

    The field is free text ("comma-separated tags or JSON array"), so this is
    forgiving on purpose: strip brackets and quotes, split on commas, drop
    blanks. A malformed value yields an empty set rather than an error.
    """
    if not raw:
        return set()

    cleaned = str(raw).strip().strip('[]')
    return {
        tag.strip().strip('"\'').lower()
        for tag in cleaned.split(',')
        if tag.strip().strip('"\'')
    }


def _jaccard(left, right):
    """Overlap of two tag sets, 0..1. Empty on either side means no signal."""
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _price_closeness(price, other):
    """
    1.0 for identical prices, tapering to 0.0 at the edge of the price band.

    Products in wildly different price tiers are rarely substitutes even inside
    one category, so this is a gentle nudge rather than a filter.
    """
    if not price or not other:
        return 0.0

    price, other = float(price), float(other)
    if price <= 0 or other <= 0:
        return 0.0

    spread = abs(price - other) / max(price, other)
    if spread > PRICE_BAND_RATIO:
        return 0.0
    return 1.0 - (spread / PRICE_BAND_RATIO)


def clamp_limit(raw, default=DEFAULT_LIMIT):
    """
    Coerce a caller-supplied limit into 1..MAX_LIMIT.

    Returns ``None`` for input that is not a positive integer so the view can
    tell "you sent garbage" apart from "you sent nothing".
    """
    if raw is None or raw == '':
        return default

    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None

    if value < 1:
        return None
    return min(value, MAX_LIMIT)


def _cache_key(*parts):
    """
    Build a cache key with any user-controlled component hashed.

    Category slugs reach this from the query string; hashing avoids both the
    250-character key limit and characters that some cache backends reject.
    """
    digest = hashlib.sha256('|'.join(str(p) for p in parts).encode('utf-8')).hexdigest()
    return f'reco:{digest}'


# ---------------------------
# Trending (cold-start floor)
# ---------------------------
def trending_products(limit=DEFAULT_LIMIT, category=None):
    """
    Products selling well right now, newest and best-rated first among equals.

    Needs no personalization data at all, which is why everything else falls
    back to it. Results are cached by (limit, category) because they are the
    same for every visitor.

    ``category`` may be a Category, a slug string, or None.
    """
    category_slug = getattr(category, 'slug', category) or ''
    key = _cache_key('trending', limit, category_slug)

    cached_ids = cache.get(key)
    if cached_ids is not None:
        return _ordered_by_ids(cached_ids)

    from transactions.models import OrderItem

    now = timezone.now()
    since = now - timedelta(days=TRENDING_WINDOW_DAYS)
    queryset = _visible_products()
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)

    # Subqueries rather than two annotations over multi-valued joins: annotating
    # Count('orderitem') and Avg('reviews__rating') together makes the ORM join
    # both relations at once, so a product with 200 order lines and 50 reviews
    # materializes 10,000 intermediate rows to compute two numbers. Coalesce
    # keeps products with no sales or no reviews at 0 rather than NULL, which
    # matters on a young catalogue.
    recent_order_count = (
        OrderItem.objects
        .filter(product=OuterRef('pk'), order__ordered_at__gte=since)
        .values('product')
        .annotate(total=Count('id'))
        .values('total')
    )
    average_rating = (
        Review.objects
        .filter(product=OuterRef('pk'))
        .values('product')
        .annotate(average=Avg('rating'))
        .values('average')
    )
    queryset = queryset.annotate(
        recent_orders=Coalesce(Subquery(recent_order_count, output_field=IntegerField()), 0),
        avg_rating=Coalesce(Subquery(average_rating, output_field=FloatField()), 0.0),
    )

    # Order before slicing. Product has no Meta.ordering, so an unordered
    # LIMIT hands back an arbitrary 200 rows -- and a different 200 next time.
    # Trending applies no prefilter, so without this the best sellers can simply
    # miss the pool once the catalogue passes CANDIDATE_POOL_LIMIT.
    queryset = queryset.order_by('-recent_orders', '-created_at', 'id')

    candidates = list(queryset[:CANDIDATE_POOL_LIMIT])

    def score(product):
        volume = (product.recent_orders or 0) * WEIGHT_ORDER_VOLUME
        rating = float(product.avg_rating or 0) * WEIGHT_AVG_RATING
        # Linear decay across the window: brand new scores 1.0, a month old 0.0.
        age_days = max((now - product.created_at).days, 0)
        recency = max(0.0, 1.0 - (age_days / TRENDING_WINDOW_DAYS)) * WEIGHT_RECENCY
        return volume + rating + recency

    ranked = sorted(candidates, key=lambda p: (-score(p), p.id))[:limit]

    cache.set(key, [p.id for p in ranked], TRENDING_CACHE_SECONDS)
    return ranked


def _excluding(products, excluded_ids, limit):
    """
    Trim a fallback list to ``limit`` after removing ids the caller can't show.

    Callers ask trending for more than they need, because filtering afterwards
    would otherwise return limit-1 whenever an excluded product is itself
    trending -- which is the common case, since the product being viewed is
    disproportionately likely to be popular.
    """
    return [p for p in products if p.pk not in excluded_ids][:limit]


def _ordered_by_ids(ids):
    """Rehydrate a cached id list, preserving its order."""
    if not ids:
        return []
    by_id = {p.id: p for p in _visible_products().filter(id__in=ids)}
    return [by_id[i] for i in ids if i in by_id]


# ---------------------------
# Related (content-based)
# ---------------------------
def related_products(product, limit=DEFAULT_LIMIT):
    """
    Products similar to ``product`` by category, tags, brand and price.

    The candidate pool is prefiltered to rows sharing *something* with the
    product, so scoring never walks the whole catalogue. When nothing shares
    anything -- a lone product in a fresh catalogue -- this falls back to
    trending rather than returning an empty list.
    """
    if product is None:
        return []

    tags = parse_tags(product.tags)

    match = Q()
    if product.category_id:
        match |= Q(category_id=product.category_id)
    if product.brand:
        match |= Q(brand__iexact=product.brand)
    for tag in tags:
        match |= Q(tags__icontains=tag)

    candidates = _visible_products().exclude(pk=product.pk)
    if match:
        candidates = candidates.filter(match)
    # Ordered before slicing: Product has no Meta.ordering, so an unordered
    # LIMIT would hand back an arbitrary slice of the matching rows.
    candidates = list(candidates.order_by('-created_at', 'id')[:CANDIDATE_POOL_LIMIT])

    def score(other):
        total = 0.0
        if product.category_id and other.category_id == product.category_id:
            total += WEIGHT_SAME_CATEGORY
        total += _jaccard(tags, parse_tags(other.tags)) * WEIGHT_TAG_OVERLAP
        if product.brand and other.brand and other.brand.lower() == product.brand.lower():
            total += WEIGHT_SAME_BRAND
        total += _price_closeness(product.price, other.price) * WEIGHT_PRICE_BAND
        return total

    scored = [(score(p), p) for p in candidates]
    # Drop zero-scored rows: they only matched the prefilter incidentally.
    # The prefilter uses substring matching on tags while scoring uses exact set
    # overlap, so "run" can prefilter against "running" and then score nothing.
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))
    ranked = [p for _, p in scored[:limit]]

    # Fall back after scoring, not before it. Checking only whether the pool was
    # empty missed the case above, where candidates exist but all score zero --
    # which is exactly when a product page would render no row at all.
    if not ranked:
        return _excluding(trending_products(limit + 1), {product.pk}, limit)

    return ranked


# ---------------------------
# Personalized (for-you)
# ---------------------------
def _add_signal(profile, product, weight):
    """Fold one product the user engaged with into the taste profile."""
    if product is None:
        return

    if product.category_id:
        profile['categories'][product.category_id] = profile['categories'].get(product.category_id, 0.0) + weight
    if product.brand:
        brand = product.brand.lower()
        profile['brands'][brand] = profile['brands'].get(brand, 0.0) + weight
    for tag in parse_tags(product.tags):
        profile['tags'][tag] = profile['tags'].get(tag, 0.0) + weight


def build_user_profile(user):
    """
    Summarize what a user seems to like, plus what they already own.

    Returns a dict of weighted category/tag/brand affinities and the set of
    product ids they have purchased. An all-empty profile means "no signal" and
    is the caller's cue to fall back to trending.
    """
    from transactions.models import OrderItem

    profile = {'categories': {}, 'tags': {}, 'brands': {}, 'purchased_ids': set()}

    now = timezone.now()
    history_since = now - timedelta(days=HISTORY_WINDOW_DAYS)

    # Every query below is windowed and capped. Interaction events were already
    # bounded; leaving the other three unbounded meant an active customer's
    # whole history loaded on every uncached request, and weighted ancient
    # purchases as heavily as last month's browsing.
    purchased = OrderItem.objects.filter(
        order__customer=user, order__ordered_at__gte=history_since
    ).select_related('product', 'product__category').order_by('-order__ordered_at')[:RECENT_PURCHASE_LIMIT]
    for item in purchased:
        profile['purchased_ids'].add(item.product_id)
        _add_signal(profile, item.product, SIGNAL_PURCHASE)

    favourites = Favourite.objects.filter(
        customer=user, added_at__gte=history_since
    ).select_related('product', 'product__category').order_by('-added_at')[:RECENT_FAVOURITE_LIMIT]
    for fav in favourites:
        _add_signal(profile, fav.product, SIGNAL_FAVOURITE)

    # Only positive reviews say anything about taste; a 1-star review is a
    # signal to show *less* of that, which this simple model cannot express, so
    # it is ignored rather than counted backwards.
    reviews = Review.objects.filter(
        customer=user, rating__gte=4, created_at__gte=history_since
    ).select_related('product', 'product__category').order_by('-created_at')[:RECENT_REVIEW_LIMIT]
    for review in reviews:
        _add_signal(profile, review.product, SIGNAL_REVIEW)

    since = now - timedelta(days=INTERACTION_WINDOW_DAYS)
    events = InteractionEvent.objects.filter(
        user=user, created_at__gte=since
    ).select_related('product', 'product__category')[:RECENT_INTERACTION_LIMIT]
    for event in events:
        weight = SIGNAL_CART_ADD if event.event_type == 'cart_add' else SIGNAL_VIEW
        _add_signal(profile, event.product, weight)

    return profile


def _has_signal(profile):
    return bool(profile['categories'] or profile['tags'] or profile['brands'])


def _normalized(weights, keep=None):
    """
    Scale a weight map so its largest entry is 1.0.

    ``keep`` trims to that many strongest entries first. Each surviving tag and
    brand becomes an unindexable LIKE in the prefilter, so an untrimmed profile
    turns into hundreds of OR'd predicates for an active shopper.
    """
    if not weights:
        return {}

    items = weights.items()
    if keep is not None and len(weights) > keep:
        items = sorted(weights.items(), key=lambda pair: -pair[1])[:keep]
        weights = dict(items)

    peak = max(weights.values())
    if peak <= 0:
        return {}
    return {key: value / peak for key, value in weights.items()}


def personalized_products(user, limit=DEFAULT_LIMIT):
    """
    Products matching a user's taste, excluding anything they already bought.

    Falls back to trending for anonymous users and for signed-in users with no
    history at all -- the common case on a young store.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return trending_products(limit)

    profile = build_user_profile(user)
    if not _has_signal(profile):
        return trending_products(limit)

    categories = _normalized(profile['categories'])
    tags = _normalized(profile['tags'], keep=PROFILE_TAG_LIMIT)
    brands = _normalized(profile['brands'], keep=PROFILE_BRAND_LIMIT)

    # Prefilter to products touching the profile at all, so scoring stays bounded.
    match = Q()
    if categories:
        match |= Q(category_id__in=list(categories))
    for brand in brands:
        match |= Q(brand__iexact=brand)
    for tag in tags:
        match |= Q(tags__icontains=tag)

    candidates = _visible_products().exclude(pk__in=profile['purchased_ids'])
    if match:
        candidates = candidates.filter(match)
    # Ordered before slicing, as above: an unordered LIMIT would score an
    # arbitrary slice of the matching rows.
    candidates = list(candidates.order_by('-created_at', 'id')[:CANDIDATE_POOL_LIMIT])

    def score(product):
        total = 0.0
        if product.category_id:
            total += categories.get(product.category_id, 0.0) * WEIGHT_CATEGORY_AFFINITY
        if product.brand:
            total += brands.get(product.brand.lower(), 0.0) * WEIGHT_BRAND_AFFINITY
        product_tags = parse_tags(product.tags)
        if product_tags:
            # Average affinity across the product's own tags, so a product
            # tagged with one strong match is not diluted by a long tag list.
            total += (sum(tags.get(t, 0.0) for t in product_tags) / len(product_tags)) * WEIGHT_TAG_AFFINITY
        return total

    scored = [(score(p), p) for p in candidates]
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))
    ranked = [p for _, p in scored[:limit]]

    # A profile can match nothing purchasable (e.g. they bought the only product
    # in their favourite category). Trending is still better than nothing.
    if not ranked:
        excluded = profile['purchased_ids']
        # Over-fetch enough to survive the exclusions without letting a customer
        # with hundreds of purchases request (and cache) a huge trending list.
        over_fetch = min(limit + len(excluded), limit + FALLBACK_OVER_FETCH)
        return _excluding(trending_products(over_fetch), excluded, limit)

    return ranked


# ---------------------------
# Dispatch
# ---------------------------
RECOMMENDATION_TYPES = ('related', 'for-you', 'trending')


def recommend(kind, user=None, product=None, category=None, limit=DEFAULT_LIMIT):
    """
    Single dispatch point for the API layer.

    Raises ValueError on an unknown ``kind``, or on a ``category`` passed to a
    type that cannot honour it, so the view can turn either into a 400 without
    duplicating the rules.
    """
    if kind not in RECOMMENDATION_TYPES:
        raise ValueError(f"Unknown recommendation type '{kind}'")

    # Only trending is scoped by category. Silently ignoring it elsewhere would
    # return an unscoped list to a caller who believes they narrowed it.
    if category and kind != 'trending':
        raise ValueError(f"category is only supported when type=trending, not type={kind}")

    if kind == 'related':
        return related_products(product, limit)
    if kind == 'for-you':
        return personalized_products(user, limit)
    return trending_products(limit, category=category)
