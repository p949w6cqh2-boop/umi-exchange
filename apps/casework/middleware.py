"""
4-hour sensitive-session re-auth for casework decrypt views (Manual §5.3,
design §3.1/§3.8).

First entry into /c/<slug>/cases/ in a session requires a one-time password
confirmation; thereafter, any gap longer than 4 hours requires it again.
Non-decrypting helper routes (the re-auth page itself, the service worker,
the offline manifest) are exempt. The offline sync endpoint returns 403 JSON
{"reauth": true} instead of a redirect so the client can keep its queue.
"""

import time
from urllib.parse import urlencode, urlparse

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

SESSION_KEY = "casework_auth_at"
SESSION_USER_KEY = "casework_auth_uid"  # bind the stamp to the user who earned it
MAX_AGE_SECONDS = 4 * 60 * 60

EXEMPT_URL_NAMES = {"reauth", "sw", "visit-manifest"}


class SensitiveSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        match = getattr(request, "resolver_match", None)
        # resolver_match isn't set yet in middleware __call__; resolve lazily
        from django.urls import Resolver404, resolve

        try:
            match = resolve(request.path_info)
        except Resolver404:
            match = None

        if match and match.namespace == "casework" and request.user.is_authenticated:
            if match.url_name not in EXEMPT_URL_NAMES:
                ts = request.session.get(SESSION_KEY)
                uid = request.session.get(SESSION_USER_KEY)
                # Require a fresh stamp AND that it belongs to THIS user, so a
                # stale stamp left in a reused session can never satisfy another
                # user's gate (defense-in-depth beyond Django's logout flush).
                fresh = bool(ts) and (time.time() - ts) <= MAX_AGE_SECONDS and uid == str(request.user.pk)
                if not fresh:
                    if match.url_name == "sync":
                        return JsonResponse({"reauth": True}, status=403)
                    reauth = reverse("casework:reauth", kwargs={"slug": match.kwargs.get("slug")})
                    # Encoded: a raw next= lost everything after its first '&' (2026-10 bug hunt, L24).
                    target = f"{reauth}?{urlencode({'next': _return_to(request, match)})}"
                    if request.headers.get("HX-Request"):
                        # A fragment request: send the whole page to re-auth. A 302 made htmx swap
                        # the full re-auth page into the notes list (L65), as accounts/idle.py avoids.
                        response = HttpResponse(status=204)
                        response["HX-Redirect"] = target
                        return response
                    return redirect(target)
        return self.get_response(request)


def _return_to(request, match):
    """Where re-auth sends them back to. A GET comes back to itself. A form can't be re-sent, so a
    POST comes back to its case page (its own URL is POST-only: a 405, L65), and an htmx request to
    the page the person was on, not the fragment it asked for."""
    if request.headers.get("HX-Request"):
        current = urlparse(request.headers.get("HX-Current-URL", ""))
        if current.path:
            return current.path + (f"?{current.query}" if current.query else "")
    elif request.method == "GET":
        return request.get_full_path()
    slug, pk = match.kwargs.get("slug"), match.kwargs.get("pk")
    if pk:
        return reverse("casework:detail", kwargs={"slug": slug, "pk": pk})
    return reverse("casework:list", kwargs={"slug": slug})


def mark_authenticated(request):
    request.session[SESSION_KEY] = time.time()
    # str(): the user pk is a UUID — the JSON session serializer (DB/file
    # sessions, i.e. any Redis-less deploy) cannot encode a raw UUID and
    # would 500 the re-auth POST at session save. CI's Redis cache sessions
    # pickle, which masked this. Store the portable form everywhere.
    request.session[SESSION_USER_KEY] = str(request.user.pk)
