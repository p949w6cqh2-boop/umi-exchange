"""
Federation Stage A fixtures. Remote-peer signing is implemented here with
joserfc directly (independent of apps.federation.crypto) so the tests pin the
wire contract, not the implementation.
"""

import base64
import hashlib
import json
import time
import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from joserfc import jws
from joserfc.jwk import OKPKey

from apps.communities.models import Community, Member


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def rfc7638_thumbprint(jwk: dict) -> str:
    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]}, separators=(",", ":"), sort_keys=True)
    return b64url(hashlib.sha256(canonical.encode()).digest())


def body_digest(body: bytes) -> str:
    return "sha256:" + b64url(hashlib.sha256(body).digest())


@pytest.fixture
def fed_settings(settings):
    """Enable federation with a fresh instance key for this test."""
    key = OKPKey.generate_key("Ed25519")
    settings.FEDERATION_ENABLED = True
    settings.FEDERATION_PRIVATE_KEY = json.dumps(key.as_dict(private=True))
    return SimpleNamespace(
        key=key, jwk=key.as_dict(private=False), instance_id=rfc7638_thumbprint(key.as_dict(private=False))
    )


@pytest.fixture
def remote():
    """A fake remote instance: keypair + signed instance document + request signer."""
    key = OKPKey.generate_key("Ed25519")
    pub = key.as_dict(private=False)
    instance_id = rfc7638_thumbprint(pub)

    def instance_document(base_url="https://peer.example", *, tamper=False):
        payload = {
            "umi_federation": "1",
            "instance_id": instance_id,
            "base_url": base_url,
            "jwk": pub,
            "capabilities": [],
            "software": {"name": "umi-exchange"},
            "locality": "Testville",
            "contact": "",
        }
        token = jws.serialize_compact(
            {"alg": "Ed25519", "jwk": pub}, json.dumps(payload).encode(), key, algorithms=["Ed25519"]
        )
        if tamper:
            head, pay, sig = token.split(".")
            flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
            token = f"{head}.{pay}.{flipped}"
        return token

    def sign(method, url, body: bytes, aud: str, *, iat=None, jti=None, iss=None, key_override=None):
        claims = {
            "iss": iss or instance_id,
            "aud": aud,
            "iat": int(time.time()) if iat is None else iat,
            "jti": jti or str(uuid.uuid4()),
            "htm": method,
            "htu": url,
            "digest": body_digest(body),
        }
        return jws.serialize_compact(
            {"alg": "Ed25519"}, json.dumps(claims).encode(), key_override or key, algorithms=["Ed25519"]
        )

    return SimpleNamespace(key=key, jwk=pub, instance_id=instance_id, instance_document=instance_document, sign=sign)


def make_user(handle):
    User = get_user_model()  # noqa: N806
    return User.objects.create_user(username=handle, email=f"{handle}@example.test", password="pw-Str0ng!pass")


@pytest.fixture
def world(db):
    admin_u, plain_u = make_user("fedadmin"), make_user("fedplain")
    community = Community.objects.create(name="St. Patrick Conference", slug="st-patrick", created_by=admin_u)
    admin = Member.objects.create(
        user=admin_u, community=community, role="admin", display_name="Father Tom", is_active=True
    )
    plain = Member.objects.create(user=plain_u, community=community, role="member", display_name="Sam", is_active=True)
    return SimpleNamespace(community=community, admin=admin, plain=plain, admin_u=admin_u, plain_u=plain_u)


@pytest.fixture
def peer(db, remote):
    from apps.federation.models import FederationPeer

    return FederationPeer.objects.create(
        base_url="https://peer.example",
        instance_id=remote.instance_id,
        jwk=remote.jwk,
        label="Peer Parish",
        status="pending",
    )


@pytest.fixture
def active_link(world, peer):
    """An active link from the local community to the (now active) peer."""
    from apps.federation.models import FederationLink

    peer.status = "active"
    peer.save(update_fields=["status"])
    return FederationLink.objects.create(
        peer=peer,
        community=world.community,
        remote_community_uuid=uuid.uuid4(),
        remote_community_label="Peer Board",
        status="active",
    )


@pytest.fixture
def authority_match(fed_settings, active_link, world):
    """Stage C2 shared fixture: a shared Need + an inbound proposal accepted by
    the production path, yielding the authority-side Match + FederatedMatch."""
    import uuid as _uuid

    from django.utils import timezone

    from apps.communities.models import Category
    from apps.consent.models import Consent
    from apps.federation import matching, sharing
    from apps.federation.models import FederatedMatch
    from apps.matches.models import Match
    from apps.needs.models import Need

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
        contact_pref="email",
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
    share = sharing.share_record(need, active_link, actor_user=world.admin_u)
    res = matching.receive_proposal(active_link.peer, need_remote_uuid=share.remote_uuid, proposal_uuid=_uuid.uuid4())
    match = Match.objects.get(pk=res["match_uuid"])
    fmatch = FederatedMatch.objects.get(match=match)
    return SimpleNamespace(need=need, share=share, match=match, fmatch=fmatch, link=active_link)


@pytest.fixture(autouse=True)
def _encryption_key(settings):
    """Stage C2 stores contact payloads envelope-encrypted — every federation
    test gets a fresh KEK (the apps/people conftest recipe)."""
    from cryptography.fernet import Fernet

    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()
