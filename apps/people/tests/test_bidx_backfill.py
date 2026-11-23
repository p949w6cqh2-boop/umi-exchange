"""§12.3 Stage C — backfill the name blind index onto Person rows written before it existed.

    python manage.py backfill_person_bidx              # dry run: counts only
    python manage.py backfill_person_bidx --apply      # index the rows that lack a bidx
    python manage.py backfill_person_bidx --reindex --apply   # recompute every bidx (BLIND_INDEX_KEY rotation)

Writes name_bidx and nothing else; never prints a name; carries on past an unreadable row and fails
at the end naming it (rotate_keks shape); a second run finds nothing to do.
"""

import io

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.people.models import Person

pytestmark = pytest.mark.django_db


def _legacy(member, name):
    """A row as it stood before Stage B: name ciphertext present, bidx NULL."""
    p = Person(created_in_community=member.community, created_by=member)
    p.display_name = name
    p.save()
    Person.objects.filter(pk=p.pk).update(name_bidx=None)
    return Person.objects.get(pk=p.pk)


def _run(*args):
    out, err = io.StringIO(), io.StringIO()
    call_command("backfill_person_bidx", *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def test_dry_run_counts_and_writes_nothing(member):
    legacy = _legacy(member, "Rosa Delgado")
    out, _ = _run()
    assert "Dry run" in out
    assert "1" in out
    legacy.refresh_from_db()
    assert legacy.name_bidx is None


def test_dry_run_needs_no_blind_index_key(member, settings):
    _legacy(member, "Rosa Delgado")
    settings.BLIND_INDEX_KEY = ""
    out, _ = _run()  # counting decrypts nothing and hashes nothing
    assert "Dry run" in out


def test_apply_indexes_the_missing_row_and_name_search_finds_it(member):
    legacy = _legacy(member, "Rosa Delgado")
    assert list(Person.objects.by_name("Rosa Delgado", community=member.community)) == []
    _run("--apply")
    assert list(Person.objects.by_name("rosa  DELGADO", community=member.community)) == [legacy]
    census = io.StringIO()
    call_command("person_bidx_status", stdout=census, stderr=io.StringIO())
    assert "missing=0" in census.getvalue()


def test_apply_touches_only_the_bidx(member):
    legacy = _legacy(member, "Rosa Delgado")
    enc, dek = bytes(legacy.display_name_enc), bytes(legacy.display_name_enc_dek)
    _run("--apply")
    legacy.refresh_from_db()
    assert bytes(legacy.display_name_enc) == enc
    assert bytes(legacy.display_name_enc_dek) == dek
    assert legacy.display_name == "Rosa Delgado"


def test_second_run_finds_nothing(member):
    _legacy(member, "Rosa Delgado")
    _run("--apply")
    out, _ = _run("--apply")
    assert "Nothing to index" in out


def test_already_indexed_rows_are_left_alone(person, member):
    before = bytes(person.name_bidx)
    _legacy(member, "Rosa Delgado")
    out, _ = _run("--apply")
    person.refresh_from_db()
    assert bytes(person.name_bidx) == before
    assert "Indexed 1" in out


def test_nameless_rows_stay_null(member):
    p = Person.objects.create(created_in_community=member.community, created_by=member)
    _run("--apply")
    p.refresh_from_db()
    assert p.name_bidx is None  # never an empty-string HMAC


def test_apply_fails_closed_without_the_key_and_writes_nothing(member, settings):
    legacy = _legacy(member, "Rosa Delgado")
    settings.BLIND_INDEX_KEY = ""
    with pytest.raises((CommandError, ImproperlyConfigured)):
        _run("--apply")
    legacy.refresh_from_db()
    assert legacy.name_bidx is None


def test_unreadable_row_does_not_stop_the_run_and_is_named_at_the_end(member):
    good = _legacy(member, "Rosa Delgado")
    bad = _legacy(member, "Lost Dek")
    Person.objects.filter(pk=bad.pk).update(display_name_enc_dek=None)  # ciphertext, no DEK
    err = io.StringIO()
    with pytest.raises(CommandError):
        call_command("backfill_person_bidx", "--apply", stdout=io.StringIO(), stderr=err)
    good.refresh_from_db()
    assert good.name_bidx is not None
    assert str(bad.pk) in err.getvalue()


def test_output_never_carries_a_name(member):
    _legacy(member, "Rosa Delgado")
    out, err = _run("--apply")
    assert "Rosa" not in out + err
    assert "Delgado" not in out + err


def test_reindex_recomputes_every_bidx_under_a_new_key(person, member, settings):
    old = bytes(person.name_bidx)
    settings.BLIND_INDEX_KEY = "a-rotated-blind-index-key"
    assert list(Person.objects.by_name("Maria Garcia", community=person.created_in_community)) == []
    _run("--reindex", "--apply")
    person.refresh_from_db()
    assert bytes(person.name_bidx) != old
    assert list(Person.objects.by_name("Maria Garcia", community=person.created_in_community)) == [person]


def test_reindex_dry_run_counts_every_named_row(person, member):
    _legacy(member, "Rosa Delgado")
    out, _ = _run("--reindex")
    assert "Dry run" in out
    assert "2" in out
