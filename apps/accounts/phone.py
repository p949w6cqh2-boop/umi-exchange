"""Codes by phone (docs/specs/phone-codes.md).

The ONE module that talks to a texting provider, so the tests replace it and the suite never sends
a text or places a call. The provider makes the 6-digit code, sends it, expires it and checks it;
the board stores no code at all.

Two providers, chosen by PHONE_CODES_PROVIDER (the founder's call, 2026-10-03: "lets do firebase for
now then after we get a nonprofit we will switch to twilio"):
  * "firebase" (now): Google Identity Platform. About $0 at parish size (10 free texts a day), texts
    only, and every send needs a reCAPTCHA token from the browser. Google keeps the verified number
    on a Firebase user record, so we delete that record the moment the code checks out.
  * "twilio" (after the 501(c)(3)): Twilio Verify, texts and voice calls (landlines).

Guard rails, because a texting bill is the real cost of abuse ("SMS pumping"):
  * US and Canada numbers only (+1);
  * at most DAILY_LIMIT codes a day per account AND per number, whatever the throttle setting;
  * neither the number nor the code is ever logged or audited.
The whole feature is OFF until PHONE_CODES_ENABLED is set with the chosen provider's credentials.
"""

import base64
import json
import logging
import re
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from .ratelimit import _h, check

CHANNELS = ("sms", "call")
DAILY_LIMIT = 5
TWILIO_URL = "https://verify.twilio.com/v2/Services/{sid}/{path}"
FIREBASE_URL = "https://identitytoolkit.googleapis.com/v1/{path}"

log = logging.getLogger(__name__)


def provider():
    return "twilio" if settings.PHONE_CODES_PROVIDER == "twilio" else "firebase"


def channels():
    """Firebase sends texts only; Twilio can also call a landline and read the code out."""
    return CHANNELS if provider() == "twilio" else ("sms",)


def needs_recaptcha():
    return provider() == "firebase"


def enabled():
    if not settings.PHONE_CODES_ENABLED:
        return False
    if provider() == "twilio":
        return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_VERIFY_SERVICE_SID)
    return bool(settings.FIREBASE_API_KEY)


def normalize(raw):
    """'+1XXXXXXXXXX' for a US or Canada number, else None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":  # no North American area code starts with 0 or 1
        return None
    return "+1" + digits


def within_daily_limit(user, number):
    """Counts this attempt against the account and the number. Always on: it guards money."""
    by_account, _, _ = check(f"phonecode:acct:{_h(str(user.pk))}", DAILY_LIMIT, 86400)
    by_number, _, _ = check(f"phonecode:num:{_h(number)}", DAILY_LIMIT, 86400)
    return by_account and by_number


def _request(url, *, data=None, headers=None, method="POST"):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        # Fixed https hosts (TWILIO_URL, FIREBASE_URL) with quoted parts: not attacker-reachable.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310 (fixed https URL)
            return json.loads(resp.read().decode())
    except Exception as exc:  # a 4xx here also means "no such code": never log the number or code
        log.warning("phone code request failed: %s", type(exc).__name__)
        return None


# ── Twilio Verify ─────────────────────────────────────────────────────────────


def _twilio(path, fields):
    url = TWILIO_URL.format(sid=urllib.parse.quote(settings.TWILIO_VERIFY_SERVICE_SID, safe=""), path=path)
    auth = base64.b64encode(f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()).decode()
    return _request(url, data=urllib.parse.urlencode(fields).encode(), headers={"Authorization": f"Basic {auth}"})


# ── Firebase / Google Identity Platform ───────────────────────────────────────


def _firebase(path, body=None, method="POST"):
    key = urllib.parse.quote(settings.FIREBASE_API_KEY, safe="")
    url = FIREBASE_URL.format(path=path) + f"?key={key}"
    data = json.dumps(body).encode() if body is not None else None
    return _request(url, data=data, headers={"Content-Type": "application/json"}, method=method)


def recaptcha_site_key():
    """The reCAPTCHA site key Firebase issues for this project, cached for a day. "" on failure."""
    if not needs_recaptcha():
        return ""
    cached = cache.get("phonecode:recaptcha-site-key")
    if cached:
        return cached
    data = _firebase("recaptchaParams", method="GET") or {}
    site_key = data.get("recaptchaSiteKey") or ""
    if site_key:
        cache.set("phonecode:recaptcha-site-key", site_key, 86400)
    return site_key


# ── what the views call ───────────────────────────────────────────────────────


def send_code(number, channel, *, recaptcha_token=""):
    """Send a fresh code to an already-normalized number.

    Returns an opaque state the caller keeps in the session and hands back to check_code, or None
    when nothing was sent. A send that needs reCAPTCHA and has no token is refused here, before any
    request leaves the board."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel!r}")
    if channel not in channels():
        return None
    if provider() == "twilio":
        data = _twilio("Verifications", {"To": number, "Channel": channel})
        return "twilio" if data and data.get("status") == "pending" else None
    if not recaptcha_token:
        return None
    data = _firebase("accounts:sendVerificationCode", {"phoneNumber": number, "recaptchaToken": recaptcha_token})
    return (data or {}).get("sessionInfo") or None


def check_code(number, code, state):
    if not state:
        return False
    if provider() == "twilio":
        data = _twilio("VerificationCheck", {"To": number, "Code": code})
        return bool(data and data.get("status") == "approved")
    data = _firebase("accounts:signInWithPhoneNumber", {"sessionInfo": state, "code": code}) or {}
    ok = data.get("phoneNumber") == number
    if data.get("idToken"):
        # The board keeps the proof; Google need not keep the number. Best effort.
        _firebase("accounts:delete", {"idToken": data["idToken"]})
    return ok
