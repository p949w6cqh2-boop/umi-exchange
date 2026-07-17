"""Layer C §D/§J — structured community identity (pipeline S4, slice/community-identity).

§D: four small facts on Community.settings (patron, welcome_lines, signin_blurb,
scene_choices), written through the settings Identity section, auto-escaped on
every surface — the wall has no second door. §J: the hub wears the identity
(rotating greeting sub-line — the founder's call, day cadence — scene picks,
the pages card), the anon index carries the blurb, and the switcher swaps the
whole bundle. Mirrors test_pages.py's shape: module world fixture, per-file helpers."""

import pytest
from django.test import Client
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def world():
    community = CommunityFactory()
    admin = MemberFactory(community=community, role="admin", display_name="Fr. Declan")
    coordinator = MemberFactory(community=community, role="coordinator", display_name="Anne Coordinator")
    member = MemberFactory(community=community, role="member", display_name="Nuala Member")
    return community, admin, coordinator, member


def _settings_url(community):
    return reverse("community-settings", kwargs={"slug": community.slug})


def _identity_payload(**kw):
    data = {
        "action": "set_identity",
        "patron": "St. Brigid",
        "welcome_lines": "Bear one another's burdens.\nCarry each other, and so fulfil the law.",
        "signin_blurb": "A parish board for asking and answering, quietly.",
        "scene_hub": "lakes",
        "scene_landing": "threshold",
    }
    data.update(kw)
    return data


class TestIdentityWrite:
    def test_settings_page_shows_identity_section(self, world):
        community, admin, _, _ = world
        body = _login(admin).get(_settings_url(community)).content.decode()
        assert "Identity" in body
        assert "Blank keeps the warm default." in body
        assert 'name="patron"' in body
        assert 'name="welcome_lines"' in body
        assert 'name="signin_blurb"' in body
        assert 'name="scene_hub"' in body and 'name="scene_landing"' in body

    def test_admin_sets_identity_and_it_is_audited_without_values(self, world):
        from apps.audit.models import AuditLog

        community, admin, _, _ = world
        resp = _login(admin).post(_settings_url(community), _identity_payload())
        assert resp.status_code == 302
        community.refresh_from_db()
        assert community.settings["patron"] == "St. Brigid"
        assert community.settings["welcome_lines"] == [
            "Bear one another's burdens.",
            "Carry each other, and so fulfil the law.",
        ]
        assert community.settings["signin_blurb"].startswith("A parish board")
        assert community.settings["scene_choices"] == {"hub": "lakes", "landing": "threshold"}
        log = AuditLog.objects.filter(action="community.identity_set").latest("timestamp")
        # PII-free: key names only, never the words themselves.
        assert "patron" in str(log.details)
        assert "St. Brigid" not in str(log.details)

    def test_coordinator_may_write_identity(self, world):
        community, _, coordinator, _ = world
        resp = _login(coordinator).post(_settings_url(community), _identity_payload())
        assert resp.status_code == 302
        community.refresh_from_db()
        assert community.settings.get("patron") == "St. Brigid"

    def test_member_cannot_write_identity(self, world):
        community, _, _, member = world
        _login(member).post(_settings_url(community), _identity_payload(), follow=True)
        community.refresh_from_db()
        assert "patron" not in (community.settings or {})

    def test_error_rerenders_with_the_typed_words_kept(self, world):
        # The founder's queued follow-up: a validation error must not discard
        # what the admin typed — re-render the form with their words in it.
        community, admin, _, _ = world
        resp = _login(admin).post(
            _settings_url(community),
            _identity_payload(patron="x" * 81, welcome_lines="The kettle is always on."),
        )
        assert resp.status_code == 200  # re-rendered, not redirected away
        body = resp.content.decode()
        assert "x" * 81 in body  # the over-long patron, still there to shorten
        assert "The kettle is always on." in body  # the good lines, not retyped
        community.refresh_from_db()
        assert "patron" not in (community.settings or {})  # still nothing half-landed

    def test_lengths_enforced_warmly(self, world):
        community, admin, _, _ = world
        client = _login(admin)
        cases = [
            {"patron": "x" * 81},
            {"welcome_lines": "y" * 141},
            {"welcome_lines": "\n".join(f"line {i}" for i in range(11))},
            {"signin_blurb": "z" * 301},
        ]
        for overrides in cases:
            client.post(_settings_url(community), _identity_payload(**overrides), follow=True)
            community.refresh_from_db()
            assert "patron" not in (community.settings or {}), overrides

    def test_blank_clears_each_key(self, world):
        community, admin, _, _ = world
        client = _login(admin)
        client.post(_settings_url(community), _identity_payload())
        client.post(
            _settings_url(community),
            _identity_payload(patron="", welcome_lines="", signin_blurb="", scene_hub="", scene_landing=""),
        )
        community.refresh_from_db()
        for key in ("patron", "welcome_lines", "signin_blurb", "scene_choices"):
            assert key not in community.settings, key

    def test_unknown_scene_slug_is_not_stored(self, world):
        community, admin, _, _ = world
        _login(admin).post(_settings_url(community), _identity_payload(scene_hub="evil", scene_landing="lakes"))
        community.refresh_from_db()
        assert community.settings.get("scene_choices") == {"landing": "lakes"}

    def test_partial_post_touches_only_the_sent_fields(self, world):
        community, admin, _, _ = world
        client = _login(admin)
        client.post(_settings_url(community), _identity_payload())
        # A crafted or partial submit carries only one field — everything else
        # the writer didn't send must survive untouched.
        client.post(_settings_url(community), {"action": "set_identity", "patron": "St. Kevin"})
        community.refresh_from_db()
        assert community.settings["patron"] == "St. Kevin"
        assert community.settings["welcome_lines"], "welcome_lines wiped by a partial POST"
        assert community.settings["signin_blurb"], "signin_blurb wiped by a partial POST"
        assert community.settings["scene_choices"], "scene_choices wiped by a partial POST"

    def test_scene_update_merges_per_surface(self, world):
        community, admin, _, _ = world
        client = _login(admin)
        client.post(_settings_url(community), _identity_payload())  # hub=lakes, landing=threshold
        client.post(_settings_url(community), {"action": "set_identity", "scene_hub": "board"})
        community.refresh_from_db()
        assert community.settings["scene_choices"] == {"hub": "board", "landing": "threshold"}

    def test_theme_and_identity_writers_preserve_each_other(self, world):
        community, admin, _, _ = world
        client = _login(admin)
        client.post(_settings_url(community), {"action": "set_theme", "theme": "ocean"})
        client.post(_settings_url(community), _identity_payload())
        community.refresh_from_db()
        assert community.settings["theme"] == "ocean"
        assert community.settings["patron"] == "St. Brigid"

    def test_scene_slugs_match_the_committed_prints(self):
        from pathlib import Path

        from apps.communities.identity import SCENE_SLUGS

        stems = {p.stem.lstrip("_") for p in Path("templates/illustrations").glob("_*.html")}
        assert set(SCENE_SLUGS) == stems


