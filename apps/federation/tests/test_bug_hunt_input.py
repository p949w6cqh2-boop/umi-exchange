"""2026-10 bug hunt: federation bodies that are valid JSON but not the right shape.

The handshake is anonymous by design. A body whose top level was a list or a string, or whose
`pairing` or `community` was not an object, reached `.get()` and returned 500 instead of 400.
The signed endpoints read their bodies the same way, so all of them now refuse a non-object body.
"""

import json
import uuid

import pytest
from django.core.cache import cache

from apps.federation import crypto
from apps.federation.tests.conftest import signed_handshake

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]


@pytest.fixture(autouse=True)
def _fresh_throttle():
    cache.clear()  # the handshake allows 5 an hour per IP


def _post(client, payload, remote=None, fed_settings=None):
    data = payload if isinstance(payload, str) else json.dumps(payload)
    ip = f"10.7.7.{uuid.uuid4().int % 250 + 1}"
    if remote is not None:  # signed by the document's key, as every handshake must be now
        return signed_handshake(client, remote, fed_settings, data, HTTP_X_REAL_IP=ip)
    return client.post("/federation/v1/handshake", data=data, content_type="application/json", HTTP_X_REAL_IP=ip)


def _valid(remote):
    code = crypto.mint_pairing_code()
    salt = uuid.uuid4().hex
    return {
        "document": remote.instance_document(),
        "pairing": {"salt": salt, "hash": crypto.remote_code_hash(code, salt)},
        "community": {"uuid": str(uuid.uuid4()), "label": "Their Parish Board"},
    }


def test_a_non_object_pairing_is_a_400(client, fed_settings, remote):
    payload = _valid(remote)
    payload["pairing"] = "x"
    assert _post(client, payload, remote, fed_settings).status_code == 400


def test_a_non_object_community_reads_as_absent_not_as_a_500(client, fed_settings, remote):
    """`community` is optional in a handshake; a value that is not an object is treated like
    a missing one, exactly as omitting it is."""
    payload = _valid(remote)
    payload["community"] = "x"
    assert _post(client, payload, remote, fed_settings).status_code == 200


@pytest.mark.parametrize("body", ["[1, 2, 3]", '"just a string"', "42"])
def test_a_non_object_body_is_a_400(client, fed_settings, remote, body):
    assert _post(client, body).status_code == 400


def test_a_well_formed_handshake_still_works(client, fed_settings, remote):
    assert _post(client, _valid(remote), remote, fed_settings).status_code == 200
