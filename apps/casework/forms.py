"""
Django forms for casework (design §3.6/§3.7). All forms work as plain POSTs
(no-JS fallback); HTMX adds inline validation via casework:validate.
"""

from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.communities.models import Member
from apps.consent.models import Consent
from apps.people.models import Person

from .models import CaseNote

PRIMARY_NEEDS = [
    ("food", "Food"),
    ("rent", "Rent"),
    ("utilities", "Utilities"),
    ("transportation", "Transportation"),
    ("medical", "Medical"),
    ("clothing", "Clothing"),
    ("other", "Other"),
]

DATETIME_LOCAL = dict(
    widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"],
)


def _consent_is_active(c: Consent) -> bool:
    if getattr(c, "status", "active") != "active" or c.revoked_at:
        return False
    return not (c.expires_at and c.expires_at <= timezone.now())


class CaseCreateForm(forms.Form):
    """Open a case: pick/create the person + the consent gate (§3.6)."""

    person = forms.ModelChoiceField(
        queryset=Person.objects.none(), required=False, label="Existing person", empty_label="— choose —"
    )
    new_person_name = forms.CharField(required=False, max_length=200, label="…or new person: full name")
    new_person_contact = forms.CharField(required=False, max_length=200, label="Contact (phone or email)")

    assigned_to = forms.ModelChoiceField(queryset=Member.objects.none(), required=False, label="Assign to")
    sensitivity = forms.ChoiceField(
        choices=[("standard", "Standard"), ("restricted", "Restricted (admins + named people only)")],
        initial="restricted",
        help_text="Restricted is the safe default. Choose Standard only when the case carries no domestic-violence or other safety risk — every coordinator can read a standard case.",
    )
    primary_needs = forms.MultipleChoiceField(
        choices=PRIMARY_NEEDS, required=False, widget=forms.CheckboxSelectMultiple
    )
    intake_date = forms.DateField(
        initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    physical_ref = forms.CharField(required=False, max_length=100, label="Paper file reference")
    summary = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={"rows": 3}))

    CONSENT_MODES = [
        ("existing", "Use an existing digital consent"),
        ("record", "Record verbal or paper consent now"),
        ("emergency", "Emergency: open without consent (audited)"),
    ]
    consent_mode = forms.ChoiceField(choices=CONSENT_MODES, widget=forms.RadioSelect, initial="record")
    existing_consent = forms.ModelChoiceField(queryset=Consent.objects.none(), required=False, empty_label="— choose —")
    record_method = forms.ChoiceField(choices=[("verbal", "Verbal"), ("paper", "Paper (filed)")], required=False)
    include_export = forms.BooleanField(required=False, label="Consent also covers data export (case_export)")
    emergency_justification = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, community, member, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.community, self.member = community, member
        self.fields["person"].queryset = Person.objects.filter(created_in_community=community, merged_into__isnull=True)
        self.fields["assigned_to"].queryset = Member.objects.filter(
            community=community, is_active=True, role__in=("coordinator", "admin")
        )
        user_ids = Member.objects.filter(community=community, is_active=True).values_list("user_id", flat=True)
        self.fields["existing_consent"].queryset = Consent.objects.filter(
            status="active", revoked_at__isnull=True, participant_id__in=user_ids
        )

    def clean(self):
        data = super().clean()
        person, new_name = data.get("person"), (data.get("new_person_name") or "").strip()
        if bool(person) == bool(new_name):
            raise forms.ValidationError("Choose an existing person OR enter a new person's name (not both).")

        mode = data.get("consent_mode")
        if mode == "existing":
            consent = data.get("existing_consent")
            if not consent:
                self.add_error("existing_consent", "Pick the consent record.")
            else:
                if not _consent_is_active(consent):
                    self.add_error("existing_consent", "That consent is not active.")
                elif "case_records" not in (consent.scope or []):
                    self.add_error("existing_consent", "That consent does not cover case records.")
                elif person and person.linked_user_id:
                    if consent.participant_id != person.linked_user_id:
                        self.add_error("existing_consent", "That consent belongs to a different person.")
                elif not person or not person.linked_user_id:
                    self.add_error(
                        "existing_consent", "This person has no account — record verbal/paper consent instead."
                    )
        elif mode == "record":
            if not data.get("record_method"):
                self.add_error("record_method", "How was consent given?")
        elif mode == "emergency":
            if len((data.get("emergency_justification") or "").strip()) < 10:
                self.add_error("emergency_justification", "A brief justification is required (audited).")
        return data


