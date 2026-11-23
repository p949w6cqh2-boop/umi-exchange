"""Seed a wholly fictional demo parish so the app can be shown alive, not empty.

Everything here is invented for demos: no real parishioners, no real parish
specifics. The command is idempotent (safe to re-run) and additive (it never
deletes), and it refuses to run when DEBUG is off — demo data must never reach
a production database.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.communities.models import Category, Community, Member, Vouch
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
    ("tom", "Tom Byrne", "coordinator"),
    ("frank", "Frank O'Shea", "member"),  # the verified deacon
    ("sheila", "Sheila Brennan", "member"),
    ("joe", "Joe Callahan", "member"),
    ("rosa", "Rosa Alvarez", "member"),
    ("pete", "Pete Whelan", "member"),
    ("aggie", "Aggie Lynch", "member"),
    ("dan", "Dan Murphy", "member"),
    ("grace", "Grace Okafor", "member"),
    ("liam", "Liam Tierney", "member"),
]

# A number for the connect to open onto. Invented: 555-0100 to 555-0199 are set aside for
# fiction. Without them, and with every seeded ask and offer on the form's default contact
# choice ("in the app"), every reveal in the demo read "They prefer to arrange things through
# the community" (found by the tutorial v2 recording, 2026-10-06).
PHONES = {
    "marta": "555-0101",
    "nuala": "555-0102",
    "tom": "555-0103",
    "frank": "555-0115",
    "sheila": "555-0120",
    "joe": "555-0144",
    "rosa": "555-0126",
    "pete": "555-0137",
    "aggie": "555-0172",
    "dan": "555-0131",
    "grace": "555-0150",
    "liam": "555-0158",
}
DEMO_CONTACT_PREF = "phone"

CATEGORIES = [
    ("Transport", "\U0001f697"),
    ("Meals", "\U0001f372"),
    ("Home Repair", "\U0001f527"),
    ("Tutoring", "\U0001f4da"),
    ("Company", "☕"),
    ("Groceries", "\U0001f9fa"),
    ("Communion at home", "✝️"),  # the first coordinator's ask, 2026-10-02
]

NEEDS = [
    # (requester, category, title, description, urgency)
    (
        "nuala",
        "Transport",
        "A ride to the 9:30 Mass on Sunday",
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
        "Someone to look at a leaky kitchen faucet",
        "It drips all night. I have the washers, I just can't get under the sink anymore.",
        "medium",
    ),
    (
        "rosa",
        "Tutoring",
        "Math help for Marco, Tuesday evenings",
        "He's in fifth grade and losing heart over fractions. An hour a week would change things.",
        "medium",
    ),
    (
        "joe",
        "Company",
        "Company for a cup of coffee now and then",
        "The house got very quiet this year. I put the coffee on around three most days.",
        "low",
    ),
    (
        "sheila",
        "Groceries",
        "A hand with the grocery run this Friday",
        "I can pay for the groceries, I just can't carry them up the hill anymore.",
        "medium",
    ),
    (
        "grace",
        "Home Repair",
        "A crib for the new baby",
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
        "Sundays at 8:00, 9:30, and 11:00. Saturday vigil at 6:00.\n\n"
        "Weekday Mass at 9:30, Tuesday to Friday, in the side chapel. "
        "Confessions Saturday from 5:00, or knock on the sacristy door.",
    ),
    (
        "Ministries",
        "ministries",
        "draft",
        False,
        "The meal train, the visiting team, and rides to Mass — who does what, and how to join in. "
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
        "I always cook too much on Mondays and Thursdays. Happy to drop a plate off.",
    ),
    (
        "liam",
        "Home Repair",
        "Handy with faucets, hinges, and shelves",
        "Forty years as a pipefitter. Small jobs are no trouble at all.",
    ),
    (
        "frank",
        "Tutoring",
        "Retired teacher, happy to tutor",
        "Math and Spanish, elementary or high school. Patience included.",
    ),
    (
        "marta",
        "Company",
        "A free hour most afternoons",
        "I walk the park around three and I'm always glad for the company.",
    ),
    (
        "nuala",
        "Home Repair",
        "An outgrown crib, in great shape",
        "Our youngest is in a bed now. The crib is clean and solid, and it needs a home.",
    ),
]


@dataclass(frozen=True)
class ParishSeed:
    """Everything that makes one demo parish itself; the Command below is the same for all of them.

    `matches` rows are (need title, offer title, transitions walked, helper said yes first).
    `tags` rows are (slug, label, tier, member, request note, verify note, verifier).
    """

    slug: str
    name: str
    members: list
    phones: dict
    contact_pref: str
    categories: list
    coordinators_only_categories: tuple
    needs: list
    offers: list
    matches: list
    identity: dict
    pages: list
    creator: str
    proposer: str
    page_author: str
    page_publisher: str
    tags: list


ST_BRIGIDS = ParishSeed(
    slug=DEMO_SLUG,
    name="St. Brigid's",
    members=MEMBERS,
    phones=PHONES,
    contact_pref=DEMO_CONTACT_PREF,
    categories=CATEGORIES,
    coordinators_only_categories=("Communion at home",),
    needs=NEEDS,
    offers=OFFERS,
    # Three matches: one proposed, one accepted, one fulfilled — the board mid-life.
    matches=[
        # Dan said yes to Marta's introduction; Nuala's yes completes it
        ("A ride to the 9:30 Mass on Sunday", "I can drive Sunday mornings", (), True),
        ("Someone to look at a leaky kitchen faucet", "Handy with faucets, hinges, and shelves", ("accepted",), False),
        ("A crib for the new baby", "An outgrown crib, in great shape", ("accepted", "fulfilled"), False),
    ],
    identity=IDENTITY,
    pages=PAGES,
    creator="marta",
    proposer="marta",
    page_author="tom",
    page_publisher="marta",
    # Frank's verified Deacon tag: clergy tags are admin-verified, so Marta (admin) signs.
    tags=[
        (
            "deacon",
            "Deacon",
            "coordinator_verified",
            "frank",
            "Ordained 2011, serves at the 11:00 Mass.",
            "Known to the parish office.",
            "marta",
        )
    ],
)

# A second parish for fresh B-roll, shaped for TikTok (the founder's ask, 2026-11-21: "a brand new
# community to roll in the back", "Optimize it for TikTok"). Built from what wins on his TikTok:
# person-level dignity ("You are not alone", the stigma cut) and the board shown working ("two
# people say yes"). Every title is five words or fewer so it reads at phone size, and three members
# both ask and offer, because giving and receiving is the point. No scripture is quoted here: a
# quotation needs its NABRE wording checked, and none was. Local recording rig only.
ST_KATERIS = ParishSeed(
    slug="st-kateris",
    name="St. Kateri's",
    members=[
        # (username, display name, role); none may reuse a St. Brigid's username
        ("lena", "Lena Morales", "admin"),
        ("isaac", "Isaac Grant", "coordinator"),
        ("bea", "Bea Thompson", "member"),
        ("omar", "Omar Haddad", "member"),
        ("june", "June Park", "member"),
        ("theo", "Theo Ruiz", "member"),
        ("abby", "Abby Collins", "member"),
        ("sam", "Sam Okoro", "member"),
        ("lucy", "Lucy Nguyen", "member"),
        ("walt", "Walt Brooks", "member"),
    ],
    # The same range set aside for fiction, numbers St. Brigid's does not use.
    phones={
        "lena": "555-0161",
        "isaac": "555-0162",
        "bea": "555-0163",
        "omar": "555-0164",
        "june": "555-0165",
        "theo": "555-0166",
        "abby": "555-0167",
        "sam": "555-0168",
        "lucy": "555-0169",
        "walt": "555-0170",
    },
    contact_pref="phone",
    categories=CATEGORIES,
    coordinators_only_categories=("Communion at home",),
    needs=[
        ("walt", "Transport", "A ride to Sunday Mass", "My knees won't do the bus anymore. Any Sunday works.", "high"),
        (
            "bea",
            "Company",
            "Someone to sit with me",
            "My husband passed in the spring. The evenings are the hardest part.",
            "medium",
        ),
        (
            "june",
            "Groceries",
            "Groceries this week",
            "I'm between jobs right now. Anything helps, even a small bag.",
            "high",
        ),
        (
            "omar",
            "Home Repair",
            "Fix a leaking sink",
            "It drips all night. I have the part, just not the tools.",
            "medium",
        ),
        (
            "abby",
            "Meals",
            "Meals after the twins",
            "They came three weeks early. A dinner or two would mean the world.",
            "medium",
        ),
        (
            "theo",
            "Tutoring",
            "Reading help for my son",
            "He's in third grade and losing heart. An hour a week would help.",
            "medium",
        ),
        (
            "lucy",
            "Communion at home",
            "Communion at home, please",
            "I'm homebound after surgery for a few weeks.",
            "high",
        ),
    ],
    offers=[
        ("sam", "Transport", "I can drive Sundays", "Room for three in the car, and I don't mind an early start."),
        ("isaac", "Company", "I'll sit with you", "My evenings are free. Coffee, cards, or just company."),
        ("lena", "Meals", "Extra dinners most weeks", "I always cook too much. Happy to drop a plate off."),
        (
            "walt",
            "Home Repair",
            "Handy with sinks and shelves",
            "Thirty years as a plumber. Small jobs are no trouble.",
        ),
        (
            "june",
            "Tutoring",
            "Reading help after school",
            "I was a school librarian for twelve years. Patience included.",
        ),
        ("omar", "Groceries", "Grocery runs on Fridays", "I go every Friday anyway. Happy to carry a list."),
    ],
    matches=[
        ("A ride to Sunday Mass", "I can drive Sundays", (), True),
        ("Someone to sit with me", "I'll sit with you", ("accepted",), False),
        ("Fix a leaking sink", "Handy with sinks and shelves", ("accepted", "fulfilled"), False),
    ],
    identity={
        "patron": "St. Kateri",
        "welcome_lines": [
            "No one here walks alone.",
            "Ask for what you need. Offer what you have.",
        ],
        "signin_blurb": "St. Kateri's neighbours asking and answering. If you have a code, you're already welcome.",
        "scene_choices": {"hub": "carrying", "landing": "threshold"},
    },
    pages=[
        (
            "Our story",
            "our-story",
            "published",
            True,
            "St. Kateri's began with six families sharing rides to Sunday Mass. The rides turned into "
            "dinners, and the dinners turned into this board.\n\n"
            "Ask for what you need. Offer what you have. Nobody keeps score, and no one here walks alone.",
        ),
        (
            "Mass times",
            "mass-times",
            "published",
            False,
            "Sundays at 8:30 and 10:30. Saturday vigil at 5:00.\n\nWeekday Mass at 8:00, Monday to Friday.",
        ),
    ],
    creator="lena",
    proposer="lena",
    page_author="isaac",
    page_publisher="lena",
    tags=[],
)

PARISHES = {spec.slug: spec for spec in (ST_BRIGIDS, ST_KATERIS)}


class Command(BaseCommand):
    help = (
        "Seed a fictional demo parish (idempotent, DEBUG-only): St. Brigid's by default, "
        "or another one named with --parish."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--parish",
            default=DEMO_SLUG,
            help=f"Which demo parish to seed: {', '.join(PARISHES)} (default {DEMO_SLUG}).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo_parish only runs with DEBUG on. It seeds fictional demo data "
                "and must never touch a production database."
            )
        spec = PARISHES.get(options.get("parish") or DEMO_SLUG)
        if spec is None:
            raise CommandError(
                f"No demo parish called {options.get('parish')!r}. Choose one of: {', '.join(PARISHES)}."
            )

        from apps.accounts.models import User

        # Never adopt a real account. Seed accounts carry @demo.invalid addresses; any other account
        # holding a seed username (after a runbook flush freed the name, or when MEMBERS grows) was
        # made a demo admin or coordinator, marked human-verified and given a fake phone (2026-10
        # bug hunt, L35). Refuse before writing anything.
        taken = sorted(
            User.objects.filter(username__in=[username for username, _, _ in spec.members])
            .exclude(email__iendswith="@demo.invalid")
            .values_list("username", flat=True)
        )
        if taken:
            raise CommandError(
                "These seed usernames belong to real accounts, so nothing was seeded: "
                + ", ".join(taken)
                + ". Rename the seed members or pick another database."
            )

        users = {}
        for username, display, _role in spec.members:
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
            # Human verification (#148) soft-gates the four write doors. Without this
            # the seed produces a twelve-member parish where nobody can join, post a
            # need or an offer, or propose a match — the fixture looks alive and is
            # unusable. "coordinator" is the honest provenance: these people are known
            # to the parish in person. "backfill" would claim they predate the gate and
            # "email" would claim a link nobody clicked.
            #
            # Deliberately OUTSIDE `if created`: get_or_create returns created=False on
            # every later run, so anything set only in that branch stops happening for
            # rows an earlier run made — which is exactly how these accounts missed the
            # field when it was added. This repairs an existing parish on reseed.
            if not user.is_human_verified:
                user.verified_at = timezone.now()
                user.verified_via = "coordinator"
                user.save(update_fields=["verified_at", "verified_via"])
            # Same rule, same reason: outside `if created`, so a reseed gives an older
            # parish its numbers too (the live demo's path, docs/demo-reseed-runbook.md §3).
            if not user.phone:
                user.phone = spec.phones[username]
                user.save(update_fields=["phone"])
            users[username] = user

        community, _ = Community.objects.get_or_create(
            slug=spec.slug,
            # Public: the demo's front door (§I pre-auth landing) must render
            # for a signed-out visitor — that's the screen that shows it.
            defaults={"name": spec.name, "created_by": users[spec.creator], "visibility": "public"},
        )

        members = {}
        for username, display, role in spec.members:
            member, _ = Member.objects.get_or_create(
                user=users[username],
                community=community,
                defaults={"display_name": display, "role": role},
            )
            # A helper receives an asker's details only once this community has vouched for them
            # (docs/specs/vouch-before-volunteer-reveal.md, the founder's 17a). These people are
            # known to the parish in person, the provenance the verified_via line above already
            # records, so the parish vouches for each one; without it every filmed connect moment
            # opens on a held name. Outside any `if created`, so a reseed repairs an older parish.
            Vouch.objects.get_or_create(community=community, user=users[username])
            members[username] = member

        categories = {}
        for name, icon in spec.categories:
            category, _ = Category.objects.get_or_create(community=community, name=name, defaults={"icon": icon})
            categories[name] = category
        # Migration 0006 marks existing rows; a fresh seed runs after it, so mark here too.
        Category.objects.filter(community=community, name__in=spec.coordinators_only_categories).update(
            coordinators_only_contact=True
        )

        needs = {}
        for requester, category, title, description, urgency in spec.needs:
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
                    "contact_pref": spec.contact_pref,
                },
            )
            if need.contact_pref != spec.contact_pref:  # repair on reseed, as above
                need.contact_pref = spec.contact_pref
                need.save(update_fields=["contact_pref"])
            needs[title] = need

        offers = {}
        for offerer, category, title, description in spec.offers:
            offer, _ = Offer.objects.get_or_create(
                community=community,
                offerer=members[offerer],
                title=title,
                defaults={
                    "category": categories[category],
                    "description": description,
                    "status": "active",
                    "expires_at": timezone.now() + timedelta(days=120),
                    "contact_pref": spec.contact_pref,
                },
            )
            if offer.contact_pref != spec.contact_pref:  # repair on reseed, as above
                offer.contact_pref = spec.contact_pref
                offer.save(update_fields=["contact_pref"])
            offers[title] = offer

        for need_title, offer_title, through, helper_said_yes in spec.matches:
            self._match(
                needs[need_title],
                offers[offer_title],
                members[spec.proposer],
                through=through,
                helper_said_yes=helper_said_yes,
            )

        # §D/§J — the parish identity, only filling keys that are absent.
        community_settings = dict(community.settings or {})
        missing = {k: v for k, v in spec.identity.items() if k not in community_settings}
        if missing:
            community_settings.update(missing)
            community.settings = community_settings
            community.save(update_fields=["settings"])

        # The pages canon — created once; transitions walked only at creation
        # so a re-run never republishes what a demo admin has since changed.
        from apps.pages.models import CommunityPage

        for title, page_slug, status, on_landing, content in spec.pages:
            if CommunityPage.objects.filter(community=community, slug=page_slug).exists():
                continue
            page = CommunityPage.objects.create(
                community=community,
                title=title,
                slug=page_slug,
                content_md=content,
                created_by=members[spec.page_author],
                show_on_landing=on_landing,
            )
            if status in ("published", "archived"):
                page.publish(by=members[spec.page_publisher])
            if status == "archived":
                page.transition_to("archived")

        for tag_slug, label, tier, holder, request_note, verify_note, verifier in spec.tags:
            tag, _ = Tag.objects.get_or_create(
                community=community,
                slug=tag_slug,
                defaults={"label": label, "tier": tier},
            )
            member_tag, created = MemberTag.objects.get_or_create(member=members[holder], tag=tag)
            if created or member_tag.status not in ("verified",):
                if member_tag.status == "self_claimed":
                    member_tag.request_verification(evidence_note=request_note)
                if member_tag.status == "pending":
                    member_tag.verify(members[verifier], evidence_note=verify_note)

        first = {role: next(u for u, _, r in spec.members if r == role) for role in ("admin", "coordinator", "member")}
        # rotate_demo_password covers MEMBERS only, so it must not be offered for another parish.
        closing = (
            "On a live site, run rotate_demo_password next: that password is public."
            if spec is ST_BRIGIDS
            else "Local recording rig only: rotate_demo_password does not cover this parish's members."
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{spec.name} demo parish is ready: {len(members)} members, "
                f"{Need.objects.filter(community=community).count()} needs, "
                f"{Offer.objects.filter(community=community).count()} offers, "
                f"{Match.objects.filter(need__community=community).count()} matches. "
                f"Sign in as {first['admin']} (admin), {first['coordinator']} (coordinator), "
                f"or {first['member']} (member) — password {DEMO_PASSWORD!r} for all.\n"
                f"{closing}"
            )
        )

    def _match(self, need, offer, proposer, through, helper_said_yes=False):
        match = Match.objects.filter(need=need, offer=offer).first()
        if match is None:
            match = Match.objects.create(need=need, offer=offer, proposed_by=proposer)
        # Contact opens only after both people have said yes (2026-10-06), and every seeded
        # match is a coordinator's introduction, so the yeses are recorded here: both on a
        # match that is accepted or later, the helper's alone where the asker's tap is still
        # to come. Outside `if created`, like everything else here, so a reseed repairs an
        # older parish.
        stamp = timezone.now()
        fields = []
        if (through or helper_said_yes) and match.helper_yes_at is None:
            match.helper_yes_at = stamp
            fields.append("helper_yes_at")
        if through and match.asker_yes_at is None:
            match.asker_yes_at = stamp
            fields.append("asker_yes_at")
        if fields:
            match.save(update_fields=fields)
        for status in through:
            if match.status != status:
                try:
                    match.transition_to(status)
                except Exception:
                    break
        return match
