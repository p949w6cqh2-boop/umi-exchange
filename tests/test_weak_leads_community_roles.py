"""2026-10 bug hunt, weaker leads: community roles and trust (L2, L3, L4, L9, L11, L31), verified
and fixed.

L2   The last-admin check ran without a lock, so two admins leaving (or demoting each other) at
     the same moment both passed it and the community was left with no admin.
L3   A coordinator who left kept the role, and rejoining with the join code brought it back, with
     casework access to every standard case. Rejoining now comes back as a member.
L4   A coordinator could broker a match between two neighbours who had blocked each other, and the
     refusals said "this neighbour", which told a blocked person they were blocked.
L9   A coordinator or admin could verify their own tag; at admin tier that includes "Priest".
L11  An account that had not passed the human check could create a community and publish a page
     anonymous visitors see, under the platform's name.
L31  The vouch form matched usernames ignoring case and took the first, so with "Maria" and
     "maria" both registered the vouch could land on the wrong person; registration allowed the
     case variant in the first place.
"""

import threading
import uuid
from unittest import mock

import pytest
from django.core.cache import cache
from django.db import connections
from django.test import Client
from django.urls import reverse

from apps.accounts.forms import RegistrationForm
from apps.audit.models import AuditLog
from apps.communities.models import Community, Member
from apps.matches.models import Match
from apps.moderation.models import Block
from apps.pages.models import CommunityPage
from apps.tags.models import MemberTag, Tag
from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory, OfferFactory, UserFactory

ORIGINAL_LAST_ADMIN = Member.is_last_active_admin.fget


@pytest.fixture(autouse=True)
def _env(settings):
    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _as(user):
    c = Client()
    c.force_login(user)
    return c


# ── L2: the last admin, under concurrency ──────────────────────


def _race(requests):
    """Run each (client, url, data) at once. Each request waits just after its last-admin check
    for the other to make its own, which is the interleaving that left no admin."""
    barrier = threading.Barrier(len(requests), timeout=3)

    def checked_then_wait(self):
        value = ORIGINAL_LAST_ADMIN(self)
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # the other request is waiting on the lock: exactly the fix
        return value

    def run(client, url, data):
        try:
            client.post(url, data)
        finally:
            connections.close_all()

    with mock.patch.object(Member, "is_last_active_admin", property(checked_then_wait)):
        threads = [threading.Thread(target=run, args=r) for r in requests]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)


@pytest.mark.django_db(transaction=True)
def test_two_admins_leaving_at_once_leave_one_admin():
    community = CommunityFactory()
    a = MemberFactory(community=community, role="admin")
    b = MemberFactory(community=community, role="admin")
    url = reverse("community-leave", kwargs={"slug": community.slug})

    _race([(_as(a.user), url, {}), (_as(b.user), url, {})])

    assert Member.objects.filter(community=community, role="admin", is_active=True).count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_admins_demoting_each_other_at_once_leave_one_admin():
    community = CommunityFactory()
    a = MemberFactory(community=community, role="admin")
    b = MemberFactory(community=community, role="admin")
    url = reverse("community-settings", kwargs={"slug": community.slug})

    _race(
        [
            (_as(a.user), url, {"action": "change_role", "member_id": str(b.pk), "role": "member"}),
            (_as(b.user), url, {"action": "change_role", "member_id": str(a.pk), "role": "member"}),
        ]
    )

    assert Member.objects.filter(community=community, role="admin", is_active=True).count() == 1


@pytest.mark.django_db
def test_the_last_admin_still_cannot_leave():
    community = CommunityFactory()
    a = MemberFactory(community=community, role="admin")
    _as(a.user).post(reverse("community-leave", kwargs={"slug": community.slug}))
    assert Member.objects.get(pk=a.pk).is_active


# ── L3 ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_coordinator_who_leaves_comes_back_as_a_member():
    community = CommunityFactory()
    MemberFactory(community=community, role="admin")
    coord = MemberFactory(community=community, role="coordinator")
    c = _as(coord.user)
    c.post(reverse("community-leave", kwargs={"slug": community.slug}))

    c.post(reverse("community-join"), {"join_code": community.join_code, "display_name": ""})

    coord.refresh_from_db()
    assert coord.is_active and coord.role == "member"
    joined = AuditLog.objects.filter(action="member.joined", resource_id=coord.pk).latest("timestamp")
    assert joined.details == {"role": "member", "rejoined": True, "role_before": "coordinator"}


# ── L4 ─────────────────────────────────────────────────────────


def _board():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    coord = MemberFactory(community=community, role="coordinator")
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=cat)
    offer = OfferFactory(community=community, offerer=offerer, category=cat)
    return community, coord, requester, offerer, need, offer


@pytest.mark.django_db
def test_a_coordinator_cannot_broker_a_match_between_two_who_blocked_each_other():
    community, coord, requester, offerer, need, offer = _board()
    Block.objects.create(community=community, blocker=offerer, blocked=requester)

    resp = _as(coord.user).post(
        reverse("match-propose", kwargs={"slug": community.slug}), {"need_id": str(need.pk), "offer_id": str(offer.pk)}
    )

    assert resp.status_code == 409
    assert not Match.objects.filter(need=need, offer=offer).exists()


