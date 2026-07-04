"""
Read-only census of casework PII encryption state (the Stage D gate for E).

  python manage.py casework_envelope_status

Per field: empty / legacy (direct-KEK) / envelope / unreadable. Stage E
(removing the legacy read branch) is safe only when every field shows
legacy=0 and unreadable=0.
"""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

from apps.casework.envelope_backfill import CENSUS_ONLY_FIELDS, FIELD_MAP


class Command(BaseCommand):
    help = "Census of casework encrypted-field state (legacy vs envelope)."

    def handle(self, *args, **opts):
        from apps.people import crypto

        all_clear = True
        for model_name, ct, dek in FIELD_MAP + CENSUS_ONLY_FIELDS:
            model = django_apps.get_model("casework", model_name)
            empty = legacy = envelope = unreadable = 0
            for obj in model.objects.only("pk", ct, dek).iterator():
                blob, wrapped = getattr(obj, ct), getattr(obj, dek)
                if not blob:
                    empty += 1
                    continue
                try:
                    if wrapped:
                        crypto.envelope_decrypt_str(blob, wrapped)
                        envelope += 1
                    else:
                        crypto.decrypt_str(blob)
                        legacy += 1
                except ValueError:
                    unreadable += 1
            ready = legacy == 0 and unreadable == 0
            all_clear = all_clear and ready
            self.stdout.write(
                f"{model_name}.{ct}: empty={empty} legacy={legacy} "
                f"envelope={envelope} unreadable={unreadable}"
                f"{'' if ready else '  <-- not ready'}"
            )

        if all_clear:
            self.stdout.write(self.style.SUCCESS("All casework PII is envelope-encrypted — Stage E is safe."))
        else:
            self.stderr.write(self.style.WARNING("Legacy or unreadable rows remain — do NOT run Stage E yet."))
