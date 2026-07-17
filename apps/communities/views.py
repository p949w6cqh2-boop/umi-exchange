"""Community views: landing, join, feed, settings, QR code."""

import io
import re
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, FormView, ListView, TemplateView

from apps.accounts.ratelimit import rate_limit
from apps.audit.services import emit
from apps.communities.identity import SCENE_SLUGS, parse_identity_post
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.tags.badges import verified_badges_for

from .forms import CommunityCreateForm, CommunitySettingsForm, JoinForm
from .models import Community, Member, Resource, generate_join_code
from .themes import THEME_DEFAULT, THEMES


class LandingView(TemplateView):
    template_name = "pages/landing.html"


# Join-code redemption is brute-forceable without a throttle (codes are 8-char
# CSPRNG, but the space only protects if attempts are bounded). Per-user, not
# per-IP: a parish onboarding event legitimately joins many members from one
# NAT, while account creation is already IP-throttled upstream.
@method_decorator(rate_limit("join", 10, 3600, by="user"), name="post")
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

        existing = Member.objects.filter(user=self.request.user, community=community).first()
        if existing is not None:
            if not existing.is_active:
                # Returning member: reactivate the archived row (Member is unique
                # per (user, community), so a stale is_active=False row can't be
                # replaced — and feed access requires is_active=True, so without
                # this the returning member is told "already a member" and then
                # 404s on the feed). Role/display_name are preserved as archived.
                existing.is_active = True
                existing.save(update_fields=["is_active"])
                emit(
                    "member.joined",
                    existing,
                    user=self.request.user,
                    request=self.request,
                    details={"role": existing.role, "rejoined": True},
                )
                messages.success(self.request, f"Welcome back to {community.name}!")
            else:
                messages.info(self.request, "You are already a member of this community.")
            return redirect("community-feed", slug=community.slug)

        display_name = form.cleaned_data.get("display_name") or self.request.user.username
        member = Member.objects.create(
            user=self.request.user, community=community, display_name=display_name, role="member"
        )
        emit("member.joined", member, user=self.request.user, request=self.request, details={"role": member.role})
        messages.success(self.request, f"Welcome to {community.name}!")
        return redirect("community-feed", slug=community.slug)


class LeaveCommunityView(LoginRequiredMixin, View):
    """POST: the requesting member leaves a community. Soft (is_active=False) so
    history/audit/FK references survive (keyring: archive > delete). The last
    active admin cannot leave — they'd orphan the community."""

    def post(self, request, slug):
        community = get_object_or_404(Community, slug=slug)
        member = get_object_or_404(Member, user=request.user, community=community, is_active=True)
        if member.is_last_active_admin:
            messages.error(request, "Make someone else an admin before you leave this community.")
            return redirect("community-feed", slug=slug)
        member.is_active = False
        member.save(update_fields=["is_active"])
        emit("member.left", member, user=request.user, request=request, details={"role": member.role})
        messages.success(request, f"You have left {community.name}.")
        return redirect("landing")


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

    def get_success_url(self):
        return reverse("community-welcome", kwargs={"slug": self.object.slug})


