"""Instance identity, instance documents, and the §3.2 signed-request envelope."""

import json
import time
import uuid

import pytest
from django.conf import settings
from django.test import RequestFactory

from apps.federation import crypto
from apps.federation.crypto import FederationAuthError

from .conftest import body_digest, rfc7638_thumbprint

pytestmark = pytest.mark.django_db

# htu is bound to our advertised SITE_URL (not the Host header), so sign against it.
URL = settings.SITE_URL.rstrip("/") + "/federation/v1/handshake/confirm"


def _request(body: bytes, signature: str | None):
    rf = RequestFactory()
    extra = {"HTTP_X_UMI_SIGNATURE": signature} if signature else {}
    return rf.post("/federation/v1/handshake/confirm", data=body, content_type="application/json", **extra)


class TestIdentity:
    def test_generate_private_jwk_shape(self):
        jwk = crypto.generate_private_jwk()
        assert jwk["kty"] == "OKP"
        assert jwk["crv"] == "Ed25519"
        assert "d" in jwk and "x" in jwk

    def test_instance_id_matches_rfc7638(self, fed_settings):
        assert crypto.my_instance_id() == rfc7638_thumbprint(fed_settings.jwk)

    def test_public_jwk_excludes_private_material(self, fed_settings):
        assert "d" not in crypto.public_jwk()

    def test_missing_key_raises_improperly_configured(self, settings):
        from django.core.exceptions import ImproperlyConfigured

        settings.FEDERATION_ENABLED = True
        settings.FEDERATION_PRIVATE_KEY = ""
        with pytest.raises(ImproperlyConfigured):
            crypto.load_instance_key()


class TestInstanceDocument:
    def test_roundtrip(self, fed_settings):
        token = crypto.build_instance_document()
        payload = crypto.verify_instance_document(token)
        assert payload["umi_federation"] == "1"
        assert payload["instance_id"] == fed_settings.instance_id
        assert payload["jwk"] == fed_settings.jwk

    def test_tampered_document_rejected(self, fed_settings, remote):
        with pytest.raises(FederationAuthError):
            crypto.verify_instance_document(remote.instance_document(tamper=True))

    def test_thumbprint_mismatch_rejected(self, fed_settings, remote):
        # a document whose payload claims someone else's instance_id
        from joserfc import jws as _jws

        payload = {"umi_federation": "1", "instance_id": "not-the-right-thumbprint", "jwk": remote.jwk}
        token = _jws.serialize_compact(
            {"alg": "Ed25519", "jwk": remote.jwk}, json.dumps(payload).encode(), remote.key, algorithms=["Ed25519"]
        )
        with pytest.raises(FederationAuthError):
            crypto.verify_instance_document(token)


class TestSignedRequests:
    def test_roundtrip(self, fed_settings, remote, peer):
        body = b'{"code": "ABC"}'
        sig = remote.sign("POST", URL, body, fed_settings.instance_id)
        got_peer, claims = crypto.verify_signed_request(_request(body, sig))
        assert got_peer.pk == peer.pk
        assert claims["iss"] == remote.instance_id

    def test_missing_header_rejected(self, fed_settings, peer):
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(b"{}", None))
        assert e.value.code == "bad_signature"

    def test_unknown_iss_rejected(self, fed_settings, remote, db):
        body = b"{}"
        sig = remote.sign("POST", URL, body, fed_settings.instance_id)  # no FederationPeer row
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(body, sig))
        assert e.value.code == "bad_signature"

    def test_wrong_aud_rejected(self, fed_settings, remote, peer):
        body = b"{}"
        sig = remote.sign("POST", URL, body, "someone-else")
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(body, sig))
        assert e.value.code == "bad_signature"

    def test_skewed_iat_rejected(self, fed_settings, remote, peer):
        body = b"{}"
        sig = remote.sign("POST", URL, body, fed_settings.instance_id, iat=int(time.time()) - 400)
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(body, sig))
        assert e.value.code == "bad_signature"

    def test_replayed_jti_rejected(self, fed_settings, remote, peer):
        body = b"{}"
        jti = str(uuid.uuid4())
        sig = remote.sign("POST", URL, body, fed_settings.instance_id, jti=jti)
        crypto.verify_signed_request(_request(body, sig))
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(body, sig))
        assert e.value.code == "replayed"

    def test_digest_mismatch_rejected(self, fed_settings, remote, peer):
        sig = remote.sign("POST", URL, b'{"a":1}', fed_settings.instance_id)
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(b'{"a":2}', sig))
        assert e.value.code == "bad_signature"

    def test_signed_get_with_query_string_verifies(self, fed_settings, remote, peer):
        # L-2: htu binds the full path+query, so a legitimately-signed query verifies.
        path = "/federation/v1/discovery?since=2026-W27&cursor=abc"
        url = settings.SITE_URL.rstrip("/") + path
        sig = remote.sign("GET", url, b"", fed_settings.instance_id)
        req = RequestFactory().get(path, HTTP_X_UMI_SIGNATURE=sig)
        got_peer, _claims = crypto.verify_signed_request(req)
        assert got_peer.pk == peer.pk

    def test_tampered_query_string_rejected(self, fed_settings, remote, peer):
        # A signature is bound to the query it was signed for — changing it → bad_htu.
        signed = "/federation/v1/discovery?since=2026-W27"
        sig = remote.sign("GET", settings.SITE_URL.rstrip("/") + signed, b"", fed_settings.instance_id)
        req = RequestFactory().get("/federation/v1/discovery?since=2026-W28", HTTP_X_UMI_SIGNATURE=sig)
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(req)
        # htu mismatch surfaces as the generic "bad_signature" code (the audit
        # reason is "bad_htu") — same as test_htu_bound_to_site_url_not_host_header.
        assert e.value.code == "bad_signature"

    def test_htu_bound_to_site_url_not_host_header(self, fed_settings, remote, peer):
        # A signature whose htu is built from the (proxy) Host header rather than
        # our advertised SITE_URL must be rejected — this is the binding target.
        body = b"{}"
        sig = remote.sign(
            "POST", "http://evil-proxy-host/federation/v1/handshake/confirm", body, fed_settings.instance_id
        )
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(body, sig))
        assert e.value.code == "bad_signature"

    def test_tampered_signature_rejected(self, fed_settings, remote, peer):
        from joserfc.jwk import OKPKey

        body = b"{}"
        wrong_key = OKPKey.generate_key("Ed25519")
        sig = remote.sign("POST", URL, body, fed_settings.instance_id, key_override=wrong_key)
        with pytest.raises(FederationAuthError) as e:
            crypto.verify_signed_request(_request(body, sig))
        assert e.value.code == "bad_signature"


class TestPairing:
    def test_mint_code_length_and_alphabet(self):
        code = crypto.mint_pairing_code()
        assert len(code) == 12
        assert all(c.isalnum() and not c.islower() for c in code)

    def test_derive_link_pepper_symmetric(self):
        p1 = crypto.derive_link_pepper("CODE123", "aaa", "bbb")
        p2 = crypto.derive_link_pepper("CODE123", "bbb", "aaa")
        assert p1 == p2
        assert len(p1) == 32
        assert crypto.derive_link_pepper("OTHER", "aaa", "bbb") != p1

    def test_digest_helper_matches_contract(self):
        assert crypto.request_body_digest(b"hello") == body_digest(b"hello")
