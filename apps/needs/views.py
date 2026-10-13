"""Need views: create and detail."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView

from apps.accounts.verification import VerifiedRequiredMixin
from apps.audit.services import emit
from apps.communities.models import Community, Member
from apps.moderation.services import flag_listed_words, is_blocked_between, review_note
from apps.offers.models import Offer
from apps.tags.badges import verified_badges_for

from .forms import NeedForm
from .models import Need


class NeedCreateView(LoginRequiredMixin, VerifiedRequiredMixin, CreateView):
    model = Need
    form_class = NeedForm
    template_name = "needs/create.html"

    def get_community_and_member(self):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=self.request.user, community=self.community, is_active=True)

    def get_form_kwargs(self):
        self.get_community_and_member()
        kwargs = super().get_form_kwargs()
        kwargs["community"] = self.community
        kwargs["member"] = self.member
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["member"] = self.member
        ctx["categories"] = self.community.categories.filter(is_active=True)
        return ctx

    def form_valid(self, form):
        super().form_valid(form)
        emit(
            "need.created",
            self.object,
            user=self.request.user,
            request=self.request,
            details={"urgency": self.object.urgency},
        )
        if flag_listed_words(
            self.object, "need", self.object.title, self.object.description, author=self.member, request=self.request
        ):
            messages.info(self.request, "Your ask is on the board. " + review_note("It"))
        else:
            messages.success(self.request, "Your need has been posted!")
        return redirect("community-feed", slug=self.community.slug)


class NeedDetailView(LoginRequiredMixin, DetailView):
    model = Need
    template_name = "needs/detail.html"
    context_object_name = "need"

    def get_object(self, queryset=None):
        from django.http import Http404

        obj = super().get_object(queryset)
        if not obj.community.is_active:
            raise Http404("This community is closed.")  # switched off in admin (2026-10 bug hunt, L7)
        viewer = Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).first()
        if viewer is None:
            raise Http404("You are not a member of this community.")
        if obj.moderation_hidden and not viewer.is_coordinator:
            raise Http404("This post is no longer available.")
        # Coordinators keep oversight through a block, as through a hidden post (the
        # founder's call, 2026-10-13, bug hunt L1). The pair is still never matched.
        if not viewer.is_coordinator and is_blocked_between(viewer, obj.requester):
            raise Http404("This post is no longer available.")
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        need = self.object
        community = need.community
        member = Member.objects.filter(user=self.request.user, community=community, is_active=True).first()
        ctx["community"] = community
        ctx["member"] = member
        ctx["poster_badges"] = verified_badges_for([need.requester_id], member).get(need.requester_id, [])
        ctx["is_own_need"] = member and need.requester == member
        # Only a coordinator reaches a blocked-with neighbour's page (L1, above). They see the post,
        # but get no contact reveal and no offer buttons: the pair is never matched, and a block
        # must not hand its blocked person a way to reach the one who blocked them. Another
        # coordinator still has both.
        blocked_with_poster = bool(member) and need.requester != member and is_blocked_between(member, need.requester)
        ctx["blocked_with_poster"] = blocked_with_poster
        # §8.2: contact stays locked for ordinary members (revealed only via an
        # accepted match). Coordinators get oversight access here — audited (§8.3).
        contact_info = None
        if (
            member
            and member.is_coordinator
            and need.requester != member
            and need.requester.is_active
            and not blocked_with_poster
        ):
            contact_info = need.requester.contact_dict(need.contact_pref)
            emit(
                "need.contact_disclosed",
                need,
                user=self.request.user,
                request=self.request,
                details={"viewer_role": member.role},
            )
        ctx["contact_info"] = contact_info
        ctx["show_contact"] = contact_info is not None
        # Federation (§2.3/§4.1): the owner's share-beyond-this-community
        # panel — None (hidden) unless flag on + owner + an active link.
        from apps.federation.sharing import share_panel

        ctx["share_panel"] = share_panel(need, member)
        # Suggested offers: same category, active. The own-need branch lists other
        # members' offers, so it carries the same two filters as the feed and the
        # hub — a coordinator-hidden offer, or one from a blocked neighbour, must
        # not be re-listed here. The else branch is self-scoped (offerer=member) so
        # it needs no block filter, but it does filter hidden: propose already 404s
        # on hidden content (apps/matches/views.py:58), so listing your own hidden
        # offer is a dead button, and its own detail page 404s you out anyway
        # (apps/offers/views.py:62). Keyed by Jasiah 2026-07-25.
        from apps.moderation.services import blocked_member_ids

        if ctx["is_own_need"]:
            ctx["suggested_offers"] = (
                Offer.objects.filter(
                    community=community, category=need.category, status="active", moderation_hidden=False
                )
                .exclude(offerer=member)
                .exclude(offerer_id__in=blocked_member_ids(member))
                .select_related("offerer")[:5]
            )
        elif blocked_with_poster:
            ctx["suggested_offers"] = Offer.objects.none()
        else:
            ctx["suggested_offers"] = Offer.objects.filter(
                community=community,
                category=need.category,
                status="active",
                moderation_hidden=False,
                offerer=member,
            ).select_related("offerer")[:5]
        # Active matches on this need
        matches = need.matches.select_related("offer", "proposed_by", "federated").order_by("-proposed_at")
        if member and need.requester != member and not member.is_coordinator:
            # On someone else's need, a neighbour this member blocked (or who blocked them) is not
            # listed, as on the board. The asker keeps every match on their own need: a block is
            # preventative, not a recall; coordinators keep oversight (2026-10 bug hunt).
            from apps.moderation.services import blocked_member_ids

            blocked = blocked_member_ids(member)
            matches = matches.exclude(proposed_by_id__in=blocked).exclude(offer__offerer_id__in=blocked)
        ctx["matches"] = matches
        return ctx


class NeedDeleteView(LoginRequiredMixin, DeleteView):
    model = Need

    def get(self, request, *args, **kwargs):
        # Deleting is a POST from the post's own page; there is no confirmation page. A GET (a
        # sign-in that returns here with next=) was a 500 on the missing template (2026-10 bug
        # hunt, L5): go back to the post instead.
        return redirect("need-detail", slug=kwargs["slug"], pk=kwargs["pk"])

    def form_valid(self, form):
        # Block deletion while a Match is live (proposed/accepted): the cascade
        # would destroy the Match and strand the counterpart Offer in "matched"
        # forever, with no reset path and no notification. Cancel the match first.
        if self.object.matches.filter(status__in=("proposed", "accepted")).exists():
            return HttpResponse(
                "This need has an active match. Cancel the match before deleting it.",
                status=409,
                content_type="text/plain",
            )
        # A need under an active legal hold is evidence: nothing deletes it (docs/specs/legal-hold.md).
        from apps.holds.services import need_is_held

        if need_is_held(self.object):
            return HttpResponse(
                "This need is under a legal hold and can't be deleted.",
                status=409,
                content_type="text/plain",
            )
        # The audit row and the delete go together or not at all: the audit table is append-only,
        # so a delete that then failed left a need.deleted row that could never be taken back.
        try:
            with transaction.atomic():
                # self.object is loaded in post() before deletion — emit while its pk still exists.
                emit(
                    "need.deleted",
                    self.object,
                    user=self.request.user,
                    request=self.request,
                    details={"status": self.object.status},
                )
                return super().form_valid(form)
        except ProtectedError:
            # A record must outlive the post (a released legal hold still points at it). Keep it
            # and take it off the board instead of failing with a 500 (2026-10 bug hunt).
            Need.objects.filter(pk=self.object.pk).update(status="closed", updated_at=timezone.now())
            emit(
                "need.closed",
                self.object,
                user=self.request.user,
                request=self.request,
                details={"status": self.object.status, "kept": True},
            )
            messages.info(self.request, "This need was closed and taken off the board.")
            return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse_lazy("community-feed", kwargs={"slug": self.object.community.slug})

    def get_object(self, queryset=None):
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        obj = super().get_object(queryset)
        if not obj.community.is_active:
            raise Http404("This community is closed.")  # switched off in admin (2026-10 bug hunt, L7)
        member = Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).first()
        if not member:
            raise Http404("You are not a member of this community.")
        if obj.requester != member and member.role not in ["admin", "coordinator"]:
            raise PermissionDenied("You do not have permission to delete this need.")
        return obj