class CommunityWelcomeView(LoginRequiredMixin, TemplateView):
    """The setup wizard — shown right after creating a community, revisitable
    from settings. Four moves with data-derived checkmarks (no tracking):
    share the code, make it yours, add coordinators, put the first thing on
    the board. Admin-gated: this is the founder's page."""

    template_name = "communities/welcome.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=request.user, community=self.community, is_active=True)
        if not self.member.is_admin:
            raise PermissionDenied("Only this community's admin sees the setup guide.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        members = Member.objects.filter(community=self.community, is_active=True)
        ctx.update(
            {
                "community": self.community,
                "member": self.member,
                "themes": THEMES,
                "current_theme": (self.community.settings or {}).get("theme", THEME_DEFAULT),
                "steps": {
                    "shared": members.count() > 1,
                    "themed": "theme" in (self.community.settings or {}),
                    "coordinators": members.filter(role__in=("coordinator", "admin")).count() > 1,
                    "posted": Need.objects.filter(community=self.community).exists()
                    or Offer.objects.filter(community=self.community).exists(),
                },
            }
        )
        return ctx


class ResourceListView(LoginRequiredMixin, TemplateView):
    """Beyond the board — the community's curated help directory. Members
    read; coordinators add and archive (never delete) on the same page."""

    template_name = "communities/resources.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=request.user, community=self.community, is_active=True)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        resources = Resource.objects.filter(community=self.community, is_active=True)
        grouped = {}
        for r in resources:
            grouped.setdefault(r.get_category_display(), []).append(r)
        ctx.update(
            {
                "community": self.community,
                "member": self.member,
                "grouped": grouped,
                "categories": Resource.CATEGORY_CHOICES,
            }
        )
        return ctx

    def post(self, request, *args, **kwargs):
        if not self.member.is_coordinator:
            raise PermissionDenied("Only coordinators curate the directory.")
        action = request.POST.get("action", "")
        if action == "add":
            title = (request.POST.get("title") or "").strip()[:120]
            url = (request.POST.get("url") or "").strip()
            category = request.POST.get("category", "other")
            blurb = (request.POST.get("blurb") or "").strip()[:280]
            validate = URLValidator(schemes=["http", "https"])
            try:
                validate(url)
            except ValidationError:
                messages.error(request, "That link doesn't look like a web address.")
                return redirect("community-resources", slug=self.community.slug)
            if not title:
                messages.error(request, "Give the link a name people will recognise.")
                return redirect("community-resources", slug=self.community.slug)
            resource = Resource.objects.create(
                community=self.community,
                title=title,
                url=url,
                category=category if category in dict(Resource.CATEGORY_CHOICES) else "other",
                blurb=blurb,
                added_by=self.member,
            )
            emit(
                "resource.added", resource, user=request.user, request=request, details={"category": resource.category}
            )
            messages.success(request, "Added to the directory.")
        elif action == "archive":
            resource = get_object_or_404(
                Resource, pk=request.POST.get("resource_id"), community=self.community, is_active=True
            )
            resource.is_active = False
            resource.save(update_fields=["is_active"])
            emit(
                "resource.archived",
                resource,
                user=request.user,
                request=request,
                details={"category": resource.category},
            )
            messages.success(request, "Archived — it can come back any time.")
        else:
            messages.error(request, "Unknown action.")
        return redirect("community-resources", slug=self.community.slug)


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

    def dispatch(self, request, *args, **kwargs):
        # §I: the ONE anonymous branch. A community that chose a front door
        # (≥1 pre-auth page, not private, active) sends logged-out visitors to
        # it; every other anonymous case falls through to LoginRequiredMixin's
        # redirect unchanged, so missing and private stay indistinguishable.
        if not request.user.is_authenticated:
            from apps.pages.models import CommunityPage

            community = Community.objects.filter(slug=kwargs["slug"], is_active=True).first()
            if community is not None and CommunityPage.objects.pre_auth_visible(community).exists():
                return redirect("pages:index", slug=community.slug)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=self.request.user, community=self.community, is_active=True)

        needs = Need.objects.filter(community=self.community, status="open", moderation_hidden=False).select_related(
            "category", "requester"
        )
        offers = Offer.objects.filter(
            community=self.community, status="active", moderation_hidden=False
        ).select_related("category", "offerer")

        cat = self.request.GET.get("category")
        urg = self.request.GET.get("urgency")
        q = self.request.GET.get("q")
        if cat:
            # category_id is a UUID FK — a malformed value would raise ValueError
            # inside the ORM filter and 500 the feed. Ignore an unparseable param.
            try:
                cat = uuid.UUID(str(cat))
            except (ValueError, TypeError):
                cat = None
        if cat:
            needs = needs.filter(category_id=cat)
            offers = offers.filter(category_id=cat)
        if urg:
            needs = needs.filter(urgency=urg)
        if q:
            from apps.needs.search import apply_search

            needs = apply_search(needs, q)
            offers = apply_search(offers, q)
        from apps.needs.search import order_by_relevance

        # Type tabs (All / Asks / Offers): a lane the surfer can pick.
        kind = self.request.GET.get("type")
        # Tag items with their type for template rendering. Order + slice at
        # the DB layer (LIMIT) so memory stays bounded regardless of community size.
        cap = self.feed_per_type_cap
        need_list = [] if kind == "offer" else list(order_by_relevance(needs, q)[:cap])
        offer_list = [] if kind == "need" else list(order_by_relevance(offers, q)[:cap])
        for n in need_list:
            n.item_type = "need"
        for o in offer_list:
            o.item_type = "offer"

        if q:
            # Searching: each list arrives relevance-ranked (ts_rank); merge by
            # rank so the best answer tops the board, not merely the newest.
            combined = sorted(
                need_list + offer_list,
                key=lambda x: getattr(x, "_rank", 0.0),
                reverse=True,
            )
        else:
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
        ctx["feed_type"] = self.request.GET.get("type", "")
        # Pulse strip: the week's collective numbers (hub selector, read-only).
        if not self.request.htmx:
            from apps.hub.selectors import week_stats

            ctx["week_stats"] = week_stats(self.community)
        self._attach_poster_badges(ctx.get("items", []))
        # Federation (Stage C3): surface the cross-community board only when
        # the flag is on AND this community holds a live link (no query when off).
        from django.conf import settings as dj_settings

        ctx["federation_links_active"] = False
        if getattr(dj_settings, "FEDERATION_ENABLED", False):
            from apps.federation.models import FederationLink

            ctx["federation_links_active"] = FederationLink.objects.filter(
                community=self.community, status="active"
            ).exists()
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
        ctx["is_admin"] = self.member.is_admin
        ctx["role_choices"] = Member.ROLE_CHOICES
        ctx["current_theme"] = (self.community.settings or {}).get("theme", THEME_DEFAULT)
        ctx["theme_custom"] = (self.community.settings or {}).get("theme_custom", {})
        s = self.community.settings or {}
        ctx["identity"] = {
            "patron": s.get("patron", ""),
            "welcome_lines": "\n".join(s.get("welcome_lines", [])),
            "signin_blurb": s.get("signin_blurb", ""),
            "scene_choices": s.get("scene_choices", {}),
        }
        ctx["scene_slugs"] = SCENE_SLUGS
        if "form" not in ctx:
            ctx["form"] = CommunitySettingsForm(instance=self.community)
        return ctx

    def post(self, request, slug):
        action = request.POST.get("action")
        if action == "regenerate_join_code":
            new_code = generate_join_code()
            self.community.join_code = new_code
            self.community.save(update_fields=["join_code"])
            emit("community.code_reset", self.community, user=request.user, request=request)
            messages.success(request, f"Join code regenerated: {new_code}")
            return redirect("community-settings", slug=self.community.slug)

        if action == "set_theme":
            key = request.POST.get("theme", THEME_DEFAULT)
            # Optional custom overrides — only accept valid #RRGGBB hex.
            custom = {}
            for var in ("primary", "accent"):
                val = (request.POST.get(f"custom_{var}") or "").strip()
                if re.fullmatch(r"#[0-9A-Fa-f]{6}", val):
                    custom[var] = val
            # Same shared-blob rule as set_identity: mutate under the row lock.
            with transaction.atomic():
                community = Community.objects.select_for_update().get(pk=self.community.pk)
                settings = dict(community.settings or {})
                settings["theme"] = key if key in THEMES else THEME_DEFAULT
                if custom:
                    settings["theme_custom"] = custom
                else:
                    settings.pop("theme_custom", None)
                community.settings = settings
                community.save(update_fields=["settings"])
            self.community.settings = settings
            emit(
                "community.theme_set",
                self.community,
                user=request.user,
                request=request,
                details={"theme": settings["theme"]},
            )
            messages.success(request, "Theme updated.")
            nxt = request.POST.get("next", "")
            # url_has_allowed_host_and_scheme rejects the bypasses the manual
            # startswith check missed (e.g. "/\evil.com" and "/%2f%2fevil.com",
            # which browsers normalize to a protocol-relative //evil.com).
            if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                return redirect(nxt)
            return redirect("community-settings", slug=self.community.slug)

        if action == "set_identity":
            updates, errors = parse_identity_post(request.POST)
            if errors:
                messages.error(request, " ".join(errors))
                return redirect("community-settings", slug=self.community.slug)
            scene_updates = updates.pop("scene_choices", None)
            changed = []
            # settings is a shared JSON blob with two writers (theme + identity):
            # read-modify-write under a row lock or concurrent saves clobber
            # each other's keys (CLAUDE.md: contended writes use select_for_update).
            with transaction.atomic():
                community = Community.objects.select_for_update().get(pk=self.community.pk)
                settings = dict(community.settings or {})
                for key, value in updates.items():
                    if value:
                        if settings.get(key) != value:
                            settings[key] = value
                            changed.append(key)
                    elif key in settings:
                        # Blank clears the key — zero customization is today's warm default.
                        settings.pop(key)
                        changed.append(key)
                if scene_updates is not None:
                    scenes = dict(settings.get("scene_choices") or {})
                    for surface, slug in scene_updates.items():
                        if slug in SCENE_SLUGS:
                            if scenes.get(surface) != slug:
                                scenes[surface] = slug
                                changed.append("scene_choices")
                        elif slug == "" and surface in scenes:
                            scenes.pop(surface)
                            changed.append("scene_choices")
                        # Unknown slug: silent no-op (resolve_theme posture).
                    if scenes:
                        settings["scene_choices"] = scenes
                    else:
                        settings.pop("scene_choices", None)
                community.settings = settings
                community.save(update_fields=["settings"])
            self.community.settings = settings
            emit(
                "community.identity_set",
                self.community,
                user=request.user,
                request=request,
                # PII-free: the key names only, never the parish's words.
                details={"keys": sorted(set(changed))},
            )
            messages.success(request, "Identity saved. The hub wears it now.")
            return redirect("community-settings", slug=self.community.slug)

        if action == "change_role":
            # Least privilege: only admins change roles (coordinators manage content).
            if not self.member.is_admin:
                messages.error(request, "Only admins can change member roles.")
                return redirect("community-settings", slug=self.community.slug)
            # Same-community lookup prevents cross-community IDOR.
            target = self.community.members.filter(id=request.POST.get("member_id"), is_active=True).first()
            new_role = request.POST.get("role")
            if not target or new_role not in dict(Member.ROLE_CHOICES):
                messages.error(request, "Invalid member or role.")
                return redirect("community-settings", slug=self.community.slug)
            if target.is_last_active_admin and new_role != "admin":
                messages.error(request, "The community must keep at least one admin.")
                return redirect("community-settings", slug=self.community.slug)
            old_role = target.role
            if new_role != old_role:
                target.role = new_role
                target.save(update_fields=["role"])
                emit(
                    "member.role_changed",
                    target,
                    user=request.user,
                    request=request,
                    details={"from": old_role, "to": new_role},
                )
            messages.success(request, f"{target.display_name}'s role updated.")
            return redirect("community-settings", slug=self.community.slug)

        form = CommunitySettingsForm(request.POST, instance=self.community)
        if form.is_valid():
            form.save()
            emit(
                "community.updated",
                self.community,
                user=request.user,
                request=request,
                details={"visibility": self.community.visibility},
            )
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


