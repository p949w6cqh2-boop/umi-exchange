"""
§10.5 — minimal fixed-window rate limiting (Manual §5.6).

  check(scope_key, limit, window)  -> (allowed, remaining, reset_epoch)
  @rate_limit("name", limit, window, by="ip"|"user")   # view decorator
  AuthRateLimitMiddleware                               # auth POST limits

Identifiers are SHA-256-hashed before becoming cache keys (no raw IPs or
emails at rest anywhere, matching the audit-log discipline). Fixed-window
is deliberate: simple, O(1), and the manual's thresholds don't need
sliding precision.
"""

import hashlib
import ipaddress
import time
from functools import wraps

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

AUTH_IP_LIMIT, AUTH_IP_WINDOW = 5, 60  # 5/min per IP
AUTH_ACCT_LIMIT, AUTH_ACCT_WINDOW = 20, 3600  # 20/hr per account

# A browser that has signed in to an account carries this signed cookie, and passes that account's
# per-account limit at the sign-in door (2026-10 bug hunt, L46): keyed on the name typed, the limit
# let anyone lock a person out by failing to sign in as them. The per-IP limit still applies.
KNOWN_DEVICE_COOKIE = "umi_device"
KNOWN_DEVICE_SALT = "apps.accounts.ratelimit.known-device"
KNOWN_DEVICE_MAX_AGE = 365 * 24 * 3600


def client_ip(request) -> str:
    """Trusted client IP for rate-limiting and audit hashing.

    We trust only X-Real-IP, which the reverse proxy (Caddy) sets and
    overwrites on every request. The left-most X-Forwarded-For entry is
    client-supplied and therefore spoofable — trusting it would let an
    attacker bypass per-IP limits and poison audit IP hashes — so it is
    deliberately NOT used. Falls back to the direct peer (REMOTE_ADDR).
    """
    return request.META.get("HTTP_X_REAL_IP", "").strip() or request.META.get("REMOTE_ADDR", "") or ""


# Backwards-compatible alias for internal callers.
_client_ip = client_ip


def ip_bucket(ip: str) -> str:
    """The address a limit counts by: IPv6 by its /64, IPv4 as it is.

    One subscriber is usually handed a whole /64, so counting the full IPv6 address let one person
    rotate past every per-IP limit (2026-10 bug hunt, L53). django_ratelimit's default IPv6 mask
    does the same for the views it guards. Audit hashing keeps the full address (client_ip).
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address)
    return ip


def remember_device(sender, request, user, **kwargs):
    """user_logged_in: have AuthRateLimitMiddleware hand this browser the known-device cookie."""
    if request is not None:
        request._umi_known_device = str(user.pk)


def _known_device_for(request, ident) -> bool:
    """True when this browser carries a valid cookie from a sign-in to the account `ident` names."""
    raw = request.COOKIES.get(KNOWN_DEVICE_COOKIE)
    if not raw:
        return False
    try:
        user_pk = signing.loads(raw, salt=KNOWN_DEVICE_SALT, max_age=KNOWN_DEVICE_MAX_AGE)
    except signing.BadSignature:
        return False
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    return (
        get_user_model().objects.filter(pk=user_pk).filter(Q(username__iexact=ident) | Q(email__iexact=ident)).exists()
    )


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def check(scope_key: str, limit: int, window: int):
    """Fixed-window counter. Returns (allowed, remaining, reset_epoch)."""
    bucket = int(time.time() // window)
    key = f"rl:{scope_key}:{bucket}"
    cache.add(key, 0, timeout=window + 5)
    try:
        count = cache.incr(key)
    except ValueError:  # key evicted between add and incr
        cache.set(key, 1, timeout=window + 5)
        count = 1
    reset = (bucket + 1) * window
    return count <= limit, max(0, limit - count), reset


def _too_many(request, limit, remaining, reset) -> HttpResponse:
    retry = max(1, reset - int(time.time()))
    wants_json = request.headers.get("HX-Request") == "true" or request.content_type == "application/json"
    if wants_json:
        resp = JsonResponse({"error": "rate_limited", "retry_after": retry}, status=429)
    else:
        resp = HttpResponse(
            "Too many attempts — please wait a moment and try again.", status=429, content_type="text/plain"
        )
    resp["Retry-After"] = str(retry)
    _stamp(resp, limit, remaining, reset)
    return resp


def _stamp(resp, limit, remaining, reset):
    resp["X-RateLimit-Limit"] = str(limit)
    resp["X-RateLimit-Remaining"] = str(remaining)
    resp["X-RateLimit-Reset"] = str(reset)


def rate_limit(scope: str, limit: int, window: int, by: str = "ip"):
    """Decorator for view callables (use with method_decorator on CBVs).
    by="user" falls back to IP for anonymous requests."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not getattr(settings, "RATELIMIT_ENABLED", True):
                return view(request, *args, **kwargs)
            if by == "user" and request.user.is_authenticated:
                ident = str(request.user.pk)
            else:
                ident = _h(ip_bucket(_client_ip(request)))
            allowed, remaining, reset = check(f"{scope}:{by}:{ident}", limit, window)
            if not allowed:
                return _too_many(request, limit, remaining, reset)
            resp = view(request, *args, **kwargs)
            try:
                _stamp(resp, limit, remaining, reset)
            except Exception:
                pass
            return resp

        return wrapper

    return decorator


