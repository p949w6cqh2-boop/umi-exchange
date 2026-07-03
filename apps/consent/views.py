"""Consent views — user can view and revoke their consents."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView


class ConsentListView(LoginRequiredMixin, ListView):
    """User sees their own consents."""

    template_name = "consent/list.html"
    context_object_name = "consents"

    def get_queryset(self):
        return self.request.user.consents_given.all().order_by("-granted_at")


class ConsentRevokeView(LoginRequiredMixin, View):
    """POST to revoke a consent."""

    def post(self, request, pk):
        from apps.audit.services import emit

        from .models import Consent

        consent = get_object_or_404(Consent, pk=pk, participant=request.user, status="active")
        consent.status = "revoked"
        consent.revoked_at = timezone.now()
        consent.save(update_fields=["status", "revoked_at"])
        # Withdrawing permission to hold PII is accountability-critical — it must
        # leave an append-only trail, like every other state change. Details are
        # PII-free (scope is a list of scope-type enums, not personal data).
        emit(
            "consent.revoked",
            consent,
            user=request.user,
            request=request,
            details={"grantee_type": consent.grantee_type, "scope": consent.scope},
        )
        # §4.3: if this consent gated any federated shares, stop advertising them
        # and send each peer a signed delete-request. A federation problem must
        # never block the user's revocation, so this is best-effort.
        from django.conf import settings

        if getattr(settings, "FEDERATION_ENABLED", False):
            try:
                from apps.federation.sharing import revoke_shares_for_consent

                revoke_shares_for_consent(consent, actor_user=request.user)
            except Exception:  # nosec B110 — federation side-effects can't block a user's revoke
                pass
        messages.success(request, "Consent revoked.")
        return redirect("consent-list")