class AboutView(TemplateView):
    """Public: the founder's story + mission (Lake 0's soul, plain-text)."""

    template_name = "pages/about.html"


class PrivacyView(TemplateView):
    """Public: the retention/privacy promise in plain language (policy set
    by Jasiah 2026-07-11; enforcement = crypto-shred sweeps + backup aging)."""

    template_name = "pages/privacy.html"


class BeliefsView(TemplateView):
    """Public: what we believe — CST foundation, the vision, faithful citizenship."""

    template_name = "pages/beliefs.html"


class WhyUmiView(TemplateView):
    """Public: an honest, factual comparison — mutual aid vs case-management referral."""

    template_name = "pages/why_umi.html"


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


# --- Layer P: the platform floor (pipeline §B) --------------------------------
# The protocol lives ON the instance so the footer's promise holds on an offline
# laptop. No runtime markdown: the fragment is pre-rendered by
# scripts/render_protocol.py, committed, and staleness-tested against spec.md.

SPEC_PATH = Path(django_settings.BASE_DIR) / "docs" / "protocol" / "spec.md"
SPEC_FRAGMENT_PATH = Path(django_settings.BASE_DIR) / "templates" / "pages" / "_protocol_spec.html"

# Monitored address until a real domain is registered and deployed; upgrade
# path to security@<domain> is noted in SECURITY.md. (Steward's key, 2026-07-16.)
SECURITY_CONTACT = "usermegadatainfrastructure@proton.me"
SECURITY_POLICY_URL = "https://github.com/p949w6cqh2-boop/umi-exchange/blob/main/SECURITY.md"


