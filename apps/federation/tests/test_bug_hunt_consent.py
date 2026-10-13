"""2026-10 bug hunt leads L57 and L62 (federation consent), verified and fixed.

L57  Revoking a consent while federation was switched off skipped revoke_shares_for_consent, so
     its shares stayed active, and once federation was back on, discovery advertised and
     receive_proposal matched a record whose consent was gone. Now the shares stop on every
     revoke (the peer is only told while federation is on), and discovery and proposals
     re-check the consent itself, whatever path revoked or expired it.
L62  The poller verified a consent receipt's signature but never its claims, so a valid
     receipt for another record, or one minted for another instance, was stored as this
     listing's consent evidence. The record and the audience must now match.
"""

import json
import uuid

import pytest
from django.conf import settings as dj_settings
from django.urls import reverse
from django.utils import timezone
from joserfc import jws

from apps.consent.models import Consent
from apps.federation import crypto, matching, polling
from apps.federation.models import ShadowListing

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

DISCOVERY = "/federation/v1/discovery"


def _discover(client, remote, fed_settings):
    sig = remote.sign("GET", dj_settings.SITE_URL.rstrip("/") + DISCOVERY, b"", fed_settings.instance_id)
    return client.get(DISCOVERY, HTTP_X_UMI_SIGNATURE=sig).json()["listings"]


# ── L57 ────────────────────────────────────────────────────────


def test_revoking_consent_with_federation_off_still_stops_the_share(
    client, authority_match, world, monkeypatch, settings
):
    share = authority_match.share
    called = []
    monkeypatch.setattr("apps.federation.sharing.client_mod.post_revocation", lambda *a, **k: called.append(1))
    settings.FEDERATION_ENABLED = False

    client.force_login(world.plain_u)
    client.post(reverse("consent-revoke", args=[share.consent_id]))

    share.refresh_from_db()
    assert share.status == "revoked"
    assert not called  # with federation off, nothing goes over the wire


@pytest.mark.parametrize("how", ["revoked", "expired"])
def test_a_share_whose_consent_ended_is_neither_advertised_nor_matched(
    client, fed_settings, remote, authority_match, how
):
    share = authority_match.share
    if how == "revoked":
        Consent.objects.filter(pk=share.consent_id).update(status="revoked", revoked_at=timezone.now())
    else:
        Consent.objects.filter(pk=share.consent_id).update(expires_at=timezone.now() - timezone.timedelta(days=1))

    assert _discover(client, remote, fed_settings) == []
    result = matching.receive_proposal(
        authority_match.link.peer, need_remote_uuid=share.remote_uuid, proposal_uuid=uuid.uuid4()
    )
    assert result == {"status": "rejected", "reason": "not_shared"}


# ── L62 ────────────────────────────────────────────────────────


def _receipt(remote, *, record, peer):
    payload = {"record": record, "scope": ["federated_share"], "home": remote.instance_id, "peer": peer}
    return jws.serialize_compact({"alg": "Ed25519"}, json.dumps(payload).encode(), remote.key, algorithms=["Ed25519"])


def _poll_one(monkeypatch, link, row):
    monkeypatch.setattr(
        "apps.federation.polling.client_mod.get_discovery", lambda base_url, headers, **scope: {"listings": [row]}
    )
    return polling.poll_link(link)


def _row(remote_uuid, receipt):
    return {
        "kind": "need",
        "remote_uuid": str(remote_uuid),
        "category": "Food",
        "urgency": "high",
        "locality": "Testville",
        "freshness": "2026-W41",
        "receipt_jws": receipt,
    }


def test_a_receipt_for_another_record_is_not_stored(fed_settings, active_link, remote, monkeypatch):
    mine = uuid.uuid4()
    receipt = _receipt(remote, record=f"need:{uuid.uuid4()}", peer=crypto.my_instance_id())

    assert _poll_one(monkeypatch, active_link, _row(mine, receipt)) == 0
    assert not ShadowListing.objects.filter(remote_uuid=mine).exists()


def test_a_receipt_minted_for_another_instance_is_not_stored(fed_settings, active_link, remote, monkeypatch):
    mine = uuid.uuid4()
    receipt = _receipt(remote, record=f"need:{mine}", peer="someone-elses-instance-id")

    assert _poll_one(monkeypatch, active_link, _row(mine, receipt)) == 0
    assert not ShadowListing.objects.filter(remote_uuid=mine).exists()


def test_a_matching_receipt_is_stored(fed_settings, active_link, remote, monkeypatch):
    mine = uuid.uuid4()
    receipt = _receipt(remote, record=f"need:{mine}", peer=crypto.my_instance_id())

    assert _poll_one(monkeypatch, active_link, _row(mine, receipt)) == 1
