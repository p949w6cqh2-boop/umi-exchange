"""Community views: landing, join, feed, settings, QR code."""

import io
import re

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, FormView, ListView, TemplateView

from apps.audit.services import emit
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.tags.badges import verified_badges_for

from .forms import CommunityCreateForm, CommunitySettingsForm, JoinForm
from .models import Community, Member, generate_join_code
from .themes import THEME_DEFAULT, THEMES


class LandingView(TemplateView):
    template_name = "pages/landing.html"


class JoinCommunityView(LoginRequiredMixin, FormView):
    template_name = "communities/join.html"
    form_class = JoinForm

    def get_initial(self):
        initial = super().get_initial()
        code_from_url = self.request.GET.get("code", "")
        if code_from_url:
            initial["join_code"] = code_from_url.upper()
        return initial

    def form_valid(self, form):
        code = form.cleaned_data["join_code"].upper().strip()
        try:
            community = Community.objects.get(join_code=code, is_active=True)
        except Community.DoesNotExist:
            form.add_error("join_code", "This code does not match any community. Please check and try again.")
            return self.form_invalid(form)

        if Member.objects.filter(user=self.request.user, community=community).exists():
            messages.info(self.request, "You are already a member of this community.")
            return redirect("community-feed", slug=community.slug)

        display_name = form.cleaned_data.get("display_name") or self.request.user.username
        member = Member.objects.create(
            user=self.request.user, community=community, display_name=display_name, role="member"
        )
        emit("member.joined", member, user=self.request.user, request=self.request, details={"role": member.role})
        messages.success(self.request, f"Welcome to {community.name}!")
        return redirect("community-feed", slug=community.slug)


class CommunityCreateView(LoginRequiredMixin, CreateView):
    model = Community
    form_class = CommunityCreateForm
    template_name = "communities/create.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        emit(
            "community.created",
            self.object,
            user=self.request.user,
            request=self.request,
            details={"visibility": self.object.visibility},
        )
        # Creator becomes admin
        creator = Member.objects.create(
            user=self.request.user,
            community=self.object,
            display_name=self.request.user.username,
            role="admin",
        )
        emit("member.joined", creator, user=self.request.user, request=self.request, details={"role": creator.role})
        messages.success(self.request, f"Community '{self.object.name}' created!")
        return response


