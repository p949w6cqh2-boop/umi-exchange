"""
Read-only census of Person PII encryption state (the Stage-E gate).

  python manage.py people_envelope_status

Per field: empty / legacy (direct-KEK) / envelope / unreadable. The Person
Stage E contract (removing the legacy read branch) is safe only when every
field shows legacy=0 and unreadable=0. NOTE: casework's case-detail view reads
Person.display_name, so a DEK-less Person row would fail there too post-contract.
"""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

from apps.people.envelope_backfill import FIELD_MAP


class Command(BaseCommand):
    help = "Census of Person encrypted-field state (legacy vs envelope)."

    def handle(self, *args, **opts):
        from apps.people import crypto

        person = django_apps.get_model("people", "Person")
        all_clear = True
        for ct, dek, codec in FIELD_MAP:
            empty = legacy = envelope = unreadable = 0
            for obj in person.objects.only("pk", ct, dek).iterator():
                blob, wrapped = getattr(obj, ct), getattr(obj, dek)
                if not blob:
                    empty += 1
                    continue
                try:
                    if wrapped:
                        (crypto.envelope_decrypt_json if codec == "json" else crypto.envelope_decrypt_str)(
                            blob, wrapped
                        )
                        envelope += 1
                    else:
                        (crypto.decrypt_json if codec == "json" else crypto.decrypt_str)(blob)
                        legacy += 1
                except ValueError:
                    unreadable += 1
            ready = legacy == 0 and unreadable == 0
            all_clear = all_clear and ready
            self.stdout.write(
                f"Person.{ct}: empty={empty} legacy={legacy} "
                f"envelope={envelope} unreadable={unreadable}"
                f"{'' if ready else '  <-- not ready'}"
            )

        if all_clear:
            self.stdout.write(self.style.SUCCESS("All Person PII is envelope-encrypted — Stage E is safe."))
        else:
            self.stderr.write(self.style.WARNING("Legacy or unreadable rows remain — do NOT run Person Stage E yet."))
