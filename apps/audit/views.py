"""The coordinator activity page (docs/specs/coordinator-activity.md, C13)."""

from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView

from apps.communities.models import Community, Member

from .coordinator_activity import describe, events

PAGE_SIZE = 50


class CoordinatorActivityView(LoginRequiredMixin, TemplateView):
    """Which coordinator did what in this community. Coordinators and admins of THIS community
    only, the same gate as the dashboard."""

    template_name = "audit/activity.html"

    def dispatch(self, request, *args, **kwargs):
        # Anonymous first, before any lookup (same reason as DashboardView: no existence oracle).
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.community = get_object_or_404(Community, slug=kwargs["slug"])
        self.member = Member.objects.filter(
            user=request.user, community=self.community, is_active=True, role__in=["coordinator", "admin"]
        ).first()
        if not self.member:
            return HttpResponseForbidden("Coordinator access required.")
        return super().dispatch(request, *args, **kwargs)

    def _since(self):
        raw = self.request.GET.get("since", "")
        try:
            day = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None, ""
        return timezone.make_aware(day), raw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = events(self.community)
        since, since_raw = self._since()
        if since:
            rows = rows.filter(timestamp__gte=since)
        page = Paginator(rows, PAGE_SIZE).get_page(self.request.GET.get("page"))
        ctx.update(
            {
                "community": self.community,
                "member": self.member,
                "page_obj": page,
                "events": describe(page.object_list, self.community),
                "since": since_raw,
            }
        )
        return ctx
