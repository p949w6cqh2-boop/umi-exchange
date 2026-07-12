"""Forms for reporting content and working the moderation queue."""

from django import forms

from .models import REASON_CHOICES

TARGET_TYPE_CHOICES = [("need", "Need"), ("offer", "Offer"), ("member", "Member")]

_DETAIL_MAX = 2000
_NOTE_MAX = 2000


class FlagForm(forms.Form):
    target_type = forms.ChoiceField(choices=TARGET_TYPE_CHOICES)
    target_id = forms.UUIDField()
    reason = forms.ChoiceField(choices=REASON_CHOICES)
    detail = forms.CharField(required=False, max_length=_DETAIL_MAX, widget=forms.Textarea)


class ResolveFlagForm(forms.Form):
    ACTION_CHOICES = [("hide", "Hide the content"), ("no_action", "Resolve without action")]

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    note = forms.CharField(required=False, max_length=_NOTE_MAX, widget=forms.Textarea)


class DismissFlagForm(forms.Form):
    note = forms.CharField(required=False, max_length=_NOTE_MAX, widget=forms.Textarea)
