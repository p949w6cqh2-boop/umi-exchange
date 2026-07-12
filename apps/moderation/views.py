"""
Views for report/flag + coordinator moderation queue.

URL hierarchy (all under c/<slug>/moderation/):
  POST /flag/            → FlagCreateView       (any active member)
  GET  /queue/           → ModerationQueueView  (coordinator/admin)
  POST /<pk>/resolve/    → FlagResolveView      (coordinator/admin; can hide content)
  POST /<pk>/dismiss/    → FlagDismissView      (coordinator/admin)

Rate limiting: flag submission is gated at 5/hr per member per community.
Every action is audited (§8.3). Hiding is safe-fail: need → closed,
offer → withdrawn — existing terminal statuses, never a delete.
"""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.accounts.ratelimit import check as rl_check
from apps.audit.services import emit
from apps.common.state import TransitionConflict
from apps.communities.models import Community, Member
from apps.needs.models import Need
from apps.notifications.adapter import NotificationAdapter
from apps.offers.models import Offer

from .forms import DismissFlagForm, FlagForm, ResolveFlagForm
from .models import Flag

_FLAG_LIMIT = 5
_FLAG_WINDOW = 3600  # per hour


def _community_and_member(request, slug):
    """Resolve community + active member for the request user. Raises 404 on mismatch."""
    community = get_object_or_404(Community, slug=slug, is_active=True)
    member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
    return community, member


def _htmx_toast(message, type_="error", status=200):
    return HttpResponse(
        status=status,
        headers={"HX-Trigger": json.dumps({"showToast": {"message": message, "type": type_}})},
    )


def _error(request, message, status=400):
    if request.headers.get("HX-Request"):
        return _htmx_toast(message, "error", status)
    return HttpResponse(message, status=status)


class _HideBlockedError(Exception):
    """Raised inside the resolve transaction when the target cannot be hidden."""

    def __init__(self, message, status=409):
        super().__init__(message)
        self.message = message
        self.status = status


def _resolve_target(community, target_type, target_id):
    """Fetch the flag target within this community, or None."""
    if target_type == "need":
        return Need.objects.filter(pk=target_id, community=community).first()
    if target_type == "offer":
        return Offer.objects.filter(pk=target_id, community=community).first()
    return Member.objects.filter(pk=target_id, community=community, is_active=True).first()


def _notify_coordinators(community, flag, reporter):
    """In-app (+ email if configured) heads-up to every coordinator/admin."""
    coordinators = (
        Member.objects.filter(community=community, is_active=True, role__in=("coordinator", "admin"))
        .exclude(pk=reporter.pk)
        .select_related("user")
    )
    link = reverse("moderation:queue", kwargs={"slug": community.slug})
    for coordinator in coordinators:
        NotificationAdapter.send(
            coordinator.user,
            "flag_submitted",
            "Content reported",
            f"A {flag.target_type} was reported ({flag.get_reason_display().lower()}). Please review the queue.",
            link=link,
        )


class FlagCreateView(LoginRequiredMixin, View):
    """POST: an active member reports a need, offer, or member."""

    def post(self, request, slug):
        community, member = _community_and_member(request, slug)

        allowed, _, _ = rl_check(f"flag:{community.id}:{member.id}", _FLAG_LIMIT, _FLAG_WINDOW)
        if not allowed:
            return _error(
                request, "You've submitted several reports recently. Please wait before reporting again.", 429
            )

        form = FlagForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid report submission.")

        target_type = form.cleaned_data["target_type"]
        target = _resolve_target(community, target_type, form.cleaned_data["target_id"])
        if target is None:
            return _error(request, "That item could not be found in this community.", 404)

        flag = Flag(
            community=community,
            reporter=member,
            reason=form.cleaned_data["reason"],
            detail=form.cleaned_data.get("detail", ""),
            **{target_type: target},
        )
        try:
            flag.full_clean()
            flag.save()
        except ValidationError as e:
            return _error(request, "; ".join(e.messages))
        except IntegrityError:
            # Partial unique constraint: one OPEN flag per reporter per target.
            return _error(request, "You've already reported this — a coordinator will review it.")

        emit(
            "flag.submitted",
            flag,
            user=request.user,
            request=request,
            details={"target_type": target_type, "reason": flag.reason},
        )
        _notify_coordinators(community, flag, member)

        if request.headers.get("HX-Request"):
            return _htmx_toast("Thank you — a coordinator will review your report.", "success")
        if flag.target_url:
            return redirect(f"{flag.target_url}?reported=1")
        return redirect("community-feed", slug=slug)


