"""Batch-2 regression (federation):

- A link with no remote community identity must not mint a null-grantee Consent.
  covers() treats a NULL grantee_id as "matches any community" (legacy-row rule),
  so a Consent(grantee_id=None) would authorize federated_share to EVERY peer
  community — collapsing the §4.1 per-peer gate.
- Revoking a link must release a local offer held by a mirror-role match (proposed
  abroad). Mirror rows have match=NULL, so the authority cancel loop skips them;
  without a dedicated teardown the offer stays `matched` forever once the link is cut.
"""

import uuid
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation.models import FederatedMatch
from apps.needs.models import Need
from apps.offers.models import Offer

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


def test_revoke_releases_mirror_held_offer(client, fed_settings, active_link, world):
    cat = Category.objects.create(community=world.community, name="Rides")
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="I can drive",
        status="matched",  # held while proposed abroad (mirror accepted)
        expires_at=timezone.now() + timedelta(days=30),
    )
    fmatch = FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=uuid.uuid4(),
        mirror_status="accepted",
        offer=offer,
    )
    client.force_login(world.admin_u)
    resp = client.post(
        reverse("federation_admin:settings", kwargs={"slug": world.community.slug}),
        {"action": "revoke", "link_id": str(active_link.pk)},
    )
    assert resp.status_code in (200, 302)
    active_link.refresh_from_db()
    offer.refresh_from_db()
    fmatch.refresh_from_db()
    assert active_link.status == "revoked"
    assert fmatch.mirror_status == "cancelled"  # mirror torn down on revoke
    assert offer.status == "active"  # the held offer is released, not stranded
