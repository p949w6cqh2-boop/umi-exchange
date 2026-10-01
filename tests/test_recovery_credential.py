"""F0-a — the one-time credential model (docs/specs/account-recovery.md §One credential model).

One table serves recovery codes, coordinator resets, admin unlocks and claim links: a secret tied
to a user, hashed at rest, single-use, with a per-purpose expiry. These tests pin the properties
every later feature (A1, A2, A4, claim links) will lean on.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts import credentials
from apps.accounts.credentials import ALPHABET, generate_code, issue, normalize, redeem
from apps.accounts.models import RecoveryCredential
from tests.factories import MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


# ── The code itself ────────────────────────────────────────────


def test_code_is_three_groups_of_four_in_the_unambiguous_alphabet():
    code = generate_code()
    groups = code.split("-")
    assert [len(g) for g in groups] == [4, 4, 4]
    for ch in code.replace("-", ""):
        assert ch in ALPHABET


def test_alphabet_has_no_characters_a_person_confuses_on_paper():
    for ch in "0O1lI":
        assert ch not in ALPHABET


def test_codes_do_not_repeat():
    assert len({generate_code() for _ in range(200)}) == 200


def test_normalize_forgives_case_spaces_and_dashes():
    assert normalize(" k4m2 9xq7-bt3w ") == "K4M29XQ7BT3W"


# ── Issuing ────────────────────────────────────────────────────


def test_plaintext_is_never_stored():
    user = UserFactory()
    cred, plaintext = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    row = RecoveryCredential.objects.get(pk=cred.pk)
    stored = " ".join(str(v) for v in RecoveryCredential.objects.filter(pk=cred.pk).values().first().values())
    assert normalize(plaintext) not in stored
    assert plaintext not in stored
    assert row.token_hash == credentials.hash_code(plaintext)
    assert len(row.token_hash) == 64


def test_expiry_follows_the_purpose():
    user = UserFactory()
    now = timezone.now()
    code, _ = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    reset, _ = issue(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET)
    unlock, _ = issue(user, RecoveryCredential.PURPOSE_ADMIN_UNLOCK)
    claim, _ = issue(user, RecoveryCredential.PURPOSE_CLAIM)
    assert code.expires_at is None  # a code in a wallet, needed in eight months
    assert timedelta(minutes=14) < reset.expires_at - now <= timedelta(minutes=15, seconds=5)
    assert timedelta(minutes=59) < unlock.expires_at - now <= timedelta(hours=1, seconds=5)
    assert timedelta(days=29) < claim.expires_at - now <= timedelta(days=30, seconds=5)


def test_issuer_label_survives_the_issuers_deletion():
    user = UserFactory()
    coordinator = MemberFactory(role="coordinator", display_name="Dan")
    cred, _ = issue(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET, issued_by=coordinator)
    assert cred.issued_by_label == "Dan"
    coordinator.delete()
    cred.refresh_from_db()
    assert cred.issued_by is None
    assert cred.issued_by_label == "Dan"


def test_reissuing_a_recovery_code_retires_the_old_one():
    user = UserFactory()
    _, old = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    _, new = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, old) is None
    assert redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, new) is not None


def test_reissue_does_not_touch_other_purposes_or_other_users():
    user, other = UserFactory(), UserFactory()
    _, reset = issue(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET)
    _, others_code = issue(other, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert redeem(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET, reset) is not None
    assert redeem(other, RecoveryCredential.PURPOSE_RECOVERY_CODE, others_code) is not None


# ── Redeeming ──────────────────────────────────────────────────


def test_right_code_redeems_once_and_records_when():
    user = UserFactory()
    cred, plaintext = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    won = redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext)
    assert won is not None and won.pk == cred.pk
    cred.refresh_from_db()
    assert cred.used_at is not None


def test_code_typed_loosely_still_redeems():
    user = UserFactory()
    _, plaintext = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext.lower().replace("-", " ")) is not None


def test_used_code_is_rejected():
    user = UserFactory()
    _, plaintext = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext) is not None
    assert redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext) is None


def test_expired_credential_is_rejected():
    user = UserFactory()
    cred, plaintext = issue(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET)
    RecoveryCredential.objects.filter(pk=cred.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    assert redeem(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET, plaintext) is None


def test_wrong_code_is_rejected():
    user = UserFactory()
    issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, generate_code()) is None


def test_code_only_works_for_its_own_user():
    owner, stranger = UserFactory(), UserFactory()
    _, plaintext = issue(owner, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert redeem(stranger, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext) is None
    assert redeem(owner, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext) is not None


def test_code_only_works_for_its_own_purpose():
    user = UserFactory()
    _, plaintext = issue(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET)
    assert redeem(user, RecoveryCredential.PURPOSE_ADMIN_UNLOCK, plaintext) is None


def test_comparison_is_constant_time():
    user = UserFactory()
    _, plaintext = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    with mock.patch.object(credentials.hmac, "compare_digest", wraps=credentials.hmac.compare_digest) as cmp:
        redeem(user, RecoveryCredential.PURPOSE_RECOVERY_CODE, plaintext)
    assert cmp.called


def test_two_redemptions_racing_yield_exactly_one_winner():
    """The race, made deterministic: both callers have already matched the row; only the
    conditional claim decides. The loser must get None even though its match was valid."""
    user = UserFactory()
    cred, _ = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    assert credentials._claim(cred.pk) is True
    assert credentials._claim(cred.pk) is False


# ── Purge: archive semantics ───────────────────────────────────


def test_purge_is_a_dry_run_by_default_and_spares_used_rows():
    user = UserFactory()
    dead, _ = issue(user, RecoveryCredential.PURPOSE_COORDINATOR_RESET)
    used, used_plain = issue(user, RecoveryCredential.PURPOSE_ADMIN_UNLOCK)
    live, _ = issue(user, RecoveryCredential.PURPOSE_RECOVERY_CODE)
    redeem(user, RecoveryCredential.PURPOSE_ADMIN_UNLOCK, used_plain)
    past = timezone.now() - timedelta(days=1)
    RecoveryCredential.objects.filter(pk__in=[dead.pk, used.pk]).update(expires_at=past)

    call_command("purge_recovery_credentials")
    assert RecoveryCredential.objects.filter(pk=dead.pk).exists()  # dry run touched nothing

    call_command("purge_recovery_credentials", "--apply")
    assert not RecoveryCredential.objects.filter(pk=dead.pk).exists()
    assert RecoveryCredential.objects.filter(pk=used.pk).exists()  # the audit trail needs it
    assert RecoveryCredential.objects.filter(pk=live.pk).exists()
