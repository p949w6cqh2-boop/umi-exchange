"""B8: coordinator-assisted sign-up, without the speed check (#170; build plan B8).

The public sign-up silently drops a form submitted faster than a human reads it: right against a
script, wrong against a coordinator on their tenth neighbor of the morning. His ruling 2026-09-30:
build it now, outside the ethics gate. This route is signed-in, for this community's coordinators
and admins; it drops ONLY the speed check (the hidden-field check stays), never signs the new
person in, gives an email-less person their paper recovery code, and is audited and rate-limited
per coordinator. The public route is untouched.
"""

import re

import pytest
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.models import RecoveryCredential, User
from apps.audit.models import AuditLog
from tests.factories import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db
CODE_RE = re.compile(r"\b[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}\b")


@pytest.fixture(autouse=True)
def _mail_and_no_throttle(settings):
    from django.core.cache import cache

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_ENABLED = False
    cache.clear()


@pytest.fixture
def parish():
    return CommunityFactory()


def _url(parish):
    return reverse("intake-register", kwargs={"slug": parish.slug})


def _as(member):
    client = Client()
    client.force_login(member.user)
    return client


def _fields(username="walkin", **extra):
    data = {"username": username, "email": "", "password": "Str0ng-pass-word!", "password_confirm": "Str0ng-pass-word!"}
    data.update(extra)
    return data


# ── Who ────────────────────────────────────────────────────────


def test_anonymous_goes_to_login(parish):
    resp = Client().get(_url(parish))
    assert resp.status_code == 302 and "/auth/login/" in resp["Location"]


def test_plain_member_is_refused(parish):
    member = MemberFactory(community=parish, role="member")
    assert _as(member).get(_url(parish)).status_code == 403
    assert _as(member).post(_url(parish), _fields()).status_code == 403
    assert not User.objects.filter(username="walkin").exists()


def test_coordinator_of_another_parish_is_refused(parish):
    elsewhere = MemberFactory(community=CommunityFactory(), role="coordinator")
    assert _as(elsewhere).post(_url(parish), _fields()).status_code == 403


# ── The fix itself ─────────────────────────────────────────────


def test_an_instant_submit_with_no_timestamp_creates_the_account(parish):
    """Exactly what the public route silently drops: no hp_ts, submitted immediately."""
    coord = MemberFactory(community=parish, role="coordinator")
    resp = _as(coord).post(_url(parish), _fields())
    assert resp.status_code == 200
    assert User.objects.filter(username="walkin").exists()


def test_ten_in_a_row_all_land(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    client = _as(coord)
    for i in range(10):
        client.post(_url(parish), _fields(username=f"neighbor{i}"))
    assert User.objects.filter(username__startswith="neighbor").count() == 10


def test_the_hidden_field_check_still_trips(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _as(coord).post(_url(parish), _fields(website="http://spam.example"))
    assert not User.objects.filter(username="walkin").exists()


def test_the_coordinator_stays_signed_in_as_themselves(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    client = _as(coord)
    client.post(_url(parish), _fields())
    assert client.session["_auth_user_id"] == str(coord.user.pk)


def test_email_less_neighbor_gets_their_paper_code(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    resp = _as(coord).post(_url(parish), _fields())
    user = User.objects.get(username="walkin")
    assert RecoveryCredential.objects.filter(user=user, purpose="recovery_code").count() == 1
    assert len(set(CODE_RE.findall(resp.content.decode()))) == 1
    assert _url(parish) in resp.content.decode()  # "next neighbor" goes back to the form


def test_neighbor_with_an_email_gets_the_confirm_link_not_a_code(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _as(coord).post(_url(parish), _fields(email="walkin@example.org"))
    user = User.objects.get(username="walkin")
    assert user.email is None  # option C: nothing written until the link is clicked
    assert not RecoveryCredential.objects.filter(user=user).exists()
    assert [m.to for m in mail.outbox] == [["walkin@example.org"]]


def test_audited_as_intake_with_the_community(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    _as(coord).post(_url(parish), _fields())
    row = AuditLog.objects.get(action="account.registered.intake")
    assert row.user == coord.user
    assert row.details == {"community": parish.slug}


@override_settings(RATELIMIT_ENABLE=True)
def test_rate_limited_per_coordinator(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    client = _as(coord)
    codes = [client.post(_url(parish), _fields(username=f"n{i}")).status_code for i in range(31)]
    assert all(c == 200 for c in codes[:30])
    assert codes[30] in (403, 429)


# ── The public door is unchanged ───────────────────────────────


def test_public_register_still_drops_an_instant_submit():
    resp = Client().post(reverse("register"), _fields(username="scripted"), REMOTE_ADDR="10.8.8.8")
    assert resp.status_code == 302
    assert not User.objects.filter(username="scripted").exists()


def test_settings_page_links_to_it(parish):
    coord = MemberFactory(community=parish, role="coordinator")
    body = _as(coord).get(reverse("community-settings", kwargs={"slug": parish.slug})).content.decode()
    assert _url(parish) in body
