"""Forms for Member Tags & Verification."""

from django import forms

from .models import VISIBILITY_CHOICES, MemberTag, Tag

INPUT = (
    "w-full border border-[var(--umi-border)] rounded-lg px-3 py-3 text-base "
    "min-h-[44px] focus:outline-none focus:ring-2 focus:ring-[var(--umi-primary)]/40"
)
TEXTAREA = f"{INPUT} min-h-[88px]"


class TagClaimForm(forms.Form):
    """Choose a tag from the community catalog to claim."""

    tag = forms.ModelChoiceField(
        queryset=Tag.objects.none(),
        widget=forms.Select(attrs={"class": INPUT}),
        empty_label="— choose a tag —",
    )
    visibility = forms.ChoiceField(
        choices=VISIBILITY_CHOICES,
        initial="community",
        widget=forms.Select(attrs={"class": INPUT}),
    )

    def __init__(self, *args, community=None, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        if community:
            already_claimed = (
                MemberTag.objects.filter(
                    member=member,
                    tag__community=community,
                )
                .exclude(status="removed")
                .values_list("tag_id", flat=True)
            )
            self.fields["tag"].queryset = (
                Tag.objects.filter(community=community, is_active=True)
                .exclude(id__in=already_claimed)
                .order_by("sort_order", "label")
            )


class RequestVerifyForm(forms.Form):
    """Member submits evidence to request verification of a self-claimed tag."""

    evidence_note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": TEXTAREA,
                "rows": 3,
                "placeholder": "Optional: how can this be confirmed? No PII — e.g. 'confirmed at ordination 2019'.",
            }
        ),
    )


class VerifyTagForm(forms.Form):
    """Coordinator/admin provides evidence and confirms verification."""

    evidence_note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(
            attrs={
                "class": TEXTAREA,
                "rows": 3,
                "placeholder": "How was this confirmed? (no PII — e.g. 'pastor confirmed faculties 2025-03-15').",
            }
        ),
    )


class RejectTagForm(forms.Form):
    """Coordinator/admin provides a reason for rejection."""

    reason = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.Textarea(
            attrs={
                "class": TEXTAREA,
                "rows": 2,
                "placeholder": "Reason (shown to member, no PII).",
            }
        ),
    )


class RevokeTagForm(forms.Form):
    """Coordinator/admin provides a reason for revocation."""

    reason = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.Textarea(
            attrs={
                "class": TEXTAREA,
                "rows": 2,
                "placeholder": "Reason for revocation (no PII).",
            }
        ),
    )
