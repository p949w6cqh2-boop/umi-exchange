"""Outbound sharing service (Stage B §4.1) — consent-gated via Consent.covers()."""

import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import crypto, sharing
from apps.federation.models import FederatedShare
from apps.needs.models import Need

pytestmark = pytest.mark.django_db


@pytest.fixture
def a_need(world):
    cat = Category.objects.create(community=world.community, name="Food")
    return Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="Groceries for the week",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )


def _consent(user, grantee_id, scopes=("federated_share",)):
    return Consent.objects.create(
        participant=user,
        granted_to="Peer Board",
        grantee_type="community",
        grantee_id=grantee_id,
        scope=list(scopes),
        purpose="federation sharing",
        method="digital",
        status="active",
    )


def test_share_refused_without_consent(fed_settings, active_link, a_need, world):
    with pytest.raises(sharing.ShareError):
        sharing.share_record(a_need, active_link, actor_user=world.admin_u)
    assert not FederatedShare.objects.exists()


def test_share_succeeds_with_covering_consent(fed_settings, active_link, a_need, world):
    _consent(world.plain_u, active_link.remote_community_uuid)
    share = sharing.share_record(a_need, active_link, actor_user=world.admin_u)

    assert share.status == "active"
    a_need.refresh_from_db()
    assert a_need.share_scope == "federated"
    # A signed, verifiable, PII-free receipt is attached.
    payload = crypto.verify_consent_receipt(share.receipt_jws, crypto.public_jwk())
    assert payload["scope"] == ["federated_share"]
    assert payload["record"] == f"need:{share.remote_uuid}"
    assert AuditLog.objects.filter(action="fed.share_created", resource_type="federatedshare").exists()


def test_share_idempotent(fed_settings, active_link, a_need, world):
    _consent(world.plain_u, active_link.remote_community_uuid)
    s1 = sharing.share_record(a_need, active_link, actor_user=world.admin_u)
    s2 = sharing.share_record(a_need, active_link, actor_user=world.admin_u)
    assert s1.pk == s2.pk
    assert FederatedShare.objects.filter(need=a_need).count() == 1


def test_consent_for_a_different_peer_does_not_authorize(fed_settings, active_link, a_need, world):
    _consent(world.plain_u, uuid.uuid4())  # some OTHER community
    with pytest.raises(sharing.ShareError):
        sharing.share_record(a_need, active_link, actor_user=world.admin_u)


def test_consent_missing_scope_does_not_authorize(fed_settings, active_link, a_need, world):
    _consent(world.plain_u, active_link.remote_community_uuid, scopes=("display_name",))
    with pytest.raises(sharing.ShareError):
        sharing.share_record(a_need, active_link, actor_user=world.admin_u)


def test_share_refused_on_inactive_link(fed_settings, active_link, a_need, world):
    _consent(world.plain_u, active_link.remote_community_uuid)
    active_link.status = "suspended"
    active_link.save(update_fields=["status"])
    with pytest.raises(sharing.ShareError):
        sharing.share_record(a_need, active_link, actor_user=world.admin_u)


def test_revoked_consent_stops_authorizing(fed_settings, active_link, a_need, world):
    consent = _consent(world.plain_u, active_link.remote_community_uuid)
    consent.status = "revoked"
    consent.save(update_fields=["status"])
    with pytest.raises(sharing.ShareError):
        sharing.share_record(a_need, active_link, actor_user=world.admin_u)
