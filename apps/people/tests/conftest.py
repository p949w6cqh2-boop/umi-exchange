"""Fixtures for Person envelope-encryption tests."""

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model


@pytest.fixture(autouse=True)
def _encryption_key(settings):
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()


def _make_member():
    import uuid

    from apps.communities.models import Community, Member

    User = get_user_model()  # noqa: N806
    sfx = uuid.uuid4().hex[:8]
    user = User.objects.create_user(username=f"pe_{sfx}", email=f"pe_{sfx}@example.test", password="pw-Str0ng!pass")
    community = Community.objects.create(name=f"People Env {sfx}", slug=f"people-env-{sfx}", created_by=user)
    return Member.objects.create(user=user, community=community, role="coordinator", display_name="Coord")


@pytest.fixture
def person(_encryption_key, db):
    """A saved Person with all three PII fields set (envelope-encrypted)."""
    from apps.people.models import Person

    member = _make_member()
    p = Person(created_in_community=member.community, created_by=member)
    p.display_name = "Maria Garcia"
    p.contact = {"phone": "555-0100", "email": "m@example.test"}
    p.dob = "1980-04-12"
    p.save()
    return p


@pytest.fixture
def member(_encryption_key, db):
    return _make_member()
