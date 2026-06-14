"""
§10 improvement tests: audit width (10.1), structured consent (10.2),
full-text search (10.4), rate limiting (10.5), match-expiry sweep (10.6).
"""
import uuid
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import emit
from apps.casework.models import CaseFile
from apps.consent.models import Consent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------- §10.1
def test_audit_action_field_widened_to_32():
    assert AuditLog._meta.get_field("action").max_length == 32


def test_emit_writes_dotted_actions_and_rejects_overlong(world):
    row = emit("match.contact_revealed", world.case, details={"x": 1})
    assert row.action == "match.contact_revealed"
    with pytest.raises(ValueError):
        emit("x" * 33, world.case)


# ---------------------------------------------------------------- §10.2
def test_record_mode_consent_carries_structured_grantee(world, auth, u):
    client = auth(world.coord_u)
    client.post(u("create"), {
        "new_person_name": "Grantee Test",
        "sensitivity": "standard",
        "intake_date": timezone.localdate().isoformat(),
        "consent_mode": "record", "record_method": "verbal"})
    case = CaseFile.objects.exclude(pk=world.case.pk).get()
    assert case.consent.grantee_type == "community"
    assert str(case.consent.grantee_id) == str(world.community.id)


def test_consent_covers_authorization_check(world):
    legacy = world.consent  # created without grantee_id → label-era row
    assert legacy.covers(grantee_type="community",
                         grantee_id=world.community.id,
                         scopes=["case_records"])
    assert not legacy.covers(grantee_type="organization",
                             grantee_id=world.community.id,
                             scopes=["case_records"])
    assert not legacy.covers(grantee_type="community",
                             grantee_id=world.community.id,
                             scopes=["case_records", "not_granted_scope"])

    other = Consent.objects.create(
        participant=world.subject_u, granted_to="Some Other Conference",
        scope=["case_records"], purpose="t", method="digital",
        grantee_type="community", grantee_id=uuid.uuid4())
    assert not other.covers(grantee_type="community",
                            grantee_id=world.community.id,
                            scopes=["case_records"])

    legacy.status = "revoked"
    legacy.revoked_at = timezone.now()
    legacy.save(update_fields=["status", "revoked_at"])
    assert not legacy.covers(grantee_type="community",
                             grantee_id=world.community.id,
                             scopes=["case_records"])


# ---------------------------------------------------------------- §10.4
def _make_need(world, title, description=""):
    from apps.communities.models import Category
    from apps.needs.models import Need
    category, _ = Category.objects.get_or_create(
        community=world.community, name="Repairs",
        defaults={"icon": "🔧", "sort_order": 1})
    base = dict(community=world.community, requester=world.coordinator,
                category=category, title=title,
                description=description or title, urgency="medium")
    try:
        return Need.objects.create(**base)
    except Exception:
        base.update(status="open", contact_pref="in_app",
                    expires_at=timezone.now() + timedelta(days=30))
        return Need.objects.create(**base)


def test_apply_search_matches_and_excludes(world):
    from apps.needs.models import Need
    from apps.needs.search import apply_search
    need = _make_need(world, "Repairing the leaky faucet",
                      "Kitchen faucet drips constantly.")
    qs = Need.objects.filter(community=world.community)
    assert need in apply_search(qs, "faucet")
    assert need not in apply_search(qs, "zebra")
    assert apply_search(qs, "") .count() == qs.count()  # empty query = no-op


@pytest.mark.skipif(connection.vendor != "postgresql",
                    reason="stemmed FTS is Postgres-only by design (§10.4)")
def test_fts_stems_beyond_icontains(world):
    from apps.needs.models import Need
    from apps.needs.search import apply_search
    need = _make_need(world, "Repairing the leaky faucet")
    qs = Need.objects.filter(community=world.community)
    # "repairs" is NOT a substring of the title — only the tsvector path
    # (repairs → repair, repairing → repair) can find this.
    assert need in apply_search(qs, "repairs")


# ---------------------------------------------------------------- §10.5
def test_check_counts_down_then_blocks():
    from apps.accounts.ratelimit import check
    scope = f"unit:{uuid.uuid4()}"
    for i in range(5):
        allowed, remaining, reset = check(scope, 5, 60)
        assert allowed and remaining == 4 - i
    allowed, remaining, _ = check(scope, 5, 60)
    assert not allowed and remaining == 0


def test_reauth_returns_429_after_five_attempts(world, auth, u):
    client = auth(world.coord_u)
    for _ in range(5):
        resp = client.post(u("reauth"), {"password": "wrong-password"})
        assert resp.status_code == 200  # form re-renders with the error
    resp = client.post(u("reauth"), {"password": "wrong-password"})
    assert resp.status_code == 429
    assert resp["Retry-After"]
    assert resp["X-RateLimit-Limit"] == "5"
    assert resp["X-RateLimit-Remaining"] == "0"


# ---------------------------------------------------------------- §10.6
def _make_proposed_match(world, days_old):
    from apps.matches.models import Match
    need = _make_need(world, f"Need for sweep {uuid.uuid4().hex[:6]}")
    match = Match.objects.create(need=need, proposed_by=world.plain,
                                 status="proposed")
    Match.objects.filter(pk=match.pk).update(
        proposed_at=timezone.now() - timedelta(days=days_old))
    match.refresh_from_db()
    return match


def test_sweep_is_opt_in(world):
    from apps.matches.tasks import expire_stale_proposals
    world.community.settings = {}
    world.community.save(update_fields=["settings"])
    match = _make_proposed_match(world, days_old=30)
    assert expire_stale_proposals() == 0
    match.refresh_from_db()
    assert match.status == "proposed"


def test_sweep_expires_audits_and_notifies_once(world):
    from apps.matches.tasks import expire_stale_proposals
    from apps.notifications.models import Notification

    world.community.settings = {"match_expiry_days": 7}
    world.community.save(update_fields=["settings"])
    stale = _make_proposed_match(world, days_old=8)
    fresh = _make_proposed_match(world, days_old=2)

    assert expire_stale_proposals() == 1
    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == "expired"
    assert fresh.status == "proposed"
    assert AuditLog.objects.filter(action="match.expired",
                                   resource_id=stale.pk).exists()
    assert Notification.objects.filter(recipient=world.plain_u,
                                       type="match_expired").count() == 1

    # idempotent: nothing left in 'proposed' past the window
    assert expire_stale_proposals() == 0
    assert Notification.objects.filter(recipient=world.plain_u,
                                       type="match_expired").count() == 1
