"""
Views for Member Tags & Verification.

URL hierarchy (all under c/<slug>/tags/):
  GET  /             → MemberTagListView   (member's own tags + available to claim)
  POST /claim/       → TagClaimView
  POST /<pk>/request-verify/ → TagRequestVerifyView
  POST /<pk>/remove/ → TagRemoveView
  GET  /queue/       → VerificationQueueView  (coordinator/admin)
  POST /<pk>/verify/ → TagVerifyView
  POST /<pk>/reject/ → TagRejectView
  POST /<pk>/revoke/ → TagRevokeView

Rate limiting: claim + request-verify are gated at 10/hr per member per community.
"""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.accounts.ratelimit import check as rl_check
from apps.common.state import TransitionConflict
from apps.communities.models import Community, Member

from .forms import RejectTagForm, RequestVerifyForm, RevokeTagForm, TagClaimForm, VerifyTagForm
from .models import MemberTag

_TAGREQ_LIMIT = 10
_TAGREQ_WINDOW = 3600  # per hour


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


class MemberTagListView(LoginRequiredMixin, TemplateView):
    """Member's own tags + the catalog of available tags to claim."""

    template_name = "tags/my_tags.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        community, member = _community_and_member(self.request, self.kwargs["slug"])
        my_tags = (
            MemberTag.objects.filter(member=member)
            .exclude(status__in=("removed", "revoked"))
            .select_related("tag")
            .order_by("tag__sort_order", "tag__label")
        )
        claim_form = TagClaimForm(community=community, member=member)
        ctx.update(
            {
                "community": community,
                "member": member,
                "my_tags": my_tags,
                "claim_form": claim_form,
                "request_verify_form": RequestVerifyForm(),
            }
        )
        return ctx


class TagClaimView(LoginRequiredMixin, View):
    """POST: claim a tag (creates MemberTag, sets initial status via claim())."""

    def post(self, request, slug):
        community, member = _community_and_member(request, slug)

        # Rate limit: 10 claims+requests per hour per member per community
        allowed, _, _ = rl_check(f"tagreq:{community.id}:{member.id}", _TAGREQ_LIMIT, _TAGREQ_WINDOW)
        if not allowed:
            return _error(request, "You've submitted too many tag requests. Please wait before trying again.", 429)

        form = TagClaimForm(request.POST, community=community, member=member)
        if not form.is_valid():
            return _error(request, "Invalid tag selection.")

        tag = form.cleaned_data["tag"]
        visibility = form.cleaned_data["visibility"]

        try:
            mt = MemberTag(member=member, tag=tag, visibility=visibility)
            mt.clean()
            mt.save()
            mt.claim(request=request)
        except IntegrityError:
            return _error(request, "You have already claimed this tag.")
        except ValidationError as e:
            return _error(request, str(e.message))

        if request.headers.get("HX-Request"):
            return _htmx_toast(f'"{tag.label}" added to your profile.', "success")
        return redirect("tags:my-tags", slug=slug)


class TagRemoveView(LoginRequiredMixin, View):
    """POST: member soft-removes their own tag."""

    def post(self, request, slug, pk):
        community, member = _community_and_member(request, slug)
        mt = get_object_or_404(MemberTag, pk=pk, member=member)

        try:
            mt.remove(request=request)
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)

        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=200,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "showToast": {"message": f'"{mt.tag.label}" removed.', "type": "success"},
                            "tagRemoved": {"id": str(pk)},
                        }
                    )
                },
            )
        return redirect("tags:my-tags", slug=slug)


class TagRequestVerifyView(LoginRequiredMixin, View):
    """POST: member requests coordinator/admin verification of a self-claimed tag."""

    def post(self, request, slug, pk):
        community, member = _community_and_member(request, slug)
        mt = get_object_or_404(MemberTag, pk=pk, member=member)

        allowed, _, _ = rl_check(f"tagreq:{community.id}:{member.id}", _TAGREQ_LIMIT, _TAGREQ_WINDOW)
        if not allowed:
            return _error(request, "Too many verification requests. Please wait before trying again.", 429)

        form = RequestVerifyForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid submission.")

        evidence_note = form.cleaned_data.get("evidence_note", "")

        try:
            if mt.status == "self_claimed":
                mt.request_verification(evidence_note=evidence_note, request=request)
            elif mt.status == "rejected":
                mt.re_request(evidence_note=evidence_note, request=request)
            else:
                return _error(request, "This tag cannot be submitted for verification in its current state.", 400)
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)

        if request.headers.get("HX-Request"):
            return _htmx_toast("Verification request submitted — a coordinator will review it shortly.", "success")
        return redirect("tags:my-tags", slug=slug)


