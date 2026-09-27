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
    # The address rides in the token (2026-09-26, #172): a click proves control of the
    # address the link was SENT to, which is not necessarily the one on the account by
    # the time it is clicked. Confirming the current address from a link sent to an old
    # one would bless an inbox nobody proved.
    return signing.dumps({"uid": str(user.pk), "email": user.email or ""}, salt=EMAIL_VERIFY_SALT)


def read_email_token_claims(token):
    """{"uid", "email"} from a valid, unexpired token; None otherwise (no exceptions out).

    "email" is None for a LEGACY token (issued before 2026-09-26, uid only). Four went out
    that day; they stay valid for their 48 hours and confirm the account's current address.
    The residual is bounded and named: an admin changing that address inside the same 48h.
    """
    try:
        data = signing.loads(token, salt=EMAIL_VERIFY_SALT, max_age=EMAIL_TOKEN_MAX_AGE)
    except signing.BadSignature:  # SignatureExpired subclasses BadSignature
        return None
    if not data.get("uid"):
        return None
    return {"uid": data["uid"], "email": data["email"] if "email" in data else None}


def read_email_token(token):
    """User pk from a valid, unexpired token; None otherwise (no exceptions out)."""
    claims = read_email_token_claims(token)
    return claims["uid"] if claims else None


# ── add-an-email-later token (docs/specs/account-recovery.md §A) ─────────────
#
# A SEPARATE SALT, and that is the security property, not tidiness. The register
# token above carries only a uid. Sharing a salt would let any old registration
# link be replayed against the confirm route to attach an address of the
# attacker's choosing to that account — the token would say "this uid is
# genuine", and the address would be whatever the URL claimed.
#
# The pending address rides INSIDE the signed payload rather than in a database
# column. User.email is unique=True, so an unconfirmed write would let anyone
# squat an address they do not control, and squatting also denies that address
# to its real owner permanently. Nothing is written until the link is clicked.
EMAIL_ADD_SALT = "accounts.email-add"


def make_add_email_token(user, email):
    return signing.dumps({"uid": str(user.pk), "email": email}, salt=EMAIL_ADD_SALT)


def read_add_email_token(token):
    """(uid, email) from a valid, unexpired token; (None, None) otherwise."""
    try:
        data = signing.loads(token, salt=EMAIL_ADD_SALT, max_age=EMAIL_TOKEN_MAX_AGE)
    except signing.BadSignature:  # SignatureExpired subclasses BadSignature
        return None, None
    return data.get("uid"), data.get("email")


def send_add_email_verification(request, user, email):
    """Sent to the NEW address, never to user.email — the whole point is that
    the account may not have one yet."""
    token = make_add_email_token(user, email)
    body = render_to_string(
        "emails/verify_email.txt",
        {
            "username": user.username,
            "link": request.build_absolute_uri(f"/auth/email/confirm/{token}/"),
        },
    )
    send_mail("Confirm your email — UMI Exchange", body, None, [email], fail_silently=False)


def send_verification_email(request, user):
    """One verification message. Delivery inherits the email runbook's backend —
    console in dev, SMTP in production once the steward's creds land.

    The ONE sender allowed to address `user.email` directly rather than
    `user.deliverable_email`: a confirmation link has to go to the unproven address,
    because proving it is the whole point. tests/test_email_confirmation.py allowlists
    exactly this function by name; any other raw recipient fails the build."""
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
