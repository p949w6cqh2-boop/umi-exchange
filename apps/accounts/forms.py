"""Account forms: registration and login."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    """Registration with optional email."""

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]",
                "placeholder": "Choose a password",
            }
        )
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]",
                "placeholder": "Confirm password",
            }
        )
    )

    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]",
                    "placeholder": "Choose a username",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]",
                    "placeholder": "Email (optional)",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]",
                "placeholder": "Username",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]",
                "placeholder": "Password",
            }
        )
    )


INPUT_CLASS = "w-full border border-gray-300 rounded-lg px-3 py-3 text-base min-h-[44px]"


class ProfileForm(forms.ModelForm):
    """Form for updating user profile (email, phone)."""

    class Meta:
        model = User
        fields = ["email", "phone"]
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Email (optional)",
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": INPUT_CLASS,
                    "placeholder": "Phone (optional)",
                }
            ),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This email is already in use.")
        return email or None  # Store empty as NULL (unique constraint)
