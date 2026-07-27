"""Need creation form with metadata privacy mitigations."""

import re

from django import forms

from apps.communities.validators import sanitize_text_field

from .models import Need

INPUT = "umi-input"


class NeedForm(forms.ModelForm):
    # No on-behalf field here, deliberately. One existed and was never rendered by
    # templates/needs/create.html, so it could only be reached by a hand-crafted
    # POST — a write-only sink for a third party's name that no screen ever showed
    # and no member could ask to have removed. The Need.on_behalf_of column, its
    # envelope property, the retention sweep and shred_on_behalf all remain for
    # legacy rows. If Lake 1 ever needs posting on someone's behalf, it should be
    # built with the same consent discipline as casework: a record naming THEM
    # (consent.subject_person), and limited display until it exists.

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
        if commit:
            need.save()
        return need