class ModerationQueueView(LoginRequiredMixin, ListView):
    """Coordinator/admin queue of open flags for this community."""

    template_name = "moderation/queue.html"
    context_object_name = "flags"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        if not member.is_coordinator:
            raise PermissionDenied("Only coordinators and admins can access the moderation queue.")
        self._community = community
        self._member = member
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return (
            Flag.objects.filter(community=self._community, status="open")
            .select_related("reporter", "need", "offer", "member")
            .order_by("created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(
            {
                "community": self._community,
                "member": self._member,
                "resolve_form": ResolveFlagForm(),
                "dismiss_form": DismissFlagForm(),
            }
        )
        return ctx


class _FlagActionView(LoginRequiredMixin, View):
    """Shared plumbing for resolve/dismiss."""

    def _flag_for(self, request, slug, pk):
        community, member = _community_and_member(request, slug)
        if not member.is_coordinator:
            raise PermissionDenied
        flag = get_object_or_404(Flag, pk=pk, community=community)
        return community, member, flag

    def _done(self, request, slug, flag, message):
        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=200,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "showToast": {"message": message, "type": "success"},
                            "queueItemResolved": {"id": str(flag.pk)},
                        }
                    )
                },
            )
        return redirect("moderation:queue", slug=slug)


class FlagResolveView(_FlagActionView):
    """POST: coordinator resolves a flag, optionally hiding the content.

    Hiding is safe-fail: need → 'closed', offer → 'withdrawn' (existing
    terminal statuses). A need already in a live match must have the match
    cancelled first — same rule as deletion.
    """

    def post(self, request, slug, pk):
        community, member, flag = self._flag_for(request, slug, pk)

        form = ResolveFlagForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid submission.")

        action = form.cleaned_data["action"]
        note = form.cleaned_data.get("note", "")

        if action == "hide" and flag.member_id:
            return _error(
                request,
                "Hiding applies to needs and offers. For a member report, resolve with a note "
                "and use the existing member tools (role change, deactivation) if action is needed.",
                400,
            )

        try:
            with transaction.atomic():
                # Claim the flag first — a concurrent coordinator 409s here,
                # and the row lock serializes the content update below.
                flag.resolution = "content_hidden" if action == "hide" else "no_action"
                flag.resolution_note = note
                flag.transition_to("resolved", extra_update_fields=("resolution", "resolution_note"))
                if action == "hide":
                    self._hide_target(request, flag)
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)
        except _HideBlockedError as e:
            return _error(request, e.message, e.status)

        type(flag).objects.filter(pk=flag.pk).update(resolved_by=member)
        flag.resolved_by = member
        emit(
            "flag.resolved",
            flag,
            user=request.user,
            request=request,
            details={"target_type": flag.target_type, "resolution": flag.resolution},
        )
        return self._done(request, slug, flag, "Report resolved.")

    def _hide_target(self, request, flag):
        if flag.need_id:
            need = Need.objects.select_for_update(of=("self",)).get(pk=flag.need_id)
            if need.status == "matched":
                raise _HideBlockedError("This need is in a live match. Cancel the match first, then hide it.")
            if need.status != "open":
                raise _HideBlockedError("This need is already off the board.")
            need.status = "closed"
            need.save(update_fields=["status", "updated_at"])
            emit(
                "need.hidden",
                need,
                user=request.user,
                request=request,
                details={"flag": str(flag.pk), "reason": flag.reason},
            )
        else:
            offer = Offer.objects.select_for_update(of=("self",)).get(pk=flag.offer_id)
            if offer.status == "matched":
                raise _HideBlockedError("This offer is in a live match. Cancel the match first, then hide it.")
            if offer.status != "active":
                raise _HideBlockedError("This offer is already off the board.")
            offer.status = "withdrawn"
            offer.save(update_fields=["status", "updated_at"])
            emit(
                "offer.hidden",
                offer,
                user=request.user,
                request=request,
                details={"flag": str(flag.pk), "reason": flag.reason},
            )


class FlagDismissView(_FlagActionView):
    """POST: coordinator dismisses a flag — reviewed, not a violation."""

    def post(self, request, slug, pk):
        community, member, flag = self._flag_for(request, slug, pk)

        form = DismissFlagForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid submission.")

        flag.resolution_note = form.cleaned_data.get("note", "")
        try:
            flag.transition_to("dismissed", extra_update_fields=("resolution_note",))
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)

        type(flag).objects.filter(pk=flag.pk).update(resolved_by=member)
        flag.resolved_by = member
        emit(
            "flag.dismissed",
            flag,
            user=request.user,
            request=request,
            details={"target_type": flag.target_type},
        )
        return self._done(request, slug, flag, "Report dismissed.")
