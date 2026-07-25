"""
Envelope backfill must terminate on an unreadable row (bug-hunt batch 1, #11).

forward_func's selector (ciphertext present + DEK NULL) is re-evaluated every
pass. A row whose ciphertext can't be decrypted (retired/wrong KEK, corrupt
blob) is caught and *skipped without writing its DEK*, so it keeps matching the
selector and is re-selected forever — an infinite loop that hangs the migration
and the deploy. skip_locked can't exclude it (no other txn holds it).

Test strategy: cap crypto.decrypt_str call count. A correct backfill touches
each row about once and finishes; the buggy loop blows past the cap.
"""

import pytest
from cryptography.fernet import Fernet
from django.apps import apps as django_apps

from apps.casework.envelope_backfill import forward_func
from apps.casework.models import CaseFile
from apps.people import crypto

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


def _legacy_case(world, blob):
    case = CaseFile.objects.create(
        community=world.community,
        subject_person=world.person,
        opened_by=world.coordinator,
        assigned_to=world.coordinator,
        consent=world.consent,
    )
    CaseFile.objects.filter(pk=case.pk).update(summary_enc=blob, summary_enc_dek=None)
    return case


def test_casework_backfill_terminates_on_unreadable_row(world, monkeypatch):
    good = _legacy_case(world, crypto.encrypt_str("real summary"))
    stranger_blob = Fernet(Fernet.generate_key()).encrypt(b"opaque")  # not under any configured KEK
    bad = _legacy_case(world, stranger_blob)

    _cap_decrypt(monkeypatch)
    try:
        forward_func(django_apps)
    except _LoopExceededError as exc:
        pytest.fail(str(exc))

    good.refresh_from_db()
    bad.refresh_from_db()
    assert good.summary_enc_dek is not None  # readable row converted to envelope
    assert bad.summary_enc_dek is None  # unreadable row left as-is, not retried forever
