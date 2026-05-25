"""
Match views: propose, detail, accept/fulfill/cancel.
Implements self-matching prevention (Section 8.6) and race condition handling (Section 8.7).
"""
import json
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView
from django_ratelimit.decorators import ratelimit

from apps.communities.models import Community, Member
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.audit.models import AuditLog
from apps.communities.validators import sanitize_text_field
from apps.notifications.adapter import NotificationAdapter
from .models import Match


@method_decorator(ratelimit(key="user", rate="10/m", method="POST", block=True), name="post")
class MatchProposeView(LoginRequiredMixin, View):
    """POST: propose a match between a need and an offer."""

    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)

        need_id = request.POST.get("need_id")
        offer_id = request.POST.get("offer_id")

        need = get_object_or_404(Need, id=need_id, community=community)
        offer = get_object_or_404(Offer, id=offer_id, community=community) if offer_id else None

        # Self-matching prevention (Protocol Section 8.6)
        if need.requester == member:
            messages.error(request, "You cannot propose a match on your own need.")
            return redirect("need-detail", slug=slug, pk=need_id)

        # Need must be open
        if need.status != "open":
            messages.error(request, "This need is not accepting matches.")
            return redirect("need-detail", slug=slug, pk=need_id)

        match = Match.objects.create(need=need, offer=offer, proposed_by=member)

        # Audit log
        AuditLog.log(member.user, "create", "match", match.id, request=request)

        # Notifications
        NotificationAdapter.send(
            need.requester.user, "match_proposed",
            f"{member.display_name} proposed a match on your need '{need.title}'",
            f"View the match to accept or decline.",
            link=f"/c/{slug}/matches/{match.id}/",
        )

        messages.success(request, "Match proposed! Both parties will be notified.")
        return redirect("match-detail", slug=slug, pk=match.id)


class MatchDetailView(LoginRequiredMixin, DetailView):
    model = Match
    template_name = "matches/detail.html"
    context_object_name = "match"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        match = self.object
        community = match.need.community
        member = Member.objects.filter(user=self.request.user, community=community, is_active=True).first()

        ctx["community"] = community
        ctx["member"] = member
        ctx["is_requester"] = member and match.need.requester == member
        ctx["is_offerer"] = member and match.offer and match.offer.offerer == member
        ctx["is_participant"] = ctx["is_requester"] or ctx["is_offerer"]
        ctx["is_coordinator"] = member and member.is_coordinator

        # Contact revelation (Protocol Section 8.2)
        ctx["contact_info"] = match.get_contact_info_for(member)
        ctx["show_contact"] = ctx["contact_info"] is not None

        return ctx


class MatchUpdateView(LoginRequiredMixin, View):
    """POST: update match status (accept, fulfill, cancel, unfulfill)."""

    def post(self, request, slug, pk):
        new_status = request.POST.get("status")
        notes = sanitize_text_field(request.POST.get("notes", ""))
        if new_status not in ("accepted", "fulfilled", "unfulfilled", "cancelled"):
            return HttpResponse(status=400)

        community = get_object_or_404(Community, slug=slug)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)

        # Race condition prevention (Protocol Section 8.7): pessimistic locking
        with transaction.atomic():
            match = Match.objects.select_for_update().get(pk=pk)

            try:
                match.transition_to(new_status)
            except ValidationError as e:
                if request.htmx:
                    return HttpResponse(
                        status=409,
                        headers={"HX-Trigger": json.dumps({"showToast": {
                            "message": str(e.message), "type": "error"
                        }})},
                    )
                messages.error(request, str(e.message))
                return redirect("match-detail", slug=slug, pk=pk)

        # Audit log
        AuditLog.log(member.user, "update", "match", match.id, details={"status": new_status}, request=request)

        # Notifications
        if new_status == "accepted":
            # Contact revelation notification
            other = match.offer.offerer if match.need.requester == member else match.need.requester
            contact = match.get_contact_info_for(member)
            NotificationAdapter.send(
                other.user, "match_accepted",
                f"Match accepted on '{match.need.title}'!",
                f"Contact info has been shared. Check the match detail.",
                link=f"/c/{slug}/matches/{match.id}/",
            )
        elif new_status == "fulfilled":
            messages.success(request, "Match marked as fulfilled! Thank you.")
        elif new_status == "cancelled":
            messages.info(request, "Match cancelled.")

        return redirect("match-detail", slug=slug, pk=pk)
