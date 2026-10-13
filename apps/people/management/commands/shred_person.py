"""
Erase one person (§5.8 / privacy page; 2026-10 bug hunt, L16): crypto-shred their name, contact
and date of birth (clearing the name's blind index), every record merged into theirs, and every
case about them. Writes audit rows holding only ids, counts and the reason.

Refuses, changing nothing, under a legal hold or while one of their cases is still open.
Erasure is complete once every backup taken before the shred has aged out
(docs/runbooks/key-rotation.md).

  python manage.py shred_person --person <uuid> [--person <uuid> ...] \
      [--reason erasure_request|steward_decision]
"""

from django.core.management.base import BaseCommand, CommandError

from apps.common.ids import parse_uuid
from apps.people.erasure import REASONS, ErasureRefusedError, shred_person
from apps.people.models import Person


class Command(BaseCommand):
    help = "Crypto-shred one person's identity and every case about them."

    def add_arguments(self, parser):
        parser.add_argument("--person", action="append", required=True, dest="person_ids", metavar="UUID")
        parser.add_argument("--reason", choices=REASONS, default="erasure_request")

    def handle(self, *args, **opts):
        for raw in opts["person_ids"]:
            pk = parse_uuid(raw)
            person = Person.objects.filter(pk=pk).first() if pk else None
            if person is None:
                raise CommandError(f"Unknown person {raw}")
            try:
                cases = shred_person(person, reason=opts["reason"])
            except ErasureRefusedError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(f"{person.pk}: shredded, with {cases} case(s) about them."))
