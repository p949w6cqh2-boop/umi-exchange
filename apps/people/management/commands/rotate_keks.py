"""
KEK rotation, step 3 of the runbook: re-wrap every envelope DEK under the
NEW primary KEK. Touches only the tiny wrapped-DEK tokens — ciphertexts and
their per-record DEKs are untouched, which is the whole point of §12.2.

Extend ENVELOPE_DEK_FIELDS as more envelope columns arrive (casework next).
"""

import time

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.people import crypto

ENVELOPE_DEK_FIELDS = [
    # (app_label, model_name, dek_field)
    ("needs", "Need", "on_behalf_of_dek"),
    ("casework", "CaseFile", "summary_enc_dek"),
    ("casework", "CaseFile", "emergency_justification_enc_dek"),
    ("casework", "CaseNote", "body_enc_dek"),
    ("casework", "FollowUp", "detail_enc_dek"),
    ("casework", "WarmHandoff", "summary_enc_dek"),
    ("federation", "FederatedMatch", "contact_payload_dek"),
    ("federation", "FederationEvent", "payload_dek"),
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
        # One wrap no configured KEK opens (a row restored from an old dump, say) used to abort the
        # run, leaving every later row under the old key and naming none of them (2026-10 bug hunt,
        # L27). Now the run goes on, and fails at the end, naming each row, so the old KEK stays.
        failures = []
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
                        last_pk = obj.pk  # advance past a failed row too, or the loop never ends
                        try:
                            rewrapped = crypto.rewrap_dek(getattr(obj, dek_field))
                        except ValueError:
                            failures.append(f"{app_label}.{model_name}.{dek_field} {obj.pk}")
                            continue
                        # .update() bypasses Model.save() — and with it the
                        # CaseNote A7 immutability guard, which would raise on a
                        # finalized note and abort rotation partway (leaving later
                        # models un-rotated). We touch only the wrapped-DEK token;
                        # the row is already locked by select_for_update above.
                        model.objects.filter(pk=obj.pk).update(**{dek_field: rewrapped})
                        total += 1
                if opts["sleep"]:
                    time.sleep(opts["sleep"])
            grand_total += total
            self.stdout.write(self.style.SUCCESS(f"{app_label}.{model_name}: rotated {total} DEK wrap(s)."))
        self.stdout.write(self.style.SUCCESS(f"Total: {grand_total}."))
        if failures:
            self.stderr.write("Could not re-wrap (no configured KEK opens them):")
            for row in failures:
                self.stderr.write(f"  {row}")
            raise CommandError(
                f"{len(failures)} DEK wrap(s) could not be rotated (listed above). Every other row was. "
                "Keep the old KEK configured until these rows are dealt with."
            )
