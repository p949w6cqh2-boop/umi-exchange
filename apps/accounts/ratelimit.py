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
import time
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

AUTH_IP_LIMIT, AUTH_IP_WINDOW = 5, 60  # 5/min per IP
AUTH_ACCT_LIMIT, AUTH_ACCT_WINDOW = 20, 3600  # 20/hr per account


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
                ident = _h(_client_ip(request))
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
    5/min per IP, then 20/hr per submitted account identifier."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.paths = tuple(getattr(settings, "RATELIMIT_AUTH_PATHS", ()))

    def __call__(self, request):
        if (
            getattr(settings, "RATELIMIT_ENABLED", True)
            and self.paths
            and request.method == "POST"
            and request.path.startswith(self.paths)
        ):
            allowed, remaining, reset = check(f"auth:ip:{_h(_client_ip(request))}", AUTH_IP_LIMIT, AUTH_IP_WINDOW)
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
                if not allowed:
                    return _too_many(request, AUTH_ACCT_LIMIT, remaining, reset)
        return self.get_response(request)
