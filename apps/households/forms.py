from django import forms

from .models import Household

INPUT_CLASS = "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]"


class HouseholdCreateForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": 'e.g., "The Rodriguez Family" (optional)'})}


class HouseholdJoinForm(forms.Form):
    household_code = forms.CharField(max_length=10, widget=forms.TextInput(attrs={
        "class": f"{INPUT_CLASS} text-center font-mono tracking-widest uppercase",
        "placeholder": "H-XXXXXX",
    }))
