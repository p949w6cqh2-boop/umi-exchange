"""The word list flags, it never refuses (founder's decision, 2026-10-12).

Until now a word on the list ("drugs", "abuse", "suicide", ...) refused the whole post, so a
neighbour asking for a prescription pickup was turned away. Now the post goes up, and an
automatic flag (no reporter) puts it in the coordinators' review queue. The poster is told,
because the UI narrates its own restraint (voice rule 4). The same holds everywhere the list
used to refuse: asks, offers, the display name chosen on joining, and match notes.
"""

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.communities.models import Member
from apps.moderation.forms import FlagForm
from apps.moderation.models import Flag
from apps.needs.models import Need
from apps.notifications.models import Notification
from apps.offers.models import Offer
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory, UserFactory

pytestmark = pytest.mark.django_db

REVIEW_COPY = "a coordinator will take a look"


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _client(member_or_user):
    c = Client()
    c.force_login(getattr(member_or_user, "user", member_or_user))
    return c


def _parish():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    coordinator = MemberFactory(community=community, role="coordinator")
    asker = MemberFactory(community=community)
    return community, category, coordinator, asker


def _post_need(member, category, **fields):
    data = {
        "category": str(category.id),
        "title": "Ride to the pharmacy",
        "description": "",
        "urgency": "medium",
        "neighborhood": "",
        "contact_pref": "in_app",
    }
    data.update(fields)
    return _client(member).post(reverse("need-create", args=[member.community.slug]), data, follow=True)


def _auto_flags(target_type, target_id):
    return Flag.objects.filter(target_type=target_type, target_id=target_id, reporter__isnull=True)


# ── Asks and offers go up, flagged ─────────────────────────────


def test_an_ask_using_a_listed_word_is_posted_and_flagged():
    community, category, coordinator, asker = _parish()

    resp = _post_need(asker, category, description="Pick up my prescription drugs")

    need = Need.objects.get(title="Ride to the pharmacy")
    assert need.moderation_hidden is False  # on the board, not held back
    flag = _auto_flags("need", need.pk).get()
    assert (flag.status, flag.reason, flag.detail, flag.community) == ("open", "word_list", "drugs", community)
    assert REVIEW_COPY in resp.content.decode()
    assert Notification.objects.filter(recipient=coordinator.user, type="flag_received").exists()
    assert AuditLog.objects.filter(action="flag.created", resource_id=str(flag.pk), user__isnull=True).exists()


def test_an_offer_using_a_listed_word_is_posted_and_flagged():
    community, category, coordinator, helper = _parish()

    resp = _client(helper).post(
        reverse("offer-create", args=[community.slug]),
        {
            "category": str(category.id),
            "title": "Weapon-free self defence class",
            "description": "",
            "contact_pref": "in_app",
        },
        follow=True,
    )

    offer = Offer.objects.get(title="Weapon-free self defence class")
    assert offer.moderation_hidden is False
    assert _auto_flags("offer", offer.pk).get().detail == "weapon"
    assert REVIEW_COPY in resp.content.decode()


def test_an_ordinary_ask_is_not_flagged():
    _, category, _, asker = _parish()

    resp = _post_need(asker, category, description="Two bags of groceries, thank you")

    assert not Flag.objects.exists()
    assert REVIEW_COPY not in resp.content.decode()


def test_the_poster_is_never_notified_about_their_own_post():
    community, category, coordinator, _ = _parish()

    _post_need(coordinator, category, description="Narcotics take-back day, I can drive")

    assert _auto_flags("need", Need.objects.get().pk).exists()
    assert not Notification.objects.filter(recipient=coordinator.user, type="flag_received").exists()


# ── A display name chosen on joining ───────────────────────────


def test_a_display_name_using_a_listed_word_joins_and_is_flagged():
    community, _, coordinator, _ = _parish()
    newcomer = UserFactory()

    resp = _client(newcomer).post(
        reverse("community-join"),
        {"join_code": community.join_code, "display_name": "Escort to appointments"},
        follow=True,
    )

    member = Member.objects.get(user=newcomer, community=community)
    assert member.is_active
    assert _auto_flags("member", member.pk).get().detail == "escort"
    assert REVIEW_COPY in resp.content.decode()


# ── Match notes ────────────────────────────────────────────────


def _proposed_match(community, asker, category):
    helper = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=asker, category=category)
    return MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")


def test_match_notes_using_a_listed_word_go_through_and_are_flagged_once():
    community, category, _, asker = _parish()
    match = _proposed_match(community, asker, category)
    url = reverse("match-update", kwargs={"slug": community.slug, "pk": match.id})
    client = _client(asker)

    assert client.post(url, {"status": "accepted", "notes": "Bring the drugs list"}).status_code == 302
    assert client.post(url, {"status": "fulfilled", "notes": "Got the drugs, thank you"}).status_code == 302

    match.refresh_from_db()
    assert (match.status, match.notes) == ("fulfilled", "Got the drugs, thank you")
    assert _auto_flags("match", match.pk).filter(status="open").count() == 1  # one open per target, no pile-on


# ── The coordinators' queue ────────────────────────────────────


def test_the_queue_shows_an_automatic_flag_and_keep_works_without_a_reporter():
    community, category, coordinator, asker = _parish()
    _post_need(asker, category, description="Support group for abuse survivors")
    flag = Flag.objects.get()
    queue = reverse("moderation:queue", args=[community.slug])

    page = _client(coordinator).get(queue).content.decode()
    assert "flagged automatically" in page
    assert "abuse" in page

    resp = _client(coordinator).post(reverse("moderation:resolve", args=[community.slug, flag.pk]), {"action": "keep"})
    assert resp.status_code == 302
    flag.refresh_from_db()
    assert (flag.status, flag.resolution) == ("resolved", "keep")


def test_hide_from_an_automatic_flag_takes_the_ask_down():
    community, category, coordinator, asker = _parish()
    _post_need(asker, category, description="Selling drugs")
    flag = Flag.objects.get()

    _client(coordinator).post(reverse("moderation:resolve", args=[community.slug, flag.pk]), {"action": "hide"})

    assert Need.objects.get().moderation_hidden is True


def test_a_match_flag_offers_no_hide_and_refuses_one():
    community, category, coordinator, asker = _parish()
    match = _proposed_match(community, asker, category)
    _client(asker).post(
        reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}),
        {"status": "accepted", "notes": "Murder mystery night after?"},
    )
    flag = Flag.objects.get(target_type="match")

    page = _client(coordinator).get(reverse("moderation:queue", args=[community.slug])).content.decode()
    assert reverse("match-detail", args=[community.slug, match.pk]) in page
    assert 'value="hide"' not in page

    _client(coordinator).post(reverse("moderation:resolve", args=[community.slug, flag.pk]), {"action": "hide"})
    flag.refresh_from_db()
    assert flag.status == "open"  # nothing to hide on a match: the coordinator talks to the two people


def test_members_cannot_file_a_word_list_flag_by_hand():
    assert not FlagForm({"reason": "word_list", "detail": ""}).is_valid()
