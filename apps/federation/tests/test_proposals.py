"""Cross-instance proposals — authority side (Stage C slice 1, §6/§7)."""

import json
import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import crypto, matching
from apps.federation.models import FederatedMatch
from apps.matches.models import Match
from apps.needs.models import Need

pytestmark = pytest.mark.django_db

PROPOSALS_PATH = "/federation/v1/proposals"


def _proposals_url():
    from django.conf import settings

    return settings.SITE_URL.rstrip("/") + PROPOSALS_PATH


@pytest.fixture
def shared_need(fed_settings, active_link, world):
    """A Need shared to the active link, with a pepper on the link so blind
    tokens can be derived, and the requester (world.plain) given an email."""
    active_link.pairing_pepper = b"0" * 32
    active_link.save(update_fields=["pairing_pepper"])
    world.plain_u.email = "maria@example.test"
    world.plain_u.save(update_fields=["email"])
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
        granted_to="Peer",
        grantee_type="community",
        grantee_id=active_link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    from apps.federation import sharing

    share = sharing.share_record(need, active_link, actor_user=world.admin_u)
    return need, share


def _receive(share, **kw):
    peer = share.link.peer
    args = {"need_remote_uuid": share.remote_uuid, "proposal_uuid": uuid.uuid4()}
    args.update(kw)
    return matching.receive_proposal(peer, **args)


def test_proposal_creates_authoritative_match(shared_need):
    need, share = shared_need
    res = _receive(share)
    assert res["status"] == "created"
    match = Match.objects.get(pk=res["match_uuid"])
    assert match.offer is None and match.status == "proposed"
    fm = FederatedMatch.objects.get(match=match)
    assert fm.role == "authority" and fm.link_id == share.link_id
    # proxy member stands in for the remote proposer, inactive.
    assert match.proposed_by.is_active is False
    assert "(federated)" in match.proposed_by.display_name
    assert AuditLog.objects.filter(action="fed.proposal_received").exists()


def test_proposal_idempotent_on_proposal_uuid(shared_need):
    need, share = shared_need
    pid = uuid.uuid4()
    r1 = _receive(share, proposal_uuid=pid)
    r2 = _receive(share, proposal_uuid=pid)
    assert r1["status"] == "created" and r2["status"] == "duplicate"
    assert r1["match_uuid"] == r2["match_uuid"]
    assert Match.objects.count() == 1


def test_proposal_unknown_need_not_shared(shared_need):
    _need, share = shared_need
    peer = share.link.peer
    res = matching.receive_proposal(peer, need_remote_uuid=uuid.uuid4(), proposal_uuid=uuid.uuid4())
    assert res == {"status": "rejected", "reason": "not_shared"}


def test_proposal_on_closed_need_is_gone(shared_need):
    need, share = shared_need
    need.status = "matched"
    need.save(update_fields=["status"])
    assert _receive(share)["reason"] == "gone"
    assert not Match.objects.exists()


def test_blind_token_self_match_rejected(shared_need):
    need, share = shared_need
    # A proposer whose token equals the requester's = the same human (§8.6).
    token = crypto.blind_token(b"0" * 32, "maria@example.test")
    res = _receive(share, blind_token=token)
    assert res == {"status": "rejected", "reason": "self_match"}
    assert not Match.objects.exists()


def test_different_blind_token_is_allowed(shared_need):
    need, share = shared_need
    token = crypto.blind_token(b"0" * 32, "someone.else@example.test")
    assert _receive(share, blind_token=token)["status"] == "created"


def test_proposal_rejected_after_link_revoked(shared_need):
    """C2: revoking the link must immediately stop the peer creating further
    matches. receive_proposal's share lookup must scope by link status (as
    DiscoveryView already does), else a revoked link's still-'active' share keeps
    accepting proposals while the admin UI and audit log say 'revoked'."""
    need, share = shared_need
    assert _receive(share)["status"] == "created"  # baseline works while active

    share.link.transition_to("revoked")  # admin clicks Revoke

    res = _receive(share)  # a fresh proposal (new uuid) from the same peer
    assert res == {"status": "rejected", "reason": "not_shared"}
    assert Match.objects.count() == 1  # only the pre-revocation match survives


def test_proposal_rejected_after_link_suspended(shared_need):
    """A suspended link likewise stops accepting inbound proposals."""
    need, share = shared_need
    share.link.transition_to("suspended")

    res = _receive(share)
    assert res == {"status": "rejected", "reason": "not_shared"}
    assert not Match.objects.exists()


def test_proposals_capped_per_need_per_link(shared_need):
    """M-4: one link can't flood a single Need — non-terminal proposals are
    capped (default 3, product-tunable via the constant)."""
    from apps.federation.matching import MAX_OPEN_PROPOSALS_PER_NEED_PER_LINK

    need, share = shared_need
    cap = MAX_OPEN_PROPOSALS_PER_NEED_PER_LINK
    for _ in range(cap):
        assert _receive(share)["status"] == "created"

    res = _receive(share)  # the (cap+1)-th from the same link
    assert res == {"status": "rejected", "reason": "too_many_open"}
    assert Match.objects.count() == cap


def test_per_peer_cap_isolated_by_instance(fed_settings, monkeypatch):
    """M-2: the post-auth cap buckets by peer instance_id, so two peers (even on
    one source IP) don't throttle each other; one peer's own bucket enforces."""
    from types import SimpleNamespace

    from apps.federation import views

    monkeypatch.setitem(views.FED_PEER_HOURLY_CAPS, "proposals", 1)
    a = SimpleNamespace(instance_id=f"peer-A-{uuid.uuid4()}")
    b = SimpleNamespace(instance_id=f"peer-B-{uuid.uuid4()}")

    assert views._peer_over_cap("proposals", a) is False  # A, 1st: under cap
    assert views._peer_over_cap("proposals", a) is True  # A, 2nd: over its cap
    assert views._peer_over_cap("proposals", b) is False  # B: own bucket, unaffected


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_proposals_endpoint_per_peer_throttle(client, fed_settings, remote, shared_need, monkeypatch):
    """The view returns 429 once a peer exceeds its per-peer cap (same IP)."""
    from apps.federation import views

    monkeypatch.setitem(views.FED_PEER_HOURLY_CAPS, "proposals", 1)
    _need, share = shared_need

    def _post():
        body = json.dumps(
            {"proposals": [{"need_remote_uuid": str(share.remote_uuid), "proposal_uuid": str(uuid.uuid4())}]}
        ).encode()
        sig = remote.sign("POST", _proposals_url(), body, fed_settings.instance_id)
        return client.post(PROPOSALS_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)

    assert _post().status_code == 200  # 1st under cap
    assert _post().status_code == 429  # 2nd over the per-peer cap


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_proposals_endpoint_signed(client, fed_settings, remote, shared_need):
    need, share = shared_need
    body = json.dumps(
        {"proposals": [{"need_remote_uuid": str(share.remote_uuid), "proposal_uuid": str(uuid.uuid4())}]}
    ).encode()
    sig = remote.sign("POST", _proposals_url(), body, fed_settings.instance_id)
    resp = client.post(PROPOSALS_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "created"


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_proposals_endpoint_requires_signature(client, fed_settings, active_link):
    resp = client.post(PROPOSALS_PATH, data=b"{}", content_type="application/json")
    assert resp.status_code == 403
