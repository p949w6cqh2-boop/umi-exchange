from django import forms

from .models import Community
from .validators import sanitize_text_field

INPUT = "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]"


class CommunityCreateForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ["name", "description", "visibility"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT, "placeholder": "Community name"}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 3, "placeholder": "Optional description"}),
            "visibility": forms.Select(attrs={"class": INPUT}),
        }


class JoinForm(forms.Form):
    join_code = forms.CharField(max_length=12, widget=forms.TextInput(attrs={
        "class": f"{INPUT} text-2xl font-mono tracking-[0.3em] text-center uppercase",
        "placeholder": "AK7X9M2P",
        "maxlength": 12,
    }))
    display_name = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={
        "class": INPUT,
        "placeholder": "Display name (optional)",
    }))


    def clean_display_name(self):
        return sanitize_text_field(self.cleaned_data.get("display_name", ""))
