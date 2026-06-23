"""
Tests for the Member Tags & Verification system.

Covers:
  - State machine transitions (valid + invalid)
  - Authorization (coordinator can't verify admin_verified tags)
  - Visibility rules (public, community, coordinators_only, public_when_verified)
  - Audit events emitted on every state change
  - Public-priest rule (public_when_verified override)
  - 3-rejection flagging
  - Default tag seeding via signal
  - Visibility ordering enforcement
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditLog
from apps.communities.models import Community
from apps.tags.models import DEFAULT_TAGS, VISIBILITY_ORDER, MemberTag, Tag

from .conftest import CommunityFactory, MemberFactory


@pytest.fixture
def community():
    return CommunityFactory()


@pytest.fixture
def member(community):
    return MemberFactory(community=community, display_name="Alice", role="member")


@pytest.fixture
def admin_member(community):
    return MemberFactory(community=community, display_name="Carol (Admin)", role="admin")


@pytest.fixture
def coord_member(community):
    return MemberFactory(community=community, display_name="Dave (Coordinator)", role="coordinator")


@pytest.fixture
def viewer_member(community):
    return MemberFactory(community=community, display_name="Bob", role="member")


@pytest.fixture
def coord_verified_tag(community):
    return Tag.objects.get(community=community, slug="svdp-member")


@pytest.fixture
def admin_verified_tag(community):
    return Tag.objects.get(community=community, slug="priest")


@pytest.fixture
def coordinators_only_tag(community):
    return Tag.objects.get(community=community, slug="nurse")


@pytest.fixture
def self_serve_tag(community):
    return Tag.objects.get(community=community, slug="homeowner")


# ── State Machine Tests ──────────────────────────────────────────────


class TestStateMachine:
    """Test that MemberTag state machine enforces valid transitions."""

    @pytest.mark.django_db
    def test_self_serve_claim(self, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag)
        mt.claim()
        assert mt.status == "self_claimed"

    @pytest.mark.django_db
    def test_verification_required_claim_goes_to_pending(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag)
        mt.claim()
        assert mt.status == "pending"

    @pytest.mark.django_db
    def test_self_claimed_to_pending(self, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        mt.request_verification()
        mt.refresh_from_db()
        assert mt.status == "pending"

    @pytest.mark.django_db
    def test_pending_to_verified(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.verify(coord_member, evidence_note="Confirmed SVdP membership")
        mt.refresh_from_db()
        assert mt.status == "verified"
        assert mt.verified_by == coord_member
        assert mt.verified_at is not None

    @pytest.mark.django_db
    def test_pending_to_rejected(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.reject(coord_member, reason="No evidence provided")
        mt.refresh_from_db()
        assert mt.status == "rejected"
        assert mt.rejection_reason == "No evidence provided"
        assert mt.rejection_count == 1

    @pytest.mark.django_db
    def test_verified_to_revoked(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="verified",
            verified_by=coord_member,
        )
        mt.revoke(coord_member, reason="No longer active")
        mt.refresh_from_db()
        assert mt.status == "revoked"
        assert mt.revoked_at is not None

    @pytest.mark.django_db
    def test_verified_to_removed(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="verified",
        )
        mt.remove()
        mt.refresh_from_db()
        assert mt.status == "removed"

    @pytest.mark.django_db
    def test_rejected_to_pending_re_request(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="rejected",
            rejection_count=1,
        )
        mt.re_request(evidence_note="Updated evidence")
        mt.refresh_from_db()
        assert mt.status == "pending"

    @pytest.mark.django_db
    def test_invalid_transition_raises(self, member, self_serve_tag):
        """revoked is terminal — can't go anywhere."""
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="revoked")
        from apps.common.state import TransitionConflict

        with pytest.raises(TransitionConflict):
            mt.transition_to("pending")

    @pytest.mark.django_db
    def test_removed_is_terminal(self, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="removed")
        from apps.common.state import TransitionConflict

        with pytest.raises(TransitionConflict):
            mt.transition_to("self_claimed")


# ── Authorization Tests ──────────────────────────────────────────────


