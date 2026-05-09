"""Account views: registration, login, profile settings."""
# pyrefly: ignore [missing-import]
from django.contrib.auth import login
# pyrefly: ignore [missing-import]
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, TemplateView
from django_ratelimit.decorators import ratelimit

from .forms import RegistrationForm, LoginForm


@method_decorator(ratelimit(key="ip", rate="3/m", method="POST", block=True), name="post")
class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = "accounts/register.html"
    success_url = reverse_lazy("community-join")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
class UMILoginView(DjangoLoginView):
    form_class = LoginForm
    template_name = "accounts/login.html"


class UMILogoutView(LogoutView):
    next_page = reverse_lazy("landing")


class SettingsView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/settings.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["memberships"] = self.request.user.member_set.filter(is_active=True).select_related("community")

        # 2FA context — check if django-two-factor-auth is available
        try:
            from django_otp.plugins.otp_totp.models import TOTPDevice
            ctx["two_factor_available"] = True
            ctx["two_factor_enabled"] = TOTPDevice.objects.filter(
                user=self.request.user, confirmed=True
            ).exists()
        except ImportError:
            ctx["two_factor_available"] = False
            ctx["two_factor_enabled"] = False

        # Coordinator 2FA requirement flag (deployment-time decision)
        from django.conf import settings as django_settings
        ctx["require_2fa_for_coordinators"] = getattr(
            django_settings, "REQUIRE_2FA_FOR_COORDINATORS", False
        )
        ctx["is_coordinator"] = ctx["memberships"].filter(
            role__in=["coordinator", "admin"]
        ).exists()

        return ctx
