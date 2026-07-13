"""Batch-2 regression (federation): a link with no remote community identity must
not mint a null-grantee Consent. covers() treats a NULL grantee_id as "matches any
community" (legacy-row rule), so a Consent(grantee_id=None) would authorize
federated_share to EVERY peer community — collapsing the §4.1 per-peer gate."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.communities.models import Category
from apps.consent.models import Consent
from apps.needs.models import Need

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


def test_share_on_null_identity_link_mints_no_consent(client, fed_settings, active_link, world):
    active_link.remote_community_uuid = None
    active_link.save(update_fields=["remote_community_uuid"])
    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="Groceries",
        urgency="high",
        contact_pref="email",
        expires_at=timezone.now() + timedelta(days=14),
    )
    client.force_login(world.plain_u)
    resp = client.post(
        f"/c/{world.community.slug}/federation/share",
        {"kind": "need", "record_id": str(need.id), "link_id": str(active_link.pk), "action": "share"},
    )
    assert resp.status_code in (200, 302)
    # No consent minted at all — a null-grantee one would authorize sharing to ANY peer.
    assert not Consent.objects.filter(participant=world.plain_u).exists()
