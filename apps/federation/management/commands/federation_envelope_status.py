"""
Read-only census of federation envelope state (§11: the same tooling that
covers every other envelope column). Federation payloads are envelope-only
(no legacy scheme): rows read empty (never exchanged / already shredded),
envelope (healthy), or unreadable (wrap lost or KEK retired too early).

  python manage.py federation_envelope_status
"""

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

FIELDS = [
    # (model, ciphertext_field, dek_field)
    ("FederatedMatch", "contact_payload_enc", "contact_payload_dek"),
    ("FederationEvent", "payload_enc", "payload_dek"),
]


class Command(BaseCommand):
    help = "Census of federation encrypted-payload state (envelope health)."

    def handle(self, *args, **opts):
        from apps.people import crypto

        all_clear = True
        for model_name, ct, dek in FIELDS:
            model = django_apps.get_model("federation", model_name)
            empty = envelope = unreadable = 0
            for obj in model.objects.only("pk", ct, dek).iterator():
                blob, wrapped = getattr(obj, ct), getattr(obj, dek)
                if not blob:
                    empty += 1
                    continue
                try:
                    crypto.envelope_decrypt_json(blob, wrapped)
                    envelope += 1
                except ValueError:
                    unreadable += 1
            ready = unreadable == 0
            all_clear = all_clear and ready
            self.stdout.write(
                f"{model_name}.{ct}: empty={empty} envelope={envelope} unreadable={unreadable}"
                f"{'' if ready else '  <-- investigate'}"
            )
        if all_clear:
            self.stdout.write(self.style.SUCCESS("All federation payloads are envelope-encrypted and readable."))
        else:
            self.stderr.write(
                self.style.WARNING(
                    "Unreadable federation payloads — investigate before retiring any KEK (do NOT proceed)."
                )
            )
