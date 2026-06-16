"""
Shared field encryption for sensitive PII — now with envelope support
(design §12.2 phase 1). Full replacement for the casework-deliverable
version; the original API (encrypt_str / decrypt_str / encrypt_json /
decrypt_json) is unchanged in signature and, with a single configured key,
unchanged in behavior.

Two layers:

  Direct fields (casework 🔒 columns today):
      ciphertext = Fernet(primary KEK).encrypt(plaintext)
      decrypt accepts ANY configured KEK (MultiFernet) → rotation-ready.

  Envelope fields (Need.on_behalf_of now; casework later):
      DEK        = fresh Fernet key per record
      ciphertext = Fernet(DEK).encrypt(plaintext)
      wrapped    = MultiFernet(KEKs).encrypt(DEK)      ← stored beside it
      shred      = delete `wrapped` → ciphertext is permanently opaque.

Keys come from settings.ENCRYPTION_KEYS (list, primary first), falling back
to the legacy single settings.ENCRYPTION_KEY. Read at call time on purpose:
tests and rotations may swap keys mid-process; the cost is negligible at
this scale.
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


# --------------------------------------------------------------- key access
def _key_bytes(key) -> bytes:
    return key.encode() if isinstance(key, str) else bytes(key)


def _keks() -> list[bytes]:
    keys = list(getattr(settings, "ENCRYPTION_KEYS", None) or [])
    if not keys:
        single = getattr(settings, "ENCRYPTION_KEY", "") or ""
        keys = [single] if single else []
    if not keys:
        raise ImproperlyConfigured("ENCRYPTION_KEYS/ENCRYPTION_KEY not set; encrypted fields are unavailable.")
    return [_key_bytes(k) for k in keys]


def kek_multifernet() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in _keks()])


def _primary_fernet() -> Fernet:
    return Fernet(_keks()[0])


# ------------------------------------------------- direct-KEK fields (as-is)
def encrypt_str(value: str | None) -> bytes | None:
    if value is None or value == "":
        return None
    return _primary_fernet().encrypt(value.encode("utf-8"))


def decrypt_str(blob: bytes | None) -> str | None:
    if not blob:
        return None
    try:
        return kek_multifernet().decrypt(bytes(blob)).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt field (no configured KEK matches — wrong or retired ENCRYPTION_KEY?)"
        ) from exc


def encrypt_json(value) -> bytes | None:
    if value in (None, "", {}, []):
        return None
    return encrypt_str(json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def decrypt_json(blob: bytes | None):
    raw = decrypt_str(blob)
    return None if raw is None else json.loads(raw)


# ----------------------------------------------------------- envelope layer
def generate_dek() -> bytes:
    return Fernet.generate_key()


def wrap_dek(dek: bytes) -> bytes:
    return kek_multifernet().encrypt(bytes(dek))


def unwrap_dek(wrapped: bytes) -> bytes:
    try:
        return kek_multifernet().decrypt(bytes(wrapped))
    except InvalidToken as exc:
        raise ValueError("Could not unwrap DEK (no configured KEK matches).") from exc


def rewrap_dek(wrapped: bytes) -> bytes:
    """KEK rotation: decrypt with any configured KEK, re-encrypt with the
    primary. MultiFernet.rotate does exactly this in one call."""
    try:
        return kek_multifernet().rotate(bytes(wrapped))
    except InvalidToken as exc:
        raise ValueError("Could not rotate DEK wrap (no configured KEK matches).") from exc


def envelope_encrypt_str(value: str | None) -> tuple[bytes | None, bytes | None]:
    """→ (ciphertext, wrapped_dek), both None for empty input."""
    if value is None or value == "":
        return None, None
    dek = generate_dek()
    ciphertext = Fernet(dek).encrypt(value.encode("utf-8"))
    return ciphertext, wrap_dek(dek)


def envelope_decrypt_str(ciphertext: bytes | None, wrapped_dek: bytes | None) -> str | None:
    if not ciphertext:
        return None
    if not wrapped_dek:
        raise ValueError("Envelope ciphertext without a DEK — row was crypto-shredded or the DEK column was lost.")
    dek = unwrap_dek(wrapped_dek)
    try:
        return Fernet(dek).decrypt(bytes(ciphertext)).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("DEK does not match this ciphertext.") from exc


def envelope_encrypt_json(value) -> tuple[bytes | None, bytes | None]:
    if value in (None, "", {}, []):
        return None, None
    return envelope_encrypt_str(json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def envelope_decrypt_json(ciphertext, wrapped_dek):
    raw = envelope_decrypt_str(ciphertext, wrapped_dek)
    return None if raw is None else json.loads(raw)