class ProtocolView(TemplateView):
    """Public, community-unscoped: the UMI Protocol, readable on this very server."""

    template_name = "pages/protocol.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # The fragment is nh3-written at build time — the only |safe surface here.
        # Split markers let the template keep the keyed reading order:
        # document head → intro card → TOC → sections.
        head, toc, body = SPEC_FRAGMENT_PATH.read_text(encoding="utf-8").split("<!--SPLIT-->")
        ctx.update(spec_head=head, spec_toc=toc, spec_body=body)
        ctx["security_policy_url"] = SECURITY_POLICY_URL
        return ctx


class ProtocolSpecRawView(View):
    """The canonical spec.md, streamed as plain markdown next to the rendered page."""

    def get(self, request):
        try:
            content = SPEC_PATH.read_bytes()
        except OSError:
            # A missing canonical file is a server fault — warm page, never a traceback.
            return render(request, "500.html", status=500)
        return HttpResponse(content, content_type="text/markdown; charset=utf-8")


class SecurityTxtView(View):
    """RFC 9116 security.txt — the ONLY copy; Caddy proxies this path through."""

    def get(self, request):
        expires = datetime.now(dt_timezone.utc) + timedelta(days=365)
        lines = [
            f"Contact: mailto:{SECURITY_CONTACT}",
            f"Expires: {expires.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            f"Policy: {SECURITY_POLICY_URL}",
            f"Canonical: {request.build_absolute_uri('/.well-known/security.txt')}",
            "Preferred-Languages: en",
        ]
        return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")
