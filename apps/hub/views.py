from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.communities.models import Community, Member
from apps.hub import selectors


class HubResolverView(LoginRequiredMixin, View):
    """Bare /hub/ — pick the community to focus, then redirect.

    0 memberships → onboarding (/join/); a valid last-visited slug → there;
    exactly 1 → straight in; otherwise (many, no valid last) → most-recent.
    """

    def get(self, request):
        memberships = Member.objects.filter(
            user=request.user, is_active=True, community__is_active=True
        ).select_related("community")
        slugs = {m.community.slug for m in memberships}
        if not slugs:
            return redirect("/join/")
        last = request.session.get("hub:last_slug")
        if last in slugs:
            return redirect("hub:community", slug=last)
        if len(slugs) == 1:
            return redirect("hub:community", slug=next(iter(slugs)))
        most_recent = max(memberships, key=lambda m: m.joined_at)
        return redirect("hub:community", slug=most_recent.community.slug)


class HubView(LoginRequiredMixin, TemplateView):
    template_name = "hub/index.html"

    def dispatch(self, request, *args, **kwargs):
        # LoginRequiredMixin redirects anonymous users before we touch the DB.
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=request.user, community=self.community, is_active=True)
        request.session["hub:last_slug"] = self.community.slug
        return super().dispatch(request, *args, **kwargs)

    def get_template_names(self):
        if self.request.htmx:
            return ["hub/_hub_body.html"]
        return ["hub/index.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["member"] = self.member
        ctx["communities"] = selectors.member_communities(self.request.user)
        ctx["open_matches"] = selectors.open_matches_for(self.member)
        ctx["notifications"] = selectors.recent_notifications(self.request.user)
        ctx["member_tags"] = selectors.own_tags(self.member)
        # The Pulse (hub v2): witnessed generosity + immediate agency.
        ctx["pulse"] = selectors.pulse_events(self.community)
        ctx["spotlight"] = selectors.spotlight_need(self.member)
        ctx["cycle"] = 0
        ctx["season_impact"] = selectors.season_impact(self.member)
        ctx["week_stats"] = selectors.week_stats(self.community)
        return ctx


class HubPartialView(LoginRequiredMixin, TemplateView):
    """Base for the hub's live HTMX partials: member-gated, community-scoped."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=request.user, community=self.community, is_active=True)
        return super().dispatch(request, *args, **kwargs)


class HubPulseView(HubPartialView):
    """The living stream — polled by the hub every minute."""

    template_name = "hub/_pulse.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["pulse"] = selectors.pulse_events(self.community)
        return ctx


class HubSpotlightView(HubPartialView):
    """One ask, right now — 'show me another' cycles the queue."""

    template_name = "hub/_spotlight.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            cycle = max(0, int(self.request.GET.get("cycle", 0)))
        except (TypeError, ValueError):
            cycle = 0
        ctx["community"] = self.community
        ctx["spotlight"] = selectors.spotlight_need(self.member, cycle=cycle)
        ctx["cycle"] = cycle
        return ctx
