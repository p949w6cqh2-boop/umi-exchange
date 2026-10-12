"""Leaving hides your posts; coming back, you choose which return (founder's decision 2026-10-12,
bug hunt #8).

Leaving withdrew nothing. The leaver's asks stayed on the board under their name, neighbours
proposed on them, the leaver was emailed links that 404, and coordinators kept reading their
live email and phone, including a number changed after leaving. Now leaving takes their open
asks and offers off the board (hidden, never deleted), cancels the matches still in progress
(the other person is told), and stops the community handing out their contact. Rejoining does
not repost anything: the posts stay hidden until the member puts each one back, or closes it.
"""

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.communities.models import Member
from apps.matches.models import Match
from apps.moderation.models import Flag
from apps.moderation.services import reinstate_member, remove_member
from apps.needs.models import Need
from apps.needs.tasks import expire_stale_needs
from apps.notifications.models import Notification
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db

CARD = "stayed off the board"


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
    coordinator = MemberFactory(community=community, role="coordinator", display_name="Cora")
    leaver = MemberFactory(community=community, display_name="Lee")
    neighbour = MemberFactory(community=community, display_name="Nia")
    need = NeedFactory(community=community, requester=leaver, category=category, title="Ride to Mass")
    offer = OfferFactory(community=community, offerer=leaver, category=category, title="Can fix bikes")
    return community, category, coordinator, leaver, neighbour, need, offer


def _leave(member):
    return _client(member).post(reverse("community-leave", args=[member.community.slug]))


def _rejoin(member):
    return _client(member).post(reverse("community-join"), {"join_code": member.community.join_code}, follow=True)


def _board(viewer):
    return _client(viewer).get(reverse("community-feed", args=[viewer.community.slug])).content.decode()


def _choose(member, action, post):
    kind = "need" if isinstance(post, Need) else "offer"
    return _client(member).post(
        reverse("left-posts", args=[member.community.slug]), {"action": action, "kind": kind, "id": str(post.pk)}
    )


# ── Leaving ────────────────────────────────────────────────────


def test_leaving_takes_open_posts_off_the_board_without_deleting_them():
    community, category, _, leaver, neighbour, need, offer = _parish()
    done = NeedFactory(community=community, requester=leaver, category=category, status="fulfilled")
    assert "Ride to Mass" in _board(neighbour)

    assert _leave(leaver).status_code == 302

    board = _board(neighbour)
    assert "Ride to Mass" not in board and "Can fix bikes" not in board
    need.refresh_from_db()
    offer.refresh_from_db()
    assert (need.status, need.moderation_hidden) == ("open", True) and need.hidden_on_leave_at is not None
    assert (offer.status, offer.moderation_hidden) == ("active", True) and offer.hidden_on_leave_at is not None
    done.refresh_from_db()
    assert not done.moderation_hidden and done.hidden_on_leave_at is None  # history stays as it was


def test_leaving_cancels_matches_in_progress_and_tells_the_other_person():
    community, category, _, leaver, neighbour, need, _ = _parish()
    their_need = NeedFactory(community=community, requester=neighbour, category=category, title="Groceries")
    on_mine = MatchFactory(need=need, offer=None, proposed_by=neighbour, status="proposed")
    on_theirs = MatchFactory(need=their_need, offer=None, proposed_by=leaver, status="proposed")
    on_theirs.transition_to("accepted")
    Notification.objects.all().delete()

    _leave(leaver)

    for match in (on_mine, on_theirs):
        match.refresh_from_db()
        assert match.status == "cancelled"
    assert Notification.objects.filter(recipient=neighbour.user, type="match_cancelled").count() == 2
    assert not Notification.objects.filter(recipient=leaver.user).exists()
    their_need.refresh_from_db()
    assert their_need.status == "open" and "Groceries" in _board(neighbour)  # their ask is back up


def test_nobody_can_propose_on_a_leavers_ask():
    community, _, _, leaver, neighbour, need, _ = _parish()
    _leave(leaver)

    resp = _client(neighbour).post(reverse("match-propose", args=[community.slug]), {"need_id": str(need.pk)})

    assert resp.status_code == 404
    assert not Match.objects.exists()


def test_coordinators_no_longer_see_a_leavers_contact():
    community, _, coordinator, leaver, _, need, _ = _parish()
    Need.objects.filter(pk=need.pk).update(contact_pref="phone")
    leaver.user.phone = "555-0100"
    leaver.user.save(update_fields=["phone"])
    page = reverse("need-detail", args=[community.slug, need.pk])
    assert "555-0100" in _client(coordinator).get(page).content.decode()

    _leave(leaver)
    leaver.user.phone = "555-0199"  # a number changed after leaving
    leaver.user.save(update_fields=["phone"])

    html = _client(coordinator).get(page).content.decode()
    assert "555-0100" not in html and "555-0199" not in html


