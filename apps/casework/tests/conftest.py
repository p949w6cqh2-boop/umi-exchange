"""
Shared fixtures. NOTE: the suite exercises real URLs + middleware, so it
assumes the three §0 install edits are in place (INSTALLED_APPS, the
SensitiveSessionMiddleware line, and the config/urls.py include).
"""

import time
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.casework.middleware import SESSION_KEY, SESSION_USER_KEY
from apps.casework.models import CaseFile
from apps.communities.models import Community, Member
from apps.consent.models import Consent
from apps.people.models import Person


@pytest.fixture(autouse=True)
def _encryption_key(settings):
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()


def make_user(handle):
    User = get_user_model()  # noqa: N806
    try:
        return User.objects.create_user(username=handle, email=f"{handle}@example.test", password="pw-Str0ng!pass")
    except TypeError:  # email-only custom managers
        return User.objects.create_user(email=f"{handle}@example.test", password="pw-Str0ng!pass")


def make_community(created_by):
    kwargs = dict(name="St. Patrick Conference", slug="st-patrick", created_by=created_by)
    try:
        return Community.objects.create(**kwargs)
    except Exception:
        return Community.objects.create(visibility="private", join_code="TESTCODE1234", **kwargs)


@pytest.fixture
def world(db):
    """One community, the full cast, a linked person, an active consent,
    and a standard case assigned to `coordinator`."""
    admin_u, coord_u = make_user("admin"), make_user("anne")
    coord2_u, plain_u = make_user("luis"), make_user("sam")
    subject_u = make_user("maria")

    community = make_community(admin_u)

    def member(user, role, name):
        return Member.objects.create(user=user, community=community, role=role, display_name=name, is_active=True)

    admin = member(admin_u, "admin", "Father Tom")
    coordinator = member(coord_u, "coordinator", "Anne")
    coordinator2 = member(coord2_u, "coordinator", "Luis")
    plain = member(plain_u, "member", "Sam")
    subject_member = member(subject_u, "member", "Maria")

    person = Person(created_in_community=community, created_by=coordinator, linked_user=subject_u)
    person.display_name = "Maria Garcia"
    person.contact = {"raw": "555-0100"}
    person.save()

    consent = Consent.objects.create(
        participant=subject_u,
        granted_to=community.name,
        scope=["case_records", "case_export"],
        purpose="Casework tests",
        method="digital",
    )

    case = CaseFile.objects.create(
        community=community, subject_person=person, opened_by=coordinator, assigned_to=coordinator, consent=consent
    )

    return SimpleNamespace(
        community=community,
        person=person,
        consent=consent,
        case=case,
        admin=admin,
        coordinator=coordinator,
        coordinator2=coordinator2,
        plain=plain,
        subject_member=subject_member,
        admin_u=admin_u,
        coord_u=coord_u,
        coord2_u=coord2_u,
        plain_u=plain_u,
        subject_u=subject_u,
    )


@pytest.fixture
def auth(client):
    """auth(user) → logged-in client with a fresh sensitive-session stamp."""

    def _login(user, stamp=True):
        client.force_login(user)
        if stamp:
            s = client.session
            s[SESSION_KEY] = time.time()
            s[SESSION_USER_KEY] = user.pk
            s.save()
        return client

    return _login


@pytest.fixture
def u(world):
    """URL helper: u('detail', pk=case.pk)"""

    def _u(name, **kw):
        return reverse(f"casework:{name}", kwargs={"slug": world.community.slug, **kw})

    return _u


@pytest.fixture
def make_note(world):
    from apps.casework.models import CaseNote

    def _make(author=None, case=None, status="draft", body="Visited; all well.", **kw):
        note = CaseNote(
            case=case or world.case,
            author=author or world.coordinator,
            status=status,
            finalized_at=(timezone.now() if status == "final" else None),
            **kw,
        )
        note.body = body
        note.save()
        return note

    return _make
