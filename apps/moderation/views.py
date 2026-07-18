"""Flag creation (any member) + the coordinators' moderation queue.

Mirrors the tags verification queue's community gating; every action is
audited (§8.3) with PII-free details. Hiding is reversible: a boolean the
coordinator can flip back, never a delete (keyring: archive over delete).
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView

from apps.accounts.ratelimit import rate_limit
from apps.audit.services import emit
from apps.communities.models import Community, Member
from apps.needs.models import Need
from apps.notifications.adapter import NotificationAdapter
from apps.offers.models import Offer
from apps.pages.models import CommunityPage

from .forms import FlagForm
from .models import Block, Flag
from .services import reinstate_member, remove_member

TARGET_MODELS = {"need": Need, "offer": Offer, "member": Member, "page": CommunityPage}


def _resolve_target(community, target_type, target_id):
    """The flagged thing, scoped HARD to this community (IDOR guard)."""
    model = TARGET_MODELS[target_type]
    if target_type == "member":
        return get_object_or_404(model, pk=target_id, community=community, is_active=True)
    if target_type == "page":
        # The queue row names the author (conflict-of-interest line) — fetch it with the page.
        return get_object_or_404(model.objects.select_related("created_by"), pk=target_id, community=community)
    return get_object_or_404(model, pk=target_id, community=community)


def _target_url(community, target_type, target):
    if target_type == "need":
        return f"/c/{community.slug}/needs/{target.pk}/"
    if target_type == "offer":
        return f"/c/{community.slug}/offers/{target.pk}/"
    if target_type == "page":
        return reverse("pages:view", kwargs={"slug": community.slug, "page_slug": target.slug})
    return f"/c/{community.slug}/"


@method_decorator(rate_limit("flag", 10, 3600, by="user"), name="post")
class FlagCreateView(LoginRequiredMixin, View):
    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug, is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        target_type = request.POST.get("target_type", "")
        if target_type not in TARGET_MODELS:
            messages.error(request, "That can't be reported.")
            return redirect("community-feed", slug=community.slug)
        target = _resolve_target(community, target_type, request.POST.get("target_id"))

        form = FlagForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Pick a reason and try again.")
            return redirect(_target_url(community, target_type, target))

        try:
            # Inner atomic block: the duplicate-INSERT rollback stays contained
            # instead of poisoning the surrounding transaction.
            with transaction.atomic():
                flag = Flag.objects.create(
                    community=community,
                    reporter=member,
                    target_type=target_type,
                    target_id=target.pk,
                    reason=form.cleaned_data["reason"],
                    detail=form.cleaned_data["detail"],
                )
        except IntegrityError:
            messages.info(request, "You've already reported this — a coordinator will review it.")
            return redirect(_target_url(community, target_type, target))

        emit("flag.created", flag, user=request.user, request=request, details={"target_type": target_type})
        for coordinator in Member.objects.filter(
            community=community, is_active=True, role__in=("coordinator", "admin")
        ).select_related("user"):
            NotificationAdapter.send(
                coordinator.user,
                "flag_received",
                "A neighbour raised a concern",
                "Something on the board was flagged for review.",
                link=f"/c/{community.slug}/moderation/",
            )
        messages.success(request, "Thank you — a coordinator will take a look.")
        return redirect(_target_url(community, target_type, target))


class ModerationQueueView(LoginRequiredMixin, ListView):
    template_name = "moderation/queue.html"
    context_object_name = "flags"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        if not member.is_coordinator:
            raise PermissionDenied("Only coordinators and admins can review reports.")
        self._community = community
        self._member = member
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Flag.objects.filter(community=self._community, status="open").select_related("reporter")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        for flag in ctx["flags"]:
            try:
                target = _resolve_target(self._community, flag.target_type, flag.target_id)
            except Http404:
                target = None  # target gone (e.g. member already deactivated) — dismissable
            rows.append({"flag": flag, "target": target})
        recent = (
            Flag.objects.filter(community=self._community)
            .exclude(status="open")
            .select_related("reporter", "resolved_by")
            .order_by("-resolved_at")[:10]
        )
        removed_members = (
            Member.objects.filter(community=self._community, removed_at__isnull=False)
            .select_related("removed_by")
            .order_by("-removed_at")
        )
        ctx.update(
            {
                "community": self._community,
                "member": self._member,
                "rows": rows,
                "recent": recent,
                "removed_members": removed_members,
            }
        )
        return ctx


class FlagResolveView(LoginRequiredMixin, View):
    """POST action — hide: content down + resolve; keep: resolve, content
    stays; dismiss: closed, no action. All audited; the reporter is told it
    was reviewed, never the outcome details."""

    def post(self, request, slug, pk):
        community = get_object_or_404(Community, slug=slug, is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        if not member.is_coordinator:
            raise PermissionDenied("Only coordinators and admins can act on reports.")
        action = request.POST.get("action", "")
        if action not in ("hide", "keep", "dismiss"):
            messages.error(request, "Unknown action.")
            return redirect("moderation:queue", slug=community.slug)

        with transaction.atomic():
            flag = get_object_or_404(Flag.objects.select_for_update(), pk=pk, community=community, status="open")
            if action == "hide":
                target = _resolve_target(community, flag.target_type, flag.target_id)
                if flag.target_type == "member":
                    if target.is_coordinator:
                        raise PermissionDenied("Coordinators can't be hidden from the queue — handle directly.")
                    # Durable, complete removal: deactivate, stamp who/when, take
                    # their content off the board, cancel in-flight matches, and
                    # refuse a silent rejoin. Audits "member.removed" itself.
                    remove_member(target, by=member, request=request)
                else:
                    target.moderation_hidden = True
                    target.save(update_fields=["moderation_hidden"])
                    emit(
                        "content.hidden",
                        target,
                        user=request.user,
                        request=request,
                        details={"target_type": flag.target_type},
                    )
            flag.status = "dismissed" if action == "dismiss" else "resolved"
            flag.resolution = action
            flag.resolved_by = member
            flag.resolved_at = timezone.now()
            flag.save(update_fields=["status", "resolution", "resolved_by", "resolved_at"])

        emit(f"flag.{flag.status}", flag, user=request.user, request=request, details={"action": action})
        NotificationAdapter.send(
            flag.reporter.user,
            "flag_reviewed",
            "Your report was reviewed",
            "A coordinator looked into the concern you raised. Thank you for speaking up.",
            link="",
        )
        messages.success(request, "Handled — thank you.")
        return redirect("moderation:queue", slug=community.slug)


def _safe_redirect(request, community):
    """Back to where they were if it's a safe local URL, else the feed."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(nxt)
    return redirect("community-feed", slug=community.slug)


