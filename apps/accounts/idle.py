"""
Idle sign-out. The first coordinator asked for it on 2026-10-02: "have it time you out of
the website after 5-10 minutes of being idle." The people she helps borrow phones and share
family tablets, and a board left signed in on a kitchen counter is an account anyone can use.

Every request from a signed-in person stamps the session. A request that arrives more than
SESSION_IDLE_TIMEOUT_SECONDS after the last stamp signs them out first. Background requests
(the hub's once-a-minute pulse) carry X-Umi-Background and never stamp, or an open tab would
keep a session alive forever.

static/js/idle-timeout.js is the visible half: it warns a minute before, and tells the server
about typing it cannot see, so a long request in the middle of being written is never lost.
Without JavaScript the rule still holds; there is just no warning.
"""

import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

SESSION_KEY = "idle_last_seen"
BACKGROUND_HEADER = "X-Umi-Background"


class IdleTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            limit = settings.SESSION_IDLE_TIMEOUT_SECONDS
            now = time.time()
            last = request.session.get(SESSION_KEY)
            if last is not None and now - last > limit:
                return _sign_out(request, limit)
            if request.headers.get(BACKGROUND_HEADER) != "1":
                request.session[SESSION_KEY] = now
        return self.get_response(request)


def _sign_out(request, limit):
    logout(request)
    minutes = max(1, limit // 60)
    messages.info(
        request,
        f"You were signed out after {minutes} minute{'' if minutes == 1 else 's'} without activity, "
        "to keep your account safe. Sign in to pick up where you left off.",
    )
    if getattr(request, "htmx", False):
        # A fragment request: reload the whole page, which then lands on sign-in.
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response
    if request.content_type == "application/json" or "application/json" in request.headers.get("Accept", ""):
        # The offline casework sync reads this answer and keeps its queue (visit_offline.js).
        return JsonResponse({"reauth": True}, status=403)
    if request.method != "GET":
        # A form cannot be re-sent after signing in, so do not send them back to its URL.
        return redirect(settings.LOGIN_URL)
    return redirect_to_login(request.get_full_path())
