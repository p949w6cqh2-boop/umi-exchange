"""Community, Member, and Category models — the organisational layer."""

import secrets
import string
import uuid

from django.conf import settings as django_settings
from django.db import models
from django.utils.text import slugify

DEFAULT_SETTINGS = {
    "auto_expire_days": 30,
    "timezone": "America/New_York",
    "neighborhood_mode": "optional",  # required | optional | hidden
    "notification_defaults": {"email_digest": "daily"},
}

DEFAULT_CATEGORIES = [
    ("\U0001f527", "Home Repair"),
    ("\U0001f697", "Transportation"),
    ("\U0001f35e", "Food"),
    ("\U0001f476", "Childcare"),
    ("\U0001f4da", "Tutoring"),
    ("\U0001f4bb", "Tech Help"),
    ("\U0001f30d", "Translation"),
    ("\U0001f33f", "Yard Work"),
    ("\U0001f91d", "Companionship"),
    ("\u2795", "Other"),
]


def generate_join_code():
    """8-char alphanumeric token. Uses a CSPRNG: join codes are auth tokens, so
    they must be unguessable. Collisions handled by unique constraint + retry."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(8))


class Community(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    join_code = models.CharField(max_length=12, unique=True, default=generate_join_code)
    visibility = models.CharField(
        max_length=10,
        default="private",
        choices=[("public", "Public"), ("private", "Private"), ("unlisted", "Unlisted")],
    )
    settings = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_communities"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communities_community"
        verbose_name_plural = "communities"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if not self.slug:
            self.slug = slugify(self.name)[:100]
        if not self.settings:
            self.settings = DEFAULT_SETTINGS.copy()
        super().save(*args, **kwargs)
        if is_new:
            for i, (icon, name) in enumerate(DEFAULT_CATEGORIES):
                Category.objects.get_or_create(community=self, name=name, defaults={"icon": icon, "sort_order": i})

    def get_absolute_url(self):
        return f"/c/{self.slug}/"

    @property
    def auto_expire_days(self):
        return self.settings.get("auto_expire_days", 30)

    @property
    def neighborhood_mode(self):
        return self.settings.get("neighborhood_mode", "optional")


class Member(models.Model):
    ROLE_CHOICES = [("member", "Member"), ("coordinator", "Coordinator"), ("admin", "Admin")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="members")
    household = models.ForeignKey(
        "households.Household", null=True, blank=True, on_delete=models.SET_NULL, related_name="members"
    )
    role = models.CharField(max_length=15, default="member", choices=ROLE_CHOICES)
    display_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    notification_prefs = models.JSONField(default=dict)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communities_member"
        unique_together = ["user", "community"]
        indexes = [models.Index(fields=["community", "is_active", "role"])]

    def __str__(self):
        return f"{self.display_name} @ {self.community.name}"

    @property
    def is_coordinator(self):
        return self.role in ("coordinator", "admin")

    @property
    def is_admin(self):
        return self.role == "admin"

    def contact_dict(self, pref):
        """§8.2 contact shape: display name + only the channels `pref` opts into.
        Shared by match contact-revelation and coordinator oversight on need/offer detail."""
        info = {"display_name": self.display_name, "preference": pref}
        if pref in ("email", "any") and self.user.email:
            info["email"] = self.user.email
        if pref in ("phone", "any") and self.user.phone:
            info["phone"] = self.user.phone
        return info

    @property
    def is_last_active_admin(self):
        """True if this is the only active admin — guards self-leave / demotion
        that would orphan the community with no admin."""
        if self.role != "admin" or not self.is_active:
            return False
        return (
            not Member.objects.filter(community_id=self.community_id, role="admin", is_active=True)
            .exclude(pk=self.pk)
            .exists()
        )


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, default="\U0001f527")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communities_category"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.icon} {self.name}"
