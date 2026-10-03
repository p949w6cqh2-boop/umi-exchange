"""Codes by phone instead of paper (docs/specs/phone-codes.md), decided 2026-10-02.

The first coordinator: "we will use phones, she said we should stay away from paper. Switch paper
codes to phone codes." The founder's four answers: Twilio Verify; paper kept as the backup;
Communion-at-home numbers seen by coordinators only; voice-call codes for landlines.

The provider is reached through apps/accounts/phone.py alone, and every test here replaces it, so
the suite never sends a text or places a call. The feature ships OFF (PHONE_CODES_ENABLED).
"""

import html
import json
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts import phone
from apps.audit.models import AuditLog
from tests.conftest import CategoryFactory, MemberFactory, NeedFactory

User = get_user_model()
pytestmark = pytest.mark.django_db

NUMBER = "(555) 234-5678"
E164 = "+15552345678"


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    from django.core.cache import cache

    settings.RATELIMIT_ENABLED = False
    cache.clear()


@pytest.fixture
def on(settings):
    settings.PHONE_CODES_ENABLED = True
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "token_test"
    settings.TWILIO_VERIFY_SERVICE_SID = "VA_test"


@pytest.fixture
def fake():
    """Stands in for Twilio: records sends, approves only the code 123456."""
    with (
        mock.patch.object(phone, "send_code", return_value=True) as send,
        mock.patch.object(phone, "check_code", side_effect=lambda number, code: code == "123456") as check,
    ):
        yield send, check


def _user(phone_number=NUMBER, confirmed=False):
    u = User.objects.create_user(username="ruth", password="Str0ng-p4ss!x9", phone=phone_number)
    if confirmed:
        u.phone_confirmed_at = timezone.now()
        u.save(update_fields=["phone_confirmed_at"])
    return u


def _client(user):
    c = Client()
    c.force_login(user)
    return c


# ── numbers: US and Canada only, a guard against SMS-pumping fraud ───────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("(555) 234-5678", E164),
        ("555.234.5678", E164),
        ("1-555-234-5678", E164),
        ("+1 555 234 5678", E164),
        ("+44 20 7946 0958", None),
        ("123", None),
        ("", None),
        ("(055) 234-5678", None),  # no area code starts with 0 or 1
    ],
)
def test_only_us_and_canada_numbers_get_codes(raw, expected):
    assert phone.normalize(raw) == expected


# ── off by default ───────────────────────────────────────────────────────────


def test_off_by_default_nothing_new_appears(client, settings):
    assert settings.PHONE_CODES_ENABLED is False
    assert phone.enabled() is False
    html = _client(_user()).get(reverse("account-settings")).content.decode()
    assert "Text me a code" not in html
    assert "Get a code by phone" not in client.get(reverse("login")).content.decode()
    assert client.get(reverse("phone-recover")).status_code == 404


def test_switched_on_without_credentials_is_still_off(settings):
    settings.PHONE_CODES_ENABLED = True
    settings.TWILIO_AUTH_TOKEN = ""
    assert phone.enabled() is False


# ── proving a phone ──────────────────────────────────────────────────────────


def test_settings_offers_a_text_and_a_call_for_an_unproven_number(on):
    html = _client(_user()).get(reverse("account-settings")).content.decode()
    assert "Not confirmed yet" in html
    assert "Text me a code" in html and "Call me with a code" in html


@pytest.mark.parametrize("channel", ["sms", "call"])
def test_sending_a_code_texts_or_calls_the_normalized_number(on, fake, channel):
    send, _ = fake
    user = _user()
    resp = _client(user).post(reverse("phone-send"), {"channel": channel})
    assert resp.status_code == 302 and resp["Location"] == reverse("phone-confirm")
    send.assert_called_once_with(E164, channel)


def test_a_number_outside_us_and_canada_gets_no_code(on, fake):
    send, _ = fake
    _client(_user("+44 20 7946 0958")).post(reverse("phone-send"), {"channel": "sms"})
    send.assert_not_called()


def test_at_most_five_codes_a_day(on, fake):
    # The cap guards money, so it holds even with the sign-in throttle switched off (this file).
    send, _ = fake
    c = _client(_user())
    for _ in range(7):
        c.post(reverse("phone-send"), {"channel": "sms"})
    assert send.call_count == 5


def test_the_right_code_proves_the_number(on, fake):
    user = _user()
    c = _client(user)
    c.post(reverse("phone-send"), {"channel": "sms"})
    c.post(reverse("phone-confirm"), {"code": "000000"})
    user.refresh_from_db()
    assert user.phone_confirmed_at is None
    c.post(reverse("phone-confirm"), {"code": "123456"})
    user.refresh_from_db()
    assert user.phone_confirmed_at is not None
    assert user.deliverable_phone == NUMBER


def test_changing_the_number_clears_the_proof(on):
    user = _user(confirmed=True)
    user.phone = "(555) 999-0000"
    user.save()
    user.refresh_from_db()
    assert user.phone_confirmed_at is None
    assert user.deliverable_phone is None


def test_no_number_and_no_code_reach_the_audit_record(on, fake):
    user = _user()
    c = _client(user)
    c.post(reverse("phone-send"), {"channel": "sms"})
    c.post(reverse("phone-confirm"), {"code": "123456"})
    rows = AuditLog.objects.filter(action__startswith="account.phone")
    assert rows.count() >= 2
    blob = json.dumps([r.details for r in rows])
    assert "5552345678" not in blob and "123456" not in blob


# ── getting back in with a phone code ────────────────────────────────────────


