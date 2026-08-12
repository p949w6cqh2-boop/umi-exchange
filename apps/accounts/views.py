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
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView
from django_otp import login as otp_login
from django_otp import match_token, user_has_device
from django_ratelimit.decorators import ratelimit

from .forms import LoginForm, OTPTokenForm, ProfileForm, RegistrationForm, UsernameRecoveryForm

# The password step stashes the authenticated-but-not-logged-in user here; the
# OTP step consumes it. Short-lived: a pending login is not a session.
OTP_PENDING_SESSION_KEY = "otp:pending"
OTP_PENDING_MAX_AGE_SECONDS = 300


@method_decorator(ratelimit(key="ip", rate="3/m", method="POST", block=True), name="post")
class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("community-join")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend="django.contrib.auth.backends.ModelBackend")
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

    def form_valid(self, form):
        messages.success(self.request, "Profile updated.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["memberships"] = self.request.user.member_set.filter(is_active=True).select_related("community")
        from django.conf import settings

        ctx["enable_2fa"] = getattr(settings, "ENABLE_2FA", False)
        if ctx["enable_2fa"]:
            ctx["is_2fa_enabled"] = self.request.user.totpdevice_set.filter(confirmed=True).exists()
        return ctx


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
