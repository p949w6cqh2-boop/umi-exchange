"""Batch-6 regression (2026-10 bug hunt, low-severity defects).

1. The Pulse kept showing a hidden need's title through its 'answered' and 'fulfilled' events.
2. A blocked neighbour's name still showed to the blocker on other people's need and match pages.
3. Deleting a need that was ever under a legal hold returned 500 and left a false
   need.deleted row in the append-only audit log.
4. The other person was never told when a match was declined, cancelled, marked not done or
   marked done.
5. Competing proposals stayed open after a need or offer was fulfilled.
6. The hourly need sweep locked Need then Match while MatchUpdateView locked Match then Need:
   a deadlock under load (reproduced by the verifier with two Postgres connections).
7. /health/ said "ok" while the shared cache (sessions, rate limits) was down.
"""

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.holds.models import LegalHold
from apps.hub.selectors import pulse_events
from apps.moderation.models import Block
from apps.needs.models import Need
from apps.notifications.models import Notification
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


def _parish():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    asker = MemberFactory(community=community, display_name="Ada Asker")
    helper = MemberFactory(community=community, display_name="Ben Helper")
    need = NeedFactory(community=community, requester=asker, category=category, title="Firewood for winter")
    return community, category, asker, helper, need


def _update(member, match, status):
    return _client(member).post(reverse("match-update", args=[match.need.community.slug, match.id]), {"status": status})


# ── 1. The Pulse respects a hide ───────────────────────────────


@pytest.mark.parametrize("end", ["accepted", "fulfilled"])
def test_pulse_does_not_show_a_hidden_needs_title(end):
    community, _, _, helper, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")
    match.transition_to("accepted")
    if end == "fulfilled":
        match.refresh_from_db()
        match.transition_to("fulfilled")
    Need.objects.filter(pk=need.pk).update(moderation_hidden=True)
    reader = MemberFactory(community=community)

    titles = [e["title"] for e in pulse_events(community, viewer=reader)]

    assert "Firewood for winter" not in titles


# ── 2. A block hides the neighbour on third-party pages ────────


def test_blocked_neighbour_is_hidden_on_someone_elses_need_and_match():
    community, _, carol, ben, need = _parish()  # carol posted the need, ben proposes
    match = MatchFactory(need=need, offer=None, proposed_by=ben, status="proposed")
    ada = MemberFactory(community=community, role="member")
    Block.objects.create(community=community, blocker=ada, blocked=ben)

    page = _client(ada).get(reverse("need-detail", args=[community.slug, need.id])).content.decode()
    assert "Ben Helper" not in page
    assert _client(ada).get(reverse("match-detail", args=[community.slug, match.id])).status_code == 404
    # The people in the match keep it.
    assert _client(carol).get(reverse("match-detail", args=[community.slug, match.id])).status_code == 200
    assert _client(ben).get(reverse("match-detail", args=[community.slug, match.id])).status_code == 200


# ── 3. Legal holds and need deletion ───────────────────────────


def _delete(member, need):
    return _client(member).post(reverse("need-delete", args=[need.community.slug, need.id]))


def test_a_need_under_an_active_hold_cannot_be_deleted():
    _, _, asker, _, need = _parish()
    LegalHold.objects.create(scope=LegalHold.SCOPE_NEED, need=need, reference="Case 2026-001")

    resp = _delete(asker, need)

    assert resp.status_code == 409
    assert Need.objects.filter(pk=need.pk).exists()
    assert not AuditLog.objects.filter(action="need.deleted", resource_id=str(need.pk)).exists()


def test_a_need_that_was_once_held_is_closed_not_deleted():
    _, _, asker, _, need = _parish()
    LegalHold.objects.create(
        scope=LegalHold.SCOPE_NEED, need=need, reference="Case 2026-001", released_at=timezone.now()
    )

    resp = _delete(asker, need)

    assert resp.status_code == 302
    need.refresh_from_db()
    assert need.status == "closed"
    assert not AuditLog.objects.filter(action="need.deleted", resource_id=str(need.pk)).exists()
    assert AuditLog.objects.filter(action="need.closed", resource_id=str(need.pk)).exists()


