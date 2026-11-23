"""
§12.3 Stage C: give every named Person row its name blind index.

    python manage.py backfill_person_bidx                     # dry run: counts only
    python manage.py backfill_person_bidx --apply             # index the rows that lack one
    python manage.py backfill_person_bidx --reindex --apply   # recompute every bidx (new BLIND_INDEX_KEY)

Rows written before Stage B carry a name ciphertext and a NULL `name_bidx`, so `by_name()` cannot
find them; `person_bidx_status` counts them as `missing`. This decrypts each such name, computes the
HMAC under BLIND_INDEX_KEY and writes `name_bidx`, and nothing else: the ciphertext and its DEK are
not rewritten. `--reindex` does the same for every named row, which is how a BLIND_INDEX_KEY
rotation is finished (set the new key, then run this).

Fails closed: `--apply` refuses to start without a usable BLIND_INDEX_KEY. A row whose name will not
decrypt is skipped, the run goes on, and it ends in an error naming each skipped row by id (the
rotate_keks shape). No name is ever printed. A second run finds nothing to do.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.people import crypto
from apps.people.models import Person

BATCH_SIZE = 200


def _pending(reindex):
    named = Person.objects.filter(display_name_enc__isnull=False)
    return named if reindex else named.filter(name_bidx__isnull=True)


class Command(BaseCommand):
    help = "Backfill Person.name_bidx (§12.3 Stage C). Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the index. Without it, only count.")
        parser.add_argument(
            "--reindex",
            action="store_true",
            help="Recompute every named row's bidx, not only the missing ones (after rotating BLIND_INDEX_KEY).",
        )
        parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)

    def handle(self, *args, apply=False, reindex=False, batch_size=BATCH_SIZE, **opts):
        what = "named Person row(s)" if reindex else "named Person row(s) without a blind index"
        count = _pending(reindex).count()
        if not count:
            self.stdout.write("Nothing to index: every named Person row already has its blind index.")
            return
        if not apply:
            self.stdout.write(f"Dry run: nothing changed. {count} {what}. Run again with --apply to index them.")
            return

        try:
            crypto.name_blind_index("key check")
        except Exception as exc:
            raise CommandError(f"Refusing to start: {exc}") from exc

        indexed, failures, last_pk = 0, [], None
        while True:
            qs = _pending(reindex).order_by("pk")
            if last_pk is not None:
                qs = qs.filter(pk__gt=last_pk)
            with transaction.atomic():
                # No skip_locked: the cursor advances by pk, so a skipped (locked) row would fall
                # behind last_pk and never be revisited. Block briefly instead; batches stay small.
                rows = list(
                    qs.select_for_update(of=("self",)).only("pk", "display_name_enc", "display_name_enc_dek")[
                        :batch_size
                    ]
                )
                if not rows:
                    break
                for obj in rows:
                    last_pk = obj.pk  # advance past a failed row too, or the loop never ends
                    try:
                        bidx = crypto.name_blind_index(obj.display_name)
                    except ValueError:
                        failures.append(str(obj.pk))
                        continue
                    Person.objects.filter(pk=obj.pk).update(name_bidx=bidx)
                    indexed += 1

        self.stdout.write(self.style.SUCCESS(f"Indexed {indexed} {what}."))
        if failures:
            self.stderr.write("Could not read the name on these Person rows (left without a blind index):")
            for pk in failures:
                self.stderr.write(f"  {pk}")
            raise CommandError(
                f"{len(failures)} Person row(s) could not be indexed (listed above by id). Every other row was. "
                "Run people_envelope_status to see why their names will not decrypt."
            )
