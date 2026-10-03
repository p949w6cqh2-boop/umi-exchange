"""Codes by phone instead of paper (docs/specs/phone-codes.md), decided 2026-10-02.

The first coordinator: "we will use phones, she said we should stay away from paper. Switch paper
codes to phone codes." The founder's answers: paper kept as the backup; Communion-at-home numbers
seen by coordinators only; voice-call codes for landlines once a provider can call. The provider,
2026-10-03: "lets do firebase for now then after we get a nonprofit we will switch to twilio."

The provider is reached through apps/accounts/phone.py alone, and every test here replaces it or its
network call, so the suite never sends a text or places a call. The feature ships OFF.
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
    """Switched on with Firebase, the provider for now."""
    settings.PHONE_CODES_ENABLED = True
    settings.PHONE_CODES_PROVIDER = "firebase"
    settings.FIREBASE_API_KEY = "AIza_test"


@pytest.fixture
def on_twilio(settings):
    """Switched on with Twilio, the provider after the 501(c)(3)."""
    settings.PHONE_CODES_ENABLED = True
    settings.PHONE_CODES_PROVIDER = "twilio"
    settings.TWILIO_ACCOUNT_SID = "AC_test"
    settings.TWILIO_AUTH_TOKEN = "token_test"
    settings.TWILIO_VERIFY_SERVICE_SID = "VA_test"


@pytest.fixture
def fake():
    """Stands in for the provider: records sends, approves only 123456 for the state it handed out."""
    with (
        mock.patch.object(phone, "send_code", return_value="state-1") as send,
        mock.patch.object(
            phone, "check_code", side_effect=lambda number, code, state: code == "123456" and state == "state-1"
        ) as check,
        mock.patch.object(phone, "recaptcha_site_key", return_value="site-key-test"),
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
    html_ = _client(_user()).get(reverse("account-settings")).content.decode()
    assert "Text me a code" not in html_
    assert "Get a code by phone" not in client.get(reverse("login")).content.decode()
    assert client.get(reverse("phone-recover")).status_code == 404


def test_firebase_is_the_provider_for_now(settings):
    assert settings.PHONE_CODES_PROVIDER == "firebase"
    assert phone.channels() == ("sms",)  # Firebase texts; it cannot call a landline


def test_switched_on_without_its_key_is_still_off(on, settings):
    settings.FIREBASE_API_KEY = ""
    assert phone.enabled() is False


# ── proving a phone ──────────────────────────────────────────────────────────


def test_settings_offers_a_text_but_no_call_with_firebase(on, fake):
    page = _client(_user()).get(reverse("account-settings")).content.decode()
    assert "Not confirmed yet" in page
    assert "Text me a code" in page and "Call me with a code" not in page


def test_settings_offers_a_call_too_with_twilio(on_twilio, fake):
    page = _client(_user()).get(reverse("account-settings")).content.decode()
    assert "Text me a code" in page and "Call me with a code" in page


def test_settings_never_loads_google(on, fake):
    assert "google.com/recaptcha" not in _client(_user()).get(reverse("account-settings")).content.decode()


def test_the_send_page_carries_recaptcha_and_widens_csp_only_there(on, fake):
    resp = _client(_user()).get(reverse("phone-send") + "?channel=sms")
    page = resp.content.decode()
    assert 'data-sitekey="site-key-test"' in page and "www.google.com/recaptcha/api.js" in page
    policy = resp["Content-Security-Policy"]
    assert "https://www.google.com/recaptcha/" in policy and "frame-src" in policy
    assert "https://www.google.com/recaptcha/" not in Client().get(reverse("login"))["Content-Security-Policy"]


def test_sending_a_code_passes_the_recaptcha_token(on, fake):
    send, _ = fake
    resp = _client(_user()).post(reverse("phone-send"), {"channel": "sms", "recaptcha_token": "tok"})
    assert resp.status_code == 302 and resp["Location"] == reverse("phone-confirm")
    send.assert_called_once_with(E164, "sms", recaptcha_token="tok")


def test_firebase_never_places_a_call(on, fake):
    send, _ = fake
    _client(_user()).post(reverse("phone-send"), {"channel": "call", "recaptcha_token": "tok"})
    send.assert_not_called()


def test_twilio_can_call_a_landline(on_twilio, fake):
    send, _ = fake
    _client(_user()).post(reverse("phone-send"), {"channel": "call"})
    send.assert_called_once_with(E164, "call", recaptcha_token="")


def test_a_number_outside_us_and_canada_gets_no_code(on, fake):
    send, _ = fake
    _client(_user("+44 20 7946 0958")).post(reverse("phone-send"), {"channel": "sms", "recaptcha_token": "tok"})
    send.assert_not_called()


def test_at_most_five_codes_a_day(on, fake):
    # The cap guards money, so it holds even with the sign-in throttle switched off (this file).
    send, _ = fake
    c = _client(_user())
    for _ in range(7):
        c.post(reverse("phone-send"), {"channel": "sms", "recaptcha_token": "tok"})
    assert send.call_count == 5


def test_the_right_code_proves_the_number(on, fake):
    user = _user()
    c = _client(user)
    c.post(reverse("phone-send"), {"channel": "sms", "recaptcha_token": "tok"})
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
    c.post(reverse("phone-send"), {"channel": "sms", "recaptcha_token": "tok"})
    c.post(reverse("phone-confirm"), {"code": "123456"})
    rows = AuditLog.objects.filter(action__startswith="account.phone")
    assert rows.count() >= 2
    blob = json.dumps([r.details for r in rows])
    assert "5552345678" not in blob and "123456" not in blob


# ── getting back in with a phone code ────────────────────────────────────────


def _recover(client, username, channel="sms"):
    return client.post(reverse("phone-recover"), {"username": username, "channel": channel, "recaptcha_token": "tok"})


def test_the_recover_page_answers_the_same_for_every_account(on, fake, client):
    send, _ = fake
    User.objects.create_user(username="nophone", password="Str0ng-p4ss!x9")
    User.objects.create_user(username="unproven", password="Str0ng-p4ss!x9", phone=NUMBER)
    proven = User.objects.create_user(username="proven", password="Str0ng-p4ss!x9", phone=NUMBER)
    proven.phone_confirmed_at = timezone.now()
    proven.save(update_fields=["phone_confirmed_at"])

    answers = set()
    for name in ("nobody-by-this-name", "nophone", "unproven", "proven"):
        data = {"username": name, "channel": "sms", "recaptcha_token": "tok"}
        resp = Client().post(reverse("phone-recover"), data, follow=True)
        answers.add(
            (resp.status_code, resp.redirect_chain[-1][0], "If that account has a phone" in resp.content.decode())
        )
    assert len(answers) == 1
    send.assert_called_once_with(E164, "sms", recaptcha_token="tok")  # only the proven number gets a code


def test_the_recover_page_offers_only_texts_with_firebase(on, fake, client):
    page = client.get(reverse("phone-recover")).content.decode()
    assert "Call me and read it out" not in page
    assert 'data-sitekey="site-key-test"' in page


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


def test_landline_people_can_ask_for_a_call_with_twilio(on_twilio, fake):
    send, _ = fake
    _user(confirmed=True)
    _recover(Client(), "ruth", channel="call")
    send.assert_called_once_with(E164, "call", recaptcha_token="tok")


def test_the_sign_in_page_offers_it_once_switched_on(on, client):
    assert "Get a code by phone" in client.get(reverse("login")).content.decode()


def test_the_recover_pages_sit_behind_the_sign_in_throttle(settings):
    assert any("/auth/recover/phone/".startswith(p) for p in settings.RATELIMIT_AUTH_PATHS)


# ── the provider module itself, with the network replaced ───────────────────


def _responses(*bodies):
    """urlopen stand-in returning each JSON body in turn; records each request."""
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = json.dumps(bodies[len(calls) - 1]).encode()
        return resp

    return calls, mock.patch("apps.accounts.phone.urllib.request.urlopen", side_effect=fake_urlopen)


def test_firebase_send_returns_googles_session_info(on):
    calls, patch = _responses({"sessionInfo": "S"})
    with patch:
        assert phone.send_code(E164, "sms", recaptcha_token="tok") == "S"
    body = json.loads(calls[0].data)
    assert "accounts:sendVerificationCode" in calls[0].full_url
    assert body == {"phoneNumber": E164, "recaptchaToken": "tok"}


def test_firebase_send_without_a_recaptcha_token_never_leaves_the_board(on):
    calls, patch = _responses()
    with patch:
        assert phone.send_code(E164, "sms") is None
    assert calls == []


def test_firebase_check_approves_the_right_number_then_deletes_googles_copy(on):
    calls, patch = _responses({"phoneNumber": E164, "idToken": "T"}, {})
    with patch:
        assert phone.check_code(E164, "123456", "S") is True
    assert "accounts:signInWithPhoneNumber" in calls[0].full_url
    assert "accounts:delete" in calls[1].full_url and json.loads(calls[1].data) == {"idToken": "T"}


def test_firebase_check_refuses_a_different_number(on):
    _calls, patch = _responses({"phoneNumber": "+15550000000", "idToken": "T"}, {})
    with patch:
        assert phone.check_code(E164, "123456", "S") is False


def test_firebase_check_without_a_session_is_false(on):
    calls, patch = _responses()
    with patch:
        assert phone.check_code(E164, "123456", None) is False
    assert calls == []


def test_the_recaptcha_site_key_is_fetched_once_and_cached(on):
    calls, patch = _responses({"recaptchaSiteKey": "K"})
    with patch:
        assert phone.recaptcha_site_key() == "K"
        assert phone.recaptcha_site_key() == "K"
    assert len(calls) == 1 and "recaptchaParams" in calls[0].full_url


def test_twilio_send_and_check(on_twilio):
    _calls, patch = _responses({"status": "pending"}, {"status": "approved"})
    with patch:
        assert phone.send_code(E164, "sms") == "twilio"
        assert phone.check_code(E164, "123456", "twilio") is True


def test_a_network_failure_is_a_quiet_nothing(on):
    with mock.patch("apps.accounts.phone.urllib.request.urlopen", side_effect=OSError("down")):
        assert phone.send_code(E164, "sms", recaptcha_token="tok") is None
        assert phone.check_code(E164, "123456", "S") is False


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
