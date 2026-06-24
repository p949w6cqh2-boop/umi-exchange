from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.communities.models import Community, Member


class HubResolverView(LoginRequiredMixin, View):
    """Bare /hub/ — pick the community to focus, then redirect.

    0 memberships → onboarding (/join/); a valid last-visited slug → there;
    exactly 1 → straight in; otherwise (many, no valid last) → most-recent.
    """

    def get(self, request):
        memberships = Member.objects.filter(user=request.user, is_active=True).select_related("community")
        slugs = {m.community.slug for m in memberships}
        if not slugs:
            return redirect("/join/")
        last = request.session.get("hub:last_slug")
        if last in slugs:
            return redirect("hub:community", slug=last)
        if len(slugs) == 1:
            return redirect("hub:community", slug=next(iter(slugs)))
        most_recent = memberships.order_by("-joined_at").first()
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["member"] = self.member
        return ctx
