"""Account views: registration, login (with the OTP step for enrolled users),
profile settings."""

import time

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView
from django_otp import login as otp_login
from django_otp import match_token, user_has_device
from django_ratelimit.decorators import ratelimit

from .forms import LoginForm, OTPTokenForm, ProfileForm, RegistrationForm, UsernameRecoveryForm
from .verification import (
    honeypot_timestamp,
    read_add_email_token,
    read_email_token,
    register_post_trips,
    send_add_email_verification,
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
        response = super().form_valid(form)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
        if self.object.email:
            send_verification_email(self.request, self.object)
            messages.info(self.request, "We've sent a confirmation link to your email — click it to finish setup.")
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

        The address the form was given is never stored anywhere in the meantime
        — it rides inside the signed token — because User.email is unique=True
        and an unconfirmed write lets someone claim an address they do not own,
        which also denies it to its real owner permanently.
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

        messages.success(
            self.request,
            "Profile updated. Check that address for a confirmation link — your email is not saved until you click it.",
        )
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["memberships"] = self.request.user.member_set.filter(is_active=True).select_related("community")
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
        fields = ["email"]
        if not user.is_human_verified:
            # No verification yet, so this IS the first one and "email" is honest.
            user.verified_at = timezone.now()
            user.verified_via = "email"
            fields += ["verified_at", "verified_via"]
        # If they WERE already verified, verified_via is left exactly as it is.
        # A coordinator vouch was a human act performed at church in front of a
        # witness; it is not ours to overwrite with a weaker machine fact.
        user.save(update_fields=fields)

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
        usernames = list(
            get_user_model()
            .objects.filter(email__iexact=email, is_active=True)
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
        uid = read_email_token(token)
        if uid is None:
            messages.error(request, "That confirmation link is invalid or has expired. You can request a new one.")
            return redirect("verify-pending" if request.user.is_authenticated else "login")
        user = get_user_model().objects.filter(pk=uid).first()
        if user is None:
            messages.error(request, "That confirmation link is invalid or has expired. You can request a new one.")
            return redirect("login")
        if not user.is_human_verified:
            user.verified_at = timezone.now()
            user.verified_via = "email"
            user.save(update_fields=["verified_at", "verified_via"])
        messages.success(request, "Email confirmed — welcome aboard.")
        return redirect("hub:index" if request.user.is_authenticated else "login")


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class VerifySendView(LoginRequiredMixin, View):
    """Resend the confirmation link (throttled like the other auth POSTs)."""

    def post(self, request):
        if request.user.is_human_verified:
            return redirect("hub:index")
        if not request.user.email:
            messages.info(
                request,
                "There's no email on your account — ask a coordinator at church to vouch for you instead.",
            )
            return redirect("verify-pending")
        send_verification_email(request, request.user)
        messages.success(request, "Confirmation link sent — check your inbox (and spam folder).")
        return redirect("verify-pending")


class VerifyPendingView(LoginRequiredMixin, TemplateView):
    """The soft gate's landing page: plain words, both exits."""

    template_name = "accounts/verify_pending.html"