def test_a_need_never_held_is_still_deleted():
    _, _, asker, _, need = _parish()
    assert _delete(asker, need).status_code == 302
    assert not Need.objects.filter(pk=need.pk).exists()
    assert AuditLog.objects.filter(action="need.deleted", resource_id=str(need.pk)).exists()


# ── 4. The other person hears about every ending ──────────────


def _accepted_volunteer_match():
    community, _, asker, helper, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")
    match.transition_to("accepted")
    return asker, helper, match


@pytest.mark.parametrize("status", ["cancelled", "unfulfilled", "fulfilled"])
def test_the_counterpart_is_told_when_the_helper_ends_a_match(status):
    asker, helper, match = _accepted_volunteer_match()
    Notification.objects.all().delete()

    assert _update(helper, match, status).status_code == 302

    assert Notification.objects.filter(recipient=asker.user).count() == 1
    assert not Notification.objects.filter(recipient=helper.user).exists()


def test_the_proposer_is_told_when_their_proposal_is_declined():
    _, _, asker, helper, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")

    assert _update(asker, match, "cancelled").status_code == 302

    assert Notification.objects.filter(recipient=helper.user, type="match_cancelled").exists()


# ── 5. Competing proposals close when the need is done ─────────


def test_competing_proposals_expire_when_a_match_is_fulfilled():
    community, category, asker, helper, need = _parish()
    winner = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")
    rival_helper = MemberFactory(community=community, display_name="Rival")
    rival = MatchFactory(need=need, offer=None, proposed_by=rival_helper, status="proposed")
    winner.transition_to("accepted")
    rival.refresh_from_db()
    assert rival.status == "proposed"  # a backup survives while the winner is only accepted

    assert _update(helper, winner, "fulfilled").status_code == 302

    rival.refresh_from_db()
    assert rival.status == "expired"
    assert Notification.objects.filter(recipient=rival_helper.user).exists()


def test_competing_proposals_on_the_same_offer_expire_too():
    community, category, asker, helper, need = _parish()
    offer = OfferFactory(community=community, offerer=helper, category=category)
    other_need = NeedFactory(community=community, category=category, title="Another ask")
    winner = MatchFactory(need=need, offer=offer, proposed_by=helper, status="proposed")
    rival = MatchFactory(need=other_need, offer=offer, proposed_by=helper, status="proposed")
    winner.record_yes(asker)
    winner.transition_to("accepted")

    assert _update(helper, winner, "fulfilled").status_code == 302

    rival.refresh_from_db()
    assert rival.status == "expired"


# ── 6. One lock order: Need, then Match ────────────────────────


def _first_lock_index(queries, table):
    for i, q in enumerate(queries):
        sql = q["sql"]
        if "FOR UPDATE" in sql and f'FROM "{table}"' in sql:
            return i
    return None


def test_match_update_locks_the_need_before_the_match():
    if connection.vendor != "postgresql":
        pytest.skip("row locks are a no-op on SQLite")
    _, _, asker, helper, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")

    with CaptureQueriesContext(connection) as ctx:
        _update(asker, match, "accepted")

    need_lock = _first_lock_index(ctx.captured_queries, "needs_need")
    match_lock = _first_lock_index(ctx.captured_queries, "matches_match")
    assert need_lock is not None and match_lock is not None
    assert need_lock < match_lock


def test_the_sweep_expires_proposals_through_the_state_machine():
    from apps.needs.tasks import expire_stale_needs

    _, _, _, helper, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")
    Need.objects.filter(pk=need.pk).update(expires_at=timezone.now() - timezone.timedelta(hours=1))

    expire_stale_needs()

    match.refresh_from_db()
    assert match.status == "expired"
    assert AuditLog.objects.filter(action="match.expired", resource_id=str(match.pk)).exists()


# ── 7. Health tells the truth about the cache ─────────────────


def test_health_is_503_when_the_cache_is_down(monkeypatch):
    from django.core.cache import cache as default_cache

    def down(*args, **kwargs):
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(default_cache, "set", down)
    resp = Client().get("/health/")
    assert resp.status_code == 503
    assert resp.json()["cache"].startswith("error")


def test_health_is_still_200_when_everything_is_up():
    resp = Client().get("/health/")
    assert resp.status_code == 200
    assert resp.json()["cache"] == "ok"
