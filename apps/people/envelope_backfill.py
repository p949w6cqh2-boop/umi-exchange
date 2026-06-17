"""
Reusable backfill logic for Person PII → envelope encryption (Stage C).

Lives outside the migration module so it's importable by the data migration,
the census command, and the tests alike. crypto is imported inside the
functions (stateless, settings-keyed; fail-closed when keys are absent).

display_name / dob are strings; contact is JSON — hence the per-field codec.
No blind index here (person_name_bidx / §12.3 is a separate enhancement).
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

BATCH_SIZE = 200

# (ciphertext_field, dek_field, codec)  codec ∈ {"str", "json"}
FIELD_MAP = [
    ("display_name_enc", "display_name_enc_dek", "str"),
    ("contact_enc", "contact_enc_dek", "json"),
    ("dob_enc", "dob_enc_dek", "str"),
]


def _iterate_pending(model, ct, dek, reverse):
    """Yield locked batches still needing conversion. Forward: ciphertext
    present + DEK NULL. Reverse: DEK present. The shrinking selector makes
    the loop terminate and the whole operation idempotent/resumable."""
    while True:
        with transaction.atomic():
            qs = model.objects.filter(**{f"{ct}__isnull": False})
            qs = qs.filter(**{f"{dek}__isnull": False}) if reverse else qs.filter(**{f"{dek}__isnull": True})
            rows = list(qs.select_for_update(skip_locked=True).only("pk", ct, dek)[:BATCH_SIZE])
            if not rows:
                return
            yield rows


def forward_func(apps, schema_editor=None):
    """Direct-KEK → envelope for every Person PII field."""
    from apps.people import crypto

    model = apps.get_model("people", "Person")
    for ct, dek, codec in FIELD_MAP:
        converted = failed = 0
        for rows in _iterate_pending(model, ct, dek, reverse=False):
            for obj in rows:
                try:
                    if codec == "json":
                        plain = crypto.decrypt_json(getattr(obj, ct))
                        ct_val, dek_val = crypto.envelope_encrypt_json(plain)
                    else:
                        plain = crypto.decrypt_str(getattr(obj, ct))
                        ct_val, dek_val = crypto.envelope_encrypt_str(plain)
                except ValueError as exc:
                    failed += 1
                    logger.warning("person envelope backfill: %s %s unreadable, skipped (%s)", ct, obj.pk, exc)
                    continue
                # .update() writes both columns together so the DEK persists.
                model.objects.filter(pk=obj.pk).update(**{ct: ct_val, dek: dek_val})
                converted += 1
        logger.info("person envelope backfill: %s converted=%d failed=%d", ct, converted, failed)
        if failed:
            logger.warning(
                "person envelope backfill: %s left %d unreadable row(s) on direct-KEK — investigate before Stage E.",
                ct,
                failed,
            )


def reverse_func(apps, schema_editor=None):
    """Envelope → direct-KEK, for rolling Stage B/C back."""
    from apps.people import crypto

    model = apps.get_model("people", "Person")
    for ct, dek, codec in FIELD_MAP:
        reverted = failed = 0
        for rows in _iterate_pending(model, ct, dek, reverse=True):
            for obj in rows:
                try:
                    if codec == "json":
                        plain = crypto.envelope_decrypt_json(getattr(obj, ct), getattr(obj, dek))
                        ct_val = crypto.encrypt_json(plain)
                    else:
                        plain = crypto.envelope_decrypt_str(getattr(obj, ct), getattr(obj, dek))
                        ct_val = crypto.encrypt_str(plain)
                except ValueError as exc:
                    failed += 1
                    logger.warning("person envelope reverse: %s %s unreadable, skipped (%s)", ct, obj.pk, exc)
                    continue
                model.objects.filter(pk=obj.pk).update(**{ct: ct_val, dek: None})
                reverted += 1
        logger.info("person envelope reverse: %s reverted=%d failed=%d", ct, reverted, failed)
