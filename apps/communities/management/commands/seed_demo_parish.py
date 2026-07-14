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
                user.set_password(DEMO_PASSWORD)
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
