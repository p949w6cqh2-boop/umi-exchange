"""
View-contract tests for Member Tags & Verification (Stage 3).

These exercise the HTTP layer of ``apps/tags/views.py`` — status codes, HTMX
triggers, rate limiting, cross-community isolation, and the redirect/HTMX
branches. The domain layer (state machine, the coordinator/admin/clergy
authorization matrix, visibility rules, audit emission) is already covered by
``tests/test_tags.py``; we deliberately do not re-test it here.
"""

import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.accounts.ratelimit import check as rl_check
from apps.tags.models import MemberTag, Tag

from .conftest import CommunityFactory, MemberFactory, UserFactory


@pytest.fixture(autouse=True)
def _clear_ratelimit_cache():
    """Claim + request-verify use the cache-backed fixed-window limiter; clear
    it around every test so counters never bleed across tests."""
    cache.clear()
    yield
    cache.clear()


# ── Community + members (the post_save signal seeds the 13 default tags) ──
@pytest.fixture
def community(db):
    return CommunityFactory()


@pytest.fixture
def member(community):
    return MemberFactory(community=community, role="member", display_name="Alice")


@pytest.fixture
def coordinator(community):
    return MemberFactory(community=community, role="coordinator", display_name="Dave")


@pytest.fixture
def admin(community):
    return MemberFactory(community=community, role="admin", display_name="Carol")


# ── Tags from the seeded catalog, by tier ──
@pytest.fixture
def self_serve_tag(community):
    return Tag.objects.get(community=community, slug="homeowner")  # tier=self_serve


@pytest.fixture
def coord_tag(community):
    return Tag.objects.get(community=community, slug="svdp-member")  # tier=coordinator_verified


@pytest.fixture
def admin_tag(community):
    return Tag.objects.get(community=community, slug="priest")  # tier=admin_verified


# ── helpers ──
def login(member):
    c = Client()
    c.force_login(member.user)
    return c


def turl(name, community, **kw):
    return reverse(f"tags:{name}", kwargs={"slug": community.slug, **kw})


def hx_trigger(resp):
    return json.loads(resp["HX-Trigger"])


# ──────────────────────────────────────────────────────────────────────
# MemberTagListView (GET my-tags)
# ──────────────────────────────────────────────────────────────────────
class TestMyTagsView:
    def test_anonymous_redirected_to_login(self, community):
        resp = Client().get(turl("my-tags", community))
        assert resp.status_code == 302

    def test_member_sees_page(self, community, member):
        resp = login(member).get(turl("my-tags", community))
        assert resp.status_code == 200

    def test_non_member_gets_404(self, community):
        outsider = UserFactory()
        c = Client()
        c.force_login(outsider)
        resp = c.get(turl("my-tags", community))
        assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# TagClaimView (POST claim)
