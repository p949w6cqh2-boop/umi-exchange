"""Seed a wholly fictional demo parish so the app can be shown alive, not empty.

Everything here is invented for demos: no real parishioners, no real parish
specifics. The command is idempotent (safe to re-run) and additive (it never
deletes), and it refuses to run when DEBUG is off — demo data must never reach
a production database.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.communities.models import Category, Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.tags.models import MemberTag, Tag

DEMO_SLUG = "st-brigids"
DEMO_PASSWORD = "demo-parish"  # dev-only; the guard below keeps this out of production

MEMBERS = [
    # (username, display name, role)
    ("marta", "Marta Keane", "admin"),
    ("nuala", "Nuala Doyle", "member"),
    ("tomas", "Tomás Byrne", "coordinator"),
    ("frank", "Frank Ó Sé", "member"),  # the verified deacon
    ("sile", "Síle Brennan", "member"),
    ("joe", "Joe Callahan", "member"),
    ("rosa", "Rosa Alvarez", "member"),
    ("pete", "Pete Whelan", "member"),
    ("aggie", "Aggie Lynch", "member"),
    ("dan", "Dan Murphy", "member"),
    ("grace", "Grace Okafor", "member"),
    ("liam", "Liam Tierney", "member"),
]

CATEGORIES = [
    ("Transport", "\U0001f697"),
    ("Meals", "\U0001f372"),
    ("Home Repair", "\U0001f527"),
    ("Tutoring", "\U0001f4da"),
    ("Company", "☕"),
    ("Groceries", "\U0001f9fa"),
]

NEEDS = [
    # (requester, category, title, description, urgency)
    (
        "nuala",
        "Transport",
        "A lift to half-nine Mass on Sunday",
        "My hip is healing well, but I can't manage the walk yet. Any Sunday would help.",
        "high",
    ),
    (
        "marta",
        "Meals",
        "A casserole for the Reilly family",
        "New baby in the house and both grandparents laid up. A dinner or two would go a long way.",
        "medium",
    ),
    (
        "aggie",
        "Home Repair",
        "Someone to look at a leaky kitchen tap",
        "It drips all night. I have the washers, I just can't get under the sink anymore.",
        "medium",
    ),
    (
        "rosa",
        "Tutoring",
        "Maths help for Cian, Tuesday evenings",
        "He's in fifth class and losing heart over fractions. An hour a week would change things.",
        "medium",
    ),
    (
        "joe",
        "Company",
        "Company for a cup of tea now and then",
        "The house got very quiet this year. I put the kettle on around three most days.",
        "low",
    ),
    (
        "sile",
        "Groceries",
        "A hand with the big shop this Friday",
        "I can pay for the messages, I just can't carry them up the hill anymore.",
        "medium",
    ),
    (
        "grace",
        "Home Repair",
        "A cot for the new baby",
        "Second-hand is perfect. We just need it before the end of the month.",
        "high",
    ),
]

# §D/§J identity — set only when absent (additive; a demo admin's later edits win).
IDENTITY = {
    "patron": "St. Brigid",
    "welcome_lines": [
        "Bear one another's burdens.",
        "The table is long; there is room.",
    ],
    "signin_blurb": (
        "St. Brigid's neighbours asking and answering, quietly. If you have a code, you're already welcome."
    ),
    "scene_choices": {"hub": "well", "landing": "lakes"},
}

# The pages canon (pipeline §J): story live on the landing, times live,
# ministries still a draft, the old bulletin put away. The story keeps
# Matthew; the hub's welcome line carries Galatians — never the same verse.
PAGES = [
    (
        "Our story",
        "our-story",
        "published",
        True,
        "St. Brigid's has kept a common table since 1928. When the mill closed, the parish fed "
        "forty families out of one kitchen, and nobody wrote down who owed what. We still don't.\n\n"
        '"Whatever you did for one of the least of these, you did for me." (Matthew 25:40)\n\n'
        "This board is that same table, set out where every neighbour can reach it. Ask for what "
        "you need. Offer what you have. Nobody keeps score.",
    ),
    (
        "Mass times",
        "mass-times",
        "published",
        False,
        "Sundays at 8:00 and 11:00. Saturday vigil at 6:00.\n\n"
        "Weekday Mass at 9:30, Tuesday to Friday, in the side chapel. "
        "Confessions Saturday from 5:00, or knock on the sacristy door.",
    ),
    (
        "Ministries",
        "ministries",
        "draft",
        False,
        "The meals rota, the visiting team, and lifts to Mass — who does what, and how to join in. "
        "(Still being written.)",
    ),
    (
        "Old bulletin",
        "old-bulletin",
        "archived",
        False,
        "The winter bulletin, kept for the record.",
    ),
]

OFFERS = [
    # (offerer, category, title, description)
    ("dan", "Transport", "I can drive Sunday mornings", "Room for three in the car, and I don't mind an early start."),
    (
        "pete",
        "Meals",
        "Two extra dinners most weeks",
        "I always cook too much on Mondays and Thursdays. Happy to drop a plate over.",
    ),
    (
        "liam",
        "Home Repair",
        "Handy with taps, hinges, and shelves",
        "Forty years a fitter. Small jobs are no trouble at all.",
    ),
    (
        "frank",
        "Tutoring",
        "Retired teacher, happy to tutor",
        "Maths and Irish, primary or secondary. Patience included.",
    ),
    (
        "marta",
        "Company",
        "A free hour most afternoons",
        "I walk the green around three and I'm always glad of the chat.",
    ),
    (
        "nuala",
        "Home Repair",
        "An outgrown cot, in good nick",
        "Our youngest is in a bed now. The cot is clean and solid, and it needs a home.",
    ),
]


class Command(BaseCommand):
    help = "Seed the fictional St. Brigid's demo parish (idempotent, DEBUG-only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo_parish only runs with DEBUG on. It seeds fictional demo data "
                "and must never touch a production database."
            )

        from apps.accounts.models import User

        users = {}
        for username, display, _role in MEMBERS:
            first = display.split(" ")[0]
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@demo.invalid", "first_name": first},
            )
            if created:
                # Demo fixture password by design (DEBUG-only guard above); validators
                # would reject the shared throwaway on purpose-built demo accounts.
                user.set_password(DEMO_PASSWORD)  # nosemgrep: unvalidated-password
                user.save()
            users[username] = user

        community, _ = Community.objects.get_or_create(
            slug=DEMO_SLUG,
            defaults={"name": "St. Brigid's", "created_by": users["marta"]},
        )

        members = {}
        for username, display, role in MEMBERS:
            member, _ = Member.objects.get_or_create(
                user=users[username],
                community=community,
                defaults={"display_name": display, "role": role},
            )
            members[username] = member

        categories = {}
        for name, icon in CATEGORIES:
            category, _ = Category.objects.get_or_create(community=community, name=name, defaults={"icon": icon})
            categories[name] = category

        needs = {}
        for requester, category, title, description, urgency in NEEDS:
            need, _ = Need.objects.get_or_create(
                community=community,
                requester=members[requester],
                title=title,
                defaults={
                    "category": categories[category],
                    "description": description,
                    "urgency": urgency,
                    "status": "open",
                    "expires_at": timezone.now() + timedelta(days=60),
                },
            )
            needs[title] = need

        offers = {}
        for offerer, category, title, description in OFFERS:
            offer, _ = Offer.objects.get_or_create(
                community=community,
                offerer=members[offerer],
                title=title,
                defaults={
                    "category": categories[category],
                    "description": description,
                    "status": "active",
                    "expires_at": timezone.now() + timedelta(days=120),
                },
            )
            offers[title] = offer

        # Three matches: one proposed, one accepted, one fulfilled — the board mid-life.
        self._match(
            needs["A lift to half-nine Mass on Sunday"],
            offers["I can drive Sunday mornings"],
            members["marta"],
            through=(),
        )
        self._match(
            needs["Someone to look at a leaky kitchen tap"],
            offers["Handy with taps, hinges, and shelves"],
            members["marta"],
            through=("accepted",),
        )
        self._match(
            needs["A cot for the new baby"],
            offers["An outgrown cot, in good nick"],
            members["marta"],
            through=("accepted", "fulfilled"),
        )

        # §D/§J — the parish identity, only filling keys that are absent.
        community_settings = dict(community.settings or {})
        missing = {k: v for k, v in IDENTITY.items() if k not in community_settings}
        if missing:
            community_settings.update(missing)
            community.settings = community_settings
            community.save(update_fields=["settings"])

        # The pages canon — created once; transitions walked only at creation
        # so a re-run never republishes what a demo admin has since changed.
        from apps.pages.models import CommunityPage

        for title, page_slug, status, on_landing, content in PAGES:
            if CommunityPage.objects.filter(community=community, slug=page_slug).exists():
                continue
            page = CommunityPage.objects.create(
                community=community,
                title=title,
                slug=page_slug,
                content_md=content,
                created_by=members["tomas"],
                show_on_landing=on_landing,
            )
            if status in ("published", "archived"):
                page.publish(by=members["marta"])
            if status == "archived":
                page.transition_to("archived")

        # Frank's verified Deacon tag: clergy tags are admin-verified, so Marta (admin) signs.
        tag, _ = Tag.objects.get_or_create(
            community=community,
            slug="deacon",
            defaults={"label": "Deacon", "tier": "coordinator_verified"},
        )
        member_tag, created = MemberTag.objects.get_or_create(member=members["frank"], tag=tag)
        if created or member_tag.status not in ("verified",):
            if member_tag.status == "self_claimed":
                member_tag.request_verification(evidence_note="Ordained 2011, serves at the 11am.")
            if member_tag.status == "pending":
                member_tag.verify(members["marta"], evidence_note="Known to the parish office.")

        self.stdout.write(
            self.style.SUCCESS(
                f"St. Brigid's demo parish is ready: {len(members)} members, "
                f"{Need.objects.filter(community=community).count()} needs, "
                f"{Offer.objects.filter(community=community).count()} offers, "
                f"{Match.objects.filter(need__community=community).count()} matches. "
                f"Sign in as marta (admin), tomas (coordinator), "
                f"or nuala (member) — password {DEMO_PASSWORD!r} for all."
            )
        )

    def _match(self, need, offer, proposer, through):
        match = Match.objects.filter(need=need, offer=offer).first()
        if match is None:
            match = Match.objects.create(need=need, offer=offer, proposed_by=proposer)
        for status in through:
            if match.status != status:
                try:
                    match.transition_to(status)
                except Exception:
                    break
        return match
