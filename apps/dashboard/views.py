"""Coordinator dashboard: metrics, stale needs, category breakdown, CSV export."""
import csv
import json
from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Avg, F
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.communities.models import Community, Member
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.matches.models import Match


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def dispatch(self, request, *args, **kwargs):
        self.community = get_object_or_404(Community, slug=kwargs["slug"])
        self.member = Member.objects.filter(
            user=request.user, community=self.community, is_active=True,
            role__in=["coordinator", "admin"],
        ).first()
        if not self.member:
            return HttpResponseForbidden("Coordinator access required.")
        return super().dispatch(request, *args, **kwargs)

    def get_period_start(self):
        period = self.request.GET.get("period", "month")
        now = timezone.now()
        deltas = {"week": 7, "month": 30, "quarter": 90, "year": 365}
        return now - timedelta(days=deltas.get(period, 30))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        c = self.community
        period_start = self.get_period_start()

        ctx["community"] = c
        ctx["member"] = self.member
        ctx["active_needs"] = Need.objects.filter(community=c, status="open").count()
        ctx["active_offers"] = Offer.objects.filter(community=c, status="active").count()
        ctx["pending_matches"] = Match.objects.filter(need__community=c, status="proposed").count()
        ctx["fulfilled"] = Match.objects.filter(
            need__community=c, status="fulfilled", fulfilled_at__gte=period_start,
        ).count()

        # Average time to match (hours)
        avg = Match.objects.filter(
            need__community=c, status__in=["accepted", "fulfilled"],
            accepted_at__isnull=False, accepted_at__gte=period_start,
        ).aggregate(avg_hours=Avg(F("accepted_at") - F("proposed_at")))
        avg_td = avg["avg_hours"]
        ctx["avg_time_to_match"] = round(avg_td.total_seconds() / 3600, 1) if avg_td else 0

        # Stale needs: open 7+ days, no matches
        ctx["stale_needs"] = Need.objects.filter(
            community=c, status="open",
            created_at__lt=timezone.now() - timedelta(days=7),
        ).annotate(match_count=Count("matches")).filter(match_count=0).order_by("created_at")[:20]

        # Category breakdown
        cats = Need.objects.filter(community=c, created_at__gte=period_start).values(
            "category__name"
        ).annotate(total=Count("id")).order_by("-total")
        ctx["category_data"] = json.dumps(list(cats))

        # Household count (for billing display)
        from apps.households.models import Household
        hh_count = Member.objects.filter(
            community=c, is_active=True, household__isnull=False,
        ).values("household").distinct().count()
        solo = Member.objects.filter(community=c, is_active=True, household__isnull=True).count()
        ctx["household_count"] = hh_count + solo
        ctx["member_count"] = Member.objects.filter(community=c, is_active=True).count()

        # Pack metrics for template iteration
        ctx["metrics"] = [
            ("Active Needs", ctx["active_needs"]),
            ("Active Offers", ctx["active_offers"]),
            ("Pending Matches", ctx["pending_matches"]),
            ("Fulfilled", ctx["fulfilled"]),
            ("Avg Time-to-Match (hrs)", ctx["avg_time_to_match"]),
        ]

        return ctx


class DashboardCSVExportView(LoginRequiredMixin, View):
    """
    Export community data as CSV. Coordinator access only.
    Privacy: no PII (emails, phone numbers) is exported — only display names,
    titles, categories, statuses, and timestamps.
    """

    def get(self, request, slug):
        community = get_object_or_404(Community, slug=slug)
        member = Member.objects.filter(
            user=request.user, community=community, is_active=True,
            role__in=["coordinator", "admin"],
        ).first()
        if not member:
            return HttpResponseForbidden("Coordinator access required.")

        export_type = request.GET.get("type", "needs")
        filename = f"umi-{community.slug}-{export_type}-{timezone.now().strftime('%Y%m%d')}.csv"

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)

        if export_type == "needs":
            writer.writerow(["Title", "Category", "Urgency", "Status", "Requester", "Neighborhood", "Created", "Expires"])
            for need in Need.objects.filter(community=community).select_related("category", "requester").order_by("-created_at"):
                writer.writerow([
                    need.title, need.category.name, need.urgency, need.status,
                    need.requester.display_name, need.neighborhood,
                    need.created_at.isoformat(), need.expires_at.isoformat(),
                ])

        elif export_type == "offers":
            writer.writerow(["Title", "Category", "Status", "Offerer", "Created", "Expires"])
            for offer in Offer.objects.filter(community=community).select_related("category", "offerer").order_by("-created_at"):
                writer.writerow([
                    offer.title, offer.category.name, offer.status,
                    offer.offerer.display_name,
                    offer.created_at.isoformat(), offer.expires_at.isoformat(),
                ])

        elif export_type == "matches":
            writer.writerow(["Need", "Offer", "Status", "Proposed By", "Proposed At", "Accepted At", "Fulfilled At"])
            for match in Match.objects.filter(need__community=community).select_related("need", "offer", "proposed_by").order_by("-proposed_at"):
                writer.writerow([
                    match.need.title,
                    match.offer.title if match.offer else "",
                    match.status, match.proposed_by.display_name,
                    match.proposed_at.isoformat(),
                    match.accepted_at.isoformat() if match.accepted_at else "",
                    match.fulfilled_at.isoformat() if match.fulfilled_at else "",
                ])

        else:
            return HttpResponse("Invalid export type. Use: needs, offers, or matches.", status=400)

        return response
