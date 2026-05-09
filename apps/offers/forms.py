from django import forms
from apps.communities.validators import sanitize_text_field
from .models import Offer

INPUT = "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px] focus:ring-2 focus:ring-blue-500"

class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["category", "title", "description", "contact_pref"]
        widgets = {
            "category": forms.HiddenInput(),
            "title": forms.TextInput(attrs={"class": INPUT, "placeholder": "What can you help with?", "maxlength": 200}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 4, "placeholder": "Describe your experience..."}),
            "contact_pref": forms.RadioSelect(),
        }

    def clean_title(self):
        """Strip HTML tags from title as defense-in-depth."""
        return sanitize_text_field(self.cleaned_data.get("title", ""))

    def clean_description(self):
        """Strip HTML tags from description as defense-in-depth."""
        return sanitize_text_field(self.cleaned_data.get("description", ""))

    def __init__(self, *args, community=None, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.community = community
        self.member = member
        if community:
            self.fields["category"].queryset = community.categories.filter(is_active=True)

    def save(self, commit=True):
        offer = super().save(commit=False)
        offer.community = self.community
        offer.offerer = self.member
        if commit:
            offer.save()
        return offer
