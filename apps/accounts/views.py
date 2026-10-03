"""Account views: registration, login (with the OTP step for enrolled users),
profile settings."""

import time

from csp.decorators import csp_update
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView
from django_otp import login as otp_login
from django_otp import match_token, user_has_device
from django_ratelimit.decorators import ratelimit

from apps.audit.services import emit

from . import phone
from .credentials import issue as issue_credential
from .credentials import redeem as redeem_credential
from .forms import (
    LoginForm,
    OTPTokenForm,
    PhoneCodeForm,
    PhoneRecoverForm,
    ProfileForm,
    RecoveryCodeForm,
    RegistrationForm,
    StaffUnlockForm,
    UsernameRecoveryForm,
)
from .idle import SESSION_KEY as IDLE_SESSION_KEY
from .models import RecoveryCredential
from .verification import (
    PENDING_EMAIL_KEY,
    honeypot_timestamp,
    read_add_email_token,
    read_email_token_claims,
    register_post_trips,
    send_add_email_verification,
    send_registration_email,
    send_verification_email,
)

# The password step stashes the authenticated-but-not-logged-in user here; the
# OTP step consumes it. Short-lived: a pending login is not a session.
OTP_PENDING_SESSION_KEY = "otp:pending"
OTP_PENDING_MAX_AGE_SECONDS = 300