class NoteForm(forms.Form):
    """The 3-minute note/visit form (design §3.6). Plain POST works without JS."""

    kind = forms.ChoiceField(choices=CaseNote.KIND_CHOICES[:4], initial="visit")
    occurred_at = forms.DateTimeField(initial=timezone.now, **DATETIME_LOCAL)
    duration_minutes = forms.IntegerField(required=False, min_value=1, max_value=600, label="Duration (min)")
    location_kind = forms.ChoiceField(choices=CaseNote.LOCATION_CHOICES, initial="home")
    actions = forms.MultipleChoiceField(
        choices=CaseNote.ACTIONS, required=False, widget=forms.CheckboxSelectMultiple, label="Quick actions"
    )
    aid_amount = forms.DecimalField(required=False, min_value=0, max_digits=8, decimal_places=2, label="Aid value ($)")
    co_visitor = forms.ModelChoiceField(queryset=Member.objects.none(), required=False, label="Co-visitor")
    body = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "What happened, what was agreed…"}),
        max_length=8000,
        label="Notes",
    )
    client_uuid = forms.UUIDField(required=False, widget=forms.HiddenInput)

    def __init__(self, community, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["co_visitor"].queryset = Member.objects.filter(community=community, is_active=True)

    def aid_cents(self):
        amt = self.cleaned_data.get("aid_amount")
        return int(amt * 100) if amt is not None else None


class VisitForm(NoteForm):
    """Visit-capture page variant: adds the case picker."""

    case = forms.ModelChoiceField(queryset=None, empty_label="— choose case —")

    def __init__(self, community, case_qs, *args, **kwargs):
        super().__init__(community, *args, **kwargs)
        self.fields["case"].queryset = case_qs
        self.fields["case"].label_from_instance = lambda c: f"{c.short_code} · {c.subject_person.initials}"
        # field order: case first
        self.order_fields(["case", *[n for n in self.fields if n != "case"]])


class FollowUpForm(forms.Form):
    title = forms.CharField(
        max_length=200, help_text="Keep it non-sensitive — no names (e.g. “Check in re: utility bill”)."
    )
    detail = forms.CharField(
        required=False,
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Sensitive detail goes here (encrypted).",
    )
    due_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    assigned_to = forms.ModelChoiceField(queryset=Member.objects.none())
    source_note = forms.UUIDField(required=False, widget=forms.HiddenInput)

    def __init__(self, community, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Member.objects.filter(community=community, is_active=True)
        self.fields["due_date"].initial = timezone.localdate() + timedelta(days=7)


class AssignForm(forms.Form):
    to_member = forms.ModelChoiceField(queryset=Member.objects.none(), label="Hand off to")
    summary = forms.CharField(
        min_length=10,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "What the incoming visitor needs to know first…"}),
        label="Handoff summary (required — it becomes their first screen)",
    )

    def __init__(self, community, exclude_member=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Member.objects.filter(community=community, is_active=True, role__in=("coordinator", "admin"))
        if exclude_member is not None:
            qs = qs.exclude(pk=exclude_member.pk)
        self.fields["to_member"].queryset = qs


class GrantForm(forms.Form):
    member = forms.ModelChoiceField(queryset=Member.objects.none())
    role = forms.ChoiceField(choices=[("viewer", "Viewer (read only)"), ("contributor", "Contributor (can add notes)")])
    reason = forms.CharField(max_length=200, help_text="Why this person needs access (audited).")
    expires_at = forms.DateTimeField(required=False, **DATETIME_LOCAL)

    def __init__(self, community, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.filter(community=community, is_active=True)


class ReauthForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autofocus": True, "autocomplete": "current-password"})
    )
