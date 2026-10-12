"""Batch-4 regression (2026-10 bug hunt, core flows that broke for ordinary members).

1. Notification titles quote the need or offer title into a 200-character column. Postgres
   rejects the overflow (SQLite never did), so a long title failed every step of matching, and
   because the match was saved before the notification, each retry added another match.
2. A description the content check refused re-rendered the form with no message at all (only
   title errors were shown), and the category, urgency and contact choices were reset.
3. The script-pattern check refused ordinary text ("data:", "Donations = welcome") and the tag
   stripper silently deleted anything between '<' and '>'. Every place this text is shown
   autoescapes it, so neither protected anything. The word list itself is unchanged (his call).
4. A community whose name slugified to an existing slug, to nothing, or to "create" failed.
5. Cancelling an accepted match (or marking it unfulfilled) reopened the need with its old
   expiry date, so the hourly sweep expired it straight away.
"""

import re
from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.communities.models import Community
from apps.matches.models import Match
from apps.needs.models import Need
from apps.notifications.models import Notification
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


def _parish(**need_kwargs):
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    asker = MemberFactory(community=community)
    helper = MemberFactory(community=community, display_name="Joseph Okafor-Washington")
    need = NeedFactory(community=community, requester=asker, category=category, **need_kwargs)
    return community, category, asker, helper, need


# ── 1. Long titles ──────────────────────────────────────────────


def test_proposing_on_a_long_titled_need_works_once():
    community, _, asker, helper, need = _parish(title="Help " + "x" * 190)
    resp = _client(helper).post(reverse("match-propose", args=[community.slug]), {"need_id": str(need.id)})

    assert resp.status_code == 302
    assert Match.objects.filter(need=need).count() == 1
    note = Notification.objects.get(recipient=asker.user, type="match_proposed")
    assert len(note.title) <= 200


def test_accepting_on_a_long_titled_need_works():
    community, _, asker, helper, need = _parish(title="Help " + "y" * 190)
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")

    resp = _client(asker).post(reverse("match-update", args=[community.slug, match.id]), {"status": "accepted"})

    assert resp.status_code in (200, 302)
    match.refresh_from_db()
    assert match.status == "accepted"


# ── 2-3. Need and offer forms ───────────────────────────────────


def _post_need(member, category, **fields):
    data = {
        "category": str(category.id),
        "title": "Ride to the pharmacy",
        "description": "",
        "urgency": "medium",
        "neighborhood": "",
        "contact_pref": "in_app",
    }
    data.update(fields)
    return _client(member).post(reverse("need-create", args=[member.community.slug]), data)


def test_a_refused_description_says_why_and_keeps_the_choices():
    community, category, asker, _, _ = _parish()
    other = CategoryFactory(community=community, name="Errands", sort_order=99)
    before = Need.objects.count()

    resp = _post_need(asker, other, description="Pick up my prescription drugs", urgency="critical")

    assert resp.status_code == 200
    assert Need.objects.count() == before
    html = resp.content.decode()
    assert "violates community guidelines" in html
    assert re.search(r'name="urgency" value="critical"[^>]*checked', html)
    assert re.search(rf'name="category" value="{other.id}"[^>]*checked', html)
    assert re.search(r'name="contact_pref" value="in_app"[^>]*checked', html)


def test_a_fresh_need_form_keeps_its_safe_defaults():
    _, _, asker, _, _ = _parish()
    html = _client(asker).get(reverse("need-create", args=[asker.community.slug])).content.decode()
    assert re.search(r'name="urgency" value="medium"[^>]*checked', html)
    assert re.search(r'name="contact_pref" value="in_app"[^>]*checked', html)
    assert not re.search(r'name="contact_pref" value="any"[^>]*checked', html)


@pytest.mark.parametrize(
    "description",
    ["Phone ran out of data: need a top-up", "Donations = welcome", "I can teach JavaScript: beginners welcome"],
)
def test_ordinary_text_is_not_mistaken_for_script(description):
    _, category, asker, _, _ = _parish()
    resp = _post_need(asker, category, title="Ordinary ask", description=description)
    assert resp.status_code == 302
    assert Need.objects.get(title="Ordinary ask").description == description


def test_text_between_angle_brackets_is_kept():
    _, category, asker, _, _ = _parish()
    text = "I need <5 lbs of rice> and beans <for the family>"
    resp = _post_need(asker, category, title="Groceries", description=text)
    assert resp.status_code == 302
    assert Need.objects.get(title="Groceries").description == text


def test_angle_bracket_text_is_shown_escaped():
    community, category, asker, _, _ = _parish()
    _post_need(asker, category, title="Kept text", description="<b>bold</b> request")
    need = Need.objects.get(title="Kept text")
    html = _client(asker).get(reverse("need-detail", args=[community.slug, need.id])).content.decode()
    assert "&lt;b&gt;bold&lt;/b&gt; request" in html
    assert "<b>bold</b>" not in html


# ── 4. Community slugs ──────────────────────────────────────────


def _create(member, name):
    return _client(member).post(reverse("community-create"), {"name": name, "description": "", "visibility": "private"})


def test_a_name_that_slugifies_to_an_existing_slug_still_creates_a_community():
    CommunityFactory(name="St. Mary", slug="st-mary")
    creator = MemberFactory()
    resp = _create(creator, "St Mary")
    assert resp.status_code == 302
    made = Community.objects.get(name="St Mary")
    assert made.slug and made.slug != "st-mary"


@pytest.mark.parametrize("name", ["!!!", "Create"])
def test_an_empty_or_reserved_slug_is_replaced(name):
    creator = MemberFactory()
    resp = _create(creator, name)
    assert resp.status_code == 302
    made = Community.objects.get(name=name)
    assert made.slug and made.slug != "create"
    assert _client(creator).get(made.get_absolute_url()).status_code in (200, 302)


# ── 5. A reopened need gets a fresh expiry ──────────────────────


@pytest.mark.parametrize("ending", ["cancelled", "unfulfilled"])
def test_a_reopened_need_is_not_expired_by_its_old_date(ending):
    _, _, _, helper, need = _parish()
    match = MatchFactory(need=need, offer=None, proposed_by=helper, status="proposed")
    match.transition_to("accepted")
    Need.objects.filter(pk=need.pk).update(expires_at=timezone.now() - timedelta(hours=1))
    match.refresh_from_db()

    match.transition_to(ending)

    need.refresh_from_db()
    assert need.status == "open"
    assert need.expires_at > timezone.now() + timedelta(days=1)