class TestAuthorization:
    """Test tier-based verification authorization."""

    @pytest.mark.django_db
    def test_coordinator_can_verify_coordinator_tier(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.verify(coord_member, evidence_note="Confirmed")
        mt.refresh_from_db()
        assert mt.status == "verified"

    @pytest.mark.django_db
    def test_coordinator_cannot_verify_admin_tier(self, member, admin_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=admin_verified_tag, status="pending")
        with pytest.raises(PermissionDenied, match="Only admins"):
            mt.verify(coord_member, evidence_note="Tried to verify priest")

    @pytest.mark.django_db
    def test_admin_can_verify_admin_tier(self, member, admin_verified_tag, admin_member):
        mt = MemberTag.objects.create(member=member, tag=admin_verified_tag, status="pending")
        mt.verify(admin_member, evidence_note="Pastor confirmed faculties 2025-03-15")
        mt.refresh_from_db()
        assert mt.status == "verified"

    @pytest.mark.django_db
    def test_admin_can_verify_coordinator_tier(self, member, coord_verified_tag, admin_member):
        """Admin can verify any tier (admin ⊃ coordinator)."""
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.verify(admin_member, evidence_note="Confirmed")
        mt.refresh_from_db()
        assert mt.status == "verified"

    @pytest.mark.django_db
    def test_regular_member_cannot_verify(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        # member is role="member", not coordinator
        with pytest.raises(PermissionDenied):
            mt.verify(member, evidence_note="Self-verify attempt")

    @pytest.mark.django_db
    def test_admin_verified_requires_evidence_note(self, member, admin_verified_tag, admin_member):
        mt = MemberTag.objects.create(member=member, tag=admin_verified_tag, status="pending")
        with pytest.raises(ValidationError, match="evidence note"):
            mt.verify(admin_member, evidence_note="")

    @pytest.mark.django_db
    def test_coordinator_cannot_revoke_admin_tier(self, member, admin_verified_tag, admin_member, coord_member):
        mt = MemberTag.objects.create(
            member=member,
            tag=admin_verified_tag,
            status="verified",
            verified_by=admin_member,
        )
        with pytest.raises(PermissionDenied, match="Only admins"):
            mt.revoke(coord_member, reason="Trying to revoke priest")


# ── Visibility Tests ─────────────────────────────────────────────────


class TestVisibility:
    """Test visibility rules and the public_when_verified override."""

    @pytest.mark.django_db
    def test_public_when_verified_override(self, member, admin_verified_tag, viewer_member):
        """A verified priest tag is visible to all community members."""
        mt = MemberTag.objects.create(
            member=member,
            tag=admin_verified_tag,
            status="verified",
            visibility="coordinators_only",  # member tries to hide it
        )
        assert mt.effective_visibility() == "public"
        assert mt.is_visible_to(viewer_member) is True

    @pytest.mark.django_db
    def test_public_when_verified_only_when_verified(self, member, admin_verified_tag, viewer_member):
        """An unverified priest tag does NOT get the public override."""
        mt = MemberTag.objects.create(
            member=member,
            tag=admin_verified_tag,
            status="pending",
            visibility="coordinators_only",
        )
        assert mt.effective_visibility() == "coordinators_only"
        assert mt.is_visible_to(viewer_member) is False

    @pytest.mark.django_db
    def test_coordinators_only_hides_from_regular_member(self, member, coordinators_only_tag, viewer_member):
        mt = MemberTag.objects.create(
            member=member,
            tag=coordinators_only_tag,
            status="self_claimed",
        )
        assert mt.is_visible_to(viewer_member) is False

    @pytest.mark.django_db
    def test_coordinators_only_visible_to_coordinator(self, member, coordinators_only_tag, coord_member):
        mt = MemberTag.objects.create(
            member=member,
            tag=coordinators_only_tag,
            status="self_claimed",
        )
        assert mt.is_visible_to(coord_member) is True

    @pytest.mark.django_db
    def test_owner_always_sees_own_tags(self, member, coordinators_only_tag):
        mt = MemberTag.objects.create(
            member=member,
            tag=coordinators_only_tag,
            status="self_claimed",
        )
        assert mt.is_visible_to(member) is True

    @pytest.mark.django_db
    def test_visibility_cannot_exceed_tag_default(self, member, coordinators_only_tag):
        """Member cannot set visibility more public than the tag's default."""
        mt = MemberTag(
            member=member,
            tag=coordinators_only_tag,
            status="self_claimed",
            visibility="public",  # more public than coordinators_only
        )
        with pytest.raises(ValidationError, match="Cannot be more public"):
            mt.clean()

    @pytest.mark.django_db
    def test_anonymous_sees_nothing(self, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        assert mt.is_visible_to(None) is False

    @pytest.mark.django_db
    def test_effective_visibility_takes_most_restrictive(self, member, coord_verified_tag):
        """Tag default is community, member sets coordinators_only → effective is coordinators_only."""
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="self_claimed",
            visibility="coordinators_only",
        )
        assert mt.effective_visibility() == "coordinators_only"

    @pytest.mark.django_db
    def test_visibility_order_values(self):
        """Verify explicit ordering: public < community < coordinators_only."""
        assert VISIBILITY_ORDER["public"] < VISIBILITY_ORDER["community"]
        assert VISIBILITY_ORDER["community"] < VISIBILITY_ORDER["coordinators_only"]


# ── Audit Tests ──────────────────────────────────────────────────────


class TestAuditEvents:
    """Every state change must emit an AuditLog entry."""

    @pytest.mark.django_db
    def test_claim_emits_audit(self, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag)
        mt.claim()
        log = AuditLog.objects.filter(resource_type="member_tag", resource_id=mt.id).first()
        assert log is not None
        assert log.action == "tag.claimed"
        assert log.details["tag_slug"] == "homeowner"

    @pytest.mark.django_db
    def test_verify_emits_audit(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.verify(coord_member, evidence_note="Confirmed")
        log = AuditLog.objects.filter(action="tag.verified", resource_id=mt.id).first()
        assert log is not None
        assert log.details["verified_by"] == str(coord_member.id)

    @pytest.mark.django_db
    def test_reject_emits_audit(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.reject(coord_member, reason="Insufficient evidence")
        log = AuditLog.objects.filter(action="tag.rejected", resource_id=mt.id).first()
        assert log is not None
        assert log.details["reason"] == "Insufficient evidence"

    @pytest.mark.django_db
    def test_revoke_emits_audit(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="verified",
            verified_by=coord_member,
        )
        mt.revoke(coord_member, reason="Left ministry")
        log = AuditLog.objects.filter(action="tag.revoked", resource_id=mt.id).first()
        assert log is not None
        assert log.details["reason"] == "Left ministry"

    @pytest.mark.django_db
    def test_remove_emits_audit(self, member, self_serve_tag):
        mt = MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        mt.remove()
        log = AuditLog.objects.filter(action="tag.removed", resource_id=mt.id).first()
        assert log is not None

    @pytest.mark.django_db
    def test_re_request_emits_audit_with_flag(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="rejected",
            rejection_count=3,
        )
        mt.re_request(evidence_note="Third try")
        log = AuditLog.objects.filter(action="tag.re_requested", resource_id=mt.id).first()
        assert log is not None
        assert log.details["flagged"] is True
        assert log.details["rejection_count"] == 3

    @pytest.mark.django_db
    def test_audit_has_no_pii(self, member, coord_verified_tag, coord_member):
        """Audit details should contain UUIDs, not names or emails."""
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.verify(coord_member, evidence_note="Confirmed")
        log = AuditLog.objects.filter(action="tag.verified", resource_id=mt.id).first()
        details_str = str(log.details)
        assert member.display_name not in details_str
        assert "alice" not in details_str  # username


# ── Three-Rejection Flag Tests ───────────────────────────────────────


class TestRejectionFlag:
    """After 3 rejections, the tag request is flagged for admin attention."""

    @pytest.mark.django_db
    def test_not_flagged_under_three(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="rejected",
            rejection_count=2,
        )
        assert mt.is_flagged is False

    @pytest.mark.django_db
    def test_flagged_at_three(self, member, coord_verified_tag):
        mt = MemberTag.objects.create(
            member=member,
            tag=coord_verified_tag,
            status="rejected",
            rejection_count=3,
        )
        assert mt.is_flagged is True

    @pytest.mark.django_db
    def test_rejection_count_increments(self, member, coord_verified_tag, coord_member):
        mt = MemberTag.objects.create(member=member, tag=coord_verified_tag, status="pending")
        mt.reject(coord_member, reason="First rejection")
        mt.refresh_from_db()
        assert mt.rejection_count == 1

        # Re-request and reject again
        mt.re_request()
        mt.refresh_from_db()
        mt.reject(coord_member, reason="Second rejection")
        mt.refresh_from_db()
        assert mt.rejection_count == 2


# ── Default Tag Seeding Tests ────────────────────────────────────────


class TestDefaultTagSeeding:
    """Test that DEFAULT_TAGS are seeded when a community is created."""

    @pytest.mark.django_db
    def test_new_community_gets_default_tags(self, user):
        c = Community.objects.create(name="New Parish", created_by=user)
        tags = Tag.objects.filter(community=c)
        assert tags.count() == len(DEFAULT_TAGS)

    @pytest.mark.django_db
    def test_priest_tag_is_admin_verified(self, user):
        c = Community.objects.create(name="Another Parish", created_by=user)
        priest = Tag.objects.get(community=c, slug="priest")
        assert priest.tier == "admin_verified"
        assert priest.public_when_verified is True

    @pytest.mark.django_db
    def test_homeowner_tag_is_self_serve(self, user):
        c = Community.objects.create(name="Yet Another", created_by=user)
        homeowner = Tag.objects.get(community=c, slug="homeowner")
        assert homeowner.tier == "self_serve"
        assert homeowner.public_when_verified is False

    @pytest.mark.django_db
    def test_idempotent_seeding(self, user):
        """Creating a community twice shouldn't duplicate tags."""
        c = Community.objects.create(name="Idempotent Test", created_by=user)
        count_before = Tag.objects.filter(community=c).count()
        # Simulate signal re-fire (won't happen in practice, but tests get_or_create)
        from apps.tags.signals import seed_default_tags

        seed_default_tags(sender=Community, instance=c, created=True)
        count_after = Tag.objects.filter(community=c).count()
        assert count_before == count_after


# ── Unique Constraint Tests ──────────────────────────────────────────


class TestConstraints:
    @pytest.mark.django_db
    def test_unique_member_tag(self, member, self_serve_tag):
        """A member can only have one assignment per tag."""
        MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            MemberTag.objects.create(member=member, tag=self_serve_tag, status="self_claimed")

    @pytest.mark.django_db
    def test_unique_tag_slug_per_community(self, community):
        """Two tags with the same slug in the same community should conflict."""
        Tag.objects.create(community=community, slug="test-tag", label="Test 1")
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Tag.objects.create(community=community, slug="test-tag", label="Test 2")
