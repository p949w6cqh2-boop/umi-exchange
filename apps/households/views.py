from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, FormView

from apps.audit.services import emit

from .forms import HouseholdCreateForm, HouseholdJoinForm
from .models import Household


class HouseholdCreateView(LoginRequiredMixin, CreateView):
    model = Household
    form_class = HouseholdCreateForm
    template_name = "households/create.html"
    success_url = reverse_lazy("account-settings")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        # Assign user's existing memberships to this household
        self.request.user.member_set.filter(household__isnull=True).update(household=self.object)
        messages.success(self.request, f"Household created! Share code: {self.object.join_code}")
        return response


class HouseholdJoinView(LoginRequiredMixin, FormView):
    form_class = HouseholdJoinForm
    template_name = "households/join.html"
    success_url = reverse_lazy("account-settings")

    def form_valid(self, form):
        code = form.cleaned_data["household_code"].upper()
        try:
            household = Household.objects.get(join_code=code)
        except Household.DoesNotExist:
            form.add_error("household_code", "Invalid household code.")
            return self.form_invalid(form)
        # Reassign only this user's own active memberships, and audit it: this
        # is a bulk write that can move memberships out of another household,
        # so it must leave a trail (§8.3) rather than silently overwriting.
        memberships = self.request.user.member_set.filter(is_active=True).exclude(household=household)
        affected = list(memberships.values_list("id", flat=True))
        if affected:
            memberships.update(household=household)
            emit(
                "household.joined",
                household,
                user=self.request.user,
                request=self.request,
                details={"memberships": [str(pk) for pk in affected]},
            )
        messages.success(self.request, f"Joined {household}.")
        return redirect(self.success_url)
