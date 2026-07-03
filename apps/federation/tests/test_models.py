"""FederationLink state machine (§12.1 mixin) + basic constraints."""

import pytest
from django.db import IntegrityError

from apps.common.state import TransitionConflict
from apps.federation.models import FederationLink

pytestmark = pytest.mark.django_db


@pytest.fixture
def link(world, peer):
    return FederationLink.objects.create(peer=peer, community=world.community, requested_by_us=True)


class TestLinkStateMachine:
    def test_defaults_pending(self, link):
        assert link.status == "pending"

    def test_pending_to_active(self, link):
        link.transition_to("active")
        link.refresh_from_db()
        assert link.status == "active"

    def test_active_suspend_resume(self, link):
        link.transition_to("active")
        link.transition_to("suspended")
        link.transition_to("active")
        assert link.status == "active"

    def test_pending_to_suspended_invalid(self, link):
        with pytest.raises(TransitionConflict):
            link.transition_to("suspended")

    def test_revoked_is_terminal(self, link):
        link.transition_to("active")
        link.transition_to("revoked")
        assert link.revoked_at is not None
        with pytest.raises(TransitionConflict):
            link.transition_to("active")

    def test_duplicate_link_rejected(self, world, peer, link):
        import uuid

        u = uuid.uuid4()
        FederationLink.objects.filter(pk=link.pk).update(remote_community_uuid=u)
        with pytest.raises(IntegrityError):
            FederationLink.objects.create(peer=peer, community=world.community, remote_community_uuid=u)
