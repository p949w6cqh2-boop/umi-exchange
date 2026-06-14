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

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

SESSION_KEY = "casework_auth_at"
MAX_AGE_SECONDS = 4 * 60 * 60

EXEMPT_URL_NAMES = {"reauth", "sw", "visit-manifest"}


class SensitiveSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        match = getattr(request, "resolver_match", None)
        # resolver_match isn't set yet in middleware __call__; resolve lazily
        from django.urls import resolve, Resolver404
        try:
            match = resolve(request.path_info)
        except Resolver404:
            match = None

        if match and match.namespace == "casework" and request.user.is_authenticated:
            if match.url_name not in EXEMPT_URL_NAMES:
                ts = request.session.get(SESSION_KEY)
                if not ts or (time.time() - ts) > MAX_AGE_SECONDS:
                    if match.url_name == "sync":
                        return JsonResponse({"reauth": True}, status=403)
                    reauth = reverse("casework:reauth",
                                     kwargs={"slug": match.kwargs.get("slug")})
                    return redirect(f"{reauth}?next={request.get_full_path()}")
        return self.get_response(request)


def mark_authenticated(request):
    request.session[SESSION_KEY] = time.time()