def _recover(client, username, channel="sms"):
    return client.post(reverse("phone-recover"), {"username": username, "channel": channel})


def test_the_recover_page_answers_the_same_for_every_account(on, fake, client):
    send, _ = fake
    User.objects.create_user(username="nophone", password="Str0ng-p4ss!x9")
    User.objects.create_user(username="unproven", password="Str0ng-p4ss!x9", phone=NUMBER)
    proven = User.objects.create_user(username="proven", password="Str0ng-p4ss!x9", phone=NUMBER)
    proven.phone_confirmed_at = timezone.now()
    proven.save(update_fields=["phone_confirmed_at"])

    answers = set()
    for name in ("nobody-by-this-name", "nophone", "unproven", "proven"):
        resp = Client().post(reverse("phone-recover"), {"username": name, "channel": "sms"}, follow=True)
        answers.add(
            (resp.status_code, resp.redirect_chain[-1][0], "If that account has a phone" in resp.content.decode())
        )
    assert len(answers) == 1
    send.assert_called_once_with(E164, "sms")  # only the proven number ever gets a code


def test_a_phone_code_starts_a_password_reset_and_never_signs_in(on, fake):
    _user(confirmed=True)
    c = Client()
    _recover(c, "ruth")
    resp = c.post(reverse("phone-recover-code"), {"code": "123456"})
    assert resp.status_code == 302
    assert "/auth/password/reset/" in resp["Location"]  # the stock set-a-new-password page
    assert "_auth_user_id" not in c.session
    assert AuditLog.objects.filter(action="account.phone_code.redeemed").exists()


def test_a_wrong_or_missing_code_fails_the_same_way(on, fake):
    _user(confirmed=True)
    c = Client()
    _recover(c, "ruth")
    wrong = html.unescape(c.post(reverse("phone-recover-code"), {"code": "000000"}).content.decode())
    never_sent = html.unescape(Client().post(reverse("phone-recover-code"), {"code": "123456"}).content.decode())
    msg = "That code didn't work"
    assert msg in wrong and msg in never_sent


def test_landline_people_can_ask_for_a_call(on, fake):
    send, _ = fake
    _user(confirmed=True)
    _recover(Client(), "ruth", channel="call")
    send.assert_called_once_with(E164, "call")


def test_the_sign_in_page_offers_it_once_switched_on(on, client):
    assert "Get a code by phone" in client.get(reverse("login")).content.decode()


def test_the_recover_pages_sit_behind_the_sign_in_throttle(settings):
    assert any("/auth/recover/phone/".startswith(p) for p in settings.RATELIMIT_AUTH_PATHS)


# ── the provider module itself, with the network replaced ───────────────────


def _fake_urlopen(status):
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = json.dumps({"status": status}).encode()
    return mock.patch("apps.accounts.phone.urllib.request.urlopen", return_value=resp)


def test_send_code_is_true_only_when_twilio_says_pending(on):
    with _fake_urlopen("pending"):
        assert phone.send_code(E164, "sms") is True
    with _fake_urlopen("canceled"):
        assert phone.send_code(E164, "sms") is False


def test_check_code_is_true_only_when_twilio_says_approved(on):
    with _fake_urlopen("approved"):
        assert phone.check_code(E164, "123456") is True
    with _fake_urlopen("pending"):
        assert phone.check_code(E164, "000000") is False


def test_a_network_failure_is_a_quiet_false(on):
    with mock.patch("apps.accounts.phone.urllib.request.urlopen", side_effect=OSError("down")):
        assert phone.send_code(E164, "sms") is False
        assert phone.check_code(E164, "123456") is False


def test_send_code_refuses_an_unknown_channel(on):
    with pytest.raises(ValueError):
        phone.send_code(E164, "whatsapp")


# ── Communion at home: coordinators only ─────────────────────────────────────


@pytest.fixture
def communion_match():
    from apps.matches.models import Match

    requester = MemberFactory(role="member")
    requester.user.phone = NUMBER
    requester.user.save()
    community = requester.community
    helper = MemberFactory(community=community, role="member")
    coordinator = MemberFactory(community=community, role="coordinator")
    category = CategoryFactory(community=community, name="Communion at home", coordinators_only_contact=True)
    need = NeedFactory(community=community, requester=requester, category=category, contact_pref="any")
    match = Match.objects.create(need=need, offer=None, proposed_by=helper, status="accepted")
    return match, requester, helper, coordinator


def test_the_helper_never_sees_a_communion_number(communion_match):
    match, requester, helper, coordinator = communion_match
    seen_by_helper = match.get_contact_info_for(helper)
    assert seen_by_helper is not None
    assert "phone" not in seen_by_helper and "email" not in seen_by_helper
    assert match.get_contact_info_for(coordinator)["phone"] == NUMBER


def test_ordinary_requests_still_share_the_number_with_the_helper(communion_match):
    match, requester, helper, coordinator = communion_match
    match.need.category.coordinators_only_contact = False
    match.need.category.save()
    assert match.get_contact_info_for(helper)["phone"] == NUMBER


def test_the_migration_marks_communion_at_home_coordinators_only():
    import importlib

    from django.apps import apps

    from apps.communities.models import Category

    mig = importlib.import_module("apps.communities.migrations.0006_category_coordinators_only_contact")
    member = MemberFactory()
    Category.objects.create(community=member.community, name="Communion at home", icon="x")
    mig.mark_communion_at_home(apps, None)
    assert Category.objects.get(community=member.community, name="Communion at home").coordinators_only_contact
