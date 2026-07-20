"""
Weighted product search.

Postgres (production) ranks with full-text search over per-field weights and,
when the ``pg_trgm`` extension is installed, adds trigram similarity so that
misspelled queries still match. Every other backend -- notably SQLite, which the
test suite runs on -- falls back to a portable weighted ``icontains`` scorer.

Both paths share :func:`_relevance_expression` and :func:`_match_q`, so the
ordering contract ("an exact name match outranks a description mention") holds
identically on either backend. Postgres only ever *adds* signal on top.

Nothing here requires a migration. ``SearchVector``/``SearchRank`` are plain SQL
constructs, and trigram support is detected at runtime -- to enable it, run
``CREATE EXTENSION pg_trgm;`` once on the database.
"""
import logging

from django.db import connection
from django.db.models import Case, F, FloatField, Q, Value, When
from django.db.models.functions import Coalesce

logger = logging.getLogger(__name__)

# ---------------------------
# Relevance weights
# ---------------------------
# Kept in one place so both backends agree on what "more relevant" means.
# The name tiers stack: an exact match also matches prefix and contains, so an
# exact hit scores 175 while a mere substring hit scores 25.
WEIGHT_NAME_EXACT = 100.0
WEIGHT_NAME_PREFIX = 50.0
WEIGHT_NAME_CONTAINS = 25.0
WEIGHT_TAGS = 12.0
WEIGHT_BRAND = 10.0
WEIGHT_CATEGORY = 8.0
WEIGHT_DESCRIPTION = 4.0

# Small nudge so in-stock products win an otherwise equal match. Deliberately
# below WEIGHT_DESCRIPTION: availability breaks ties, it never beats relevance.
WEIGHT_IN_STOCK = 2.0

# Postgres-only signals. SearchRank returns roughly 0..1 and TrigramSimilarity
# returns 0..1, so these multipliers put them on the same scale as the tiers
# above without letting a fuzzy match outrank a literal name hit.
WEIGHT_FTS = 20.0
WEIGHT_TRIGRAM = 15.0

# Below this similarity a trigram "match" is mostly noise.
TRIGRAM_THRESHOLD = 0.3

_trigram_available = None


def _is_postgres():
    return connection.vendor == "postgresql"


def _has_trigram():
    """
    Check once per process whether pg_trgm is installed.

    Cached because this runs on every search and the answer only changes when
    someone runs CREATE EXTENSION (which needs a restart to pick up anyway).
    """
    global _trigram_available

    if _trigram_available is not None:
        return _trigram_available

    if not _is_postgres():
        _trigram_available = False
        return _trigram_available

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
            _trigram_available = cursor.fetchone() is not None
    except Exception:
        # A permissions or connection problem here should degrade search, not
        # break it -- the non-trigram path still returns good results.
        logger.warning("Could not detect pg_trgm; typo tolerance disabled", exc_info=True)
        _trigram_available = False

    if not _trigram_available:
        logger.info("pg_trgm not installed; run 'CREATE EXTENSION pg_trgm;' to enable typo tolerance")

    return _trigram_available


def _match_q(query):
    """Rows worth considering at all. Anything scoring zero is excluded."""
    return (
        Q(name__icontains=query)
        | Q(tags__icontains=query)
        | Q(brand__icontains=query)
        | Q(category__name__icontains=query)
        | Q(description__icontains=query)
    )


def _tier(condition, weight):
    return Case(When(condition, then=Value(weight)), default=Value(0.0), output_field=FloatField())


def _relevance_expression(query):
    """
    Portable weighted score. Runs identically on Postgres and SQLite.

    ``stock__gt=0`` excludes NULL stock on its own, so this stays null-safe
    without relying on backend-specific NULL ordering.
    """
    return (
        _tier(Q(name__iexact=query), WEIGHT_NAME_EXACT)
        + _tier(Q(name__istartswith=query), WEIGHT_NAME_PREFIX)
        + _tier(Q(name__icontains=query), WEIGHT_NAME_CONTAINS)
        + _tier(Q(tags__icontains=query), WEIGHT_TAGS)
        + _tier(Q(brand__icontains=query), WEIGHT_BRAND)
        + _tier(Q(category__name__icontains=query), WEIGHT_CATEGORY)
        + _tier(Q(description__icontains=query), WEIGHT_DESCRIPTION)
        + _tier(Q(stock__gt=0), WEIGHT_IN_STOCK)
    )


def _portable_search(queryset, query, apply_ordering):
    queryset = queryset.filter(_match_q(query)).annotate(search_rank=_relevance_expression(query))
    return queryset.order_by("-search_rank", "id") if apply_ordering else queryset


def _postgres_search(queryset, query, apply_ordering):
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

    # Coalesce every nullable field: concatenating a NULL into a SearchVector
    # would blank out the whole vector for that row.
    vector = (
        SearchVector("name", weight="A")
        + SearchVector(Coalesce("brand", Value("")), weight="B")
        + SearchVector(Coalesce("tags", Value("")), weight="B")
        + SearchVector(Coalesce("category__name", Value("")), weight="C")
        + SearchVector(Coalesce("description", Value("")), weight="D")
    )
    # 'websearch' tolerates whatever users type -- unbalanced quotes, stray
    # operators -- instead of raising the way 'raw' would.
    search_query = SearchQuery(query, search_type="websearch")

    queryset = queryset.annotate(fts_vector=vector, fts_rank=SearchRank(vector, search_query))

    match = _match_q(query) | Q(fts_vector=search_query)
    relevance = _relevance_expression(query) + F("fts_rank") * WEIGHT_FTS

    if _has_trigram():
        from django.contrib.postgres.search import TrigramSimilarity

        queryset = queryset.annotate(name_similarity=TrigramSimilarity("name", query))
        match = match | Q(name_similarity__gt=TRIGRAM_THRESHOLD)
        relevance = relevance + F("name_similarity") * WEIGHT_TRIGRAM

    queryset = queryset.filter(match).annotate(search_rank=relevance)
    return queryset.order_by("-search_rank", "id") if apply_ordering else queryset


def search_products(queryset, query, apply_ordering=True):
    """
    Rank ``queryset`` against ``query``, most relevant first.

    Returns the queryset untouched when the query is empty, so callers can pass
    an optional search term straight through.

    Pass ``apply_ordering=False`` to filter and annotate ``search_rank`` without
    imposing an order -- used when the caller asked for an explicit sort and
    relevance should not override it.
    """
    query = (query or "").strip()
    if not query:
        return queryset

    if _is_postgres():
        return _postgres_search(queryset, query, apply_ordering)
    return _portable_search(queryset, query, apply_ordering)
