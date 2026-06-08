"""Need views: create and detail."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView

from apps.communities.models import Community, Member
from apps.offers.models import Offer

from .forms import NeedForm
from .models import Need


class NeedCreateView(LoginRequiredMixin, CreateView):
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
        messages.success(self.request, "Your need has been posted!")
        return redirect("community-feed", slug=self.community.slug)


class NeedDetailView(LoginRequiredMixin, DetailView):
    model = Need
    template_name = "needs/detail.html"
    context_object_name = "need"

    def get_object(self, queryset=None):
        from django.http import Http404

        obj = super().get_object(queryset)
        if not Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).exists():
            raise Http404("You are not a member of this community.")
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        need = self.object
        community = need.community
        member = Member.objects.filter(user=self.request.user, community=community, is_active=True).first()
        ctx["community"] = community
        ctx["member"] = member
        ctx["is_own_need"] = member and need.requester == member
        # Suggested offers: same category, active
        if ctx["is_own_need"]:
            ctx["suggested_offers"] = (
                Offer.objects.filter(community=community, category=need.category, status="active")
                .exclude(offerer=member)
                .select_related("offerer")[:5]
            )
        else:
            ctx["suggested_offers"] = Offer.objects.filter(
                community=community, category=need.category, status="active", offerer=member
            ).select_related("offerer")[:5]
        # Active matches on this need
        ctx["matches"] = need.matches.select_related("offer", "proposed_by").order_by("-proposed_at")
        return ctx


class NeedDeleteView(LoginRequiredMixin, DeleteView):
    model = Need

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