# ---------------------------------------------------------------------------
# §J — the hub wears the identity; the anon index carries the blurb
# ---------------------------------------------------------------------------


def _set_identity(admin, community, **kw):
    _login(admin).post(_settings_url(community), _identity_payload(**kw))
    community.refresh_from_db()


def _hub(community):
    return reverse("hub:community", kwargs={"slug": community.slug})


class TestWelcomeLineRotation:
    def test_rotates_by_the_day_deterministically(self):
        from datetime import date

        from apps.communities.identity import welcome_line_for_today

        community = CommunityFactory()
        community.settings = {"welcome_lines": ["Line A", "Line B"]}
        d1, d2 = date(2026, 7, 17), date(2026, 7, 18)
        first = welcome_line_for_today(community, today=d1)
        second = welcome_line_for_today(community, today=d2)
        assert {first, second} == {"Line A", "Line B"}  # consecutive days differ over a 2-list
        assert welcome_line_for_today(community, today=d1) == first  # same day, same line

    def test_single_line_is_effectively_static_and_blank_is_none(self):
        from datetime import date

        from apps.communities.identity import welcome_line_for_today

        community = CommunityFactory()
        community.settings = {"welcome_lines": ["Only line"]}
        assert welcome_line_for_today(community, today=date(2026, 7, 17)) == "Only line"
        assert welcome_line_for_today(community, today=date(2026, 7, 18)) == "Only line"
        community.settings = {}
        assert welcome_line_for_today(community, today=date(2026, 7, 17)) is None


