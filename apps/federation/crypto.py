"""
Federation instance identity + the signed-request envelope
(docs/federation-design.md §3.1-§3.2, decisions locked 2026-07-02: JWS over
TLS via joserfc, alg "Ed25519" — RFC 9864 fully-specified name).

Verification order for inbound requests: sender resolves to a pinned peer →
signature verifies → aud is us → iat within ±300 s → htm/htu/digest bind the
exact request → jti unseen (checked LAST so forged requests can't poison the
nonce cache).
"""

import base64
import functools
import hashlib
import hmac
import json
import secrets
import string
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from joserfc import jws
from joserfc.jwk import OKPKey

SKEW_SECONDS = 300
JTI_TTL_SECONDS = 600
MAX_TOKEN_BYTES = 4096
PAIRING_CODE_LENGTH = 12  # design §3.3 said 8 à la join_code; upgraded to 12 for offline brute-force margin
_CODE_ALPHABET = string.ascii_uppercase + string.digits


class FederationAuthError(Exception):
    """Signature/document verification failure. `code` is the wire error code."""

    def __init__(self, code="bad_signature", message=""):
        self.code = code
        super().__init__(message or code)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


# ── Instance identity (§3.1) ─────────────────────────


def generate_private_jwk() -> dict:
    return OKPKey.generate_key("Ed25519").as_dict(private=True)


@functools.lru_cache(maxsize=8)
def _import_key(raw: str) -> OKPKey:
    """Parse the instance private JWK once per distinct key material. Keyed on
    the raw string so prod (one static key) parses once for the process, while
    the test suite (a fresh key per test) still resolves correctly."""
    try:
        return OKPKey.import_key(json.loads(raw))
    except (ValueError, TypeError) as e:
        raise ImproperlyConfigured(f"FEDERATION_PRIVATE_KEY is not a valid Ed25519 JWK: {e}") from e


