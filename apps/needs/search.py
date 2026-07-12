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
    # Area is searchable too: the generated tsvector covers title+description
    # only, so models that carry a neighborhood get an explicit OR clause
    # (P3 audit: "find by area" otherwise silently missed).
    has_area = any(f.name == "neighborhood" for f in qs.model._meta.concrete_fields)
    if connection.vendor == "postgresql":
        cond = Q(_fts=True)
        if has_area:
            cond = cond | Q(neighborhood__icontains=q)
        return qs.annotate(
            _fts=RawSQL("search_vector @@ plainto_tsquery('english', %s)", (q,)),
        ).filter(cond)
    cond = Q(title__icontains=q) | Q(description__icontains=q)
    if has_area:
        cond = cond | Q(neighborhood__icontains=q)
    return qs.filter(cond)


def order_by_relevance(qs, q: str, fallback: str = "-created_at"):
    """Rank Postgres results by relevance; everywhere else (and with no
    query) order by ``fallback`` — one call site covers both worlds."""
    q = (q or "").strip()
    if not q or connection.vendor != "postgresql":
        return qs.order_by(fallback)
    return qs.annotate(
        _rank=RawSQL("ts_rank(search_vector, plainto_tsquery('english', %s))", (q,)),
    ).order_by("-_rank", fallback)
