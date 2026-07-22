"""
Read-only census of the §12.3 name blind index.

  python manage.py person_bidx_status

Counts Person rows by name/bidx state. `missing` = a name ciphertext exists
but the bidx is NULL (rows written before the index shipped) — those need the
gated Stage C backfill before name search is complete. `stray` = a bidx with
no name ciphertext (should always be 0; the shred/clear path nulls both).
"""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Census of the Person name blind index (§12.3)."

    def handle(self, *args, **opts):
        person = django_apps.get_model("people", "Person")
        empty = indexed = missing = stray = 0
        for obj in person.objects.only("pk", "display_name_enc", "name_bidx").iterator():
            has_name, has_bidx = bool(obj.display_name_enc), bool(obj.name_bidx)
            if has_name and has_bidx:
                indexed += 1
            elif has_name:
                missing += 1
            elif has_bidx:
                stray += 1
            else:
                empty += 1

        self.stdout.write(f"Person.name_bidx: empty={empty} indexed={indexed} missing={missing} stray={stray}")
        if stray:
            self.stderr.write(self.style.ERROR(f"{stray} row(s) carry a bidx with NO name — shred left residue; fix."))
        elif missing:
            self.stderr.write(
                self.style.WARNING(
                    f"{missing} named row(s) lack a bidx — name search is incomplete until the (gated) backfill runs."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Blind index complete — every named Person is searchable."))
