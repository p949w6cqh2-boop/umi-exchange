"""
Model tests: User, Community, Need, Offer, Match state machine, AuditLog.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.audit.models import AuditLog
from apps.households.models import Household
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer

from .factories import CategoryFactory, CommunityFactory, MemberFactory, UserFactory


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = UserFactory()
        assert user.pk is not None
        assert user.email is None  # Email is optional per protocol

    def test_email_optional(self):
        user = UserFactory(email="test@example.com")
        assert user.email == "test@example.com"


@pytest.mark.django_db
class TestCommunityModel:
    def test_create_community(self):
        community = CommunityFactory(name="Test Parish")
        assert community.pk is not None
        assert community.slug == "test-parish"
        assert community.join_code  # Auto-generated
        assert len(community.join_code) == 8

    def test_default_settings(self):
        community = CommunityFactory()
        assert community.auto_expire_days == 30
        assert community.neighborhood_mode == "optional"

    def test_auto_seed_categories(self):
        community = CommunityFactory()
        assert community.categories.count() == 10
        assert community.categories.filter(name="Food").exists()


@pytest.mark.django_db
class TestNeedModel:
    def test_create_need(self):
        member = MemberFactory()
        category = CategoryFactory(community=member.community)
        need = Need.objects.create(
            community=member.community,
            requester=member,
            category=category,
            title="Need help moving",
        )
        assert need.pk is not None
        assert need.status == "open"
        assert need.urgency == "medium"
        assert need.expires_at is not None

    def test_on_behalf_of_encryption(self):
        """Envelope encryption (§12.2) for on_behalf_of via the on_behalf_of_name property."""
        from django.conf import settings

        member = MemberFactory()
        category = CategoryFactory(community=member.community)
        need = Need.objects.create(
            community=member.community,
            requester=member,
            category=category,
            title="Test encryption",
        )
        if settings.ENCRYPTION_KEY:
            need.on_behalf_of_name = "Jane Doe"
            need.save()
            need.refresh_from_db()
            assert need.on_behalf_of_name == "Jane Doe"
            assert need.on_behalf_of_dek is not None  # envelope-wrapped, not legacy direct-KEK


@pytest.mark.django_db
class TestMatchStateMachine:
    """Test the UMI Protocol Section 4.3 state machine."""

    def _create_match(self):
        user1 = UserFactory()
        user2 = UserFactory()
        community = CommunityFactory(created_by=user1)
        category = CategoryFactory(community=community)
        requester = MemberFactory(user=user1, community=community)
        offerer = MemberFactory(user=user2, community=community)
        need = Need.objects.create(
            community=community,
            requester=requester,
            category=category,
            title="Test Need",
        )
        offer = Offer.objects.create(
            community=community,
            offerer=offerer,
            category=category,
            title="Test Offer",
        )
        match = Match.objects.create(need=need, offer=offer, proposed_by=offerer)
        return match, need, offer

    def test_proposed_to_accepted(self):
        match, need, offer = self._create_match()
        match.transition_to("accepted")
        assert match.status == "accepted"
        assert match.accepted_at is not None
        need.refresh_from_db()
        assert need.status == "matched"

    def test_accepted_to_fulfilled(self):
        match, need, offer = self._create_match()
        match.transition_to("accepted")
        match.transition_to("fulfilled")
        assert match.status == "fulfilled"
        need.refresh_from_db()
        assert need.status == "fulfilled"

    def test_proposed_to_cancelled(self):
        match, need, offer = self._create_match()
        match.transition_to("cancelled")
        assert match.status == "cancelled"

    def test_invalid_transition_raises(self):
        match, _, _ = self._create_match()
        match.transition_to("cancelled")
        with pytest.raises(ValidationError):
            match.transition_to("accepted")

    def test_fulfilled_is_terminal(self):
        match, _, _ = self._create_match()
        match.transition_to("accepted")
        match.transition_to("fulfilled")
        with pytest.raises(ValidationError):
            match.transition_to("cancelled")

    def test_contact_revelation_before_acceptance(self):
        """Protocol Section 8.2: contact info NOT revealed before acceptance."""
        match, _, _ = self._create_match()
        contact = match.get_contact_info_for(match.need.requester)
        assert contact is None  # Status is 'proposed'

    def test_contact_revelation_after_acceptance(self):
        """Protocol Section 8.2: contact info revealed after acceptance."""
        match, _, _ = self._create_match()
        match.transition_to("accepted")
        contact = match.get_contact_info_for(match.need.requester)
        assert contact is not None
        assert "display_name" in contact


@pytest.mark.django_db
class TestAuditLog:
    def test_create_audit_entry(self):
        user = UserFactory()
        import uuid

        AuditLog.log(user, "create", "need", uuid.uuid4(), details={"test": True})
        assert AuditLog.objects.count() == 1
        entry = AuditLog.objects.first()
        assert entry.action == "create"
        assert entry.user == user


@pytest.mark.django_db
class TestHousehold:
    def test_create_household(self):
        user = UserFactory()
        hh = Household.objects.create(name="The Smiths", created_by=user)
        assert hh.pk is not None
        assert hh.join_code.startswith("H-")
        assert len(hh.join_code) == 8
