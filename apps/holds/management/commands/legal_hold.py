"""Place, release and list legal holds (docs/specs/legal-hold.md; incident-response.md Part 2).

  python manage.py legal_hold place --scope case --id <uuid> --reference "subpoena served 10-03" --by <username>
  python manage.py legal_hold place --scope community --id <slug> --reference "..." --by <username>
  python manage.py legal_hold place --scope all --reference "..." --by <username>
  python manage.py legal_hold release <hold-uuid> --by <username>
  python manage.py legal_hold list [--all]

Placing and releasing are audited (scope only: the reference never enters the append-only log).
A hold is never deleted; releasing it stamps released_at.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.audit.services import emit
from apps.holds.models import LegalHold


class Command(BaseCommand):
    help = "Place, release or list legal holds that pause automated deletion for a scope."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        place = sub.add_parser("place")
        place.add_argument("--scope", required=True, choices=[c for c, _ in LegalHold.SCOPE_CHOICES])
        place.add_argument("--id", dest="target", help="uuid of the case/person/need, or the community slug")
        place.add_argument("--reference", required=True, help="the matter reference (no personal details)")
        place.add_argument("--by", required=True, help="username of the steward placing it")
        release = sub.add_parser("release")
        release.add_argument("hold_id")
        release.add_argument("--by", required=True)
        listing = sub.add_parser("list")
        listing.add_argument("--all", action="store_true", help="include released holds")

    def _user(self, username):
        user = get_user_model().objects.filter(username=username, is_staff=True).first()
        if user is None:
            raise CommandError(f"No staff account named {username!r}.")
        return user

    def handle(self, *args, **opts):
        getattr(self, f"_{opts['action']}")(opts)

    def _place(self, opts):
        scope, target = opts["scope"], opts.get("target")
        reference = opts["reference"].strip()
        if not reference:
            raise CommandError("A reference is required.")
        fields = {}
        if scope != LegalHold.SCOPE_ALL:
            if not target:
                raise CommandError(f"--id is required for scope {scope}.")
            fields[scope] = self._resolve(scope, target)
        elif target:
            raise CommandError("Scope 'all' takes no --id.")
        user = self._user(opts["by"])
        hold = LegalHold.objects.create(scope=scope, reference=reference[:200], placed_by=user, **fields)
        emit("legal_hold.placed", hold, user=user, details={"scope": scope})
        self.stdout.write(self.style.SUCCESS(f"Legal hold {hold.id} placed ({scope})."))

    def _resolve(self, scope, target):
        from apps.casework.models import CaseFile
        from apps.communities.models import Community
        from apps.needs.models import Need
        from apps.people.models import Person

        model = {"community": Community, "person": Person, "case": CaseFile, "need": Need}[scope]
        lookup = {"slug": target} if scope == "community" else {"pk": target}
        try:
            return model.objects.get(**lookup)
        except (model.DoesNotExist, ValueError, ValidationError) as exc:  # ValidationError: not a UUID
            raise CommandError(f"No {scope} matches {target!r}.") from exc

    def _release(self, opts):
        try:
            hold = LegalHold.objects.get(pk=opts["hold_id"], released_at__isnull=True)
        except (LegalHold.DoesNotExist, ValueError, ValidationError) as exc:
            raise CommandError(f"No active hold {opts['hold_id']!r}.") from exc
        user = self._user(opts["by"])
        hold.released_at = timezone.now()
        hold.released_by = user
        hold.save(update_fields=["released_at", "released_by"])
        emit("legal_hold.released", hold, user=user, details={"scope": hold.scope})
        self.stdout.write(self.style.SUCCESS(f"Legal hold {hold.id} released. Deletion resumes on the next run."))

    def _list(self, opts):
        rows = LegalHold.objects.all() if opts["all"] else LegalHold.objects.filter(released_at__isnull=True)
        if not rows.exists():
            self.stdout.write("No legal holds." if opts["all"] else "No active legal holds.")
            return
        for h in rows:
            state = "ACTIVE" if h.is_active else f"released {h.released_at:%Y-%m-%d}"
            self.stdout.write(f"{h.id}  {h.scope:<9}  {state:<20}  placed {h.placed_at:%Y-%m-%d}  {h.reference}")
