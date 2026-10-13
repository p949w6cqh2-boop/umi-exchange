"""The bug hunt's weaker leads, board and state group (verified 2026-10-13, all real).

L5   A GET on a need's or offer's delete URL was a 500 (no confirmation template).
L6   A malformed id in a propose, role-change or resource POST was a 500.
L7   A community switched off in admin stayed writable by direct URL, and its coordinators
     kept their powers there: vouch any account, reset codes, intake, settings, export.
L8   A match page showed a hidden need's title to anyone in the community holding the link.
L28  Offers never expired, though spec §10.6 says needs and offers MUST.
L33  Deleting the offer behind a fulfilled brokered match made the coordinator its "helper".
L34  A double-tapped Join was a 500.
L35  Re-seeding the demo adopted a real account holding a seed username.
L38  A need deleted mid-sweep stopped the hourly sweep.
L40  A double-tapped Propose made two identical proposals.
L41  A tag rejection could be lost (count read from memory).
L42  save(update_fields=["phone"]) kept the old number's proof.
L45  A settings rename clobbered a theme change and REVERTED a join-code rotation.
L66  A resource link over 500 characters was a 500.
L68  The export's ?type= went into Content-Disposition unchecked.
"""

import io

import pytest
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.communities.models import Community, Member, Resource
from apps.matches.models import Match
from apps.needs.models import Need
from apps.notifications.models import Notification
from apps.offers.models import Offer
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _client(member_or_user):
    c = Client(raise_request_exception=False)
    c.force_login(getattr(member_or_user, "user", member_or_user))
    return c


def _parish(**community):
    c = CommunityFactory(**community)
    cat = CategoryFactory(community=c)
    w = {
        "c": c,
        "cat": cat,
        "admin": MemberFactory(community=c, role="admin"),
        "coord": MemberFactory(community=c, role="coordinator"),
        "asker": MemberFactory(community=c),
        "helper": MemberFactory(community=c),
    }
    w["need"] = NeedFactory(community=c, requester=w["asker"], category=cat, title="Ride to the clinic")
    w["offer"] = OfferFactory(community=c, offerer=w["helper"], category=cat, title="Can drive on Fridays")
    return w


# ── L5 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["need", "offer"])
def test_a_get_on_a_delete_url_goes_to_the_post(kind):
    w = _parish()
    post, owner = (w["need"], w["asker"]) if kind == "need" else (w["offer"], w["helper"])
    resp = _client(owner).get(reverse(f"{kind}-delete", args=[w["c"].slug, post.id]))
    assert resp.status_code == 302 and resp["Location"] == reverse(f"{kind}-detail", args=[w["c"].slug, post.id])


# ── L6 ──────────────────────────────────────────────────────────


def test_malformed_ids_are_misses_not_500s():
    w = _parish()
    s = w["c"].slug
    Resource.objects.create(community=w["c"], title="Food bank", url="https://example.org/", added_by=w["admin"])
    helper = _client(w["helper"])
    assert (
        helper.post(reverse("match-propose", args=[s]), {"need_id": "x", "offer_id": str(w["offer"].id)}).status_code
        == 404
    )
    assert (
        helper.post(reverse("match-propose", args=[s]), {"need_id": str(w["need"].id), "offer_id": "x"}).status_code
        == 404
    )
    admin = _client(w["admin"])
    role = admin.post(
        reverse("community-settings", args=[s]), {"action": "change_role", "member_id": "x", "role": "member"}
    )
    assert role.status_code == 302  # "Invalid member or role.", as for any unknown member
    assert (
        admin.post(reverse("community-resources", args=[s]), {"action": "archive", "resource_id": "x"}).status_code
        == 404
    )


# ── L7 ──────────────────────────────────────────────────────────


@pytest.fixture
def closed():
    w = _parish(is_active=False)
    return w


