"""
Person name blind index (§12.3, Stages A/B/D — the backfill Stage C is a
gated, separate step). Coordinators can look a Person up by exact name
without decrypting every row: name_bidx = HMAC-SHA256(BLIND_INDEX_KEY,
normalized name). Equality only, never authorization.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.people import crypto
from apps.people.models import Person

pytestmark = pytest.mark.django_db

BIDX_KEY = "test-blind-index-key-not-a-kek"


@pytest.fixture(autouse=True)
def _blind_index_key(settings):
    settings.BLIND_INDEX_KEY = BIDX_KEY


# ------------------------------------------------------------- the helper
def test_helper_is_deterministic_and_opaque():
    a = crypto.name_blind_index("Maria Garcia")
    assert a == crypto.name_blind_index("Maria Garcia")
    assert isinstance(a, bytes) and len(a) == 32  # raw HMAC-SHA256 digest
    assert b"Maria" not in a and b"maria" not in a


def test_helper_normalizes_case_and_whitespace():
    canonical = crypto.name_blind_index("Maria Garcia")
    assert crypto.name_blind_index("  maria   GARCIA ") == canonical
    assert crypto.name_blind_index("MARIA\tGarcia\n") == canonical


def test_helper_distinguishes_names():
    assert crypto.name_blind_index("Maria Garcia") != crypto.name_blind_index("Mario Garcia")


def test_helper_empty_input_is_none():
    assert crypto.name_blind_index(None) is None
    assert crypto.name_blind_index("") is None
    assert crypto.name_blind_index("   ") is None


def test_helper_fails_closed_without_key(settings):
    settings.BLIND_INDEX_KEY = ""
    with pytest.raises(ImproperlyConfigured):
        crypto.name_blind_index("Maria Garcia")


def test_helper_rejects_key_shared_with_encryption(settings):
    """§12.3: the blind-index key must be DEDICATED, never a reused KEK."""
    settings.BLIND_INDEX_KEY = settings.ENCRYPTION_KEY
    with pytest.raises(ImproperlyConfigured):
        crypto.name_blind_index("Maria Garcia")


def test_setter_failure_leaves_instance_unchanged(person, settings):
    """A raising bidx call must not half-mutate the instance: the set path
    computes the bidx BEFORE touching any field, mirroring the clear path."""
    old_enc = bytes(person.display_name_enc)
    old_bidx = bytes(person.name_bidx)
    settings.BLIND_INDEX_KEY = settings.ENCRYPTION_KEY  # shared key → helper raises
    with pytest.raises(ImproperlyConfigured):
        person.display_name = "New Name"
    assert bytes(person.display_name_enc) == old_enc
    assert bytes(person.name_bidx) == old_bidx


# ------------------------------------------------- setter keeps bidx in sync
def test_setter_populates_bidx(person):
    person.refresh_from_db()
    assert bytes(person.name_bidx) == crypto.name_blind_index("Maria Garcia")


def test_clearing_name_nulls_bidx(person):
    person.display_name = None
    person.save(update_fields=["display_name_enc", "display_name_enc_dek", "name_bidx"])
    person.refresh_from_db()
    assert person.name_bidx is None


def test_clearing_name_needs_no_key(person, settings):
    """Crypto-shred must work even when BLIND_INDEX_KEY is missing —
    erasure can never be blocked by configuration."""
    settings.BLIND_INDEX_KEY = ""
    person.display_name = None  # must not raise
    assert person.name_bidx is None


def test_rename_recomputes_bidx(person):
    person.display_name = "Ana Bell"
    person.save(update_fields=["display_name_enc", "display_name_enc_dek", "name_bidx"])
    person.refresh_from_db()
    assert bytes(person.name_bidx) == crypto.name_blind_index("Ana Bell")
    assert bytes(person.name_bidx) != crypto.name_blind_index("Maria Garcia")


def test_empty_string_name_nulls_bidx(person):
    person.display_name = ""
    assert person.name_bidx is None


# ---------------------------------------------------------------- lookups
def test_by_name_exact_match(person):
    home = person.created_in_community
    other = Person(created_in_community=home, created_by=person.created_by)
    other.display_name = "Someone Else"
    other.save()

    found = Person.objects.by_name("Maria Garcia", community=home)
    assert list(found) == [person]


def test_by_name_is_community_scoped(person, member):
    """Same name in two communities: each lookup sees only its own row.
    An unscoped Person lookup is the cross-community leak class the repo's
    review checklist bans — community is a REQUIRED kwarg by construction."""
    twin = Person(created_in_community=member.community, created_by=member)
    twin.display_name = "Maria Garcia"
    twin.save()

    assert list(Person.objects.by_name("Maria Garcia", community=person.created_in_community)) == [person]
    assert list(Person.objects.by_name("Maria Garcia", community=member.community)) == [twin]


def test_by_name_requires_community_kwarg(person):
    with pytest.raises(TypeError):
        Person.objects.by_name("Maria Garcia")  # noqa: PLE1120 — the missing kwarg IS the test


def test_by_name_normalizes_query(person):
    home = person.created_in_community
    assert list(Person.objects.by_name("  maria   GARCIA ", community=home)) == [person]


def test_by_name_empty_query_matches_nothing(person, member):
    nameless = Person(created_in_community=member.community, created_by=member)
    nameless.save()  # name_bidx NULL — must never match an empty query
    assert list(Person.objects.by_name("", community=member.community)) == []
    assert list(Person.objects.by_name(None, community=member.community)) == []


def test_by_name_no_match(person):
    assert list(Person.objects.by_name("Nobody Here", community=person.created_in_community)) == []


# ------------------------------------------------------------ shred + census
def test_shred_clears_bidx_with_pii(person):
    """Post-erasure the name must not stay equality-testable (§12.3 CRITICAL)."""
    person.display_name = None
    person.contact = None
    person.dob = None
    person.save()
    person.refresh_from_db()
    assert person.name_bidx is None
    assert list(Person.objects.by_name("Maria Garcia", community=person.created_in_community)) == []


def test_census_reports_missing_bidx(member, person):
    import io

    from django.core.management import call_command

    # A row written before the bidx existed: name ciphertext present, bidx NULL.
    legacy = Person(created_in_community=member.community, created_by=member)
    legacy.display_name = "Pre Bidx"
    legacy.save()
    Person.objects.filter(pk=legacy.pk).update(name_bidx=None)

    out = io.StringIO()
    call_command("person_bidx_status", stdout=out)
    text = out.getvalue()
    assert "indexed=1" in text
    assert "missing=1" in text
