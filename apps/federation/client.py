"""
Minimal outbound HTTP client for federation (decision §9.3: stdlib only).
Strict timeouts, 1 MB response cap, https enforced outside DEBUG, no retries
here — retry policy belongs to the callers (Stage C moves it into a
django-q2 outbox).
"""

import json
import urllib.error
import urllib.request

from django.conf import settings

TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1_000_000


class FederationClientError(Exception):
    pass


def _request(method: str, url: str, body: bytes | None = None, headers: dict | None = None):
    if not url.startswith("https://") and not settings.DEBUG:
        raise FederationClientError("federation peers must be https")
    req = urllib.request.Request(  # noqa: S310
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
    )
    try:
        # Scheme is constrained to https above (http only under DEBUG for tests).
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # nosec B310
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise FederationClientError(f"peer returned HTTP {e.code}") from e
    except Exception as e:  # URLError, timeout, TLS failure
        raise FederationClientError(str(e)[:200]) from e
    if len(raw) > MAX_RESPONSE_BYTES:
        raise FederationClientError("peer response too large")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise FederationClientError("peer returned invalid JSON") from e


def fetch_instance_document(base_url: str) -> str:
    data = _request("GET", base_url.rstrip("/") + "/.well-known/umi-federation")
    document = data.get("document") if isinstance(data, dict) else None
    if not isinstance(document, str):
        raise FederationClientError("peer did not return an instance document")
    return document


def post_handshake(base_url: str, payload: dict) -> dict:
    return _request("POST", base_url.rstrip("/") + "/federation/v1/handshake", json.dumps(payload).encode())


def post_confirm(base_url: str, payload: dict, headers: dict) -> dict:
    return _request(
        "POST", base_url.rstrip("/") + "/federation/v1/handshake/confirm", json.dumps(payload).encode(), headers
    )


def confirm_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/federation/v1/handshake/confirm"
