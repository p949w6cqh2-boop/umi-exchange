"""
One-time: hide the open posts of members who left before leaving hid anything.

Since the founder's decision of 2026-10-12 (#218), leaving hides the leaver's open asks and active
offers (moderation_hidden, stamped hidden_on_leave_at), and coming back lists them to put back or
close (LeftPostsView). People who left before that still have their posts on the board. His call
of 2026-10-13: hide those the same reversible way, with a command he runs on the server after the
deploy.

    python manage.py hide_left_members_posts                      # dry run: counts only
    python manage.py hide_left_members_posts --apply              # hide them
    python manage.py hide_left_members_posts --community st-anne  # one community (with or without --apply)

"Left" means a membership the member switched off (is_active false, never removed): a removal
already hid its posts and has its own way back (reinstate_member). Only open asks and active offers
are hidden. Nothing is deleted, nobody is notified, and matches still in progress are counted and
left as they are. A second run finds nothing.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import emit
from apps.communities.models import Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _visible_needs():
    return Need.objects.filter(status="open", moderation_hidden=False, hidden_on_leave_at__isnull=True)


def _visible_offers():
    return Offer.objects.filter(status="active", moderation_hidden=False, hidden_on_leave_at__isnull=True)


class Command(BaseCommand):
    help = "Hide the open asks and active offers of members who left before leaving hid them. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Hide the posts. Without it, only count them.")
        parser.add_argument("--community", help="Only this community (its slug).")

    def handle(self, *args, apply=False, community=None, **options):
        left = Member.objects.filter(is_active=False, removed_at__isnull=True)
        if community:
            if not Community.objects.filter(slug=community).exists():
                raise CommandError(f"No community has the slug {community!r}.")
            left = left.filter(community__slug=community)
        left_ids = list(left.values_list("pk", flat=True))

        needs = _visible_needs().filter(requester_id__in=left_ids)
        offers = _visible_offers().filter(offerer_id__in=left_ids)
        per_community = defaultdict(lambda: {"members": set(), "needs": 0, "offers": 0})
        for slug, member_id in needs.values_list("community__slug", "requester_id"):
            per_community[slug]["members"].add(member_id)
            per_community[slug]["needs"] += 1
        for slug, member_id in offers.values_list("community__slug", "offerer_id"):
            per_community[slug]["members"].add(member_id)
            per_community[slug]["offers"] += 1
        in_progress = (
            Match.objects.filter(status__in=("proposed", "accepted"))
            .filter(
                Q(need__requester_id__in=left_ids)
                | Q(offer__offerer_id__in=left_ids)
                | Q(offer__isnull=True, proposed_by_id__in=left_ids)
            )
            .distinct()
            .count()
        )

        if not per_community:
            self.stdout.write("Nothing to hide: no member who left has an open ask or active offer on the board.")
            self._report_matches(in_progress)
            return

        if not apply:
            self.stdout.write("Dry run: nothing changed. Run again with --apply to hide these posts.")
        for slug in sorted(per_community):
            row = per_community[slug]
            self.stdout.write(
                f"{slug}: {_count(len(row['members']), 'member who left', 'members who left')}, "
                f"{_count(row['needs'], 'open ask', 'open asks')}, "
                f"{_count(row['offers'], 'active offer', 'active offers')}"
            )

        if apply:
            hidden_needs = hidden_offers = 0
            for member_id in sorted({m for row in per_community.values() for m in row["members"]}):
                n, o = self._hide(member_id)
                hidden_needs += n
                hidden_offers += o
            self.stdout.write(
                f"Hidden: {_count(hidden_needs, 'open ask', 'open asks')}, "
                f"{_count(hidden_offers, 'active offer', 'active offers')}. "
                "Each comes back only if its owner rejoins and puts it back."
            )
        self._report_matches(in_progress)

    def _hide(self, member_id):
        """Hide one leaver's posts under their membership's lock, so a rejoin that lands mid-run
        either comes first (and is skipped) or finds the posts on its left-posts page."""
        with transaction.atomic():
            member = Member.objects.select_for_update().get(pk=member_id)
            if member.is_active or member.removed_at is not None:
                return 0, 0  # came back, or was removed, while this ran
            now = timezone.now()
            n = _visible_needs().filter(requester=member).update(moderation_hidden=True, hidden_on_leave_at=now)
            o = _visible_offers().filter(offerer=member).update(moderation_hidden=True, hidden_on_leave_at=now)
            if n or o:
                emit(
                    "member.left_posts_hidden",
                    member,
                    details={"needs_hidden": n, "offers_hidden": o, "backfill": True},
                )
        return n, o

    def _report_matches(self, count):
        if count:
            are = "is" if count == 1 else "are"
            self.stdout.write(
                f"{_count(count, 'match', 'matches')} {are} still in progress with members who left. "
                "This command leaves matches as they are."
            )
