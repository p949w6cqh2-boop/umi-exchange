"""One-time credentials — issue and redeem (docs/specs/account-recovery.md, F0-a).

Every "hand someone a secret that gets them back in" path goes through here, so these rules hold
once instead of per feature:

  * the plaintext is returned to the caller exactly once and never stored — only its SHA-256;
  * codes use an alphabet with no 0/O and no 1/l/I, because a person reads them off paper;
  * comparison is hmac.compare_digest, never ==;
  * redemption is single-use and race-safe: a conditional UPDATE ... WHERE used_at IS NULL
    decides the winner, so two simultaneous redemptions cannot both succeed on any database;
  * expiry is per purpose (a paper code never expires; a coordinator reset dies in 15 minutes).

Callers own the audit event and must never put the plaintext in it (tests/test_audit_pii_hygiene.py).
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import RecoveryCredential

# Upper-case only, and without 0 O 1 I L: nothing a tired eye or a smudged print can confuse.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
GROUPS = 3
GROUP_SIZE = 4  # 12 symbols from 31 ≈ 59 bits; redemption is rate-limited on top (A1).

EXPIRY = {
    RecoveryCredential.PURPOSE_RECOVERY_CODE: None,
    RecoveryCredential.PURPOSE_COORDINATOR_RESET: timedelta(minutes=15),
    RecoveryCredential.PURPOSE_ADMIN_UNLOCK: timedelta(hours=1),
    RecoveryCredential.PURPOSE_CLAIM: timedelta(days=30),
}


def generate_code() -> str:
    """A fresh code in readable groups, e.g. K4M2-9XQ7-BT3W."""
    symbols = "".join(secrets.choice(ALPHABET) for _ in range(GROUPS * GROUP_SIZE))
    return "-".join(symbols[i : i + GROUP_SIZE] for i in range(0, len(symbols), GROUP_SIZE))


def normalize(code: str) -> str:
    """What the person typed, reduced to the symbols: case, spaces and dashes forgiven."""
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def hash_code(code: str) -> str:
    return hashlib.sha256(normalize(code).encode()).hexdigest()


def issue(user, purpose, *, issued_by=None):
    """Create a credential and return (row, plaintext). The plaintext exists only in this
    return value: show it once, then let it go.

    Re-issuing a purpose retires that user's earlier unused credentials of the same purpose,
    so a lost paper code stops working the moment a new one is printed.
    """
    if purpose not in EXPIRY:
        raise ValueError(f"unknown credential purpose: {purpose!r}")
    plaintext = generate_code()
    now = timezone.now()
    lifetime = EXPIRY[purpose]
    with transaction.atomic():
        RecoveryCredential.objects.filter(
            user=user, purpose=purpose, used_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=now)
        row = RecoveryCredential.objects.create(
            user=user,
            purpose=purpose,
            token_hash=hash_code(plaintext),
            expires_at=now + lifetime if lifetime else None,
            issued_by=issued_by,
            issued_by_label=getattr(issued_by, "display_name", "") or "",
        )
    return row, plaintext


def _live(user, purpose):
    now = timezone.now()
    return (
        RecoveryCredential.objects.filter(user=user, purpose=purpose, used_at__isnull=True, revoked_at__isnull=True)
        .exclude(expires_at__lte=now)
        .order_by("-created_at")
    )


def _claim(pk) -> bool:
    """Mark a credential used iff nobody else already has. The rowcount IS the race result."""
    return RecoveryCredential.objects.filter(pk=pk, used_at__isnull=True).update(used_at=timezone.now()) == 1


def redeem(user, purpose, plaintext):
    """Return the credential if `plaintext` is a live one for this user and purpose, marking it
    used; else None. Every failure looks the same to the caller: no reason is given, because a
    reason is an oracle."""
    if user is None or not plaintext:
        return None
    candidate = hash_code(plaintext)
    with transaction.atomic():
        for row in _live(user, purpose).select_for_update():
            if hmac.compare_digest(row.token_hash, candidate):
                if _claim(row.pk):
                    row.refresh_from_db()
                    return row
                return None
    return None


def purgeable():
    """Expired credentials nobody ever used. Used rows are never purged: they are the record
    that a recovery happened (archive semantics, keyring: archive not delete)."""
    return RecoveryCredential.objects.filter(used_at__isnull=True, expires_at__lte=timezone.now())