def load_instance_key() -> OKPKey:
    raw = getattr(settings, "FEDERATION_PRIVATE_KEY", "")
    if not raw:
        raise ImproperlyConfigured(
            "FEDERATION_PRIVATE_KEY is required when federation is enabled "
            "(generate one with `manage.py federation_keygen`)."
        )
    return _import_key(raw)


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 thumbprint for an OKP key: sha256 of the canonical
    {"crv","kty","x"} JSON, base64url without padding."""
    canonical = json.dumps({"crv": jwk["crv"], "kty": jwk["kty"], "x": jwk["x"]}, separators=(",", ":"), sort_keys=True)
    return _b64url(hashlib.sha256(canonical.encode()).digest())


def public_jwk() -> dict:
    return load_instance_key().as_dict(private=False)


def my_instance_id() -> str:
    return jwk_thumbprint(public_jwk())


# ── Instance document (§3.1) ─────────────────────────


def build_instance_document() -> str:
    pub = public_jwk()
    payload = {
        "umi_federation": "1",
        "instance_id": jwk_thumbprint(pub),
        "base_url": settings.SITE_URL,
        "jwk": pub,
        "capabilities": [],  # Stage A advertises no data capabilities
        "software": {"name": "umi-exchange"},
        "locality": getattr(settings, "FEDERATION_LOCALITY", ""),
        "contact": "",
    }
    return jws.serialize_compact(
        {"alg": "Ed25519", "jwk": pub}, json.dumps(payload).encode(), load_instance_key(), algorithms=["Ed25519"]
    )


def verify_instance_document(token: str) -> dict:
    """Self-signature proves key possession; the payload's instance_id must be
    the thumbprint of the embedded key. Trust still comes from the human
    out-of-band approval (§3.3), never from this document alone."""
    if not token or len(token) > MAX_TOKEN_BYTES or token.count(".") != 2:
        raise FederationAuthError("bad_document")
    try:
        header = json.loads(_b64url_decode(token.split(".")[0]))
        embedded = header["jwk"]
        if not isinstance(embedded, dict) or "d" in embedded:
            raise FederationAuthError("bad_document")
        key = OKPKey.import_key(embedded)
        obj = jws.deserialize_compact(token, key, algorithms=["Ed25519"])
        payload = json.loads(obj.payload)
    except FederationAuthError:
        raise
    except Exception as e:
        raise FederationAuthError("bad_document") from e
    if payload.get("umi_federation") != "1" or payload.get("instance_id") != jwk_thumbprint(embedded):
        raise FederationAuthError("bad_document")
    return payload


# ── Signed requests (§3.2) ───────────────────────────


def request_body_digest(body: bytes) -> str:
    return "sha256:" + _b64url(hashlib.sha256(body).digest())


def sign_request(method: str, url: str, body: bytes, aud: str) -> str:
    """Build the X-UMI-Signature header value for an outbound request."""
    claims = {
        "iss": my_instance_id(),
        "aud": aud,
        "iat": int(time.time()),
        "jti": _b64url(secrets.token_bytes(16)),
        "htm": method,
        "htu": url,
        "digest": request_body_digest(body),
    }
    return jws.serialize_compact(
        {"alg": "Ed25519"}, json.dumps(claims).encode(), load_instance_key(), algorithms=["Ed25519"]
    )


def verify_signed_request(request):
    """Verify an inbound federation request. Returns (peer, claims) or raises
    FederationAuthError. Known-peer failures are audited (fed.sig_rejected);
    unknown senders have no resource row to hang an audit on."""
    from apps.audit.services import emit

    from .models import FederationPeer

    token = request.headers.get("X-UMI-Signature", "")
    if not token or len(token) > MAX_TOKEN_BYTES or token.count(".") != 2:
        raise FederationAuthError("bad_signature")
    try:
        unverified = json.loads(_b64url_decode(token.split(".")[1]))
    except Exception as e:
        raise FederationAuthError("bad_signature") from e

    peer = (
        FederationPeer.objects.filter(instance_id=str(unverified.get("iss", ""))[:64]).exclude(status="blocked").first()
    )
    if peer is None:
        raise FederationAuthError("bad_signature")

    def _reject(reason, code="bad_signature"):
        emit("fed.sig_rejected", peer, request=request, details={"reason": reason})
        return FederationAuthError(code)

    try:
        obj = jws.deserialize_compact(token, OKPKey.import_key(peer.jwk), algorithms=["Ed25519"])
        claims = json.loads(obj.payload)
    except Exception:
        raise _reject("bad_jws") from None
    if claims.get("aud") != my_instance_id():
        raise _reject("bad_aud")
    iat = claims.get("iat")
    if not isinstance(iat, int) or abs(time.time() - iat) > SKEW_SECONDS:
        raise _reject("bad_iat")
    if claims.get("htm") != request.method:
        raise _reject("bad_htm")
    # Bind to our ADVERTISED URL (SITE_URL = the base_url in our instance doc),
    # not build_absolute_uri: behind a reverse proxy the inbound Host/scheme can
    # differ from what the peer signed against, which would reject every valid
    # request. The peer signs htu = <our base_url> + path.
    if claims.get("htu") != settings.SITE_URL.rstrip("/") + request.path:
        raise _reject("bad_htu")
    if claims.get("digest") != request_body_digest(request.body):
        raise _reject("bad_digest")
    jti = str(claims.get("jti") or "")[:128]
    # Last: only otherwise-valid requests may consume a nonce slot.
    if not jti or not cache.add(f"fed:jti:{peer.instance_id}:{jti}", 1, JTI_TTL_SECONDS):
        raise _reject("replayed", code="replayed")
    return peer, claims


# ── Pairing codes + link pepper (§3.3, §7) ───────────


def mint_pairing_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def local_code_hash(code: str) -> str:
    """Hash for codes WE minted — salted with SECRET_KEY (the audit ip_hash recipe)."""
    return hashlib.sha256(f"{code}:{settings.SECRET_KEY}".encode()).hexdigest()


def remote_code_hash(code: str, salt: str) -> str:
    """Hash that crosses the wire so the receiving side can verify the code its
    admin enters; salt travels with it (the code itself only travels out-of-band)."""
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def codes_match(expected_hash: str, candidate_hash: str) -> bool:
    return bool(expected_hash) and hmac.compare_digest(expected_hash, candidate_hash)


def derive_link_pepper(code: str, instance_id_a: str, instance_id_b: str) -> bytes:
    """Both sides derive the same 32-byte pepper from the shared one-time code;
    order of instance ids is irrelevant. Stored, never exported (§7)."""
    info = "umi-fed-pepper:" + ":".join(sorted([instance_id_a, instance_id_b]))
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info.encode())
    return hkdf.derive(code.encode())
