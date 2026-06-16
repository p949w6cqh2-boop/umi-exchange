"""
§12.2 stage 3 — backfill legacy direct-KEK rows into envelopes (and the
emergency reverse). Batched, row-locked, resumable, idempotent.

  python manage.py migrate_on_behalf_envelope                # forward backfill
  python manage.py migrate_on_behalf_envelope --dry-run      # count only
  python manage.py migrate_on_behalf_envelope --verify       # readability census
  python manage.py migrate_on_behalf_envelope --to-legacy    # EMERGENCY rollback:
        re-encrypts envelope rows under the primary KEK directly, so a
        pre-envelope code release can read them again (stage-2 rollback).

Safe to stop and re-run at any point: forward mode only selects rows whose
DEK is NULL; reverse mode only rows whose DEK is set.
"""

import time

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.needs.models import Need
from apps.people import crypto


class Command(BaseCommand):
    help = "Backfill Need.on_behalf_of into envelope encryption (§12.2)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--sleep", type=float, default=0.0, help="Seconds between batches (be kind to prod).")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--verify", action="store_true", help="Read-only census: legacy/envelope/unreadable.")
        parser.add_argument("--to-legacy", action="store_true", help="Emergency reverse for stage-2 rollback.")

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if opts["verify"]:
            return self._verify()

        reverse = opts["to_legacy"]
        base = Need.objects.filter(on_behalf_of__isnull=False)
        pending = base.filter(on_behalf_of_dek__isnull=False) if reverse else base.filter(on_behalf_of_dek__isnull=True)

        if opts["dry_run"]:
            self.stdout.write(f"{pending.count()} row(s) would be {'reverted' if reverse else 'backfilled'}.")
            return

        total, failed = 0, []
        while True:
            with transaction.atomic():
                rows = list(pending.select_for_update(skip_locked=True)[: opts["batch_size"]])
                if not rows:
                    break
                for need in rows:
                    try:
                        if reverse:
                            plain = crypto.envelope_decrypt_str(need.on_behalf_of, need.on_behalf_of_dek)
                            need.on_behalf_of = crypto.encrypt_str(plain)
                            need.on_behalf_of_dek = None
                        else:
                            plain = crypto.decrypt_str(need.on_behalf_of)
                            (need.on_behalf_of, need.on_behalf_of_dek) = crypto.envelope_encrypt_str(plain)
                        need.save(update_fields=["on_behalf_of", "on_behalf_of_dek"])
                        total += 1
                    except ValueError as exc:  # undecryptable row: report, continue
                        failed.append((str(need.pk), str(exc)))
            self.stdout.write(f"  …{total} done")
            if opts["sleep"]:
                time.sleep(opts["sleep"])

        self.stdout.write(self.style.SUCCESS(f"{'Reverted' if reverse else 'Backfilled'} {total} row(s)."))
        if failed:
            self.stderr.write(
                self.style.WARNING(
                    f"{len(failed)} row(s) could not be decrypted and were left untouched — investigate before stage 4:"
                )
            )
            for pk, err in failed[:20]:
                self.stderr.write(f"  {pk}: {err}")

    # ------------------------------------------------------------------
    def _verify(self):
        legacy = envelope = unreadable = empty = 0
        for need in Need.objects.only("id", "on_behalf_of", "on_behalf_of_dek").iterator():
            if not need.on_behalf_of:
                empty += 1
                continue
            try:
                if need.on_behalf_of_dek:
                    crypto.envelope_decrypt_str(need.on_behalf_of, need.on_behalf_of_dek)
                    envelope += 1
                else:
                    crypto.decrypt_str(need.on_behalf_of)
                    legacy += 1
            except ValueError:
                unreadable += 1
        self.stdout.write(f"empty={empty}  legacy={legacy}  envelope={envelope}  unreadable={unreadable}")
        if unreadable:
            self.stderr.write(self.style.WARNING("Unreadable rows exist — wrong/retired KEK or corrupt data."))
        elif legacy == 0:
            self.stdout.write(self.style.SUCCESS("All populated rows are envelopes — stage 4 (cleanup) is safe."))
