"""
§10.4 — full-text search helper for Need and Offer querysets.

Usage in the feed view (one-line swap wherever you currently do
`qs.filter(title__icontains=q)`-style search):

    from apps.needs.search import apply_search
    qs = apply_search(qs, q)            # Need or Offer queryset

Postgres: stemmed websearch over the generated `search_vector` column
(GIN-indexed, see the 0002_fulltext_search migration).
Anything else: graceful icontains fallback — identical call site.
"""

from django.db import connection
from django.db.models import Q
from django.db.models.expressions import RawSQL


def apply_search(qs, q: str):
    q = (q or "").strip()
    if not q:
        return qs
    if connection.vendor == "postgresql":
        return qs.annotate(
            _fts=RawSQL("search_vector @@ plainto_tsquery('english', %s)", (q,)),
        ).filter(_fts=True)
    return qs.filter(Q(title__icontains=q) | Q(description__icontains=q))


def order_by_relevance(qs, q: str):
    """Optional: rank Postgres results by relevance; no-op elsewhere."""
    q = (q or "").strip()
    if not q or connection.vendor != "postgresql":
        return qs
    return qs.annotate(
        _rank=RawSQL("ts_rank(search_vector, plainto_tsquery('english', %s))", (q,)),
    ).order_by("-_rank")
