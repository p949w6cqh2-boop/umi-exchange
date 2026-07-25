"""
Person envelope backfill must terminate on an unreadable row (batch 1, #11).

Same infinite-loop shape as the casework backfill: _iterate_pending's forward
selector (ciphertext present + DEK NULL) is re-evaluated each pass, and a row
that fails to decrypt is skipped without writing its DEK, so it is re-selected
forever. Cap crypto.decrypt_str to prove termination.
"""

import pytest
from cryptography.fernet import Fernet
from django.apps import apps as django_apps

from apps.people import crypto
from apps.people.envelope_backfill import forward_func
from apps.people.models import Person

pytestmark = pytest.mark.django_db


class _LoopExceededError(Exception):
    pass


def _cap_decrypt(monkeypatch, cap=25):
    real = crypto.decrypt_str
    n = {"calls": 0}

    def capped(*args, **kwargs):
        n["calls"] += 1
        if n["calls"] > cap:
            raise _LoopExceededError(f"crypto.decrypt_str called >{cap} times — backfill did not terminate")
        return real(*args, **kwargs)

    monkeypatch.setattr(crypto, "decrypt_str", capped)
    return n


def _legacy_person(member, name_blob):
    p = Person.objects.create(created_in_community=member.community, created_by=member)
    Person.objects.filter(pk=p.pk).update(display_name_enc=name_blob, display_name_enc_dek=None)
    return p


def test_people_backfill_terminates_on_unreadable_row(member, monkeypatch):
    good = _legacy_person(member, crypto.encrypt_str("Real Person"))
    stranger_blob = Fernet(Fernet.generate_key()).encrypt(b"opaque")  # not under any configured KEK
    bad = _legacy_person(member, stranger_blob)

    _cap_decrypt(monkeypatch)
    try:
        forward_func(django_apps)
    except _LoopExceededError as exc:
        pytest.fail(str(exc))

    good.refresh_from_db()
    bad.refresh_from_db()
    assert good.display_name_enc_dek is not None  # readable row converted
    assert bad.display_name_enc_dek is None  # unreadable row left as-is
