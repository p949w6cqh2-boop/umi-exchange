"""Consent views — user can view and revoke their consents."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import ListView


class ConsentListView(LoginRequiredMixin, ListView):
    """A user sees their own consents, plus the ones they recorded for a
    neighbour who has no account.

    Those second ones name nobody with a login, so without this they appear in no
    list anywhere — and a consent nobody can find is a consent nobody can
    withdraw. The person who wrote it down is the only one who can act on it, so
    the duty to be able to withdraw it falls to them.
    """

    template_name = "consent/list.html"
    context_object_name = "consents"

    def get_queryset(self):
        from django.db.models import Q

        from .models import Consent

        own = Q(participant=self.request.user)
        recorded = Q(recorded_by__user=self.request.user, recorded_by__is_active=True)  # still in that community
        return (
            Consent.objects.filter(own | recorded)
            .select_related("subject_person", "recorded_by")
            .order_by("-granted_at")
        )


class ConsentRevokeView(LoginRequiredMixin, View):
    """POST to revoke a consent."""

    def post(self, request, pk):
        from django.db.models import Q

        from apps.audit.services import emit

        from .models import Consent

        # Either your own consent, or one you recorded for a neighbour with no
        # account — see ConsentListView for why the recorder holds that duty. Only while you are
        # still in that community: a removed or departed recorder could revoke, freezing every
        # case resting on it (2026-10 bug hunt, L14).
        own = Q(participant=request.user)
        recorded = Q(recorded_by__user=request.user, recorded_by__is_active=True)
        consent = get_object_or_404(
            Consent.objects.filter(own | recorded),
            pk=pk,
            status="active",
        )
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
        # never block the user's revocation, so this is best-effort. The shares end
        # even with federation switched off, or they came back live with it (2026-10
        # bug hunt, L57); only the peer call waits on the flag. Discovery and
        # proposals also re-check the consent itself.
        from django.conf import settings

        try:
            from apps.federation.sharing import revoke_shares_for_consent

            revoke_shares_for_consent(
                consent, actor_user=request.user, notify=getattr(settings, "FEDERATION_ENABLED", False)
            )
        except Exception:  # nosec B110 — federation side-effects can't block a user's revoke
            pass
        messages.success(request, "Consent revoked.")
        return redirect("consent-list")
