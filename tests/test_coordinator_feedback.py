"""What the first coordinator hit on her own phone, 2026-10-02 — one regression test per report.

She sat down with the board for the first time and found five things that made it harder than
it should be for the people she helps:

  1. Long words ran off a phone screen. The hub greeting prints a display name as one word, and an
     email-shaped name has nowhere to break, so its flex box grew past the header and got clipped.
  2. There was no way to see a password while typing it.
  3. Adding an email on the profile "didn't update". By design the address waits for its link
     (docs/specs/account-recovery.md §A), but the settings page never said so.
  4. Community settings "didn't work". Picking a colour preset was silently undone, because a
     colour picker always submits a value, so the untouched custom pickers overrode every preset
     with the evergreen defaults. The scene menus listed file names, the hub scene was hidden on
     phones, and no field said where it shows.
  5. A need showed "3 days ago" but never the date it was posted or the date it was done.
"""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.verification import PENDING_EMAIL_KEY, make_add_email_token
from apps.communities.identity import SCENE_LABELS, SCENE_SLUGS
from apps.communities.themes import THEMES, resolve_theme
from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory

User = get_user_model()
pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent
INPUT_CSS = (ROOT / "static/css/input.css").read_text()
OUTPUT_CSS = (ROOT / "static/css/output.css").read_text()

LONG_NAME = "usermegadatainfrastructure@example.org"


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


def _css_block(css, selector):
    """The declarations of the first top-level rule for exactly `selector`."""
    match = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert match, f"no rule for {selector}"
    return match.group(1)


@pytest.fixture
def world():
    community = CommunityFactory()
    admin = MemberFactory(community=community, role="admin", display_name="Fr. Declan")
    member = MemberFactory(community=community, role="member", display_name=LONG_NAME)
    return community, admin, member


# ── 1. long words wrap instead of running off a phone ────────────────────────


def test_long_unbroken_words_wrap_everywhere():
    body = _css_block(INPUT_CSS, "body")
    assert "overflow-wrap: anywhere" in body
    assert "overflow-wrap:anywhere" in OUTPUT_CSS, "output.css was not recompiled"


def test_the_greeting_box_can_shrink_on_a_phone(world):
    community, _, member = world
    html = _login(member).get(reverse("hub:community", kwargs={"slug": community.slug})).content.decode()
    assert LONG_NAME in html
    # The flex child holding the greeting: without min-w-0 its minimum width is the whole
    # unbroken name, so it grows past the header and the header's overflow-hidden clips it.
    assert re.search(r'<div class="[^"]*\bmin-w-0\b[^"]*">\s*<span class="umi-kicker">', html)


def test_a_need_title_gets_two_lines_on_its_card(world):
    community, _, member = world
    NeedFactory(community=community, requester=member, category=CategoryFactory(community=community))
    html = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug})).content.decode()
    assert re.search(r'<h3 class="[^"]*\bline-clamp-2\b[^"]*">', html)


# ── 2. a password can be seen while it is typed ──────────────────────────────


@pytest.mark.parametrize("url_name", ["register", "login"])
def test_password_pages_load_the_show_password_script(client, url_name):
    html = client.get(reverse(url_name)).content.decode()
    assert re.search(r'<script src="/static/js/password-toggle\.js[^"]*" defer></script>', html)


def test_the_show_password_eye_is_accessible():
    # The founder's call, 2026-10-02: the familiar eye inside the box, and the eye with a
    # slash once the password shows. A screen reader still hears the words.
    js = (ROOT / "static/js/password-toggle.js").read_text()
    assert 'input[type="password"]' in js
    assert "EYE" in js and "EYE_SLASH" in js and "<svg" in js
    assert "Show password" in js and "Hide password" in js  # spoken via aria-label
    assert "aria-label" in js and "aria-pressed" in js and "aria-controls" in js
    assert '"submit"' in js  # the field goes back to hidden before the form is sent


def test_the_eye_sits_inside_the_box_with_a_full_size_tap_target():
    toggle = _css_block(INPUT_CSS, ".umi-pw-toggle")
    assert "position: absolute" in toggle and "width: 44px" in toggle
    assert "padding-right" in _css_block(INPUT_CSS, ".umi-pw-wrap > input")
    assert ".umi-pw-wrap" in OUTPUT_CSS, "output.css was not recompiled"


# ── 3. an email waiting for its link says so on the settings page ────────────


@pytest.fixture
def no_email_user():
    return User.objects.create_user(username="nomail", password="Str0ng-p4ss!x9", email=None)


def _request_email(client, address):
    return client.post(reverse("account-settings"), {"email": address, "phone": ""})


def test_settings_shows_the_address_waiting_for_its_link(client, no_email_user):
    client.force_login(no_email_user)
    _request_email(client, "later@example.org")

    html = client.get(reverse("account-settings")).content.decode()
    assert "We sent a link to <strong>later@example.org</strong>" in html
    assert "spam or junk" in html
    no_email_user.refresh_from_db()
    assert no_email_user.email is None  # still never written before the click


