"""
Minimal outbound HTTP client for federation (decision §9.3: stdlib only).
Strict timeouts, 1 MB response cap, https enforced outside DEBUG, redirects
refused, and non-public destinations rejected (SSRF hardening). No retries
here — retry policy belongs to the callers (Stage C moves it into a
django-q2 outbox).
"""

import ipaddress
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

from django.conf import settings

TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 1_000_000


class FederationClientError(Exception):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects: a peer could 30x us to http://, to an
    internal host, or to cloud metadata, defeating the checks in
    _validate_public_url (which only sees the original URL)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirectHandler)


def _validate_public_url(url: str) -> None:
    """Enforce https (outside DEBUG) and reject hosts that resolve to
    loopback/link-local/reserved/multicast addresses — the cloud-metadata and
    localhost SSRF sinks. Private ranges (RFC1918, CGNAT 100.64/10) are allowed:
    parish-to-parish federation over a LAN or Tailscale is a legitimate topology.
    NOTE: getaddrinfo here and the socket in urlopen re-resolve independently
    (a TOCTOU window); acceptable for an admin-gated Stage-A surface — a future
    hardening can pin the resolved address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FederationClientError("unsupported URL scheme")
    if parsed.scheme != "https" and not settings.DEBUG:
        raise FederationClientError("federation peers must be https")
    host = parsed.hostname
    if not host:
        raise FederationClientError("peer URL has no host")
    if settings.DEBUG:
        return  # local dev/tests may target localhost
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise FederationClientError(f"could not resolve peer host: {str(e)[:100]}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise FederationClientError("peer resolves to a non-public address")


def _request(method: str, url: str, body: bytes | None = None, headers: dict | None = None):
    _validate_public_url(url)
    req = urllib.request.Request(  # noqa: S310
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
    )
    try:
        # Scheme validated above; redirects refused by _opener.
        with _opener.open(req, timeout=TIMEOUT_SECONDS) as resp:  # nosec B310
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


def discovery_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/federation/v1/discovery"


def get_discovery(base_url: str, headers: dict) -> dict:
    """Signed GET of a peer's discovery feed. The caller builds the
    X-UMI-Signature header (crypto.sign_request over method+url+empty body)."""
    return _request("GET", discovery_url(base_url), None, headers)
