"""What the first coordinator asked for, 2026-10-02, beyond the bugs she hit.

6. A "Communion at home" category: homebound parishioners ask for a minister to bring
   communion. Added to every community that exists (all parishes), never to the defaults
   that a group which is not a parish also gets.
7. "Have it time you out of the website after 5-10 minutes of being idle." The people she
   helps borrow phones and share family tablets. Signed out after 15 quiet minutes, warned a
   minute before, and typing counts as activity, so a long request is never lost.
9. "Copy right it": the footer names the person who holds the copyright, not a project name
   that is no legal entity yet.
"""

import importlib
import json
import time

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.idle import BACKGROUND_HEADER, SESSION_KEY
from apps.communities.models import Category
from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db

LIMIT = settings.SESSION_IDLE_TIMEOUT_SECONDS


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def member():
    return MemberFactory(role="member")


def _hub(member):
    return reverse("hub:community", kwargs={"slug": member.community.slug})


def _stamp(client, seconds_ago):
    session = client.session
    session[SESSION_KEY] = time.time() - seconds_ago
    session.save()


def _signed_in(client):
    return "_auth_user_id" in client.session


# ── 6. Communion at home ─────────────────────────────────────────────────────

MIGRATION = importlib.import_module("apps.communities.migrations.0005_communion_at_home_category")


def test_every_existing_community_gets_communion_at_home_once():
    from django.apps import apps

    one, two = CommunityFactory(), CommunityFactory()
    MIGRATION.add_communion_at_home(apps, None)
    MIGRATION.add_communion_at_home(apps, None)  # a re-run adds nothing

    for community in (one, two):
        rows = Category.objects.filter(community=community, name="Communion at home")
        assert rows.count() == 1
        assert rows.get().is_active


def test_a_new_community_is_not_given_it_by_default():
    # The defaults reach groups that are not parishes; the category is each parish's own.
    community = CommunityFactory()
    assert not community.categories.filter(name="Communion at home").exists()


def test_the_request_form_offers_it(member):
    from django.apps import apps

    MIGRATION.add_communion_at_home(apps, None)
    html = _login(member).get(reverse("need-create", kwargs={"slug": member.community.slug})).content.decode()
    assert "Communion at home" in html


def test_the_demo_parish_seed_carries_it():
    from apps.communities.management.commands.seed_demo_parish import CATEGORIES

    assert "Communion at home" in [name for name, _ in CATEGORIES]


# ── 7. idle sign-out ─────────────────────────────────────────────────────────


def test_the_limit_is_fifteen_minutes_unless_tightened():
    assert LIMIT == 15 * 60


def test_a_quiet_session_is_signed_out_on_its_next_request(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT + 5)

    resp = client.get(_hub(member))

    assert resp.status_code == 302
    assert resp["Location"].startswith(settings.LOGIN_URL)
    assert not _signed_in(client)


def test_the_sign_in_page_says_why(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT + 5)

    html = client.get(_hub(member), follow=True).content.decode()
    assert "signed out after 15 minutes without activity" in html


def test_activity_inside_the_limit_keeps_the_session_and_restamps_it(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT - 30)

    assert client.get(_hub(member)).status_code == 200
    assert _signed_in(client)
    assert time.time() - client.session[SESSION_KEY] < 5


def test_the_hubs_minute_poll_is_not_activity(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, 100)
    before = client.session[SESSION_KEY]

    pulse = reverse("hub:pulse", kwargs={"slug": member.community.slug})
    assert client.get(pulse, headers={BACKGROUND_HEADER: "1", "HX-Request": "true"}).status_code == 200
    assert client.session[SESSION_KEY] == before  # an open tab cannot keep a session alive


def test_a_poll_after_the_limit_signs_out_and_reloads_the_page(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT + 5)

    pulse = reverse("hub:pulse", kwargs={"slug": member.community.slug})
    resp = client.get(pulse, headers={BACKGROUND_HEADER: "1", "HX-Request": "true"})

    assert resp.status_code == 204
    assert resp["HX-Refresh"] == "true"
    assert not _signed_in(client)


def test_the_hub_marks_its_poll_as_background(member):
    html = _login(member).get(_hub(member)).content.decode()
    assert f'hx-headers=\'{{"{BACKGROUND_HEADER}": "1"}}\'' in html


def test_a_json_request_after_the_limit_gets_the_reauth_answer(member):
    # The offline casework sync reads {"reauth": true} and keeps its queue.
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT + 5)

    resp = client.post(_hub(member), data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 403
    assert resp.json() == {"reauth": True}


def test_a_form_sent_after_the_limit_lands_on_plain_sign_in(member):
    # A POST cannot be replayed after signing in, so it gets no ?next= back to itself.
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT + 5)

    resp = client.post(reverse("account-settings"), {"email": "", "phone": ""})
    assert resp.status_code == 302
    assert resp["Location"] == settings.LOGIN_URL


def test_still_here_counts_as_activity(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT - 30)

    resp = client.get(reverse("idle-ping"))

    assert resp.status_code == 200
    assert resp["Cache-Control"] == "no-store"
    assert resp.json()["remaining"] >= LIMIT - 1
    assert time.time() - client.session[SESSION_KEY] < 5


def test_a_background_check_reports_the_time_left_without_extending_it(member):
    # The page warns and signs out on the server's clock. If it reloaded on its own clock,
    # the reload would be activity and the session would never end while a tab stayed open.
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, 100)
    before = client.session[SESSION_KEY]

    resp = client.get(reverse("idle-ping"), headers={BACKGROUND_HEADER: "1"})

    assert LIMIT - 102 <= resp.json()["remaining"] <= LIMIT - 99
    assert client.session[SESSION_KEY] == before


def test_a_background_check_after_the_limit_signs_out(member):
    client = _login(member)
    client.get(_hub(member))
    _stamp(client, LIMIT + 5)

    resp = client.get(reverse("idle-ping"), headers={BACKGROUND_HEADER: "1", "Accept": "application/json"})

    assert resp.status_code == 403
    assert not _signed_in(client)


def test_still_here_tells_a_signed_out_page_to_reload(client):
    assert client.get(reverse("idle-ping")).status_code == 401


def test_signed_in_pages_carry_the_warning_script(member, client):
    html = _login(member).get(_hub(member)).content.decode()
    assert f'data-idle-seconds="{LIMIT}"' in html
    assert 'src="/static/js/idle-timeout.js' in html

    anon = client.get(reverse("login")).content.decode()
    assert "idle-timeout.js" not in anon and "data-idle-seconds" not in anon


def test_the_warning_script_counts_typing_and_warns_a_minute_before():
    js = (settings.BASE_DIR / "static/js/idle-timeout.js").read_text()
    for event in ('"keydown"', '"input"', '"pointerdown"'):
        assert event in js
    assert "I'm still here" in js
    assert "60 * 1000" in js


# ── 9. copyright ─────────────────────────────────────────────────────────────


def test_the_footer_names_the_copyright_holder(client):
    html = client.get(reverse("login")).content.decode()
    assert "&copy; 2026 Jasiah Williams" in html
    assert "&copy; 2026 Reciprocal Aid Network" not in html