class VerificationQueueView(LoginRequiredMixin, ListView):
    """Coordinator/admin view of pending (and flagged) tag verification requests."""

    template_name = "tags/queue.html"
    context_object_name = "queue_items"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        if not member.is_coordinator:
            raise PermissionDenied("Only coordinators and admins can access the verification queue.")
        self._community = community
        self._member = member
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = (
            MemberTag.objects.filter(tag__community=self._community, status="pending")
            .select_related("member", "tag")
            .order_by("requested_at")
        )
        # Admins see all; coordinators see only coordinator-tier (not admin_verified)
        if not self._member.is_admin:
            qs = qs.filter(tag__tier="coordinator_verified")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        flagged = (
            MemberTag.objects.filter(tag__community=self._community, rejection_count__gte=3)
            .exclude(status__in=("removed", "revoked"))
            .select_related("member", "tag")
            .order_by("-rejection_count", "requested_at")
        )
        if not self._member.is_admin:
            flagged = flagged.filter(tag__tier="coordinator_verified")
        ctx.update(
            {
                "community": self._community,
                "member": self._member,
                "flagged_items": flagged,
                "verify_form": VerifyTagForm(),
                "reject_form": RejectTagForm(),
                "revoke_form": RevokeTagForm(),
            }
        )
        return ctx


class TagVerifyView(LoginRequiredMixin, View):
    """POST: coordinator/admin verifies a pending tag."""

    def post(self, request, slug, pk):
        community, member = _community_and_member(request, slug)
        if not member.is_coordinator:
            raise PermissionDenied

        mt = get_object_or_404(MemberTag, pk=pk, tag__community=community)
        form = VerifyTagForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid submission.")

        evidence_note = form.cleaned_data.get("evidence_note", "")

        try:
            mt.verify(member, evidence_note=evidence_note, request=request)
        except PermissionDenied as e:
            return _error(request, str(e), 403)
        except ValidationError as e:
            return _error(request, str(e.message), 400)
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)

        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=200,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "showToast": {
                                "message": f'"{mt.tag.label}" verified for {mt.member.display_name}.',
                                "type": "success",
                            },
                            "queueItemResolved": {"id": str(pk)},
                        }
                    )
                },
            )
        return redirect("tags:queue", slug=slug)


class TagRejectView(LoginRequiredMixin, View):
    """POST: coordinator/admin rejects a pending tag request."""

    def post(self, request, slug, pk):
        community, member = _community_and_member(request, slug)
        if not member.is_coordinator:
            raise PermissionDenied

        mt = get_object_or_404(MemberTag, pk=pk, tag__community=community)
        form = RejectTagForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid submission.")

        reason = form.cleaned_data.get("reason", "")

        try:
            mt.reject(member, reason=reason, request=request)
        except PermissionDenied as e:
            return _error(request, str(e), 403)
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)

        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=200,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "showToast": {"message": f'"{mt.tag.label}" request rejected.', "type": "success"},
                            "queueItemResolved": {"id": str(pk)},
                        }
                    )
                },
            )
        return redirect("tags:queue", slug=slug)


class TagRevokeView(LoginRequiredMixin, View):
    """POST: coordinator/admin revokes a verified tag."""

    def post(self, request, slug, pk):
        community, member = _community_and_member(request, slug)
        if not member.is_coordinator:
            raise PermissionDenied

        mt = get_object_or_404(MemberTag, pk=pk, tag__community=community)
        form = RevokeTagForm(request.POST)
        if not form.is_valid():
            return _error(request, "Invalid submission.")

        reason = form.cleaned_data.get("reason", "")

        try:
            mt.revoke(member, reason=reason, request=request)
        except PermissionDenied as e:
            return _error(request, str(e), 403)
        except TransitionConflict as e:
            return _error(request, str(e.message), 409)

        if request.headers.get("HX-Request"):
            return HttpResponse(
                status=200,
                headers={
                    "HX-Trigger": json.dumps(
                        {
                            "showToast": {"message": f'"{mt.tag.label}" revoked.', "type": "success"},
                            "queueItemResolved": {"id": str(pk)},
                        }
                    )
                },
            )
        return redirect("tags:queue", slug=slug)