# ──────────────────────────────────────────────────────────────────────
class TestClaimView:
    def test_claim_self_serve_creates_self_claimed(self, community, member, self_serve_tag):
        resp = login(member).post(turl("claim", community), {"tag": str(self_serve_tag.id), "visibility": "community"})
        assert resp.status_code == 302
        mt = MemberTag.objects.get(member=member, tag=self_serve_tag)
        assert mt.status == "self_claimed"

    def test_claim_coordinator_tier_goes_pending(self, community, member, coord_tag):
        login(member).post(turl("claim", community), {"tag": str(coord_tag.id), "visibility": "community"})
        mt = MemberTag.objects.get(member=member, tag=coord_tag)
        assert mt.status == "pending"

    def test_claim_hmx_returns_success_toast(self, community, member, self_serve_tag):
        resp = login(member).post(
            turl("claim", community),
            {"tag": str(self_serve_tag.id), "visibility": "community"},
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        assert hx_trigger(resp)["showToast"]["type"] == "success"

    def test_claim_already_held_is_rejected(self, community, member, self_serve_tag):
        MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        resp = login(member).post(turl("claim", community), {"tag": str(self_serve_tag.id), "visibility": "community"})
        assert resp.status_code == 400

    def test_claim_visibility_exceeding_default_is_rejected(self, community, member, self_serve_tag):
        # homeowner default_visibility="community"; "public" is more public → rejected
        resp = login(member).post(turl("claim", community), {"tag": str(self_serve_tag.id), "visibility": "public"})
        assert resp.status_code == 400

    def test_reclaim_after_remove_succeeds(self, community, member, self_serve_tag):
        """Regression: removing a tag then re-claiming it must succeed. The claim
        form still offers removed tags, but the unique (member, tag) row persists,
        so a naive re-INSERT raised IntegrityError → confusing 'already claimed'."""
        c = login(member)
        c.post(turl("claim", community), {"tag": str(self_serve_tag.id), "visibility": "community"})
        mt = MemberTag.objects.get(member=member, tag=self_serve_tag)
        c.post(turl("remove", community, pk=mt.id))
        mt.refresh_from_db()
        assert mt.status == "removed"

        resp = c.post(turl("claim", community), {"tag": str(self_serve_tag.id), "visibility": "community"})

        assert resp.status_code in (200, 302), f"re-claim should succeed, got {resp.status_code}"
        mt.refresh_from_db()
        assert mt.status == "self_claimed"
        assert MemberTag.objects.filter(member=member, tag=self_serve_tag).count() == 1

    def test_rate_limited_after_ten(self, community, member, self_serve_tag):
        key = f"tagreq:{community.id}:{member.id}"
        for _ in range(10):
            rl_check(key, 10, 3600)
        resp = login(member).post(turl("claim", community), {"tag": str(self_serve_tag.id), "visibility": "community"})
        assert resp.status_code == 429


# ──────────────────────────────────────────────────────────────────────
# TagRemoveView (POST remove)
# ──────────────────────────────────────────────────────────────────────
class TestRemoveView:
    def test_owner_removes_tag(self, community, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        resp = login(member).post(turl("remove", community, pk=mt.id))
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "removed"

    def test_remove_hmx_emits_tag_removed(self, community, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        resp = login(member).post(turl("remove", community, pk=mt.id), HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert hx_trigger(resp)["tagRemoved"]["id"] == str(mt.id)

    def test_remove_non_owner_404(self, community, member, coordinator, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        resp = login(coordinator).post(turl("remove", community, pk=mt.id))
        assert resp.status_code == 404

    def test_remove_already_removed_409(self, community, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="removed")
        resp = login(member).post(turl("remove", community, pk=mt.id))
        assert resp.status_code == 409


# ──────────────────────────────────────────────────────────────────────
# TagRequestVerifyView (POST request-verify)
# ──────────────────────────────────────────────────────────────────────
class TestRequestVerifyView:
    def test_self_claimed_requests_verification(self, community, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        resp = login(member).post(turl("request-verify", community, pk=mt.id), {"evidence_note": "since 2019"})
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "pending"

    def test_rejected_tag_re_requests(self, community, member, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="rejected")
        resp = login(member).post(turl("request-verify", community, pk=mt.id))
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "pending"

    def test_verified_tag_cannot_request(self, community, member, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="verified")
        resp = login(member).post(turl("request-verify", community, pk=mt.id))
        assert resp.status_code == 400

    def test_non_owner_404(self, community, member, coordinator, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        resp = login(coordinator).post(turl("request-verify", community, pk=mt.id))
        assert resp.status_code == 404

    def test_rate_limited_after_ten(self, community, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        key = f"tagreq:{community.id}:{member.id}"
        for _ in range(10):
            rl_check(key, 10, 3600)
        resp = login(member).post(turl("request-verify", community, pk=mt.id))
        assert resp.status_code == 429


# ──────────────────────────────────────────────────────────────────────
# VerificationQueueView (GET queue)
# ──────────────────────────────────────────────────────────────────────
class TestQueueView:
    def test_coordinator_sees_queue(self, community, coordinator):
        resp = login(coordinator).get(turl("queue", community))
        assert resp.status_code == 200

    def test_member_forbidden(self, community, member):
        resp = login(member).get(turl("queue", community))
        assert resp.status_code == 403

    def test_anonymous_redirected(self, community):
        resp = Client().get(turl("queue", community))
        assert resp.status_code == 302

    def test_coordinator_sees_only_coordinator_tier(self, community, member, coordinator, coord_tag, admin_tag):
        coord_mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        admin_mt = MemberTag.objects.create(member=member, tag=admin_tag, status="pending")
        resp = login(coordinator).get(turl("queue", community))
        items = list(resp.context["queue_items"])
        assert coord_mt in items
        assert admin_mt not in items

    def test_admin_sees_all_tiers(self, community, member, admin, coord_tag, admin_tag):
        coord_mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        admin_mt = MemberTag.objects.create(member=member, tag=admin_tag, status="pending")
        resp = login(admin).get(turl("queue", community))
        items = list(resp.context["queue_items"])
        assert coord_mt in items
        assert admin_mt in items

    def test_flagged_items_surface(self, community, member, admin, coord_tag):
        flagged = MemberTag.objects.create(member=member, tag=coord_tag, status="pending", rejection_count=3)
        resp = login(admin).get(turl("queue", community))
        assert flagged in list(resp.context["flagged_items"])


# ──────────────────────────────────────────────────────────────────────
# TagVerifyView (POST verify)
# ──────────────────────────────────────────────────────────────────────
class TestVerifyView:
    def test_coordinator_verifies_coordinator_tier(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        resp = login(coordinator).post(turl("verify", community, pk=mt.id))
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "verified"
        assert mt.verified_by_id == coordinator.id

    def test_verify_hmx_emits_queue_item_resolved(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        resp = login(coordinator).post(turl("verify", community, pk=mt.id), HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert hx_trigger(resp)["queueItemResolved"]["id"] == str(mt.id)

    def test_coordinator_cannot_verify_admin_tier(self, community, member, coordinator, admin_tag):
        """Safety-critical: a coordinator must not be able to verify a clergy
        (admin-tier) tag, even though they pass the view-level coordinator gate."""
        mt = MemberTag.objects.create(member=member, tag=admin_tag, status="pending")
        resp = login(coordinator).post(turl("verify", community, pk=mt.id))
        assert resp.status_code == 403
        mt.refresh_from_db()
        assert mt.status == "pending"

    def test_admin_verify_admin_tier_requires_evidence(self, community, member, admin, admin_tag):
        mt = MemberTag.objects.create(member=member, tag=admin_tag, status="pending")
        resp = login(admin).post(turl("verify", community, pk=mt.id))
        assert resp.status_code == 400

    def test_admin_verify_admin_tier_with_evidence(self, community, member, admin, admin_tag):
        mt = MemberTag.objects.create(member=member, tag=admin_tag, status="pending")
        resp = login(admin).post(turl("verify", community, pk=mt.id), {"evidence_note": "pastor confirmed 2025"})
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "verified"

    def test_member_cannot_verify(self, community, member, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        resp = login(member).post(turl("verify", community, pk=mt.id))
        assert resp.status_code == 403

    def test_verify_non_pending_409(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="self_claimed")
        resp = login(coordinator).post(turl("verify", community, pk=mt.id))
        assert resp.status_code == 409

    def test_verify_cross_community_404(self, community, member, coordinator):
        # A pending tag in a *different* community must be invisible to this coordinator.
        other = CommunityFactory()
        other_member = MemberFactory(community=other, role="member")
        other_tag = Tag.objects.get(community=other, slug="svdp-member")
        other_mt = MemberTag.objects.create(member=other_member, tag=other_tag, status="pending")
        resp = login(coordinator).post(turl("verify", community, pk=other_mt.id))
        assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# TagRejectView (POST reject)
# ──────────────────────────────────────────────────────────────────────
class TestRejectView:
    def test_coordinator_rejects_pending(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        resp = login(coordinator).post(turl("reject", community, pk=mt.id), {"reason": "no record"})
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "rejected"
        assert mt.rejection_count == 1

    def test_reject_flags_at_three(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending", rejection_count=2)
        login(coordinator).post(turl("reject", community, pk=mt.id))
        mt.refresh_from_db()
        assert mt.rejection_count == 3
        assert mt.is_flagged

    def test_member_cannot_reject(self, community, member, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        resp = login(member).post(turl("reject", community, pk=mt.id))
        assert resp.status_code == 403

    def test_reject_non_pending_409(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="verified")
        resp = login(coordinator).post(turl("reject", community, pk=mt.id))
        assert resp.status_code == 409


# ──────────────────────────────────────────────────────────────────────
# TagRevokeView (POST revoke)
# ──────────────────────────────────────────────────────────────────────
class TestRevokeView:
    def test_coordinator_revokes_verified(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="verified")
        resp = login(coordinator).post(turl("revoke", community, pk=mt.id), {"reason": "lapsed"})
        assert resp.status_code == 302
        mt.refresh_from_db()
        assert mt.status == "revoked"
        assert mt.revoked_by_id == coordinator.id

    def test_revoke_non_verified_409(self, community, member, coordinator, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="pending")
        resp = login(coordinator).post(turl("revoke", community, pk=mt.id))
        assert resp.status_code == 409

    def test_coordinator_cannot_revoke_admin_tier(self, community, member, coordinator, admin_tag):
        mt = MemberTag.objects.create(member=member, tag=admin_tag, status="verified")
        resp = login(coordinator).post(turl("revoke", community, pk=mt.id))
        assert resp.status_code == 403

    def test_member_cannot_revoke(self, community, member, coord_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_tag, status="verified")
        resp = login(member).post(turl("revoke", community, pk=mt.id))
        assert resp.status_code == 403