class TestHubIdentity:
    def test_hub_carries_todays_welcome_line_under_the_greeting(self, world):
        from apps.communities.identity import welcome_line_for_today

        community, admin, _, member = world
        _set_identity(admin, community, welcome_lines="Bear one another's burdens.")
        body = _login(member).get(_hub(community)).content.decode()
        assert welcome_line_for_today(community) == "Bear one another's burdens."
        assert "Bear one another" in body

    def test_hub_without_lines_shows_no_sub_line(self, world):
        community, _, _, member = world
        body = _login(member).get(_hub(community)).content.decode()
        assert "Bear one another" not in body

    def test_script_in_welcome_line_renders_inert_on_the_hub(self, world):
        community, admin, _, member = world
        _set_identity(admin, community, welcome_lines="<script>alert(1)</script>")
        body = _login(member).get(_hub(community)).content.decode()
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body

    def test_hub_scene_defaults_to_the_well_and_follows_the_choice(self, world):
        community, admin, _, member = world
        body = _login(member).get(_hub(community)).content.decode()
        assert 'data-scene="well"' in body
        _set_identity(admin, community, scene_hub="lakes")
        body = _login(member).get(_hub(community)).content.decode()
        assert 'data-scene="lakes"' in body

    def test_hub_pages_card_first_four_and_the_index_door(self, world):
        from apps.pages.models import CommunityPage

        community, admin, coordinator, member = world
        body = _login(member).get(_hub(community)).content.decode()
        assert "Your community" not in body  # no pages, no card shell
        for i in range(5):
            page = CommunityPage.objects.create(
                community=community,
                title=f"Card page {i}",
                slug=f"card-{i}",
                content_md="Words.",
                created_by=coordinator,
            )
            page.publish(by=admin)
        body = _login(member).get(_hub(community)).content.decode()
        assert "Your community" in body
        # Scope to the card itself — the S3 footer column (cap 6) legitimately
        # lists the fifth page; the card caps at four.
        card = body.split('id="hub-pages-h"')[1].split("</section>")[0]
        for i in range(4):
            assert f"Card page {i}" in card
        assert "Card page 4" not in card
        assert "All pages" in card

    def test_switcher_swaps_the_whole_bundle(self, world):
        community, admin, _, member = world
        # Blank scenes: A must keep the warm default (the payload helper would
        # otherwise pick lakes for everyone).
        _set_identity(
            admin,
            community,
            patron="St. Brigid",
            welcome_lines="Bear one another's burdens.",
            scene_hub="",
            scene_landing="",
        )
        other = CommunityFactory(name="Harbour House")
        other_admin = MemberFactory(community=other, role="admin")
        MemberFactory(community=other, role="member", user=member.user, display_name="Nuala Member")
        _set_identity(other_admin, other, welcome_lines="The harbour holds every boat.", scene_hub="lakes")
        client = _login(member)
        body_a = client.get(_hub(community)).content.decode()
        body_b = client.get(_hub(other)).content.decode()
        assert "Bear one another" in body_a and "harbour holds" not in body_a
        assert "harbour holds" in body_b and "Bear one another" not in body_b
        assert 'data-scene="well"' in body_a  # A keeps the default
        assert 'data-scene="lakes"' in body_b  # B wears its choice


class TestAnonIndexIdentity:
    def _open(self, world):
        from apps.pages.models import CommunityPage

        community, admin, coordinator, _ = world
        community.visibility = "public"
        community.save(update_fields=["visibility"])
        page = CommunityPage.objects.create(
            community=community,
            title="Parish festival",
            slug="festival",
            content_md="All welcome.",
            created_by=coordinator,
            show_on_landing=True,
        )
        page.publish(by=admin)
        return community

    def test_blurb_lands_on_the_anon_index_escaped(self, world):
        community, admin, *_ = world
        self._open(world)
        _set_identity(admin, community, signin_blurb="Come as <you> are.")
        body = Client().get(reverse("pages:index", kwargs={"slug": community.slug})).content.decode()
        assert "Come as &lt;you&gt; are." in body
        # And never for members — it's the sign-in door, not the lobby.
        member = MemberFactory(community=community, role="member")
        assert (
            "Come as"
            not in _login(member).get(reverse("pages:index", kwargs={"slug": community.slug})).content.decode()
        )

    def test_landing_scene_shows_when_chosen(self, world):
        community, admin, *_ = world
        self._open(world)
        url = reverse("pages:index", kwargs={"slug": community.slug})
        assert "data-scene" not in Client().get(url).content.decode()  # today's default: none
        _set_identity(admin, community, scene_landing="threshold")
        assert 'data-scene="threshold"' in Client().get(url).content.decode()


class TestSeedIdentity:
    def test_seed_extends_identity_and_pages_idempotently(self, settings):
        from django.core.management import call_command

        from apps.communities.models import Community
        from apps.pages.models import CommunityPage

        settings.DEBUG = True
        call_command("seed_demo_parish", verbosity=0)
        call_command("seed_demo_parish", verbosity=0)  # idempotent
        community = Community.objects.get(slug="st-brigids")
        assert community.visibility == "public"  # the demo front door renders for visitors
        assert community.settings.get("patron") == "St. Brigid"
        lines = community.settings.get("welcome_lines", [])
        assert any("Bear one another" in line for line in lines)  # Gal 6:2 on the hub
        pages = {p.slug: p for p in CommunityPage.objects.filter(community=community)}
        assert pages["our-story"].status == "published" and pages["our-story"].show_on_landing
        assert pages["mass-times"].status == "published"
        assert pages["ministries"].status == "draft"
        assert pages["old-bulletin"].status == "archived"
        story = pages["our-story"].content_md
        assert "We still don't." in story  # demo canon, verbatim
        assert "Matthew 25:40" in story  # the story keeps Matthew
        assert "Bear one another" not in story  # 05 and 08 no longer share a verse
        assert CommunityPage.objects.filter(community=community, slug="our-story").count() == 1