def test_a_taken_address_waits_exactly_like_a_free_one(client, no_email_user):
    User.objects.create_user(username="owner", password="Str0ng-p4ss!x9", email="taken@example.org")
    client.force_login(no_email_user)
    _request_email(client, "taken@example.org")

    html = client.get(reverse("account-settings")).content.decode()
    assert "We sent a link to <strong>taken@example.org</strong>" in html


def test_the_notice_clears_once_the_link_is_clicked_on_another_device(client, no_email_user):
    client.force_login(no_email_user)
    _request_email(client, "later@example.org")
    Client().get(reverse("account-confirm-email", args=[make_add_email_token(no_email_user, "later@example.org")]))

    html = client.get(reverse("account-settings")).content.decode()
    assert "We sent a link to" not in html


def test_the_waiting_page_points_at_the_spam_folder(client, no_email_user):
    client.force_login(no_email_user)
    session = client.session
    session[PENDING_EMAIL_KEY] = "later@example.org"
    session.save()
    html = client.get(reverse("verify-pending")).content.decode()
    assert "spam or junk" in html


# ── 4. community settings do what they say, and say where ────────────────────


def _settings(community):
    return reverse("community-settings", kwargs={"slug": community.slug})


def test_a_preset_is_not_undone_by_colour_pickers_left_alone(world):
    community, admin, _ = world
    # What a browser really sends: a colour input always submits its value.
    _login(admin).post(
        _settings(community),
        {"action": "set_theme", "theme": "royal", "custom_primary": "#275d4c", "custom_accent": "#9c7a3c"},
    )
    community.refresh_from_db()
    assert "theme_custom" not in community.settings
    assert resolve_theme(community)["primary"] == THEMES["royal"]["primary"]


def test_custom_colours_apply_only_when_the_box_is_ticked(world):
    community, admin, _ = world
    _login(admin).post(
        _settings(community),
        {"action": "set_theme", "theme": "royal", "use_custom": "on", "custom_primary": "#aa3311"},
    )
    community.refresh_from_db()
    assert resolve_theme(community)["primary"] == "#aa3311"


def test_scene_menus_show_names_not_file_names(world):
    community, admin, _ = world
    html = _login(admin).get(_settings(community)).content.decode()
    assert set(SCENE_LABELS) == set(SCENE_SLUGS)
    for slug in SCENE_SLUGS:
        assert f">{slug}<" not in html
        assert SCENE_LABELS[slug] in html


def test_each_identity_field_says_where_it_shows(world):
    community, admin, _ = world
    html = _login(admin).get(_settings(community)).content.decode()
    assert "not shown on any page yet" in html  # patron: honest until it is
    assert 'under "Welcome back"' in html
    assert "beside the greeting" in html
    assert "public front page" in html
    assert "buttons, links" in html  # where the colours land


def test_settings_previews_the_chosen_scene(world):
    community, admin, _ = world
    client = _login(admin)
    client.post(_settings(community), {"action": "set_identity", "scene_hub": "lakes"})
    html = client.get(_settings(community)).content.decode()
    assert re.search(r'data-scene-preview="hub"[^>]*src="[^"]*scenes/lakes\.webp"', html) or re.search(
        r'src="[^"]*scenes/lakes\.webp"[^>]*data-scene-preview="hub"', html
    )


def test_the_hub_scene_is_not_hidden_on_phones():
    assert "display: none" not in _css_block(INPUT_CSS, ".umi-scene-wash")


# ── 5. a need carries the day it was posted and the day it was done ──────────


def test_the_card_shows_the_day_a_need_was_posted(world):
    community, _, member = world
    need = NeedFactory(community=community, requester=member, category=CategoryFactory(community=community))
    type(need).objects.filter(pk=need.pk).update(created_at=datetime(2026, 10, 2, 16, 0, tzinfo=UTC))
    html = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug})).content.decode()
    assert re.search(r'Posted <time datetime="2026-10-02T[^"]*">Oct 2</time>', html)


def test_a_done_need_shows_both_days(world):
    community, admin, member = world
    need = NeedFactory(community=community, requester=member, category=CategoryFactory(community=community))
    type(need).objects.filter(pk=need.pk).update(
        created_at=datetime(2026, 10, 2, 16, 0, tzinfo=UTC),
        status="fulfilled",
        fulfilled_at=datetime(2026, 10, 5, 16, 0, tzinfo=UTC),
    )
    html = _login(admin).get(reverse("need-detail", args=[community.slug, need.pk])).content.decode()
    assert re.search(r"&middot; <time[^>]*>Oct 2, 2026</time>", html)  # after "Posted by <name>"
    assert re.search(r"Done <time[^>]*>Oct 5, 2026</time>", html)