class FeedView(LoginRequiredMixin, ListView):
    """Community feed: merged needs + offers, filterable, with HTMX infinite scroll."""

    template_name = "communities/feed.html"
    context_object_name = "items"
    paginate_by = 20
    # Cap rows pulled per type so the feed can't load an entire community's
    # open needs+offers into memory just to sort and paginate. The DB applies
    # the LIMIT (newest-first); we merge the two capped sets. Matches the
    # bounded-list pattern used by the casework list view.
    feed_per_type_cap = 500

    def get_queryset(self):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=self.request.user, community=self.community, is_active=True)

        needs = Need.objects.filter(community=self.community, status="open").select_related("category", "requester")
        offers = Offer.objects.filter(community=self.community, status="active").select_related("category", "offerer")

        cat = self.request.GET.get("category")
        urg = self.request.GET.get("urgency")
        q = self.request.GET.get("q")
        if cat:
            needs = needs.filter(category_id=cat)
            offers = offers.filter(category_id=cat)
        if urg:
            needs = needs.filter(urgency=urg)
        if q:
            from apps.needs.search import apply_search

            needs = apply_search(needs, q)
            offers = apply_search(offers, q)

        # Tag items with their type for template rendering. Order + slice at
        # the DB layer (LIMIT) so memory stays bounded regardless of community size.
        cap = self.feed_per_type_cap
        need_list = list(needs.order_by("-created_at")[:cap])
        offer_list = list(offers.order_by("-created_at")[:cap])
        for n in need_list:
            n.item_type = "need"
        for o in offer_list:
            o.item_type = "offer"

        combined = sorted(need_list + offer_list, key=lambda x: x.created_at, reverse=True)
        return combined

    def get_template_names(self):
        if self.request.htmx:
            return ["communities/_feed_results.html"]
        return ["communities/feed.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["member"] = self.member
        ctx["categories"] = self.community.categories.filter(is_active=True)
        self._attach_poster_badges(ctx.get("items", []))
        return ctx

    def _attach_poster_badges(self, items):
        """Attach each item's poster's verified, viewer-visible tag badges for
        read-only display on feed cards — one batched query for the whole page."""

        def poster_id(it):
            return it.requester_id if it.item_type == "need" else it.offerer_id

        badges = verified_badges_for({poster_id(it) for it in items}, self.member)
        for it in items:
            it.poster_badges = badges.get(poster_id(it), [])


class CommunitySettingsView(LoginRequiredMixin, TemplateView):
    template_name = "communities/settings.html"

    def dispatch(self, request, *args, **kwargs):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"])
        self.member = Member.objects.filter(
            user=request.user,
            community=self.community,
            is_active=True,
            role__in=["admin", "coordinator"],
        ).first()
        if not self.member:
            messages.error(request, "You need coordinator or admin access for settings.")
            return redirect("community-feed", slug=self.community.slug)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["members"] = self.community.members.filter(is_active=True).select_related("user")
        ctx["categories"] = self.community.categories.all()
        ctx["themes"] = THEMES
        ctx["current_theme"] = (self.community.settings or {}).get("theme", THEME_DEFAULT)
        ctx["theme_custom"] = (self.community.settings or {}).get("theme_custom", {})
        if "form" not in ctx:
            ctx["form"] = CommunitySettingsForm(instance=self.community)
        return ctx

    def post(self, request, slug):
        action = request.POST.get("action")
        if action == "regenerate_join_code":
            new_code = generate_join_code()
            self.community.join_code = new_code
            self.community.save(update_fields=["join_code"])
            messages.success(request, f"Join code regenerated: {new_code}")
            return redirect("community-settings", slug=self.community.slug)

        if action == "set_theme":
            settings = dict(self.community.settings or {})
            key = request.POST.get("theme", THEME_DEFAULT)
            settings["theme"] = key if key in THEMES else THEME_DEFAULT
            # Optional custom overrides — only accept valid #RRGGBB hex.
            custom = {}
            for var in ("primary", "accent"):
                val = (request.POST.get(f"custom_{var}") or "").strip()
                if re.fullmatch(r"#[0-9A-Fa-f]{6}", val):
                    custom[var] = val
            if custom:
                settings["theme_custom"] = custom
            else:
                settings.pop("theme_custom", None)
            self.community.settings = settings
            self.community.save(update_fields=["settings"])
            messages.success(request, "Theme updated.")
            return redirect("community-settings", slug=self.community.slug)

        form = CommunitySettingsForm(request.POST, instance=self.community)
        if form.is_valid():
            form.save()
            messages.success(request, "Community settings updated.")
            return redirect("community-settings", slug=self.community.slug)
        else:
            return self.render_to_response(self.get_context_data(form=form))


class JoinCodeQRView(LoginRequiredMixin, View):
    """Generate QR code PNG for community join URL."""

    def get(self, request, slug):
        community = get_object_or_404(Community, slug=slug)
        # Check admin permission
        member = Member.objects.filter(user=request.user, community=community, role="admin").first()
        if not member:
            return HttpResponse(status=403)

        import qrcode

        base_url = django_settings.SITE_URL.rstrip("/")
        join_url = f"{base_url}/join/?code={community.join_code}"

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(join_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return HttpResponse(
            buffer,
            content_type="image/png",
            headers={"Content-Disposition": f'inline; filename="{community.slug}-join-qr.png"'},
        )


class TechnologyView(TemplateView):
    template_name = "pages/technology.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tech_items"] = [
            ("Python", "1991 — 34 years"),
            ("Django", "2005 — 20 years"),
            ("PostgreSQL", "1996 — 29 years"),
            ("Redis", "2009 — 16 years"),
            ("HTML + CSS", "1993 — 32 years"),
            ("HTMX", "2020 — hypermedia"),
            ("Alpine.js", "2019 — 1.2 KB"),
            ("Docker", "2013 — 12 years"),
            ("Caddy", "2015 — auto-TLS"),
        ]
        return ctx