class AuthRateLimitMiddleware:
    """POSTs to the auth paths in settings.RATELIMIT_AUTH_PATHS:
    5/min per IP, then 20/hr per submitted account identifier, which a browser
    that has signed in to that account passes at the sign-in door (L46). It also
    hands out that known-device cookie on every sign-in."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.paths = tuple(getattr(settings, "RATELIMIT_AUTH_PATHS", ()))

    def __call__(self, request):
        refused = self._throttle(request)
        if refused is not None:
            return refused
        response = self.get_response(request)
        user_pk = getattr(request, "_umi_known_device", None)
        if user_pk:
            response.set_cookie(
                KNOWN_DEVICE_COOKIE,
                signing.dumps(user_pk, salt=KNOWN_DEVICE_SALT),
                max_age=KNOWN_DEVICE_MAX_AGE,
                secure=request.is_secure() or getattr(settings, "SESSION_COOKIE_SECURE", False),
                httponly=True,
                samesite="Lax",
            )
        return response

    def _throttle(self, request):
        """The 429 for a POST over its limits, or None."""
        if (
            getattr(settings, "RATELIMIT_ENABLED", True)
            and self.paths
            and request.method == "POST"
            and request.path.startswith(self.paths)
        ):
            allowed, remaining, reset = check(
                f"auth:ip:{_h(ip_bucket(_client_ip(request)))}", AUTH_IP_LIMIT, AUTH_IP_WINDOW
            )
            if not allowed:
                return _too_many(request, AUTH_IP_LIMIT, remaining, reset)
            # Identify the account by the field the auth backend actually uses.
            # The legacy 'login' alias is gone: no form here submits it, so
            # reading it first let an attacker send login=<random> per request
            # and mint a fresh bucket every time, neutering this throttle.
            ident = (request.POST.get("username") or request.POST.get("email") or "").strip().lower()
            if ident:
                # Scope the per-account bucket by PATH so login / register / reset
                # each get their own counter. Sharing one let a /register/ flood
                # naming a victim lock that victim out of /login/.
                allowed, remaining, reset = check(
                    f"auth:acct:{_h(ident)}:{request.path}", AUTH_ACCT_LIMIT, AUTH_ACCT_WINDOW
                )
                signing_in = request.path.startswith(settings.LOGIN_URL)
                if not allowed and not (signing_in and _known_device_for(request, ident)):
                    return _too_many(request, AUTH_ACCT_LIMIT, remaining, reset)
        return None