@method_decorator(rate_limit("block", 20, 3600, by="user"), name="post")
class BlockCreateView(LoginRequiredMixin, View):
    """A neighbour blocks another: preventative and quiet. No future matches
    between them, hidden from each other's board. The blocked person is not
    notified, and contact already revealed by a past match is not recalled."""

    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug, is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        target = get_object_or_404(Member, pk=request.POST.get("blocked_id"), community=community)
        if target.id == member.id:
            messages.error(request, "You can't block yourself.")
            return _safe_redirect(request, community)
        Block.objects.get_or_create(
            community=community,
            blocker=member,
            blocked=target,
            defaults={"reason": (request.POST.get("reason", "") or "")[:500]},
        )
        # Audited; the blocked person is deliberately not notified.
        emit("member.blocked", target, user=request.user, request=request, details={})
        messages.success(
            request,
            "Done. You won't be matched with this neighbour again, and you won't see each "
            "other on the board. They aren't told.",
        )
        return _safe_redirect(request, community)


class BlockDeleteView(LoginRequiredMixin, View):
    """Undo a block."""

    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug, is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        target = get_object_or_404(Member, pk=request.POST.get("blocked_id"), community=community)
        deleted, _ = Block.objects.filter(community=community, blocker=member, blocked=target).delete()
        if deleted:
            emit("member.unblocked", target, user=request.user, request=request, details={})
            messages.success(request, "Unblocked. You can be matched and see each other again.")
        return _safe_redirect(request, community)


class BlockListView(LoginRequiredMixin, ListView):
    """A member's own 'neighbours you've blocked' list, with unblock controls."""

    template_name = "moderation/blocks.html"
    context_object_name = "blocks"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self._community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self._member = get_object_or_404(Member, user=request.user, community=self._community, is_active=True)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Block.objects.filter(blocker=self._member).select_related("blocked")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self._community
        ctx["member"] = self._member
        return ctx


class ReinstateMemberView(LoginRequiredMixin, View):
    """Coordinator action: undo a removal, bringing the member and their content
    back on the board. The reverse of the queue's hide-a-member action."""

    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug, is_active=True)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        if not member.is_coordinator:
            raise PermissionDenied("Only coordinators and admins can reinstate a member.")
        target = get_object_or_404(
            Member, pk=request.POST.get("member_id"), community=community, removed_at__isnull=False
        )
        reinstate_member(target, by=member, request=request)
        messages.success(request, "Reinstated — they're back on the board.")
        return redirect("moderation:queue", slug=community.slug)
