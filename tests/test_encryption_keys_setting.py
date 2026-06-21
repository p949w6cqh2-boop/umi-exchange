"""ENCRYPTION_KEYS env wiring (rotation prerequisite).

Before this, settings never read a key *list* from the environment, so
rotate_keks / old-KEK retirement (which need ENCRYPTION_KEYS=[new, old]) were
un-runnable in production. These pin the wiring + the MultiFernet behavior.
"""

import pytest
from cryptography.fernet import Fernet
from django.conf import settings

from apps.people import crypto


def test_encryption_keys_setting_exists_as_list():
    # Wired in base.py via env.list(...); default [] in dev.
    assert isinstance(settings.ENCRYPTION_KEYS, list)


def test_keks_prefers_key_list_and_reads_either_key(settings):
    new = Fernet.generate_key().decode()
    old = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new, old]  # primary first
    settings.ENCRYPTION_KEY = ""

    # New writes use the primary (new) key and round-trip.
    blob = crypto.encrypt_str("hello")
    assert crypto.decrypt_str(blob) == "hello"

    # A value still wrapped under the OLD key remains readable (MultiFernet) —
    # this is exactly what lets rotate_keks run before the old KEK is dropped.
    legacy = Fernet(old.encode()).encrypt(b"legacy")
    assert crypto.decrypt_str(legacy) == "legacy"


def test_dropping_old_key_makes_old_only_ciphertext_unreadable(settings):
    new = Fernet.generate_key().decode()
    old = Fernet.generate_key().decode()
    only_old = Fernet(old.encode()).encrypt(b"secret")

    settings.ENCRYPTION_KEYS = [new]  # old KEK retired
    settings.ENCRYPTION_KEY = ""
    # Proves the retirement gate matters: anything still under the old key alone
    # is unrecoverable once the old KEK is dropped — hence rotate_keks first.
    with pytest.raises(ValueError):
        crypto.decrypt_str(only_old)
