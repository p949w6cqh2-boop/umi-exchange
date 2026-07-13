"""Account forms: registration and login."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
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

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return None  # Store as NULL so unique constraint allows multiple blanks
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "Passwords do not match.")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
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
        fields = ["email", "phone", "email_notifications"]
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
            "email_notifications": forms.CheckboxInput(attrs={"class": "accent-[var(--umi-primary)] w-5 h-5"}),
        }
        labels = {"email_notifications": "Email me when something needs my attention"}
        help_texts = {
            "email_notifications": "Turn this off and you'll still see everything in the app — we just won't email you."
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This email is already in use.")
        return email or None  # Store empty as NULL (unique constraint)
