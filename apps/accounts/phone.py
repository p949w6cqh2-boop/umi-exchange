"""Codes by phone, through Twilio Verify (docs/specs/phone-codes.md; decided 2026-10-02).

The ONE module that talks to the provider, so the tests replace it and the suite never sends a
text or places a call. Twilio makes the 6-digit code, sends it by text or voice call, expires it
after 10 minutes and locks it after 5 wrong tries; the board stores no code at all.

Guard rails, because a texting bill is the real cost of abuse ("SMS pumping"):
  * US and Canada numbers only (+1);
  * at most DAILY_LIMIT codes a day per account AND per number, whatever the throttle setting;
  * neither the number nor the code is ever logged or audited.
The whole feature is OFF until PHONE_CODES_ENABLED is set with all three Twilio values.
"""

import base64
import json
import logging
import re
import urllib.parse
import urllib.request

from django.conf import settings

from .ratelimit import _h, check

CHANNELS = ("sms", "call")
DAILY_LIMIT = 5
VERIFY_URL = "https://verify.twilio.com/v2/Services/{sid}/{path}"

log = logging.getLogger(__name__)


def enabled():
    return bool(
        settings.PHONE_CODES_ENABLED
        and settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_VERIFY_SERVICE_SID
    )


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


def _post(path, fields):
    # The host and scheme are fixed; only the configured service ID varies, quoted so it can
    # never add a path segment or query of its own.
    url = VERIFY_URL.format(sid=urllib.parse.quote(settings.TWILIO_VERIFY_SERVICE_SID, safe=""), path=path)
    auth = base64.b64encode(f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()).decode()
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Authorization": f"Basic {auth}"},
        method="POST",
    )
    try:
        # Fixed https host (VERIFY_URL), quoted service ID: not attacker-reachable.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(request, timeout=10) as resp:  # noqa: S310 (fixed https URL)
            return json.loads(resp.read().decode())
    except Exception as exc:  # a 404 here also means "no such code": never log the number or code
        log.warning("phone code request failed: %s", type(exc).__name__)
        return None


def send_code(number, channel):
    """Text ("sms") or call ("call") a fresh code to an already-normalized number."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel!r}")
    data = _post("Verifications", {"To": number, "Channel": channel})
    return bool(data and data.get("status") == "pending")


def check_code(number, code):
    data = _post("VerificationCheck", {"To": number, "Code": code})
    return bool(data and data.get("status") == "approved")
