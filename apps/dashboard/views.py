"""Coordinator dashboard: metrics, stale needs, category breakdown, CSV export."""

import csv
import json
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Avg, Count, F, Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import TemplateView

from apps.communities.models import Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer

# Characters that make Excel/Sheets/LibreOffice treat a cell as a formula.
_CSV_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Neutralize spreadsheet (CSV) formula injection: prefix a leading
    apostrophe when a cell would otherwise start with a formula-trigger char, so
    a member-controlled value like ``=HYPERLINK(...)`` can't execute when a
    coordinator opens the export. Reversible — a legitimate value starting with
    ``-``/``=`` is preserved, just apostrophe-led. Machine-generated cells
    (UUIDs, status enums, ISO timestamps) never start with a trigger char, so
    they don't need wrapping."""
    s = "" if value is None else str(value)
    return "'" + s if s and s[0] in _CSV_FORMULA_TRIGGERS else s


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def dispatch(self, request, *args, **kwargs):
        # Anonymous first, BEFORE the community lookup and the Member filter:
        # AnonymousUser in a UUID FK filter raises ValidationError (a 500), and a
        # 500-on-real-slug vs 404-on-missing-slug split is a community-existence
        # oracle for signed-out probes. Same guard as every sibling gated view.
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.community = get_object_or_404(Community, slug=kwargs["slug"])
        self.member = Member.objects.filter(
            user=request.user,
            community=self.community,
            is_active=True,
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
            need__community=c,
            status="fulfilled",
            fulfilled_at__gte=period_start,
        ).count()

        # Average time to match (hours)
        avg = Match.objects.filter(
            need__community=c,
            status__in=["accepted", "fulfilled"],
            accepted_at__isnull=False,
            accepted_at__gte=period_start,
        ).aggregate(avg_hours=Avg(F("accepted_at") - F("proposed_at")))
        avg_td = avg["avg_hours"]
        ctx["avg_time_to_match"] = round(avg_td.total_seconds() / 3600, 1) if avg_td else 0

        # Stale needs: open 7+ days, no LIVE match. The status predicate matters:
        # cancelled/expired/unfulfilled Match rows survive forever (transition_to
        # reopens the need but never deletes the dead row), so a bare Count hid
        # exactly the ask this list exists to catch — one a helper tried and
        # withdrew from.
        ctx["stale_needs"] = (
            Need.objects.filter(
                community=c,
                status="open",
                created_at__lt=timezone.now() - timedelta(days=7),
            )
            .annotate(live_matches=Count("matches", filter=Q(matches__status__in=("proposed", "accepted"))))
            .filter(live_matches=0)
            .order_by("created_at")[:20]
        )

        # Category breakdown
        cats = (
            Need.objects.filter(community=c, created_at__gte=period_start)
            .values("category__name")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        ctx["category_data"] = json.dumps(list(cats))

        # Household count (for billing display)
        hh_count = (
            Member.objects.filter(
                community=c,
                is_active=True,
                household__isnull=False,
            )
            .values("household")
            .distinct()
            .count()
        )
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


class DashboardExportView(LoginRequiredMixin, TemplateView):
    """Export community data as CSV. Coordinator/admin only."""

    def dispatch(self, request, *args, **kwargs):
        # Anonymous first — same reasoning and same order as DashboardView above.
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.community = get_object_or_404(Community, slug=kwargs["slug"])
        self.member = Member.objects.filter(
            user=request.user,
            community=self.community,
            is_active=True,
            role__in=["coordinator", "admin"],
        ).first()
        if not self.member:
            return HttpResponseForbidden("Coordinator access required.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        export_type = request.GET.get("type", "needs")
        c = self.community

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{c.slug}-{export_type}.csv"'
        writer = csv.writer(response)

        if export_type == "matches":
            # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection
            writer.writerow(["Match ID", "Need", "Status", "Proposed By", "Proposed At", "Accepted At", "Fulfilled At"])
            matches = (
                Match.objects.filter(need__community=c).select_related("need", "proposed_by").order_by("-proposed_at")
            )
            for m in matches:
                # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection
                writer.writerow(
                    [
                        str(m.id),
                        _csv_safe(m.need.title),
                        m.status,
                        _csv_safe(m.proposed_by.display_name),
                        m.proposed_at.isoformat(),
                        m.accepted_at.isoformat() if m.accepted_at else "",
                        m.fulfilled_at.isoformat() if m.fulfilled_at else "",
                    ]
                )
        else:
            # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection
            writer.writerow(
                [
                    "Need ID",
                    "Title",
                    "Category",
                    "Urgency",
                    "Status",
                    "Requester",
                    "Neighborhood",
                    "Created",
                    "Expires",
                ]
            )
            for n in Need.objects.filter(community=c).select_related("category", "requester").order_by("-created_at"):
                # nosemgrep: python.django.security.injection.csv-writer-injection.csv-writer-injection
                writer.writerow(
                    [
                        str(n.id),
                        _csv_safe(n.title),
                        _csv_safe(n.category.name),
                        n.urgency,
                        n.status,
                        _csv_safe(n.requester.display_name),
                        _csv_safe(n.neighborhood),
                        n.created_at.isoformat(),
                        n.expires_at.isoformat(),
                    ]
                )

        return response
