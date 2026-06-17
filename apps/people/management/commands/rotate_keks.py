"""
KEK rotation, step 3 of the runbook: re-wrap every envelope DEK under the
NEW primary KEK. Touches only the tiny wrapped-DEK tokens — ciphertexts and
their per-record DEKs are untouched, which is the whole point of §12.2.

Extend ENVELOPE_DEK_FIELDS as more envelope columns arrive (casework next).
"""

import time

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.people import crypto

ENVELOPE_DEK_FIELDS = [
    # (app_label, model_name, dek_field)
    ("needs", "Need", "on_behalf_of_dek"),
    ("casework", "CaseFile", "summary_enc_dek"),
    ("casework", "CaseNote", "body_enc_dek"),
    ("casework", "FollowUp", "detail_enc_dek"),
    ("casework", "WarmHandoff", "summary_enc_dek"),
    ("people", "Person", "display_name_enc_dek"),
    ("people", "Person", "contact_enc_dek"),
    ("people", "Person", "dob_enc_dek"),
]


class Command(BaseCommand):
    help = "Re-wrap all envelope DEKs under the primary KEK (§12.2 rotation)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--sleep", type=float, default=0.0)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        grand_total = 0
        for app_label, model_name, dek_field in ENVELOPE_DEK_FIELDS:
            model = django_apps.get_model(app_label, model_name)
            pending = model.objects.filter(**{f"{dek_field}__isnull": False}).order_by("pk")
            if opts["dry_run"]:
                self.stdout.write(f"{app_label}.{model_name}.{dek_field}: {pending.count()} wrap(s) would be rotated.")
                continue

            total, last_pk = 0, None
            while True:
                qs = pending.filter(pk__gt=last_pk) if last_pk else pending
                with transaction.atomic():
                    # NOTE: do NOT use skip_locked here. The cursor advances by
                    # pk, so a skipped (locked) row — whose pk is below rows we
                    # do process — would fall behind last_pk and never be
                    # revisited, leaving its DEK wrapped under the old KEK
                    # forever. Blocking briefly on a locked row guarantees every
                    # wrap is rotated; batches stay small to keep locks short.
                    rows = list(qs.select_for_update()[: opts["batch_size"]])
                    if not rows:
                        break
                    for obj in rows:
                        wrapped = getattr(obj, dek_field)
                        setattr(obj, dek_field, crypto.rewrap_dek(wrapped))
                        obj.save(update_fields=[dek_field])
                        total += 1
                        last_pk = obj.pk
                if opts["sleep"]:
                    time.sleep(opts["sleep"])
            grand_total += total
            self.stdout.write(self.style.SUCCESS(f"{app_label}.{model_name}: rotated {total} DEK wrap(s)."))
        self.stdout.write(self.style.SUCCESS(f"Total: {grand_total}."))
