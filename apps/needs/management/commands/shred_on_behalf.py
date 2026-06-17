"""
Crypto-shred (§12.2 / §10.7): destroy the per-need DEK so the encrypted
name is unrecoverable — immediately in the live DB, completely once backups
age out of retention. Nulls both columns (an unreadable ciphertext tombstone
has no value) and writes an audit row recording only the need id.

  python manage.py shred_on_behalf --need <uuid> [--need <uuid> …] \
      [--reason erasure_request]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.audit.services import emit
from apps.needs.models import Need


class Command(BaseCommand):
    help = "Crypto-shred Need.on_behalf_of for the given need id(s)."

    def add_arguments(self, parser):
        parser.add_argument("--need", action="append", required=True, dest="need_ids", metavar="UUID")
        parser.add_argument("--reason", default="erasure_request")

    def handle(self, *args, **opts):
        for need_id in opts["need_ids"]:
            try:
                need = Need.objects.get(pk=need_id)
            except (Need.DoesNotExist, ValueError) as exc:
                raise CommandError(f"Unknown need {need_id}") from exc
            if not need.on_behalf_of and not need.on_behalf_of_dek:
                self.stdout.write(f"{need_id}: nothing to shred.")
                continue
            need.on_behalf_of = None
            need.on_behalf_of_dek = None
            need.save(update_fields=["on_behalf_of", "on_behalf_of_dek"])
            emit("need.on_behalf_shredded", need, details={"reason": opts["reason"][:200]})
            self.stdout.write(self.style.SUCCESS(f"{need_id}: shredded."))