@pytest.mark.django_db
def test_refusals_do_not_tell_a_blocked_person_about_the_block():
    community, coord, requester, offerer, need, offer = _board()
    _as(offerer.user).post(
        reverse("match-propose", kwargs={"slug": community.slug}), {"need_id": str(need.pk), "offer_id": str(offer.pk)}
    )
    match = Match.objects.get(need=need, offer=offer)
    Block.objects.create(community=community, blocker=offerer, blocked=requester)

    accept = _as(requester.user).post(
        reverse("match-update", kwargs={"slug": community.slug, "pk": match.pk}), {"status": "accepted"}
    )
    other_need = NeedFactory(community=community, requester=offerer, category=need.category)
    propose = _as(requester.user).post(
        reverse("match-propose", kwargs={"slug": community.slug}), {"need_id": str(other_need.pk)}
    )

    assert accept.status_code == 409 and propose.status_code == 409
    for resp in (accept, propose):
        assert "neighbour" not in resp.content.decode().lower()


# ── L9 ─────────────────────────────────────────────────────────


def _claim(member, slug):
    tag = Tag.objects.get(community=member.community, slug=slug)
    _as(member.user).post(
        reverse("tags:claim", kwargs={"slug": member.community.slug}),
        {"tag": str(tag.pk), "visibility": tag.default_visibility},
    )
    return MemberTag.objects.get(member=member, tag=tag)


@pytest.mark.django_db
@pytest.mark.parametrize("role,slug", [("admin", "priest"), ("coordinator", "licensed-contractor")])
def test_nobody_verifies_their_own_tag(role, slug):
    me = MemberFactory(role=role)
    mt = _claim(me, slug)

    resp = _as(me.user).post(
        reverse("tags:verify", kwargs={"slug": me.community.slug, "pk": mt.pk}), {"evidence_note": "It is me."}
    )

    mt.refresh_from_db()
    assert resp.status_code == 403
    assert mt.status == "pending"


@pytest.mark.django_db
def test_another_admin_can_still_verify_it():
    me = MemberFactory(role="admin")
    other = MemberFactory(community=me.community, role="admin")
    mt = _claim(me, "priest")

    _as(other.user).post(
        reverse("tags:verify", kwargs={"slug": me.community.slug, "pk": mt.pk}), {"evidence_note": "Seen at Mass."}
    )

    mt.refresh_from_db()
    assert mt.status == "verified"


# ── L11 ────────────────────────────────────────────────────────


def _draft_page(user):
    c = _as(user)
    c.post(reverse("community-create"), {"name": "UMI Account Support", "description": "", "visibility": "unlisted"})
    community = Community.objects.get(name="UMI Account Support")
    c.post(
        reverse("pages:create", kwargs={"slug": community.slug}),
        {"title": "Verify your account", "slug": "verify", "content_md": "Keep it open.", "sort_order": 0},
    )
    page = CommunityPage.objects.get(community=community, slug="verify")
    c.post(reverse("pages:toggle-landing", kwargs={"slug": community.slug, "pk": page.pk}))
    return c, community, page


@pytest.mark.django_db
def test_an_unverified_account_cannot_publish_a_page_to_anonymous_visitors():
    newbie = UserFactory(email=None, email_confirmed_at=None, verified_at=None, verified_via="")
    c, community, page = _draft_page(newbie)

    resp = c.post(reverse("pages:publish", kwargs={"slug": community.slug, "pk": page.pk}))

    assert resp.status_code == 302 and resp["Location"] == reverse("verify-pending")
    page.refresh_from_db()
    assert page.status != "published"
    anon = Client().get(reverse("pages:view", kwargs={"slug": community.slug, "page_slug": "verify"}))
    assert anon.status_code != 200


@pytest.mark.django_db
def test_a_verified_admin_still_publishes():
    c, community, page = _draft_page(UserFactory())
    c.post(reverse("pages:publish", kwargs={"slug": community.slug, "pk": page.pk}))
    page.refresh_from_db()
    assert page.status == "published"


# ── L31 ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_registration_refuses_a_case_variant_of_an_existing_username():
    UserFactory(username="maria")
    form = RegistrationForm(
        data={
            "username": "Maria",
            "email": "",
            "password": "Str0ng-pass-word!",
            "password_confirm": "Str0ng-pass-word!",
        }
    )
    assert not form.is_valid()
    assert "username" in form.errors


@pytest.mark.django_db
def test_a_vouch_goes_to_the_exact_username():
    # The impostor sorts first, which is the one a case-blind .first() picked.
    impostor = UserFactory(
        id=uuid.UUID("00000000-0000-4000-8000-000000000001"), username="Maria", verified_at=None, verified_via=""
    )
    real = UserFactory(
        id=uuid.UUID("ffffffff-ffff-4fff-bfff-ffffffffffff"), username="maria", verified_at=None, verified_via=""
    )
    coordinator = MemberFactory(role="coordinator")

    _as(coordinator.user).post(
        reverse("member-vouch", kwargs={"slug": coordinator.community.slug}), {"username": "maria"}
    )

    real.refresh_from_db()
    impostor.refresh_from_db()
    assert real.is_human_verified and not impostor.is_human_verified


@pytest.mark.django_db
def test_an_ambiguous_vouch_verifies_nobody():
    one = UserFactory(username="Maria", verified_at=None, verified_via="")
    two = UserFactory(username="MARIA", verified_at=None, verified_via="")
    coordinator = MemberFactory(role="coordinator")

    _as(coordinator.user).post(
        reverse("member-vouch", kwargs={"slug": coordinator.community.slug}), {"username": "maria"}
    )

    one.refresh_from_db()
    two.refresh_from_db()
    assert not one.is_human_verified and not two.is_human_verified
