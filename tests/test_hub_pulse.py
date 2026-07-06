"""Hub v2 — "The Pulse": a living stream of witnessed generosity, one
spotlight ask with instant agency, your corner, and collective week stats.
No leaderboards; the helper in a pulse entry is always "a neighbour"."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.hub import selectors
from tests.conftest import (
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    community = CommunityFactory()
    frances = MemberFactory(community=community, display_name="Frances")
    nuala = MemberFactory(community=community, display_name="Nuala D.")
    tomas = MemberFactory(community=community, display_name="Tomás B.")
    return type("W", (), {"community": community, "frances": frances, "nuala": nuala, "tomas": tomas})


# ── pulse_events ────────────────────────────────────────────────


def test_pulse_merges_kinds_newest_first(world):
    need = NeedFactory(community=world.community, requester=world.nuala, title="A lift to Mass")
    OfferFactory(community=world.community, offerer=world.tomas, title="I can drive")
    match = MatchFactory(need=need, proposed_by=world.tomas, status="proposed")
    match.transition_to("accepted")
    events = selectors.pulse_events(world.community)
    kinds = [e["kind"] for e in events]
    assert "member_joined" in kinds  # the fixtures joined
    assert "need_posted" in kinds and "offer_posted" in kinds
    assert "ask_answered" in kinds
    whens = [e["when"] for e in events]
    assert whens == sorted(whens, reverse=True)  # newest first


def test_pulse_fulfilled_is_celebrated_and_helper_stays_anonymous(world):
    need = NeedFactory(community=world.community, requester=world.nuala, title="Groceries for the week")
    match = MatchFactory(need=need, proposed_by=world.tomas, status="proposed")
    match.transition_to("accepted")
    match.transition_to("fulfilled")
    events = selectors.pulse_events(world.community)
    fulfilled = [e for e in events if e["kind"] == "need_fulfilled"]
    assert fulfilled and "Groceries for the week" in fulfilled[0]["title"]
    text = str(fulfilled) + str([e for e in events if e["kind"] == "ask_answered"])
    assert "Tomás" not in text  # §8.2 spirit: the helper is "a neighbour" in public


def test_pulse_scoped_to_community_and_capped(world):
    other = CommunityFactory()
    stranger = MemberFactory(community=other)
    NeedFactory(community=other, requester=stranger, title="Elsewhere ask")
    for i in range(45):
        NeedFactory(community=world.community, requester=world.nuala, title=f"ask {i}")
    events = selectors.pulse_events(world.community)
    assert len(events) <= selectors.PULSE_CAP
    assert all("Elsewhere ask" not in (e.get("title") or "") for e in events)


# ── spotlight_need ──────────────────────────────────────────────


def test_spotlight_prefers_urgent_then_oldest_unanswered(world):
    old_low = NeedFactory(community=world.community, requester=world.nuala, title="old low", urgency="low")
    type(old_low).objects.filter(pk=old_low.pk).update(created_at=timezone.now() - timedelta(days=6))
    urgent = NeedFactory(community=world.community, requester=world.nuala, title="urgent now", urgency="critical")
    pick = selectors.spotlight_need(world.frances)
    assert pick.pk == urgent.pk

    # answered asks drop out: once the urgent one has a live match, the oldest rises
    MatchFactory(need=urgent, proposed_by=world.tomas, status="proposed")
    pick = selectors.spotlight_need(world.frances)
    assert pick.pk == old_low.pk


def test_spotlight_never_your_own_ask_and_cycles(world):
    mine = NeedFactory(community=world.community, requester=world.frances, title="my own ask", urgency="critical")
    other = NeedFactory(community=world.community, requester=world.nuala, title="their ask", urgency="low")
    assert selectors.spotlight_need(world.frances).pk == other.pk
    assert mine.pk != other.pk
    # cycling walks the queue and wraps
    second = NeedFactory(community=world.community, requester=world.tomas, title="another ask", urgency="low")
    picks = {selectors.spotlight_need(world.frances, cycle=i).pk for i in range(3)}
    assert picks == {other.pk, second.pk}


# ── season_impact + week_stats ──────────────────────────────────


def test_season_impact_counts_helper_side_fulfilled(world):
    need = NeedFactory(community=world.community, requester=world.nuala)
    match = MatchFactory(need=need, proposed_by=world.tomas, status="proposed")
    match.transition_to("accepted")
    match.transition_to("fulfilled")
    assert selectors.season_impact(world.tomas) == 1
    assert selectors.season_impact(world.nuala) == 0  # asking isn't scored either way
    assert selectors.season_impact(world.frances) == 0


def test_week_stats_shape(world):
    need = NeedFactory(community=world.community, requester=world.nuala)
    match = MatchFactory(need=need, proposed_by=world.tomas, status="proposed")
    match.transition_to("accepted")
    stats = selectors.week_stats(world.community)
    assert stats["hands_raised"] == 1
    assert stats["asks_answered"] == 1
    assert stats["fulfilled"] == 0


# ── the page + HTMX endpoints ───────────────────────────────────


def _hub_url(community):
    return reverse("hub:community", kwargs={"slug": community.slug})


def test_hub_renders_pulse_spotlight_and_week_strip(client, world):
    need = NeedFactory(community=world.community, requester=world.nuala, title="A lift to Mass", urgency="high")
    client.force_login(world.frances.user)
    body = client.get(_hub_url(world.community)).content.decode()
    assert "A lift to Mass" in body
    assert "I can help" in body  # spotlight agency
    assert "The pulse" in body  # the stream
    assert "This week" in body  # collective strip
    assert need.title in body


def test_pulse_partial_endpoint_polls(client, world):
    NeedFactory(community=world.community, requester=world.nuala, title="Fresh ask")
    client.force_login(world.frances.user)
    url = reverse("hub:pulse", kwargs={"slug": world.community.slug})
    resp = client.get(url, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert "Fresh ask" in resp.content.decode()


def test_spotlight_partial_cycles(client, world):
    NeedFactory(community=world.community, requester=world.nuala, title="ask one", urgency="low")
    NeedFactory(community=world.community, requester=world.tomas, title="ask two", urgency="low")
    client.force_login(world.frances.user)
    url = reverse("hub:spotlight", kwargs={"slug": world.community.slug})
    first = client.get(url, {"cycle": 0}, HTTP_HX_REQUEST="true").content.decode()
    second = client.get(url, {"cycle": 1}, HTTP_HX_REQUEST="true").content.decode()
    assert ("ask one" in first) != ("ask one" in second)  # cycling changes the pick


def test_pulse_endpoints_scoped_to_members(client, world):
    outsider = UserFactory()
    client.force_login(outsider)
    url = reverse("hub:pulse", kwargs={"slug": world.community.slug})
    assert client.get(url, HTTP_HX_REQUEST="true").status_code in (302, 403, 404)
