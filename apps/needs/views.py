"""Need views: create and detail."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView

from apps.accounts.verification import VerifiedRequiredMixin
from apps.audit.services import emit
from apps.communities.models import Community, Member
from apps.moderation.services import is_blocked_between
from apps.offers.models import Offer
from apps.tags.badges import verified_badges_for

from .forms import NeedForm
from .models import Need


class NeedCreateView(LoginRequiredMixin, VerifiedRequiredMixin, CreateView):
    model = Need
    form_class = NeedForm
    template_name = "needs/create.html"

    def get_community_and_member(self):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"])
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
        messages.success(self.request, "Your need has been posted!")
        return redirect("community-feed", slug=self.community.slug)


class NeedDetailView(LoginRequiredMixin, DetailView):
    model = Need
    template_name = "needs/detail.html"
    context_object_name = "need"

    def get_object(self, queryset=None):
        from django.http import Http404

        obj = super().get_object(queryset)
        viewer = Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).first()
        if viewer is None:
            raise Http404("You are not a member of this community.")
        if obj.moderation_hidden and not viewer.is_coordinator:
            raise Http404("This post is no longer available.")
        if is_blocked_between(viewer, obj.requester):
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
        # §8.2: contact stays locked for ordinary members (revealed only via an
        # accepted match). Coordinators get oversight access here — audited (§8.3).
        contact_info = None
        if member and member.is_coordinator and need.requester != member:
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
        else:
            ctx["suggested_offers"] = Offer.objects.filter(
                community=community,
                category=need.category,
                status="active",
                moderation_hidden=False,
                offerer=member,
            ).select_related("offerer")[:5]
        # Active matches on this need
        ctx["matches"] = need.matches.select_related("offer", "proposed_by").order_by("-proposed_at")
        return ctx


class NeedDeleteView(LoginRequiredMixin, DeleteView):
    model = Need

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
        # self.object is loaded in post() before deletion — emit while its pk still exists.
        emit(
            "need.deleted",
            self.object,
            user=self.request.user,
            request=self.request,
            details={"status": self.object.status},
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("community-feed", kwargs={"slug": self.object.community.slug})

    def get_object(self, queryset=None):
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        obj = super().get_object(queryset)
        member = Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).first()
        if not member:
            raise Http404("You are not a member of this community.")
        if obj.requester != member and member.role not in ["admin", "coordinator"]:
            raise PermissionDenied("You do not have permission to delete this need.")
        return obj