def test_an_old_match_partner_no_longer_sees_a_leavers_contact():
    community, _, _, leaver, neighbour, need, _ = _parish()
    Need.objects.filter(pk=need.pk).update(contact_pref="phone")
    leaver.user.phone = "555-0100"
    leaver.user.save(update_fields=["phone"])
    match = MatchFactory(need=need, offer=None, proposed_by=neighbour, status="proposed")
    match.transition_to("accepted")
    match.refresh_from_db()
    match.transition_to("fulfilled")
    page = reverse("match-detail", args=[community.slug, match.pk])
    assert "555-0100" in _client(neighbour).get(page).content.decode()

    _leave(leaver)

    assert "555-0100" not in _client(neighbour).get(page).content.decode()


def test_the_expiry_sweep_does_not_write_to_someone_who_left():
    _, _, _, leaver, _, need, _ = _parish()
    _leave(leaver)
    Need.objects.filter(pk=need.pk).update(expires_at=timezone.now() - timezone.timedelta(hours=1))

    expire_stale_needs()

    need.refresh_from_db()
    assert need.status == "expired"
    assert not Notification.objects.filter(recipient=leaver.user, type="need_expired").exists()


# ── Coming back ────────────────────────────────────────────────


def test_rejoining_keeps_posts_hidden_and_offers_the_choice():
    community, _, _, leaver, neighbour, need, offer = _parish()
    _leave(leaver)

    resp = _rejoin(leaver)

    assert Member.objects.get(pk=leaver.pk).is_active
    need.refresh_from_db()
    assert need.moderation_hidden  # nothing reposted on its own
    assert "Ride to Mass" not in _board(neighbour)
    assert CARD in resp.content.decode()
    page = _client(leaver).get(reverse("left-posts", args=[community.slug])).content.decode()
    assert "Ride to Mass" in page and "Can fix bikes" in page


def test_put_it_back_returns_just_that_post_to_the_board():
    _, _, _, leaver, neighbour, need, offer = _parish()
    _leave(leaver)
    _rejoin(leaver)

    assert _choose(leaver, "restore", need).status_code == 302

    need.refresh_from_db()
    offer.refresh_from_db()
    assert not need.moderation_hidden and need.hidden_on_leave_at is None
    assert offer.moderation_hidden  # the other one waits for its own choice
    board = _board(neighbour)
    assert "Ride to Mass" in board and "Can fix bikes" not in board


def test_close_it_keeps_the_post_off_for_good_and_the_card_goes():
    _, _, _, leaver, _, need, offer = _parish()
    _leave(leaver)
    _rejoin(leaver)

    _choose(leaver, "close", need)
    _choose(leaver, "close", offer)

    need.refresh_from_db()
    offer.refresh_from_db()
    assert (need.status, need.moderation_hidden, need.hidden_on_leave_at) == ("closed", True, None)
    assert (offer.status, offer.moderation_hidden, offer.hidden_on_leave_at) == ("withdrawn", True, None)
    assert CARD not in _board(leaver)


def test_a_restored_ask_past_its_date_gets_a_fresh_window():
    _, _, _, leaver, _, need, _ = _parish()
    _leave(leaver)
    _rejoin(leaver)
    Need.objects.filter(pk=need.pk).update(expires_at=timezone.now() - timezone.timedelta(minutes=5))

    _choose(leaver, "restore", need)

    need.refresh_from_db()
    assert need.expires_at > timezone.now()


# ── What the choice can't reach ────────────────────────────────


def test_a_member_cannot_put_back_a_post_a_coordinator_hid():
    community, _, coordinator, leaver, neighbour, need, _ = _parish()
    flag = Flag.objects.create(
        community=community, reporter=neighbour, target_type="need", target_id=need.pk, reason="spam"
    )
    _leave(leaver)
    _client(coordinator).post(reverse("moderation:resolve", args=[community.slug, flag.pk]), {"action": "hide"})
    _rejoin(leaver)

    assert "Ride to Mass" not in _client(leaver).get(reverse("left-posts", args=[community.slug])).content.decode()
    assert _choose(leaver, "restore", need).status_code == 404
    need.refresh_from_db()
    assert need.moderation_hidden


def test_a_member_cannot_choose_for_someone_elses_post():
    _, _, _, leaver, neighbour, need, _ = _parish()
    _leave(leaver)

    assert _choose(neighbour, "restore", need).status_code == 404
    need.refresh_from_db()
    assert need.moderation_hidden


def test_reinstating_a_removed_member_does_not_repost_what_leaving_hid():
    _, _, coordinator, leaver, _, need, _ = _parish()
    _leave(leaver)
    _rejoin(leaver)
    leaver.refresh_from_db()
    remove_member(leaver, by=coordinator)
    leaver.refresh_from_db()

    reinstate_member(leaver, by=coordinator)

    need.refresh_from_db()
    assert need.moderation_hidden and need.hidden_on_leave_at is not None  # still theirs to choose
