"""Community views: landing, join, feed, settings, QR code."""
import io
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView, CreateView, FormView, ListView

from .forms import CommunityCreateForm, JoinForm
from .models import Community, Member, Category
from apps.needs.models import Need
from apps.offers.models import Offer


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
        Member.objects.create(user=self.request.user, community=community, display_name=display_name, role="member")
        messages.success(self.request, f"Welcome to {community.name}!")
        return redirect("community-feed", slug=community.slug)


class CommunityCreateView(LoginRequiredMixin, CreateView):
    model = Community
    form_class = CommunityCreateForm
    template_name = "communities/create.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        # Creator becomes admin
        Member.objects.create(
            user=self.request.user, community=self.object,
            display_name=self.request.user.username, role="admin",
        )
        # Clone default categories
        defaults = [
            ("\U0001f527", "Home Repair"), ("\U0001f697", "Transportation"), ("\U0001f35e", "Food"),
            ("\U0001f476", "Childcare"), ("\U0001f4da", "Tutoring"), ("\U0001f4bb", "Tech Help"),
            ("\U0001f30d", "Translation"), ("\U0001f33f", "Yard Work"), ("\U0001f91d", "Companionship"),
            ("\u2795", "Other"),
        ]
        for i, (icon, name) in enumerate(defaults):
            Category.objects.create(community=self.object, name=name, icon=icon, sort_order=i)
        messages.success(self.request, f"Community '{self.object.name}' created!")
        return response


class FeedView(LoginRequiredMixin, ListView):
    """Community feed: merged needs + offers, filterable, with HTMX infinite scroll."""
    template_name = "communities/feed.html"
    context_object_name = "items"
    paginate_by = 20

    def get_queryset(self):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"], is_active=True)
        self.member = Member.objects.filter(user=self.request.user, community=self.community, is_active=True).first()

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
            needs = needs.filter(title__icontains=q)
            offers = offers.filter(title__icontains=q)

        # Tag items with their type for template rendering
        need_list = list(needs)
        offer_list = list(offers)
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
        return ctx


class CommunitySettingsView(LoginRequiredMixin, TemplateView):
    template_name = "communities/settings.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        community = get_object_or_404(Community, slug=self.kwargs["slug"])
        ctx["community"] = community
        ctx["members"] = community.members.filter(is_active=True).select_related("user")
        ctx["categories"] = community.categories.all()
        return ctx


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
        return HttpResponse(buffer, content_type="image/png",
            headers={"Content-Disposition": f'inline; filename="{community.slug}-join-qr.png"'})


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
