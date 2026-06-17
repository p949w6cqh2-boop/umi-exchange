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
from django.views import View
from django.views.generic import DetailView

from apps.audit.models import AuditLog
from apps.communities.models import Community, Member
from apps.communities.validators import sanitize_text_field
from apps.needs.models import Need
from apps.notifications.adapter import NotificationAdapter
from apps.offers.models import Offer

from .models import Match


def _reject(request, slug, pk, message, status):
    """Return an error response, as an HTMX toast when applicable, otherwise a
    plain response carrying the status code (so callers/tests see 400/403/409)."""
    if getattr(request, "htmx", False):
        return HttpResponse(
            status=status,
            headers={"HX-Trigger": json.dumps({"showToast": {"message": message, "type": "error"}})},
        )
    return HttpResponse(message, status=status)


class MatchProposeView(LoginRequiredMixin, View):
    """POST: propose a match between a need and an offer."""

    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)

        need_id = request.POST.get("need_id")
        offer_id = request.POST.get("offer_id")

        need = get_object_or_404(Need, id=need_id, community=community)
        offer = get_object_or_404(Offer, id=offer_id, community=community) if offer_id else None

        # Self-matching prevention (Protocol Section 8.6): the proposer must not
        # be the need's requester, and an offer owned by the requester cannot be
        # matched to that same person's need.  Check both Member-level AND
        # User-level identity to block the same human using separate sessions.
        if need.requester_id == member.id or need.requester.user_id == request.user.id:
            return _reject(request, slug, need_id, "You cannot propose a match on your own need.", 400)
        if offer is not None and (
            offer.offerer_id == need.requester_id or offer.offerer.user_id == need.requester.user_id
        ):
            return _reject(request, slug, need_id, "An offer cannot be matched to its owner's own need.", 400)

        # The offer, when supplied, must still be available (offer-less
        # "direct volunteer" proposals are allowed and skip this check).
        if offer is not None and offer.status != "active":
            messages.error(request, "That offer is no longer available.")
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
            need.requester.user,
            "match_proposed",
            f"{member.display_name} proposed a match on your need '{need.title}'",
            "View the match to accept or decline.",
            link=f"/c/{slug}/matches/{match.id}/",
        )

        messages.success(request, "Match proposed! Both parties will be notified.")
        return redirect("match-detail", slug=slug, pk=match.id)


class MatchDetailView(LoginRequiredMixin, DetailView):
    model = Match
    template_name = "matches/detail.html"
    context_object_name = "match"

    def get_object(self, queryset=None):
        """Enforce community membership — prevent cross-community IDOR."""
        from django.http import Http404

        obj = super().get_object(queryset)
        if not Member.objects.filter(
            user=self.request.user, community=obj.need.community, is_active=True
        ).exists():
            raise Http404("You are not a member of this community.")
        return obj

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

        # Audit every contact-info disclosure (Section 8.3): record who accessed
        # whose contact details and when, so reveals leave an immutable trail.
        if ctx["show_contact"] and member:
            AuditLog.log(member.user, "read", "match_contact", match.id, request=self.request)

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

        # Race condition prevention (Protocol Section 8.7): pessimistic locking.
        # Lock the Need (the contended resource) so two concurrent accepts on the
        # same need cannot both succeed; then lock the Match row itself.
        with transaction.atomic():
            # Lock only the Match row (of=("self",)): select_related pulls in the
            # nullable `offer` as a LEFT OUTER JOIN, and Postgres refuses a bare
            # FOR UPDATE on the nullable side of an outer join. We only need to
            # lock the match itself here; the Need is locked separately below.
            match = Match.objects.select_for_update(of=("self",)).select_related("need", "offer").get(pk=pk)
            need = Need.objects.select_for_update().get(pk=match.need_id)
            match.need = need  # operate on the freshly locked instance

            # Cross-community IDOR guard: the match must belong to the
            # community identified by the URL slug.  Without this, a
            # coordinator in Community A could mutate matches in Community B.
            if need.community_id != community.id:
                return _reject(request, slug, pk, "Match does not belong to this community.", 403)

            # Authorization (Protocol Section 8.2): only the need requester, the
            # offer owner (or, for a direct-volunteer match, the proposer), or a
            # community coordinator may change a match's status.
            is_requester = need.requester_id == member.id
            if match.offer is not None:
                is_offerer = match.offer.offerer_id == member.id
            else:
                is_offerer = match.proposed_by_id == member.id  # direct volunteer
            if not (is_requester or is_offerer or member.is_coordinator):
                return _reject(request, slug, pk, "You are not authorised to update this match.", 403)

            # Double-accept guard (Section 8.7): the need must still be open to accept.
            if new_status == "accepted" and need.status != "open":
                return _reject(request, slug, pk, "This need has already been matched.", 409)

            # Persist an optional note alongside the status change (saved by
            # transition_to()'s final save()). Blank input leaves notes intact.
            if notes:
                match.notes = notes

            try:
                match.transition_to(new_status)
            except ValidationError as e:
                return _reject(request, slug, pk, str(e.message), 409)

        # Audit log
        details = {"status": new_status}
        if notes:
            details["notes"] = notes
        AuditLog.log(member.user, "update", "match", match.id, details=details, request=request)

        # Notifications — inform the counterpart participant(s); never the actor.
        if new_status == "accepted":
            recipients = []
            if not is_requester:
                recipients.append(need.requester)
            if match.offer and not is_offerer:
                recipients.append(match.offer.offerer)
            elif match.offer is None and match.proposed_by_id != member.id:
                recipients.append(match.proposed_by)
            for other in recipients:
                NotificationAdapter.send(
                    other.user,
                    "match_accepted",
                    f"Match accepted on '{match.need.title}'!",
                    "Contact info has been shared — open the match page to see it.",
                    link=f"/c/{slug}/matches/{match.id}/",
                )
        elif new_status == "fulfilled":
            messages.success(request, "Match marked as fulfilled! Thank you.")
        elif new_status == "cancelled":
            messages.info(request, "Match cancelled.")

        return redirect("match-detail", slug=slug, pk=pk)