def test_a_closed_community_takes_no_new_posts(closed):
    s = closed["c"].slug
    data = {"category": str(closed["cat"].id), "title": "Ride please", "urgency": "medium", "contact_pref": "in_app"}
    assert _client(closed["asker"]).post(reverse("need-create", args=[s]), data).status_code == 404
    offer = {"category": str(closed["cat"].id), "title": "Rides", "contact_pref": "in_app"}
    assert _client(closed["helper"]).post(reverse("offer-create", args=[s]), offer).status_code == 404


def test_a_closed_community_takes_no_proposals_or_accepts(closed):
    s = closed["c"].slug
    propose = {"need_id": str(closed["need"].id), "offer_id": str(closed["offer"].id)}
    assert _client(closed["helper"]).post(reverse("match-propose", args=[s]), propose).status_code == 404
    m = MatchFactory(need=closed["need"], offer=closed["offer"], proposed_by=closed["helper"])
    assert (
        _client(closed["asker"]).post(reverse("match-update", args=[s, m.id]), {"status": "accepted"}).status_code
        == 404
    )


def test_a_closed_communitys_coordinators_cannot_vouch_or_reset(closed):
    stranger = UserFactory(verified_at=None, verified_via="")
    s = closed["c"].slug
    assert (
        _client(closed["coord"]).post(reverse("member-vouch", args=[s]), {"username": stranger.username}).status_code
        == 404
    )
    stranger.refresh_from_db()
    assert not stranger.is_human_verified
    reset = _client(closed["coord"]).post(
        reverse("member-reset", args=[s]), {"username": closed["asker"].user.username}
    )
    assert reset.status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "community-dashboard",
        "dashboard-export",
        "community-settings",
        "intake-register",
        "community-activity",
        "member-vouch-page",
    ],
)
def test_a_closed_communitys_coordinator_pages_are_gone(closed, name):
    assert _client(closed["admin"]).get(reverse(name, args=[closed["c"].slug])).status_code == 404


def test_a_closed_communitys_posts_and_matches_are_gone(closed):
    s = closed["c"].slug
    m = MatchFactory(need=closed["need"], offer=closed["offer"], proposed_by=closed["helper"])
    assert _client(closed["asker"]).get(reverse("need-detail", args=[s, closed["need"].id])).status_code == 404
    assert _client(closed["helper"]).get(reverse("offer-detail", args=[s, closed["offer"].id])).status_code == 404
    assert _client(closed["asker"]).get(reverse("match-detail", args=[s, m.id])).status_code == 404


def test_leaving_a_closed_community_still_works(closed):
    resp = _client(closed["asker"]).post(reverse("community-leave", args=[closed["c"].slug]))
    assert resp.status_code == 302
    assert not Member.objects.get(pk=closed["asker"].pk).is_active


# ── L8 ──────────────────────────────────────────────────────────


def test_a_match_page_does_not_show_a_hidden_need_to_a_bystander():
    w = _parish()
    m = MatchFactory(need=w["need"], offer=w["offer"], proposed_by=w["helper"])
    Need.objects.filter(pk=w["need"].pk).update(moderation_hidden=True)
    bystander = MemberFactory(community=w["c"])
    url = reverse("match-detail", args=[w["c"].slug, m.id])
    assert _client(bystander).get(url).status_code == 404
    assert _client(w["asker"]).get(url).status_code == 200  # the two people in it keep it
    assert _client(w["coord"]).get(url).status_code == 200


# ── L28 ─────────────────────────────────────────────────────────


