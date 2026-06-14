"""Need creation form with metadata privacy mitigations."""

import re

from django import forms

from apps.communities.validators import sanitize_text_field

from .models import Need

INPUT = "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px] focus:ring-2 focus:ring-blue-500"


class NeedForm(forms.ModelForm):
    on_behalf_of_text = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT,
                "placeholder": "\U0001f512 Their name (encrypted)",
            }
        ),
    )

    class Meta:
        model = Need
        fields = ["category", "title", "description", "urgency", "neighborhood", "contact_pref"]
        widgets = {
            "category": forms.HiddenInput(),
            "title": forms.TextInput(
                attrs={"class": INPUT, "placeholder": "What do you need help with?", "maxlength": 200}
            ),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 4, "placeholder": "Provide more details..."}),
            "urgency": forms.HiddenInput(),
            "neighborhood": forms.TextInput(attrs={"class": INPUT, "placeholder": "e.g., Westside, near the park"}),
            "contact_pref": forms.RadioSelect(),
        }

    def __init__(self, *args, community=None, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.community = community
        self.member = member
        if community:
            self.fields["category"].queryset = community.categories.filter(is_active=True)
        if not member or not member.is_coordinator:
            del self.fields["on_behalf_of_text"]

    def clean_title(self):
        """Strip HTML tags from title as defense-in-depth."""
        return sanitize_text_field(self.cleaned_data.get("title", ""))

    def clean_description(self):
        """Strip HTML tags from description as defense-in-depth."""
        return sanitize_text_field(self.cleaned_data.get("description", ""))

    def clean_neighborhood(self):
        value = self.cleaned_data.get("neighborhood", "")
        if not value:
            return value
        # Soft warning for street-address-like input
        pattern = re.compile(
            r"\d+\s+(street|st|avenue|ave|road|rd|drive|dr|lane|ln|boulevard|blvd|way|court|ct)",
            re.IGNORECASE,
        )
        if pattern.search(value):
            self._neighborhood_warning = (
                "This looks like a specific address. Consider using a general area instead "
                '(e.g., "Westside" or "near the park").'
            )
        return value

    def save(self, commit=True):
        need = super().save(commit=False)
        need.community = self.community
        need.requester = self.member
        if hasattr(self, "cleaned_data") and self.cleaned_data.get("on_behalf_of_text"):
            need.on_behalf_of_name = self.cleaned_data["on_behalf_of_text"]
        if commit:
            need.save()
        return need
