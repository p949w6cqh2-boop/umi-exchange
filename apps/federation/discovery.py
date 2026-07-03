"""
Discovery redaction (§2.2): turn a shared Need/Offer into the ONLY shape that
crosses the wire — coarse, non-identifying. Everything else (title, description,
requester/offerer identity, contact, neighborhood free-text, on_behalf_of PII)
stays home. This module is the single place that decides what is discoverable;
if a field isn't added here, it never leaves the instance.
"""


def _week_bucket(dt) -> str:
    # ISO year-week (day precision withheld) — freshness without a timeline.
    return dt.strftime("%G-W%V")


def community_locality(community) -> str:
    """Coarse admin-set label (never an address). Read from the community's
    federation settings; empty string if unset."""
    fed = (community.settings or {}).get("federation") or {}
    return str(fed.get("locality", ""))[:100]


def redact(share) -> dict:
    """Redacted discovery row for a FederatedShare. NO PII by construction."""
    rec = share.record
    row = {
        "kind": "need" if share.need_id else "offer",
        "remote_uuid": str(share.remote_uuid),
        "category": rec.category.name,
        "locality": community_locality(share.link.community),
        "freshness": _week_bucket(rec.created_at),
    }
    if share.need_id:
        row["urgency"] = rec.urgency
    else:
        row["radius_km"] = rec.radius
    return row