def test_an_offer_past_its_date_expires_and_leaves_the_board():
    from apps.offers.tasks import expire_stale_offers

    w = _parish()
    stale = OfferFactory(
        community=w["c"],
        offerer=w["helper"],
        category=w["cat"],
        title="Stale offer from last year",
        expires_at=timezone.now() - timezone.timedelta(days=1),
    )
    proposal = MatchFactory(need=w["need"], offer=stale, proposed_by=w["helper"], status="proposed")

    expire_stale_offers()

    stale.refresh_from_db()
    proposal.refresh_from_db()
    assert stale.status == "expired" and proposal.status == "expired"
    assert (
        "Stale offer from last year"
        not in _client(w["asker"]).get(reverse("community-feed", args=[w["c"].slug])).content.decode()
    )
    assert Notification.objects.filter(recipient=w["helper"].user, type="offer_expired").exists()
    w["offer"].refresh_from_db()
    assert w["offer"].status == "active"  # one still in date is left alone


# ── L33 ─────────────────────────────────────────────────────────


def test_deleting_an_offer_with_history_withdraws_it_and_keeps_the_helper():
    w = _parish()
    match = MatchFactory(need=w["need"], offer=w["offer"], proposed_by=w["coord"], status="fulfilled")

    resp = _client(w["helper"]).post(reverse("offer-delete", args=[w["c"].slug, w["offer"].id]))

    assert resp.status_code == 302
    w["offer"].refresh_from_db()
    assert w["offer"].status == "withdrawn"
    match.refresh_from_db()
    assert match.helper_member == w["helper"]


def test_an_offer_with_no_history_is_still_deleted():
    w = _parish()
    _client(w["helper"]).post(reverse("offer-delete", args=[w["c"].slug, w["offer"].id]))
    assert not Offer.objects.filter(pk=w["offer"].pk).exists()


# ── L34 ─────────────────────────────────────────────────────────


def test_a_double_tapped_join_is_not_a_500(monkeypatch):
    from apps.communities import views as cv

    community = CommunityFactory()
    person = UserFactory()
    Member.objects.create(user=person, community=community, display_name="Me", role="member")  # the other tap won

    class _Missed:  # ...after this tap had already checked and found nothing
        def first(self):
            return None

    class _Manager:
        def filter(self, **kw):
            return _Missed() if {"user", "community"} <= set(kw) else Member.objects.filter(**kw)

        def create(self, **kw):
            return Member.objects.create(**kw)

    monkeypatch.setattr(cv, "Member", type("Member", (), {"objects": _Manager()}))
    resp = _client(person).post(reverse("community-join"), {"join_code": community.join_code, "display_name": "Me"})

    assert resp.status_code == 302
    assert Member.objects.filter(user=person, community=community).count() == 1


# ── L35 ─────────────────────────────────────────────────────────


def test_the_demo_seed_never_adopts_a_real_account(settings):
    from apps.accounts.models import User

    settings.DEBUG = True
    real = User.objects.create_user(username="tom", email="tom.real@example.com", password="Real-person-pass-1")

    with pytest.raises(CommandError, match="tom"):
        call_command("seed_demo_parish", stdout=io.StringIO())

    real.refresh_from_db()
    assert not Member.objects.filter(user=real).exists() and real.phone == ""
    assert not Community.objects.filter(slug="st-brigids").exists()  # refused before writing anything


# ── L38 ─────────────────────────────────────────────────────────


