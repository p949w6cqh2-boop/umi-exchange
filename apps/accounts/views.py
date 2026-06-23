"""Account views: registration, login, profile settings."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.contrib.auth.views import LogoutView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, UpdateView
from django_ratelimit.decorators import ratelimit

from .forms import LoginForm, ProfileForm, RegistrationForm


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
