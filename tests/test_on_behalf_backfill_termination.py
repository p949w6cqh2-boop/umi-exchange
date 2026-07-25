"""
migrate_on_behalf_envelope must terminate on an unreadable row (batch 1, #11).

The command's while-loop selects rows whose DEK is NULL; an undecryptable row
is caught and appended to `failed` but never .save()'d, so it stays DEK-NULL and
is re-selected on every pass — an infinite loop that wedges the deploy. Cap
crypto.decrypt_str to prove the command finishes.
"""

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command

from apps.needs.models import Need
from apps.people import crypto

from .conftest import NeedFactory

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


def test_on_behalf_backfill_terminates_on_unreadable_row(settings, monkeypatch):
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()

    good = NeedFactory()
    Need.objects.filter(pk=good.pk).update(on_behalf_of=crypto.encrypt_str("Real Name"), on_behalf_of_dek=None)
    bad = NeedFactory()
    stranger_blob = Fernet(Fernet.generate_key()).encrypt(b"opaque")  # not under any configured KEK
    Need.objects.filter(pk=bad.pk).update(on_behalf_of=stranger_blob, on_behalf_of_dek=None)

    _cap_decrypt(monkeypatch)
    try:
        call_command("migrate_on_behalf_envelope")
    except _LoopExceededError as exc:
        pytest.fail(str(exc))

    good.refresh_from_db()
    bad.refresh_from_db()
    assert good.on_behalf_of_dek is not None  # readable row converted to envelope
    assert bad.on_behalf_of_dek is None  # unreadable row left as-is, not retried forever
