from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView
from django_ratelimit.decorators import ratelimit

from apps.communities.models import Community, Member
from apps.needs.models import Need

from .forms import OfferForm
from .models import Offer


@method_decorator(ratelimit(key="user", rate="5/m", method="POST", block=True), name="post")
class OfferCreateView(LoginRequiredMixin, CreateView):
    model = Offer
    form_class = OfferForm
    template_name = "offers/create.html"

    def get_form_kwargs(self):
        self.community = get_object_or_404(Community, slug=self.kwargs["slug"])
        self.member = get_object_or_404(Member, user=self.request.user, community=self.community, is_active=True)
        kwargs = super().get_form_kwargs()
        kwargs["community"] = self.community
        kwargs["member"] = self.member
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["categories"] = self.community.categories.filter(is_active=True)
        return ctx

    def form_valid(self, form):
        super().form_valid(form)
        messages.success(self.request, "Your offer has been posted!")
        return redirect("community-feed", slug=self.community.slug)


class OfferDetailView(LoginRequiredMixin, DetailView):
    model = Offer
    template_name = "offers/detail.html"
    context_object_name = "offer"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        offer = self.object
        ctx["community"] = offer.community
        member = Member.objects.filter(user=self.request.user, community=offer.community, is_active=True).first()
        ctx["member"] = member
        ctx["is_own_offer"] = member and offer.offerer == member
        ctx["matching_needs"] = Need.objects.filter(
            community=offer.community, category=offer.category, status="open"
        ).exclude(requester=member)[:5]
        return ctx
