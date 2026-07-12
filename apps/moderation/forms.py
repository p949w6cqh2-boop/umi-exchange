from django import forms

from .models import Flag

INPUT = (
    "w-full border border-[var(--umi-border)] rounded-lg px-3 py-2.5 text-base "
    "bg-white focus:outline-none focus:ring-2 focus:ring-[var(--umi-primary)]"
)


class FlagForm(forms.Form):
    reason = forms.ChoiceField(
        choices=Flag.REASON_CHOICES,
        widget=forms.Select(attrs={"class": INPUT}),
    )
    detail = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "class": INPUT,
                "placeholder": "Optional — what should the coordinator know?",
            }
        ),
        help_text="No names or private details needed — the coordinator can see the post.",
    )