def test_a_need_deleted_mid_sweep_does_not_stop_the_rest(monkeypatch):
    from apps.needs import tasks

    w = _parish()
    stale = [
        NeedFactory(
            community=w["c"],
            requester=w["asker"],
            category=w["cat"],
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        for _ in range(3)
    ]
    real_send = tasks.NotificationAdapter.send
    deleted = []

    def send(*args, **kwargs):
        if not deleted:  # the asker deletes another stale ask while the sweep is running
            victim = Need.objects.filter(pk__in=[n.pk for n in stale], status="open").first()
            deleted.append(victim.pk)
            victim.delete()
        return real_send(*args, **kwargs)

    monkeypatch.setattr(tasks.NotificationAdapter, "send", staticmethod(send))

    tasks.expire_stale_needs()

    left = Need.objects.filter(pk__in=[n.pk for n in stale])
    assert left.count() == 2 and all(n.status == "expired" for n in left)


# ── L40 ─────────────────────────────────────────────────────────


def test_the_same_proposal_twice_makes_one_match():
    w = _parish()
    url = reverse("match-propose", args=[w["c"].slug])
    data = {"need_id": str(w["need"].id), "offer_id": str(w["offer"].id)}
    c = _client(w["helper"])
    c.post(url, data)
    c.post(url, data)
    assert Match.objects.filter(need=w["need"], offer=w["offer"], status="proposed").count() == 1
    assert Notification.objects.filter(recipient=w["asker"].user, type="match_proposed").count() == 1


# ── L41 ─────────────────────────────────────────────────────────


def test_a_rejection_is_never_lost():
    from apps.tags.models import MemberTag, Tag

    c = CommunityFactory()
    a = MemberFactory(community=c, role="coordinator")
    b = MemberFactory(community=c, role="coordinator")
    tag = Tag.objects.create(community=c, slug="svdp", label="SVdP", tier="coordinator_verified")
    mt = MemberTag.objects.create(member=MemberFactory(community=c), tag=tag, status="pending")
    a_view = MemberTag.objects.select_related("tag", "member").get(pk=mt.pk)  # loaded, then b acts
    b_view = MemberTag.objects.select_related("tag", "member").get(pk=mt.pk)
    b_view.reject(b, reason="first")
    b_view.re_request(evidence_note="again")

    a_view.reject(a, reason="second")

    assert MemberTag.objects.get(pk=mt.pk).rejection_count == 2


# ── L42 ─────────────────────────────────────────────────────────


def test_a_new_phone_number_drops_the_old_proof_even_with_update_fields():
    user = UserFactory()
    user.phone = "555-0001"
    user.phone_confirmed_at = timezone.now()
    user.save()
    user.phone = "555-0002"
    user.save(update_fields=["phone"])
    user.refresh_from_db()
    assert user.phone_confirmed_at is None


# ── L45 ─────────────────────────────────────────────────────────


def test_a_rename_does_not_undo_a_theme_or_a_new_join_code(monkeypatch):
    from apps.communities import views as cv

    w = _parish()
    community = w["c"]
    real_save = cv.CommunitySettingsForm.save

    def meanwhile(self, *args, **kwargs):
        # Another admin's theme change and code rotation commit between this request's load and save.
        Community.objects.filter(pk=community.pk).update(settings={"theme": "royal"}, join_code="NEWCODE9")
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(cv.CommunitySettingsForm, "save", meanwhile)
    _client(w["admin"]).post(
        reverse("community-settings", args=[community.slug]),
        {"name": "Renamed parish", "description": "", "visibility": "private"},
    )

    final = Community.objects.get(pk=community.pk)
    assert final.name == "Renamed parish"
    assert final.settings.get("theme") == "royal" and final.join_code == "NEWCODE9"


# ── L66, L68 ────────────────────────────────────────────────────


def test_a_long_link_is_refused_politely():
    w = _parish()
    url = "https://contoso.sharepoint.com/sites/p/Shared%20Documents/Forms/AllItems.aspx?id=" + "a" * 520
    resp = _client(w["coord"]).post(
        reverse("community-resources", args=[w["c"].slug]),
        {"action": "add", "title": "Pantry", "url": url, "category": "food"},
    )
    assert resp.status_code == 302
    assert not Resource.objects.filter(community=w["c"]).exists()


def test_the_export_type_cannot_break_or_rename_the_download():
    w = _parish()
    c = _client(w["coord"])
    url = reverse("dashboard-export", args=[w["c"].slug])
    assert c.get(url, {"type": "needs\r\nX-Injected: 1"}).status_code == 200
    resp = c.get(url, {"type": 'x.bat"; filename="report.bat'})
    assert resp["Content-Disposition"] == f'attachment; filename="{w["c"].slug}-needs.csv"'