@method_decorator(ratelimit(key="ip", rate="3/m", method="POST", block=True), name="post")
class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("community-join")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Signed render-time stamp for the bot timing check (verification.py).
        ctx["hp_ts"] = honeypot_timestamp()
        return ctx

    def post(self, request, *args, **kwargs):
        # Option C (human-verification spec): a filled honeypot or a
        # faster-than-human submit gets the SAME redirect as success and no
        # account — a scripted registrar learns nothing from the response.
        if register_post_trips(request):
            return redirect(self.success_url)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data.get("email")
        # The account and its paper recovery code are created together or not at all: an
        # email-less account that failed to get its code would have no way back in, ever
        # (docs/specs/account-recovery.md §B).
        with transaction.atomic():
            response = super().form_valid(form)
            code = None if email else issue_recovery_code(self.request, self.object)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        if code:
            return render_recovery_code(self.request, code, continue_url=self.success_url, first_time=True)
        if email:
            # Option C: the address is NOT on the account. It rides in the link, and the
            # click writes it. It waits in the session (set AFTER login, which rotates the
            # session) so the waiting page and the resend button can reach it. The same
            # words whether or not the address is taken: #171.
            self.request.session[PENDING_EMAIL_KEY] = email
            send_registration_email(self.request, self.object, email)
            messages.info(self.request, "We've sent a confirmation link to your email. Click it to finish setup.")
        return response


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class UMILoginView(DjangoLoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"

    def form_valid(self, form):
        """Password verified. For a user with a confirmed OTP device, that is
        NOT login (#4): the settings page promises "protected with TOTP", and a
        bare DjangoLoginView made that promise false — a stolen password alone
        yielded a full session. Stash the pending user and divert to the token
        step; the session is only established there. Un-enrolled users proceed
        exactly as before."""
        user = form.get_user()
        if user_has_device(user, confirmed=True):
            self.request.session[OTP_PENDING_SESSION_KEY] = {
                "user_pk": str(user.pk),
                "backend": user.backend,
                "next": self.get_redirect_url(),  # already sanitized by DjangoLoginView
                "ts": time.time(),
            }
            return redirect("login-otp")
        return super().form_valid(form)


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class OTPVerifyView(View):
    """The second factor. Verifies via django_otp.match_token — every confirmed
    device type (TOTP, static recovery codes), with django-otp's per-device
    failure throttling — then, and only then, establishes the session and marks
    it OTP-verified."""

    template_name = "accounts/login_otp.html"

    def _pending_user(self, request):
        pending = request.session.get(OTP_PENDING_SESSION_KEY)
        if not pending:
            return None, None
        if time.time() - pending.get("ts", 0) > OTP_PENDING_MAX_AGE_SECONDS:
            del request.session[OTP_PENDING_SESSION_KEY]
            return None, None
        user = get_user_model().objects.filter(pk=pending["user_pk"], is_active=True).first()
        return user, pending

    def get(self, request):
        user, _ = self._pending_user(request)
        if user is None:
            return redirect("login")
        return render(request, self.template_name, {"form": OTPTokenForm()})

    def post(self, request):
        user, pending = self._pending_user(request)
        if user is None:
            return redirect("login")
        form = OTPTokenForm(request.POST)
        if form.is_valid():
            device = match_token(user, form.cleaned_data["token"])
            if device is not None:
                user.backend = pending["backend"]
                login(request, user)
                otp_login(request, device)  # stamps the session verified
                request.session.pop(OTP_PENDING_SESSION_KEY, None)
                next_url = pending.get("next")
                return redirect(next_url or self.get_default_redirect_url())
            form.add_error("token", "That code didn't match. Check your app and try again.")
        return render(request, self.template_name, {"form": form})

    @staticmethod
    def get_default_redirect_url():
        from django.conf import settings as django_settings

        return django_settings.LOGIN_REDIRECT_URL


class UMILogoutView(LogoutView):
    next_page = reverse_lazy("landing")

    def dispatch(self, request, *args, **kwargs):
        # Consume any pending messages so they don't leak onto the landing page
        # after sign-out (e.g. "Match cancelled!" appearing on the login screen).
        storage = messages.get_messages(request)
        for _ in storage:
            pass  # iterate to mark all as consumed
        return super().dispatch(request, *args, **kwargs)


class SettingsView(LoginRequiredMixin, UpdateView):
    """User profile settings — view and edit email, phone."""

    form_class = ProfileForm
    template_name = "accounts/settings.html"
    success_url = reverse_lazy("account-settings")

    def get_object(self, queryset=None):
        return self.request.user

    def get_initial(self):
        # `email` is no longer a model field on this form, so ModelForm cannot
        # populate it from the instance.
        initial = super().get_initial()
        initial["email"] = self.request.user.email
        return initial

    def form_valid(self, form):
        """Phone and notification preference save immediately. An email CHANGE
        does not: it goes out as a confirmation link and is written only when
        that link is clicked (docs/specs/account-recovery.md §A).

        The address the form was given is never written to the account in the
        meantime — it rides inside the signed token — because User.email is
        unique=True and an unconfirmed write lets someone claim an address they
        do not own, which also denies it to its real owner permanently. This
        browser's session keeps a copy only to show it back on this page, as
        registration already does.
        """
        response = super().form_valid(form)
        user = self.request.user
        requested = form.cleaned_data.get("email")

        if not requested or requested == user.email:
            messages.success(self.request, "Profile updated.")
            return response

        # Collision is checked here and answers EXACTLY like success: same
        # message, same redirect, and no mail to the existing owner — using
        # their inbox as the oracle would leak just as loudly as an error would.
        taken = get_user_model().objects.filter(email__iexact=requested).exclude(pk=user.pk).exists()
        if not taken:
            send_add_email_verification(self.request, user, requested)
        # Kept for a taken address too, so the page answers exactly like success.
        self.request.session[PENDING_EMAIL_KEY] = requested

        messages.success(
            self.request,
            "Profile updated. Check that address for a confirmation link — your email is not saved until you click it.",
        )
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["memberships"] = self.request.user.member_set.filter(is_active=True).select_related("community")
        pending = self.request.session.get(PENDING_EMAIL_KEY)
        if pending and pending.lower() == (self.request.user.email or "").lower():
            # Confirmed from another device (a phone's mail app): nothing is waiting any more.
            self.request.session.pop(PENDING_EMAIL_KEY, None)
            pending = None
        ctx["pending_email"] = pending
        from django.conf import settings

        ctx["enable_2fa"] = getattr(settings, "ENABLE_2FA", False)
        if ctx["enable_2fa"]:
            ctx["is_2fa_enabled"] = self.request.user.totpdevice_set.filter(confirmed=True).exists()
        return ctx


class ConfirmAddEmailView(View):
    """Landing for the add-an-email link. Possession of the link is the proof
    that the person reads that inbox, which is the entire point — no login
    required, since they may be opening it in their phone's mail app."""

    def get(self, request, token):
        uid, email = read_add_email_token(token)
        if uid is None or not email:
            messages.error(request, "That confirmation link is invalid or has expired. You can request a new one.")
            return redirect("account-settings" if request.user.is_authenticated else "login")

        user = get_user_model().objects.filter(pk=uid).first()
        if user is None:
            messages.error(request, "That confirmation link is invalid or has expired. You can request a new one.")
            return redirect("login")

        # Re-check the collision at CONFIRM time, not just at request time.
        # Someone else can register this address in the 48 hours between the two,
        # and unique=True would raise at save. Refuse rather than 500.
        if get_user_model().objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            messages.error(request, "That address could not be confirmed. Try a different one.")
            return redirect("account-settings" if request.user.is_authenticated else "login")

        user.email = email
        # The address and its proof in ONE save. User.save() clears a confirmation when
        # the address changes WITHOUT a fresh one; writing a fresh one here is what tells
        # it this change is proven (docs/specs/email-confirmation.md).
        user.email_confirmed_at = timezone.now()
        fields = ["email", "email_confirmed_at"]
        if not user.is_human_verified:
            # No verification yet, so this IS the first one and "email" is honest.
            user.verified_at = timezone.now()
            user.verified_via = "email"
            fields += ["verified_at", "verified_via"]
        # If they WERE already verified, verified_via is left exactly as it is.
        # A coordinator vouch was a human act performed at church in front of a
        # witness; it is not ours to overwrite with a weaker machine fact.
        user.save(update_fields=fields)
        # Clicked in the same browser that registered: nothing is pending any more.
        request.session.pop(PENDING_EMAIL_KEY, None)

        messages.success(request, "Email confirmed — you can now reset your password by email.")
        return redirect("account-settings" if request.user.is_authenticated else "login")


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class UsernameRecoveryView(FormView):
    """Logged-out username recovery. Mirrors the password-reset posture: the
    response is identical whether or not the address is known (no user
    enumeration), only active accounts are considered, and one email lists
    every username on the address. Throttled twice like the other auth
    endpoints: the decorator here plus the auth-path middleware
    (RATELIMIT_AUTH_PATHS)."""

    template_name = "accounts/username_recovery.html"
    form_class = UsernameRecoveryForm
    success_url = reverse_lazy("username_recovery_done")

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        # Confirmed addresses only (#172). An unproven address may be a stranger's
        # typo'd-into inbox; mailing it the username hands over half of a takeover.
        # The response below is identical either way, so nothing is enumerable.
        usernames = list(
            get_user_model()
            .objects.filter(email__iexact=email, is_active=True, email_confirmed_at__isnull=False)
            .order_by("username")
            .values_list("username", flat=True)
        )
        if usernames:
            body = render_to_string(
                "emails/username_recovery_email.txt",
                {"usernames": usernames},
            )
            send_mail(
                "Your UMI Exchange username",
                body,
                None,  # DEFAULT_FROM_EMAIL
                [email],
                fail_silently=False,
            )
        return super().form_valid(form)


class UsernameRecoveryDoneView(TemplateView):
    template_name = "accounts/username_recovery_done.html"


class VerifyEmailView(View):
    """The email link's landing. Possession of the link is the proof — no login
    required (the neighbour may be opening it on their phone's mail app)."""

    def get(self, request, token):
        claims = read_email_token_claims(token)
        if claims is None:
            messages.error(request, "That confirmation link is invalid or has expired. You can request a new one.")
            return redirect("verify-pending" if request.user.is_authenticated else "login")
        user = get_user_model().objects.filter(pk=claims["uid"]).first()
        if user is None:
            messages.error(request, "That confirmation link is invalid or has expired. You can request a new one.")
            return redirect("login")

        fields = []
        # The click proves control of the address the link was SENT to. Confirm the
        # account's address only if it is still that one. A legacy uid-only token
        # (claims["email"] is None, issued before 2026-09-26) confirms the current
        # address — bounded by its 48h life; see read_email_token_claims.
        sent_to = claims["email"]
        address_matches = bool(user.email) and (sent_to is None or sent_to.lower() == user.email.lower())
        if address_matches:
            user.email_confirmed_at = timezone.now()
            fields.append("email_confirmed_at")
        if not user.is_human_verified:
            user.verified_at = timezone.now()
            user.verified_via = "email"
            fields += ["verified_at", "verified_via"]
        if fields:
            user.save(update_fields=fields)

        if address_matches:
            messages.success(request, "Email confirmed — welcome aboard.")
        elif user.email:
            # Before #172 this branch still said "Email confirmed" while recording
            # nothing. Say what actually happened.
            messages.info(
                request, "That link was for a different address. Send a fresh one to confirm your current email."
            )
        return redirect("hub:index" if request.user.is_authenticated else "login")


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class VerifySendView(LoginRequiredMixin, View):
    """Resend the confirmation link (throttled like the other auth POSTs)."""

    def post(self, request):
        user = request.user
        needs_human = not user.is_human_verified
        # A verified account can still carry an address nobody has proven — every
        # backfill account does. Before #172 this view bounced all verified accounts to
        # the hub, which would have left exactly those people unable to ever confirm,
        # and so unable to reset a password by email once reset trusts only proven ones.
        needs_address = bool(user.email) and user.email_confirmed_at is None
        if not needs_human and not needs_address:
            return redirect("hub:index")
        if not user.email:
            pending = request.session.get(PENDING_EMAIL_KEY)
            if pending:
                # Registered with an address that is not on the account yet (option C).
                send_registration_email(request, user, pending)
                messages.success(request, "Confirmation link sent. Check your inbox (and spam folder).")
                return redirect("verify-pending")
            messages.info(
                request,
                "There's no email on your account — ask a coordinator at church to vouch for you instead.",
            )
            return redirect("verify-pending")
        send_verification_email(request, user)
        messages.success(request, "Confirmation link sent — check your inbox (and spam folder).")
        return redirect("verify-pending" if needs_human else "account-settings")


class VerifyPendingView(LoginRequiredMixin, TemplateView):
    """The soft gate's landing page: plain words, both exits."""

    template_name = "accounts/verify_pending.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # An address typed at registration is not on the account until its link is
        # clicked (option C); the session is the only place it waits.
        ctx["pending_email"] = self.request.session.get(PENDING_EMAIL_KEY)
        return ctx


# ── The printed recovery code (docs/specs/account-recovery.md §B, A1) ──────────
#
# For the person with no email: reset and username recovery are both email-only, so
# without this a forgotten password is a lost account. The code is shown exactly once and
# never stored, logged, emailed or audited in plain text. Redeeming it STARTS a password
# reset (the stock confirm view) and never signs anyone in, which is the mitigation for it
# being a bearer credential. It is single-use and replaced at the moment it is used.

RECOVERY_CODE_TEMPLATE = "accounts/recovery_code.html"


def issue_recovery_code(request, user):
    """Issue (or re-issue, retiring the old one) and audit. Returns the plaintext."""
    cred, plaintext = issue_credential(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    emit("account.recovery_code.issued", user, user=request.user, request=request)
    return plaintext


def render_recovery_code(request, code, *, continue_url, first_time=False, reset_url=None):
    return render(
        request,
        RECOVERY_CODE_TEMPLATE,
        {"code": code, "continue_url": reset_url or continue_url, "first_time": first_time, "reset_url": reset_url},
    )


class RecoveryCodeRedeemView(FormView):
    """Username + code -> a fresh code on paper, then the ordinary set-a-new-password form.

    Throttled by AuthRateLimitMiddleware on BOTH the client IP and the submitted username
    (settings.RATELIMIT_AUTH_PATHS). Every failure renders the same page with the same words,
    whether the username exists or not.
    """

    template_name = "accounts/recovery_code_redeem.html"
    form_class = RecoveryCodeForm
    FAILED = "That username and recovery code don't match. Check the code on your paper and try again."

    def form_valid(self, form):
        user = get_user_model().objects.filter(username=form.cleaned_data["username"].strip()).first()
        # The paper code, or a one-hour code the board's staff issued (A4). Same page, same answer.
        for purpose, action in (
            (RecoveryCredential.PURPOSE_RECOVERY_CODE, "account.recovery_code.redeemed"),
            (RecoveryCredential.PURPOSE_ADMIN_UNLOCK, "account.unlock.redeemed"),
            (RecoveryCredential.PURPOSE_COORDINATOR_RESET, "account.reset.redeemed"),
        ):
            cred = redeem_credential(user, purpose, form.cleaned_data["code"])
            if cred is not None:
                break
        if cred is None:
            form.add_error(None, self.FAILED)
            return self.form_invalid(form)
        emit(action, user, request=self.request)
        fresh = issue_recovery_code(self.request, user)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
        return render_recovery_code(self.request, fresh, continue_url=reset_url, reset_url=reset_url)


@method_decorator(ratelimit(key="user", rate="5/m", method="POST", block=True), name="post")
class RecoveryCodeNewView(LoginRequiredMixin, View):
    """Print a replacement from settings. The old code stops working immediately."""

    http_method_names = ["post"]

    def post(self, request):
        code = issue_recovery_code(request, request.user)
        return render_recovery_code(request, code, continue_url=reverse("account-settings"))


# ── The audited admin unlock (docs/specs/account-recovery.md §A4) ──────────────
#
# A last resort for the board's staff that is not Django /admin/: exact username, a required
# reason, and the result is a one-hour CODE the person redeems themselves at
# /auth/recover/code/. It never sets a password. The reason is kept on the credential row (which
# can be redacted), never in the append-only audit log; the audit records only that one was
# given. Every use is emailed to every superuser, including the one who did it, because a use you
# did not make is the thing worth seeing. Django /admin/ still exists and still bypasses all of
# this; this adds a better door, it does not close the old one.


@method_decorator(ratelimit(key="user", rate="10/h", method="POST", block=True), name="post")
class StaffUnlockView(LoginRequiredMixin, FormView):
    template_name = "accounts/staff_unlock.html"
    form_class = StaffUnlockForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_staff:
            raise PermissionDenied("Staff only.")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        target = get_user_model().objects.filter(username=form.cleaned_data["username"].strip()).first()
        if target is None:
            form.add_error("username", "No account has exactly that username.")
            return self.form_invalid(form)
        staff = self.request.user
        _, code = issue_credential(
            target,
            RecoveryCredential.PURPOSE_ADMIN_UNLOCK,
            issued_by_label=staff.username,
            note=form.cleaned_data["reason"],
        )
        emit("account.unlock.admin", target, user=staff, request=self.request, details={"reason_provided": True})
        _tell_superusers(target, staff)
        return render(self.request, "accounts/staff_unlock_done.html", {"code": code, "target": target})


def _tell_superusers(target, staff):
    body = (
        f"An admin unlock was issued for the account '{target.username}' by '{staff.username}'.\n\n"
        "It is a one-hour code the person uses to set their own password. The reason is recorded "
        "with it on the board.\n\nIf you did not expect this, look into it now."
    )
    for su in get_user_model().objects.filter(is_superuser=True, is_active=True):
        if su.deliverable_email:
            send_mail("Admin unlock issued — UMI Exchange", body, None, [su.deliverable_email], fail_silently=True)


class StillHereView(View):
    """The idle warning's "I'm still here", its quiet ping while someone types, and its
    background question "how long is left?" (static/js/idle-timeout.js).

    IdleTimeoutMiddleware runs first: a plain request is activity and restamps, one
    marked X-Umi-Background is not. This view only reports the seconds left on the
    stamp, so the page warns and signs out on the server's clock, never its own; a
    page that reloaded itself on its own clock would count as activity forever.
    401 tells a page that is already signed out to reload."""

    def get(self, request):
        from django.conf import settings

        if request.user.is_authenticated:
            stamp = request.session.get(IDLE_SESSION_KEY) or time.time()
            remaining = settings.SESSION_IDLE_TIMEOUT_SECONDS - (time.time() - stamp)
            response = JsonResponse({"remaining": max(0, int(remaining))})
        else:
            response = HttpResponse(status=401)
        response["Cache-Control"] = "no-store"
        return response


# ── Codes by phone (docs/specs/phone-codes.md, decided 2026-10-02, provider 2026-10-03) ──────
#
# The first coordinator: "switch paper codes to phone codes." A code goes only to a number its
# owner has proven, and getting back in with one STARTS a password reset, never a session: the
# rule the paper code follows. Every view here is a 404 while the feature is off.
#
# With Firebase as the provider, every send needs a reCAPTCHA token, so the two pages that send
# carry Google's script and widen the CSP for it; no other page on the board loads Google.

PHONE_CONFIRM_KEY = "phone_confirm"
PHONE_RECOVER_KEY = "phone_recover"
RECAPTCHA_CSP = {
    "script-src": ["https://www.google.com/recaptcha/", "https://www.gstatic.com/recaptcha/"],
    "frame-src": ["https://www.google.com/recaptcha/", "https://recaptcha.google.com/recaptcha/"],
}


def _phone_codes_or_404():
    if not phone.enabled():
        raise Http404


@method_decorator(csp_update(RECAPTCHA_CSP), name="dispatch")
@method_decorator(ratelimit(key="user", rate="10/h", method="POST", block=True), name="post")
class PhoneSendView(LoginRequiredMixin, View):
    """Text (or, with Twilio, call) a code to the number on the account, so its owner can prove it.
    GET is the one-button page that carries the reCAPTCHA; POST sends."""

    def dispatch(self, request, *args, **kwargs):
        _phone_codes_or_404()
        return super().dispatch(request, *args, **kwargs)

    def _channel(self, request):
        channel = request.POST.get("channel") or request.GET.get("channel") or "sms"
        return channel if channel in phone.channels() else None

    def get(self, request):
        number = phone.normalize(request.user.phone)
        channel = self._channel(request)
        if number is None or channel is None:
            messages.error(request, "We can text US and Canada numbers only. Check the number in your profile.")
            return redirect("account-settings")
        return render(
            request,
            "accounts/phone_send.html",
            {"channel": channel, "last_four": number[-4:], "recaptcha_site_key": phone.recaptcha_site_key()},
        )

    def post(self, request):
        channel = self._channel(request)
        number = phone.normalize(request.user.phone)
        if channel is None or number is None:
            messages.error(request, "We can text US and Canada numbers only. Check the number in your profile.")
            return redirect("account-settings")
        if not phone.within_daily_limit(request.user, number):
            messages.error(request, "That's all the codes we can send today. Try again tomorrow, or ask a coordinator.")
            return redirect("account-settings")
        state = phone.send_code(number, channel, recaptcha_token=request.POST.get("recaptcha_token", ""))
        if not state:
            messages.error(request, "We couldn't send a code just now. Try again in a few minutes.")
            return redirect("account-settings")
        request.session[PHONE_CONFIRM_KEY] = {"number": number, "state": state}
        emit(
            "account.phone_code.sent",
            request.user,
            user=request.user,
            request=request,
            details={"channel": channel, "purpose": "confirm"},
        )
        return redirect("phone-confirm")


@method_decorator(ratelimit(key="user", rate="10/h", method="POST", block=True), name="post")
class PhoneConfirmView(LoginRequiredMixin, FormView):
    """Type back the code. Twilio locks a code after 5 wrong tries and expires it at 10 minutes."""

    template_name = "accounts/phone_confirm.html"
    form_class = PhoneCodeForm
    FAILED = "That code didn't work. Check it and try again, or send a new one from your settings."

    def dispatch(self, request, *args, **kwargs):
        _phone_codes_or_404()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["last_four"] = ((self.request.session.get(PHONE_CONFIRM_KEY) or {}).get("number") or "")[-4:]
        return ctx

    def form_valid(self, form):
        user = self.request.user
        sent = self.request.session.get(PHONE_CONFIRM_KEY) or {}
        number = sent.get("number")
        # The number on the account must still be the one the code went to.
        if (
            not number
            or number != phone.normalize(user.phone)
            or not phone.check_code(number, form.cleaned_data["code"], sent.get("state"))
        ):
            form.add_error(None, self.FAILED)
            return self.form_invalid(form)
        user.phone_confirmed_at = timezone.now()
        user.save(update_fields=["phone_confirmed_at"])
        self.request.session.pop(PHONE_CONFIRM_KEY, None)
        emit("account.phone.confirmed", user, user=user, request=self.request)
        messages.success(self.request, "Phone confirmed. If you ever forget your password, we can text you a code.")
        return redirect("account-settings")


@method_decorator(csp_update(RECAPTCHA_CSP), name="dispatch")
class PhoneRecoverView(FormView):
    """Username + text or call -> a code to the account's PROVEN number, if it has one.

    The page answers the same way for every username, so it cannot be used to learn who is on
    the board. Throttled on IP and username (settings.RATELIMIT_AUTH_PATHS), and the daily cap
    in phone.py counts against the account and the number either way."""

    template_name = "accounts/phone_recover.html"
    form_class = PhoneRecoverForm

    def dispatch(self, request, *args, **kwargs):
        _phone_codes_or_404()
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Only the ways the current provider can send: Firebase texts, Twilio texts or calls.
        form.fields["channel"].choices = [c for c in form.fields["channel"].choices if c[0] in phone.channels()]
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recaptcha_site_key"] = phone.recaptcha_site_key()
        return ctx

    def form_valid(self, form):
        self.request.session.pop(PHONE_RECOVER_KEY, None)
        user = get_user_model().objects.filter(username=form.cleaned_data["username"].strip()).first()
        number = phone.normalize(user.deliverable_phone) if user else None
        channel = form.cleaned_data["channel"]
        state = None
        # The daily cap is counted BEFORE anything is sent: it guards money.
        if number and phone.within_daily_limit(user, number):
            state = phone.send_code(number, channel, recaptcha_token=self.request.POST.get("recaptcha_token", ""))
        if state:
            self.request.session[PHONE_RECOVER_KEY] = {"uid": str(user.pk), "state": state}
            emit(
                "account.phone_code.sent",
                user,
                request=self.request,
                details={"channel": channel, "purpose": "recover"},
            )
        return redirect("phone-recover-code")


class PhoneRecoverCodeView(FormView):
    """The code -> the ordinary set-a-new-password page. Never a session. Every failure, including
    "no code was ever sent", gives the same words."""

    template_name = "accounts/phone_recover_code.html"
    form_class = PhoneCodeForm
    FAILED = "That code didn't work. Check it and try again, or ask for a new one."

    def dispatch(self, request, *args, **kwargs):
        _phone_codes_or_404()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        sent = self.request.session.get(PHONE_RECOVER_KEY) or {}
        uid = sent.get("uid")
        user = get_user_model().objects.filter(pk=uid).first() if uid else None
        number = phone.normalize(user.deliverable_phone) if user else None
        if not number or not phone.check_code(number, form.cleaned_data["code"], sent.get("state")):
            form.add_error(None, self.FAILED)
            return self.form_invalid(form)
        self.request.session.pop(PHONE_RECOVER_KEY, None)
        emit("account.phone_code.redeemed", user, request=self.request)
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return redirect(reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token}))
