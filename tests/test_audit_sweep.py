"""Lake 1 append-only audit sweep (§8.3).

A dotted audit row must be emitted (via apps.audit.services.emit) for every Lake 1
state change + sensitive disclosure. Emits live in the VIEW layer so the actor and
the salted IP-hash are captured. These tests drive the real views with an
authenticated client and assert one row per event, the right resource, the actor
(NULL for system events), PII-free details, no double-emit on expiry, and that the
append-only guarantee still holds.
"""

import uuid

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer
from tests.factories import CategoryFactory, CommunityFactory, MemberFactory, UserFactory


@pytest.fixture
def world(db):
    user = UserFactory()
    community = CommunityFactory(created_by=user)
    member = MemberFactory(user=user, community=community, role="member")
    category = CategoryFactory(community=community)
    return {"user": user, "community": community, "member": member, "category": category}


@pytest.fixture
def login():
    def _login(user):
        c = Client()
        c.force_login(user)
        return c

    return _login


def rows(action):
    return AuditLog.objects.filter(action=action)


@pytest.mark.django_db
class TestLake1AuditSweep:
    def test_need_created(self, world, login):
        c = login(world["user"])
        resp = c.post(
            reverse("need-create", kwargs={"slug": world["community"].slug}),
            {
                "category": str(world["category"].id),
                "title": "Need a ride to the clinic",
                "description": "",
                "urgency": "high",
                "contact_pref": "in_app",
                "neighborhood": "",
            },
            HTTP_X_REAL_IP="203.0.113.9",
        )
        assert resp.status_code in (200, 302)
        need = Need.objects.get(community=world["community"])
        assert rows("need.created").count() == 1
        row = rows("need.created").get()
        assert row.resource_type == "need" and row.resource_id == need.id
        assert row.user_id == world["user"].id
        assert "ride to the clinic" not in str(row.details or "")  # no plaintext PII
        assert len(row.ip_hash) == 64  # client IP captured + salted-SHA-256 hashed

    def test_offer_created(self, world, login):
        c = login(world["user"])
        resp = c.post(
            reverse("offer-create", kwargs={"slug": world["community"].slug}),
            {
                "category": str(world["category"].id),
                "title": "Can give rides",
                "description": "",
                "contact_pref": "in_app",
            },
        )
        assert resp.status_code in (200, 302)
        offer = Offer.objects.get(community=world["community"])
        assert rows("offer.created").count() == 1
        assert rows("offer.created").get().resource_id == offer.id
        assert rows("offer.created").get().user_id == world["user"].id

    def test_need_deleted_hard_delete(self, world, login):
        need = Need.objects.create(
            community=world["community"], requester=world["member"], category=world["category"], title="X"
        )
        c = login(world["user"])
        resp = c.post(reverse("need-delete", kwargs={"slug": world["community"].slug, "pk": need.id}))
        assert resp.status_code in (200, 302)
        assert not Need.objects.filter(id=need.id).exists()  # confirms the real transition is a hard delete
        assert rows("need.deleted").count() == 1
        assert rows("need.deleted").get().resource_id == need.id
        assert rows("need.deleted").get().user_id == world["user"].id

    def test_offer_deleted_hard_delete(self, world, login):
        offer = Offer.objects.create(
            community=world["community"], offerer=world["member"], category=world["category"], title="X"
        )
        c = login(world["user"])
        resp = c.post(reverse("offer-delete", kwargs={"slug": world["community"].slug, "pk": offer.id}))
        assert resp.status_code in (200, 302)
        assert not Offer.objects.filter(id=offer.id).exists()
        assert rows("offer.deleted").count() == 1
        assert rows("offer.deleted").get().resource_id == offer.id

    def test_community_created_and_creator_member_joined(self, login):
        creator = UserFactory()
        c = login(creator)
        resp = c.post(reverse("community-create"), {"name": "New Parish", "description": "", "visibility": "public"})
        assert resp.status_code in (200, 302)
        from apps.communities.models import Community

        community = Community.objects.get(name="New Parish")
        assert rows("community.created").count() == 1
        assert rows("community.created").get().resource_id == community.id
        assert rows("community.created").get().user_id == creator.id
        # creator is added as admin → that membership is a member.joined too
        creator_member = community.members.get()
        mj = rows("member.joined").filter(resource_id=creator_member.id)
        assert mj.count() == 1
        assert (mj.get().details or {}).get("role") == "admin"

    def test_member_joined_via_join_flow(self, world, login):
        joiner = UserFactory()
        c = login(joiner)
        resp = c.post(
            reverse("community-join"),
            {"join_code": world["community"].join_code, "display_name": "Pat Q. Neighbour"},
        )
        assert resp.status_code in (200, 302)
        member = Member.objects.get(user=joiner, community=world["community"])
        mj = rows("member.joined").filter(resource_id=member.id)
        assert mj.count() == 1
        assert mj.get().user_id == joiner.id
        assert (mj.get().details or {}).get("role") == "member"
        assert "Pat Q. Neighbour" not in str(mj.get().details or "")  # no plaintext PII

    def test_match_accept_emits_need_and_offer_updated(self, world, login):
        community, category = world["community"], world["category"]
        requester = world["member"]
        offerer_user = UserFactory()
        offerer = MemberFactory(user=offerer_user, community=community, role="member")
        need = Need.objects.create(community=community, requester=requester, category=category, title="N")
        offer = Offer.objects.create(community=community, offerer=offerer, category=category, title="O")

        login(offerer_user).post(
            reverse("match-propose", kwargs={"slug": community.slug}),
            {"need_id": str(need.id), "offer_id": str(offer.id)},
        )
        match = Match.objects.get(need=need)
        resp = login(world["user"]).post(
            reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}), {"status": "accepted"}
        )
        assert resp.status_code in (200, 302)
        need.refresh_from_db()
        offer.refresh_from_db()
        assert need.status == "matched" and offer.status == "matched"

        nu = rows("need.updated").filter(resource_id=need.id)
        ou = rows("offer.updated").filter(resource_id=offer.id)
        assert nu.count() == 1 and ou.count() == 1
        assert nu.get().user_id == world["user"].id  # the accepting actor
        assert (nu.get().details or {}).get("status") == "matched"
        assert (ou.get().details or {}).get("status") == "matched"

    def test_match_cancel_from_proposed_emits_no_updated(self, world, login):
        """cancel-from-proposed leaves need/offer status untouched → no *.updated rows.
        Guards the old-status comparison that prevents no-op audit rows."""
        community, category = world["community"], world["category"]
        offerer_user = UserFactory()
        offerer = MemberFactory(user=offerer_user, community=community, role="member")
        need = Need.objects.create(community=community, requester=world["member"], category=category, title="N")
        offer = Offer.objects.create(community=community, offerer=offerer, category=category, title="O")
        oc = login(offerer_user)
        oc.post(
            reverse("match-propose", kwargs={"slug": community.slug}),
            {"need_id": str(need.id), "offer_id": str(offer.id)},
        )
        match = Match.objects.get(need=need)
        resp = oc.post(
            reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}), {"status": "cancelled"}
        )
        assert resp.status_code in (200, 302)
        need.refresh_from_db()
        offer.refresh_from_db()
        assert need.status == "open" and offer.status == "active"  # no cascade
        assert rows("need.updated").count() == 0
        assert rows("offer.updated").count() == 0

    def test_need_contact_disclosed_to_coordinator(self, world, login):
        poster = world["member"]
        poster.user.email = "poster@example.test"
        poster.user.save(update_fields=["email"])
        need = Need.objects.create(
            community=world["community"],
            requester=poster,
            category=world["category"],
            title="N",
            contact_pref="email",
        )
        coord_user = UserFactory()
        MemberFactory(user=coord_user, community=world["community"], role="coordinator")
        resp = login(coord_user).get(reverse("need-detail", kwargs={"slug": world["community"].slug, "pk": need.id}))
        assert resp.status_code == 200
        assert b"poster@example.test" in resp.content  # disclosed to the coordinator
        cd = rows("need.contact_disclosed").filter(resource_id=need.id)
        assert cd.count() == 1
        assert cd.get().user_id == coord_user.id
        assert "poster@example.test" not in str(cd.get().details or "")  # never the contact value itself

    def test_need_detail_no_contact_or_event_for_ordinary_member(self, world, login):
        poster = world["member"]
        poster.user.email = "poster@example.test"
        poster.user.save(update_fields=["email"])
        need = Need.objects.create(
            community=world["community"],
            requester=poster,
            category=world["category"],
            title="N",
            contact_pref="email",
        )
        other_user = UserFactory()
        MemberFactory(user=other_user, community=world["community"], role="member")
        resp = login(other_user).get(reverse("need-detail", kwargs={"slug": world["community"].slug, "pk": need.id}))
        assert resp.status_code == 200
        assert b"poster@example.test" not in resp.content  # §8.2 preserved for ordinary members
        assert rows("need.contact_disclosed").count() == 0

    def test_offer_contact_disclosed_to_coordinator(self, world, login):
        poster = world["member"]
        poster.user.email = "offerer@example.test"
        poster.user.save(update_fields=["email"])
        offer = Offer.objects.create(
            community=world["community"],
            offerer=poster,
            category=world["category"],
            title="O",
            contact_pref="email",
        )
        coord_user = UserFactory()
        MemberFactory(user=coord_user, community=world["community"], role="coordinator")
        resp = login(coord_user).get(reverse("offer-detail", kwargs={"slug": world["community"].slug, "pk": offer.id}))
        assert resp.status_code == 200
        assert b"offerer@example.test" in resp.content
        cd = rows("offer.contact_disclosed").filter(resource_id=offer.id)
        assert cd.count() == 1 and cd.get().user_id == coord_user.id
        assert "offerer@example.test" not in str(cd.get().details or "")

    def test_offer_detail_no_contact_for_ordinary_member(self, world, login):
        poster = world["member"]
        poster.user.email = "offerer@example.test"
        poster.user.save(update_fields=["email"])
        offer = Offer.objects.create(
            community=world["community"],
            offerer=poster,
            category=world["category"],
            title="O",
            contact_pref="email",
        )
        other_user = UserFactory()
        MemberFactory(user=other_user, community=world["community"], role="member")
        resp = login(other_user).get(reverse("offer-detail", kwargs={"slug": world["community"].slug, "pk": offer.id}))
        assert resp.status_code == 200
        assert b"offerer@example.test" not in resp.content
        assert rows("offer.contact_disclosed").count() == 0

    def test_expiry_task_does_not_double_emit_need_updated(self, world):
        """System expiry already writes a legacy 'update' row — it must NOT also
        emit a dotted need.updated (that lives only in the view layer)."""
        need = Need.objects.create(
            community=world["community"],
            requester=world["member"],
            category=world["category"],
            title="stale",
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        from apps.needs.tasks import expire_stale_needs

        expire_stale_needs()
        need.refresh_from_db()
        assert need.status == "expired"
        assert rows("need.updated").filter(resource_id=need.id).count() == 0  # no double-emit
        legacy = AuditLog.objects.filter(action="update", resource_type="need", resource_id=need.id)
        assert legacy.count() == 1 and legacy.get().user_id is None  # system actor

    def test_append_only_still_rejects_update_and_delete(self):
        entry = AuditLog.objects.create(
            user=None, action="need.created", resource_type="need", resource_id=uuid.uuid4()
        )
        entry.action = "tampered"
        with pytest.raises(PermissionDenied):
            entry.save()
        with pytest.raises(PermissionDenied):
            entry.delete()
        entry.refresh_from_db()
        assert entry.action == "need.created"
