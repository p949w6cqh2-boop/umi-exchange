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
from apps.audit.services import emit
from apps.communities.models import Community, Member
from apps.communities.validators import sanitize_text_field
from apps.moderation.services import is_blocked_between
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

        # Moderation containment: a hidden need/offer — a coordinator-hidden post
        # or a removed member's — is not matchable by ordinary members (mirrors
        # the read gate in needs/views.py). Coordinators keep oversight. Without
        # this, a hidden post stays matchable and its owner's contact is disclosed
        # on accept, defeating the hide.
        if (need.moderation_hidden or (offer is not None and offer.moderation_hidden)) and not member.is_coordinator:
            return _reject(request, slug, need_id, "This post is no longer available.", 404)

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

        # Block: two neighbours who've blocked each other are not matched. The
        # proposer must not be blocked-with the need's requester, nor (when an
        # offer is supplied) with the offer's owner. Preventative, not a recall.
        if is_blocked_between(member, need.requester) or (
            offer is not None and is_blocked_between(member, offer.offerer)
        ):
            return _reject(request, slug, need_id, "You can't propose a match with this neighbour.", 409)

        # H-2: a member may only propose an OFFER THEY OWN — UNLESS they are a
        # coordinator/admin brokering the match on a member's behalf.
        # Subsidiarity: the coordinator *assists*, but the offerer keeps agency —
        # a brokered proposal signals the offerer (below), who can accept or
        # decline. Without one of these paths, a stranger could bind an offer and
        # disclose its owner's contact on accept, with zero action from them.
        # Offer-less direct-volunteer proposals (offer is None) stay allowed.
        if offer is not None and offer.offerer_id != member.id and not member.is_coordinator:
            return _reject(request, slug, need_id, "You can only propose an offer you own.", 400)

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

        # Coordinator-brokered match: the offerer did not propose their own offer,
        # so signal them explicitly. This is the consent safeguard that keeps
        # brokering subsidiarity (assist) rather than substitution — the offerer
        # can still accept or decline the match.
        if offer is not None and offer.offerer_id != member.id:
            NotificationAdapter.send(
                offer.offerer.user,
                "match_proposed",
                f"{member.display_name} proposed your offer '{offer.title}' for a match",
                "Review the match — you can accept or decline.",
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
        if not Member.objects.filter(user=self.request.user, community=obj.need.community, is_active=True).exists():
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
        # The offering party is the offer owner, or — for an offer-less direct
        # volunteer match — the proposer (mirrors Match.get_contact_info_for).
        ctx["is_offerer"] = member and (
            (match.offer and match.offer.offerer == member) or (match.offer is None and match.proposed_by == member)
        )
        ctx["is_participant"] = ctx["is_requester"] or ctx["is_offerer"]
        ctx["is_coordinator"] = member and member.is_coordinator

        # Contact revelation (Protocol Section 8.2)
        ctx["contact_info"] = match.get_contact_info_for(member)
        ctx["show_contact"] = ctx["contact_info"] is not None

        # Report/block this neighbour: only for a participant, only once
        # identities are known (the accepted/fulfilled reveal), and only when the
        # counterpart is a local, active member (skips federated proxies).
        counterpart = match.counterpart_member_for(member)
        ctx["counterpart"] = counterpart
        ctx["can_flag_member"] = bool(
            ctx["is_participant"]
            and ctx["show_contact"]
            and counterpart
            and counterpart.community_id == community.id
            and counterpart.is_active
        )

        # Federation (Stage C2): on a federated match the proxy member carries
        # no channels — the counterpart's exchanged §8.2 dict lives on the
        # sidecar. Same audience, same accepted/fulfilled gate as above.
        if ctx["show_contact"] and (ctx["is_requester"] or ctx["is_coordinator"]):
            from apps.federation.matching import remote_contact_for

            remote = remote_contact_for(match)
            if remote:
                if ctx["is_requester"]:
                    ctx["contact_info"] = remote
                elif "parties" in ctx["contact_info"]:
                    ctx["contact_info"]["parties"].append(remote)

        # Audit every contact-info disclosure (Section 8.3): record who accessed
        # whose contact details and when, so reveals leave an immutable trail.
        if ctx["show_contact"] and member:
            AuditLog.log(member.user, "read", "match_contact", match.id, request=self.request)

        return ctx


class MatchUpdateView(LoginRequiredMixin, View):
    """POST: update match status (accept, fulfill, cancel, unfulfill)."""

    def post(self, request, slug, pk):
        new_status = request.POST.get("status")
        if new_status not in ("accepted", "fulfilled", "unfulfilled", "cancelled"):
            return HttpResponse(status=400)
        # sanitize_text_field raises ValidationError on script-injection / blocked
        # content. It ran before the try/except below, so a hostile note 500'd the
        # request instead of a clean 400 — validate it up front and reject cleanly.
        try:
            notes = sanitize_text_field(request.POST.get("notes", ""))
        except ValidationError as exc:
            return HttpResponse("; ".join(exc.messages), status=400)

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
            match = get_object_or_404(
                Match.objects.select_for_update(of=("self",)).select_related("need", "offer"), pk=pk
            )
            need = Need.objects.select_for_update().get(pk=match.need_id)
            match.need = need  # operate on the freshly locked instance
            # Lock the offer too (separately, for the same nullable-outer-join
            # reason as the match): an accept commits the offer, so two matches
            # sharing one offer must serialize on it — see the accept guard below.
            if match.offer_id is not None:
                match.offer = Offer.objects.select_for_update().get(pk=match.offer_id)

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

            # Offer over-commitment guard (Section 8.7 for the offer): an offer is
            # single-use — once accepted against one need it must not be accepted
            # against another. Checked under the offer's row lock so concurrent
            # accepts of two matches sharing one offer cannot both pass.
            if new_status == "accepted" and match.offer is not None and match.offer.status != "active":
                return _reject(request, slug, pk, "That offer has already been matched.", 409)

            # Moderation containment on accept (mirrors the propose-time guard and
            # the read gate): a need/offer hidden AFTER this match was proposed
            # must not be acceptable by an ordinary member — otherwise the reveal
            # that the hide was meant to prevent still happens. Coordinators keep
            # oversight.
            if (
                new_status == "accepted"
                and (need.moderation_hidden or (match.offer is not None and match.offer.moderation_hidden))
                and not member.is_coordinator
            ):
                return _reject(request, slug, pk, "This post is no longer available.", 409)

            # Block on accept: a block created after the proposal must stop the
            # §8.2 contact reveal — the exact recall a block promises. Party-based
            # (requester ↔ offering member), no actor exemption, mirroring the
            # propose-time block guard. The propose-time check can't cover a block
            # made while the match already sits in 'proposed'.
            if new_status == "accepted":
                offering_member = match.offer.offerer if match.offer is not None else match.proposed_by
                if is_blocked_between(need.requester, offering_member):
                    return _reject(request, slug, pk, "You can't accept a match with this neighbour.", 409)

            # Persist an optional note alongside the status change (saved by
            # transition_to()'s final save()). Blank input leaves notes intact.
            if notes:
                match.notes = notes

            # Capture pre-transition status so we only audit a real cascade change.
            old_need_status = need.status
            old_offer_status = match.offer.status if match.offer else None
            try:
                match.transition_to(new_status)
            except ValidationError as e:
                return _reject(request, slug, pk, str(e.message), 409)

            # Federation (Stage C2): queue the peer event INSIDE the
            # transaction so it commits (or rolls back) with the transition —
            # no-op for local matches or when the flag is off.
            from apps.federation.outbox import queue_match_event

            queue_match_event(match, new_status)

        # Audit log. Record THAT a note was provided, never the note: the audit
        # table is append-only (UPDATE/DELETE revoked), so free text here could
        # never be corrected or crypto-shredded — the note itself lives on
        # Match.notes, which a shred can reach. Mirrors the casework
        # emergency-open discipline ({"justification_provided": True}).
        details = {"status": new_status}
        if notes:
            details["notes_provided"] = True
        AuditLog.log(member.user, "update", "match", match.id, details=details, request=request)

        # Dotted state-change audit (§8.3) for the need/offer that transition_to()
        # cascaded — only when it actually changed them, so no-op saves don't log.
        if need.status != old_need_status:
            emit("need.updated", need, user=member.user, request=request, details={"status": need.status})
        if match.offer is not None and match.offer.status != old_offer_status:
            emit(
                "offer.updated",
                match.offer,
                user=member.user,
                request=request,
                details={"status": match.offer.status},
            )

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
