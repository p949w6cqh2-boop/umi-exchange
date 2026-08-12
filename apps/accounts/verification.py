"""Human verification (docs/specs/human-verification.md, keyed A+C build 2026-08-12).

One helper module, three jobs:

* the signed email-verification token (48h, `django.core.signing`);
* the register-form bot checks (honeypot field + minimum form age) — both trip paths
  return the SAME response shape as success, so a bot author gets no oracle;
* ``VerifiedRequiredMixin`` — the soft gate. An unverified account can sign in and look
  around; the doors it cannot pass are community join, posting a need or an offer, and
  proposing a match. Two exits, both plain-worded on the pending page: click the email
  link, or a coordinator vouches in person (a robot doesn't sit in a pew).
"""

import time

from django.contrib import messages
from django.core import signing
from django.core.mail import send_mail
from django.shortcuts import redirect
from django.template.loader import render_to_string

EMAIL_VERIFY_SALT = "accounts.email-verify"
HONEYPOT_TS_SALT = "accounts.register-ts"
EMAIL_TOKEN_MAX_AGE = 48 * 3600  # the spec's 48 hours
MIN_FORM_SECONDS = 3  # a human reads the form; a script does not


# ── email verification token ─────────────────────────────────────────────


def make_email_token(user):
    return signing.dumps({"uid": str(user.pk)}, salt=EMAIL_VERIFY_SALT)


def read_email_token(token):
    """User pk from a valid, unexpired token; None otherwise (no exceptions out)."""
    try:
        data = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=EMAIL_TOKEN_MAX_AGE)
    except signing.BadSignature:  # SignatureExpired subclasses BadSignature
        return None
    return data.get("uid")


def send_verification_email(request, user):
    """One verification message. Delivery inherits the email runbook's backend —
    console in dev, SMTP in production once the steward's creds land."""
    token = make_email_token(user)
    body = render_to_string(
        "emails/verify_email.txt",
        {
            "username": user.username,
            "link": request.build_absolute_uri(f"/auth/verify/{token}/"),
        },
    )
    send_mail("Confirm your email — UMI Exchange", body, None, [user.email], fail_silently=False)


# ── register-form bot checks (option C) ──────────────────────────────────


def honeypot_timestamp():
    """Signed render-time stamp for the register form."""
    return signing.dumps(time.time(), salt=HONEYPOT_TS_SALT)


def register_post_trips(request):
    """True when the POST looks scripted: honeypot filled, timestamp missing/forged,
    or the form came back faster than a human can read it. Callers must respond with
    the same shape as success (no oracle)."""
    if request.POST.get("website", "").strip():
        return True
    try:
        rendered_at = signing.loads(request.POST.get("hp_ts", ""), salt=HONEYPOT_TS_SALT)
    except signing.BadSignature:
        return True
    return (time.time() - float(rendered_at)) < MIN_FORM_SECONDS


# ── the soft gate (option A) ─────────────────────────────────────────────


class VerifiedRequiredMixin:
    """Place AFTER LoginRequiredMixin. Redirects unverified accounts to the
    pending page that names both exits. Everything read-only stays open —
    this mixin belongs only on the four write doors the spec gates."""

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not user.is_human_verified:
            messages.info(
                request,
                "One more step before you can post: confirm your email, or ask a coordinator to vouch for you.",
            )
            return redirect("verify-pending")
        return super().dispatch(request, *args, **kwargs)
