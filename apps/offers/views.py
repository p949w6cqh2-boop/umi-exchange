from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView

from apps.audit.services import emit
from apps.communities.models import Community, Member
from apps.needs.models import Need
from apps.tags.badges import verified_badges_for

from .forms import OfferForm
from .models import Offer


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
        emit(
            "offer.created",
            self.object,
            user=self.request.user,
            request=self.request,
            details={"status": self.object.status},
        )
        messages.success(self.request, "Your offer has been posted!")
        return redirect("community-feed", slug=self.community.slug)


class OfferDetailView(LoginRequiredMixin, DetailView):
    model = Offer
    template_name = "offers/detail.html"
    context_object_name = "offer"

    def get_object(self, queryset=None):
        from django.http import Http404

        obj = super().get_object(queryset)
        viewer = Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).first()
        if viewer is None:
            raise Http404("You are not a member of this community.")
        if obj.moderation_hidden and not viewer.is_coordinator:
            raise Http404("This post is no longer available.")
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        offer = self.object
        ctx["community"] = offer.community
        member = Member.objects.filter(user=self.request.user, community=offer.community, is_active=True).first()
        ctx["member"] = member
        ctx["poster_badges"] = verified_badges_for([offer.offerer_id], member).get(offer.offerer_id, [])
        ctx["is_own_offer"] = member and offer.offerer == member
        # §8.2: contact locked for ordinary members; coordinators get audited oversight.
        contact_info = None
        if member and member.is_coordinator and offer.offerer != member:
            contact_info = offer.offerer.contact_dict(offer.contact_pref)
            emit(
                "offer.contact_disclosed",
                offer,
                user=self.request.user,
                request=self.request,
                details={"viewer_role": member.role},
            )
        ctx["contact_info"] = contact_info
        ctx["show_contact"] = contact_info is not None
        # Federation (§2.3/§4.1): the owner's share panel.
        from apps.federation.sharing import share_panel

        ctx["share_panel"] = share_panel(offer, member)
        ctx["matching_needs"] = Need.objects.filter(
            community=offer.community, category=offer.category, status="open"
        ).exclude(requester=member)[:5]
        return ctx


class OfferDeleteView(LoginRequiredMixin, DeleteView):
    model = Offer

    def form_valid(self, form):
        # Block deletion while a Match is live (proposed/accepted): deleting the
        # offer nulls the Match's offer (SET_NULL) and strands the counterpart
        # Need in "matched" forever. Cancel the match first.
        if self.object.matches.filter(status__in=("proposed", "accepted")).exists():
            return HttpResponse(
                "This offer has an active match. Cancel the match before deleting it.",
                status=409,
                content_type="text/plain",
            )
        emit(
            "offer.deleted",
            self.object,
            user=self.request.user,
            request=self.request,
            details={"status": self.object.status},
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("community-feed", kwargs={"slug": self.object.community.slug})

    def get_object(self, queryset=None):
        from django.core.exceptions import PermissionDenied
        from django.http import Http404

        obj = super().get_object(queryset)
        member = Member.objects.filter(user=self.request.user, community=obj.community, is_active=True).first()
        if not member:
            raise Http404("You are not a member of this community.")
        if obj.offerer != member and member.role not in ["admin", "coordinator"]:
            raise PermissionDenied("You do not have permission to delete this offer.")
        return obj
