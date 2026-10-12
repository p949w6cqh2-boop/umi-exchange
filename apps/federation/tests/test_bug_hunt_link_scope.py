"""2026-10 bug hunt #6 (high, dormant): discovery was scoped to the peer instance, not the link.

Two links to one peer instance are allowed (one per remote community). A record shared on one
link, with consent naming that one remote community, was advertised on every link to that peer
and could be proposed on from any of its communities, and the requester's contact could follow
an accept. Now a poll names its link (our community, their community), discovery serves only that
link's shares, and a proposal must come through the link its ask was shared on. A peer with a
single link may still poll unscoped, which cannot leak; with two or more, scope is required.
"""

import json
import uuid

import pytest
from django.conf import settings as dj_settings
from django.utils import timezone

from apps.federation import polling, sharing
from apps.federation.models import FederationLink

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

DISCOVERY = "/federation/v1/discovery"
PROPOSALS = "/federation/v1/proposals"


@pytest.fixture
def two_links(fed_settings, world, peer):
    peer.status = "active"
    peer.save(update_fields=["status"])
    a, b = uuid.uuid4(), uuid.uuid4()
    link_a = FederationLink.objects.create(
        peer=peer, community=world.community, remote_community_uuid=a, remote_community_label="A", status="active"
    )
    link_b = FederationLink.objects.create(
        peer=peer, community=world.community, remote_community_uuid=b, remote_community_label="B", status="active"
    )
    link_b.pairing_pepper = b"0" * 32
    link_b.save(update_fields=["pairing_pepper"])
    return link_a, link_b


def _share_on(world, link):
    from apps.communities.models import Category
    from apps.consent.models import Consent
    from apps.needs.models import Need

    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="groceries",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to=link.remote_community_label,
        grantee_type="community",
        grantee_id=link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    return sharing.share_record(need, link, actor_user=world.admin_u)


def _discover(client, remote, fed_settings, query=""):
    path = DISCOVERY + query
    sig = remote.sign("GET", dj_settings.SITE_URL.rstrip("/") + path, b"", fed_settings.instance_id)
    return client.get(path, HTTP_X_UMI_SIGNATURE=sig)


def _scope(link):
    return f"?community={link.community_id}&peer_community={link.remote_community_uuid}"


def test_discovery_serves_only_the_link_that_polls(client, fed_settings, remote, world, two_links):
    link_a, link_b = two_links
    _share_on(world, link_b)

    for_a = _discover(client, remote, fed_settings, _scope(link_a))
    for_b = _discover(client, remote, fed_settings, _scope(link_b))

    assert for_a.status_code == 200 and for_a.json()["listings"] == []
    assert for_b.status_code == 200 and len(for_b.json()["listings"]) == 1


def test_an_unscoped_poll_from_a_peer_with_two_links_is_refused(client, fed_settings, remote, world, two_links):
    _share_on(world, two_links[1])

    resp = _discover(client, remote, fed_settings)

    assert resp.status_code == 400
    assert resp.json()["error"] == "scope_required"


def test_an_unscoped_poll_from_a_single_link_peer_still_works(client, fed_settings, remote, world, active_link):
    _share_on(world, active_link)

    resp = _discover(client, remote, fed_settings)

    assert resp.status_code == 200 and len(resp.json()["listings"]) == 1


def _propose(client, remote, fed_settings, share, scope_link):
    body = {
        "proposals": [{"proposal_uuid": str(uuid.uuid4()), "need_remote_uuid": str(share.remote_uuid)}],
        "link": {"community": str(scope_link.community_id), "peer_community": str(scope_link.remote_community_uuid)},
    }
    raw = json.dumps(body).encode()
    sig = remote.sign("POST", dj_settings.SITE_URL.rstrip("/") + PROPOSALS, raw, fed_settings.instance_id)
    return client.post(PROPOSALS, data=raw, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)


def test_a_proposal_must_come_through_the_link_its_ask_was_shared_on(client, fed_settings, remote, world, two_links):
    link_a, link_b = two_links
    share = _share_on(world, link_b)

    wrong = _propose(client, remote, fed_settings, share, link_a).json()["results"][0]
    right = _propose(client, remote, fed_settings, share, link_b).json()["results"][0]

    assert wrong["status"] == "rejected" and wrong["reason"] == "not_shared"
    assert right["status"] == "created"


def test_the_poller_names_its_link_and_signs_that_url(fed_settings, active_link, monkeypatch):
    seen = {}

    def fake_get(base_url, headers, **scope):
        seen.update(scope)
        seen["sig"] = headers["X-UMI-Signature"]
        return {"listings": []}

    monkeypatch.setattr("apps.federation.polling.client_mod.get_discovery", fake_get)

    polling.poll_link(active_link)

    assert seen["community"] == str(active_link.remote_community_uuid)
    assert seen["peer_community"] == str(active_link.community_id)
    claims = json.loads(_b64(seen["sig"].split(".")[1]))
    assert claims["htu"].endswith(f"?community={seen['community']}&peer_community={seen['peer_community']}")


def _b64(segment):
    import base64

    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
