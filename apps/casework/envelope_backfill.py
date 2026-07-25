"""
Reusable backfill logic for casework PII → envelope encryption (Stage C).

Lives outside the migration module so it's importable by the data migration,
the census command, and the tests alike. crypto is imported inside the
functions: it's a stateless, settings-keyed utility (not a model), resolved
at run time when the encryption keys are present (fail-closed otherwise).
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

BATCH_SIZE = 200

# (model_name, ciphertext_field, dek_field)
FIELD_MAP = [
    ("CaseFile", "summary_enc", "summary_enc_dek"),
    ("CaseNote", "body_enc", "body_enc_dek"),
    ("FollowUp", "detail_enc", "detail_enc_dek"),
    ("WarmHandoff", "summary_enc", "summary_enc_dek"),
]

# Fields that went straight from PLAINTEXT → envelope (never direct-KEK), so
# they are NOT part of the direct-KEK↔envelope loop above (feeding them to it
# would break the 0004 migration, which predates their columns). Censused only.
CENSUS_ONLY_FIELDS = [
    ("CaseFile", "emergency_justification_enc", "emergency_justification_enc_dek"),
]


def _iterate_pending(model, ct, dek, reverse, failed=None):
    """Yield locked batches still needing conversion. Forward: ciphertext
    present + DEK NULL. Reverse: DEK present. The shrinking selector makes
    the loop terminate and the whole operation idempotent/resumable.

    `failed` is a live set of pks the caller couldn't decrypt; they never get a
    DEK written, so without excluding them they'd keep matching the selector and
    re-select forever (an unreadable row = infinite loop). Excluding them lets
    the selector shrink to empty."""
    while True:
        with transaction.atomic():
            qs = model.objects.filter(**{f"{ct}__isnull": False})
            qs = qs.filter(**{f"{dek}__isnull": False}) if reverse else qs.filter(**{f"{dek}__isnull": True})
            if failed:
                qs = qs.exclude(pk__in=failed)
            rows = list(qs.select_for_update(skip_locked=True).only("pk", ct, dek)[:BATCH_SIZE])
            if not rows:
                return
            yield rows


def forward_func(apps, schema_editor=None):
    """Direct-KEK → envelope. `apps` may be the migration's historical
    registry or django.apps.apps (tests); both work because we touch only
    plain columns and write via .update()."""
    from apps.people import crypto

    for model_name, ct, dek in FIELD_MAP:
        model = apps.get_model("casework", model_name)
        converted = failed = 0
        failed_pks = set()
        for rows in _iterate_pending(model, ct, dek, reverse=False, failed=failed_pks):
            for obj in rows:
                try:
                    plain = crypto.decrypt_str(getattr(obj, ct))
                    ct_val, dek_val = crypto.envelope_encrypt_str(plain)
                except ValueError as exc:
                    failed += 1
                    failed_pks.add(obj.pk)
                    logger.warning(
                        "casework envelope backfill: %s %s unreadable, skipped (%s)",
                        model_name,
                        obj.pk,
                        exc,
                    )
                    continue
                # .update() bypasses Model.save() (and the CaseNote final
                # guard); both columns written together so the DEK persists.
                model.objects.filter(pk=obj.pk).update(**{ct: ct_val, dek: dek_val})
                converted += 1
        logger.info("casework envelope backfill: %s converted=%d failed=%d", model_name, converted, failed)
        if failed:
            logger.warning(
                "casework envelope backfill: %s left %d unreadable row(s) on direct-KEK — investigate before Stage E.",
                model_name,
                failed,
            )


def backfill_emergency_justification(apps, schema_editor=None):
    """Plaintext CaseFile.emergency_justification → envelope encryption (H-1).

    Separate from forward_func/FIELD_MAP: that path is direct-KEK→envelope; this
    field was never direct-KEK, it's plaintext→envelope. Reads the still-present
    plaintext column (dropped in the following migration) and writes the
    enc/dek columns. Idempotent/resumable — the selector (non-empty plaintext +
    NULL ciphertext) shrinks with every row, since envelope_encrypt_str of a
    non-empty value always yields a non-NULL ciphertext."""
    from apps.people import crypto

    model = apps.get_model("casework", "CaseFile")
    ct, dek = "emergency_justification_enc", "emergency_justification_enc_dek"
    converted = 0
    while True:
        with transaction.atomic():
            rows = list(
                model.objects.exclude(emergency_justification="")
                .filter(**{f"{ct}__isnull": True})
                .select_for_update(skip_locked=True)
                .only("pk", "emergency_justification")[:BATCH_SIZE]
            )
            if not rows:
                break
            for obj in rows:
                ct_val, dek_val = crypto.envelope_encrypt_str(obj.emergency_justification)
                model.objects.filter(pk=obj.pk).update(**{ct: ct_val, dek: dek_val})
                converted += 1
    logger.info("emergency_justification backfill: converted=%d", converted)


def reverse_emergency_justification(apps, schema_editor=None):
    """Envelope → plaintext, for unapplying the H-1 backfill (runs after the
    plaintext column is re-added by reversing the later drop migration)."""
    from apps.people import crypto

    model = apps.get_model("casework", "CaseFile")
    ct, dek = "emergency_justification_enc", "emergency_justification_enc_dek"
    while True:
        with transaction.atomic():
            rows = list(
                model.objects.filter(**{f"{dek}__isnull": False})
                .select_for_update(skip_locked=True)
                .only("pk", ct, dek)[:BATCH_SIZE]
            )
            if not rows:
                break
            for obj in rows:
                plain = crypto.envelope_decrypt_str(getattr(obj, ct), getattr(obj, dek))
                model.objects.filter(pk=obj.pk).update(emergency_justification=plain or "", **{ct: None, dek: None})


def reverse_func(apps, schema_editor=None):
    """Envelope → direct-KEK, for rolling Stage B/C back."""
    from apps.people import crypto

    for model_name, ct, dek in FIELD_MAP:
        model = apps.get_model("casework", model_name)
        reverted = failed = 0
        failed_pks = set()
        for rows in _iterate_pending(model, ct, dek, reverse=True, failed=failed_pks):
            for obj in rows:
                try:
                    plain = crypto.envelope_decrypt_str(getattr(obj, ct), getattr(obj, dek))
                    ct_val = crypto.encrypt_str(plain)
                except ValueError as exc:
                    failed += 1
                    failed_pks.add(obj.pk)
                    logger.warning(
                        "casework envelope reverse: %s %s unreadable, skipped (%s)",
                        model_name,
                        obj.pk,
                        exc,
                    )
                    continue
                model.objects.filter(pk=obj.pk).update(**{ct: ct_val, dek: None})
                reverted += 1
        logger.info("casework envelope reverse: %s reverted=%d failed=%d", model_name, reverted, failed)
