"""2026-10 bug hunt, weaker leads: signing in and getting back in (L46-L50, L52-L54), verified
and fixed.

L46  The per-account login limit is keyed on the name typed, so anyone could lock a person out
     by failing to sign in as them. A browser that has signed in to the account before now passes
     that limit (the per-IP limit still applies); an unknown browser is still held back.
L47  The admin geo gate covered only /admin/login/, which only redirects to /auth/login/, so a
     sign-in from a refused country still reached /admin/. It now covers /admin/ and /staff/.
L48  A signed-in session could change the account's email, or print a new recovery code, without
     the current password, and the old address was never told. Both now ask for the password,
     and the old proven address hears about a change.
L49  Redeeming a 15-minute coordinator reset (or a one-hour unlock) also minted a permanent paper
     code. An account with a proven email now gets no paper code from it (spec §B).
L50  Any staff account could unlock a superuser, then set the superuser's password.
L52  The register form's signed stamp never expired and could be reused for any number of
     sign-ups. It now lasts a day and works once.
L53  The auth limiter counted IPv6 by the full address, so one /64 rotated past it.
L54  two_factor's setup wizard refused re-enrolment only on GET, so an old session could POST a
     second device in and come out of it verified.
"""

import re
import time
import types
from base64 import b32decode
from unittest import mock

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts import geo
from apps.accounts import ratelimit as rl
from apps.accounts.credentials import hash_code, issue
from apps.accounts.models import GeoSignupCount, RecoveryCredential, User
from apps.accounts.verification import honeypot_timestamp
from tests.conftest import MemberFactory, UserFactory

pytestmark = pytest.mark.django_db

PW = "Owner-pass-word-9!"
RC = RecoveryCredential.PURPOSE_RECOVERY_CODE
# The limiter's clock pinned mid-window, so no fixed window rolls over during a test.
FIXED = (int(time.time()) // 3600) * 3600 + 1800


@pytest.fixture(autouse=True)
def _env(settings):
    settings.RATELIMIT_ENABLED = False
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    cache.clear()
    geo.reset_cache()
    yield
    cache.clear()


@pytest.fixture
def limiter(settings):
    settings.RATELIMIT_ENABLED = True
    cache.clear()
    with mock.patch.object(rl, "time", types.SimpleNamespace(time=lambda: FIXED)):
        yield


def _as(user):
    c = Client()
    c.force_login(user)
    return c


# ── L46 ────────────────────────────────────────────────────────


def _sign_in(client, username, password, addr):
    return client.post(reverse("login"), {"username": username, "password": password}, REMOTE_ADDR=addr)


def _hammer(username, times):
    """Wrong passwords naming the account, from addresses that never trip the per-IP limit."""
    for i in range(times):
        _sign_in(Client(), username, "wrong", f"203.0.113.{1 + i // 5}")


def test_a_browser_that_signed_in_before_is_not_locked_out(limiter):
    UserFactory(username="victim", password=PW)
    owner = Client()
    assert _sign_in(owner, "victim", PW, "198.51.100.77").status_code == 302
    owner.post(reverse("logout"), REMOTE_ADDR="198.51.100.77")
    _hammer("victim", 19)  # with the owner's own sign-in, the account's hour is used up

    assert _sign_in(owner, "victim", PW, "198.51.100.77").status_code == 302


def test_an_unknown_browser_is_still_held_back(limiter):
    UserFactory(username="victim2", password=PW)
    _hammer("victim2", 20)
    assert _sign_in(Client(), "victim2", PW, "198.51.100.78").status_code == 429


def test_a_forged_device_cookie_does_not_pass(limiter):
    UserFactory(username="victim3", password=PW)
    _hammer("victim3", 20)
    c = Client()
    c.cookies[rl.KNOWN_DEVICE_COOKIE] = "forged"
    assert _sign_in(c, "victim3", PW, "198.51.100.79").status_code == 429


def test_a_cookie_from_another_account_does_not_pass(limiter):
    UserFactory(username="mine", password=PW)
    UserFactory(username="victim4", password=PW)
    c = Client()
    assert _sign_in(c, "mine", PW, "198.51.100.80").status_code == 302
    c.post(reverse("logout"), REMOTE_ADDR="198.51.100.80")
    _hammer("victim4", 20)
    assert _sign_in(c, "victim4", PW, "198.51.100.80").status_code == 429


# ── L47 ────────────────────────────────────────────────────────

GEO = {"GEO_DB_PATH": "/tmp/test-geo.mmdb", "GEO_ALLOWED_COUNTRIES": ["US"]}


@override_settings(**GEO, GEO_GATE_ADMIN=True)
def test_the_admin_gate_covers_the_whole_admin_and_the_staff_tools():
    boss = UserFactory(username="boss", is_staff=True, is_superuser=True)
    c = _as(boss)
    with mock.patch.object(geo, "country_for", return_value="FR"):
        assert c.get("/admin/").status_code == 403
        assert c.get(reverse("staff-unlock")).status_code == 403
    with mock.patch.object(geo, "country_for", return_value="US"):
        assert c.get("/admin/").status_code == 200


@override_settings(**GEO)
def test_the_admin_stays_open_unless_the_gate_is_switched_on():
    c = _as(UserFactory(is_staff=True, is_superuser=True))
    with mock.patch.object(geo, "country_for", return_value="FR"):
        assert c.get("/admin/").status_code == 200


@override_settings(**GEO, GEO_GATE_ADMIN=True, GEO_COUNT=True)
def test_admin_work_is_not_counted_as_a_sign_up_attempt():
    c = _as(UserFactory(is_staff=True, is_superuser=True))
    with mock.patch.object(geo, "country_for", return_value="US"):
        c.post("/admin/logout/")
    assert not GeoSignupCount.objects.exists()


# ── L48 ────────────────────────────────────────────────────────


def _change_email(client, new, **extra):
    data = {"email": new, "phone": "", "email_notifications": "on", **extra}
    return client.post(reverse("account-settings"), data, REMOTE_ADDR="10.9.0.1")


def test_changing_the_email_needs_the_current_password():
    owner = UserFactory(username="owner", email="owner@example.org", password=PW)

    resp = _change_email(_as(owner), "attacker@evil.test")

    assert resp.status_code == 200  # the form again, with the error
    assert "current password" in resp.content.decode().lower()
    assert not any("attacker@evil.test" in m.to for m in mail.outbox)


def test_a_wrong_password_sends_nothing():
    owner = UserFactory(username="owner1", email="owner1@example.org", password=PW)
    _change_email(_as(owner), "attacker@evil.test", current_password="guess")
    assert not any("attacker@evil.test" in m.to for m in mail.outbox)


def test_with_the_password_the_link_goes_out_and_the_old_address_is_told():
    owner = UserFactory(username="owner2", email="owner2@example.org", password=PW)
    c = _as(owner)

    assert _change_email(c, "new2@example.org", current_password=PW).status_code == 302
    link = re.search(r"/auth/email/confirm/[^/\s]+/", mail.outbox[-1].body).group(0)
    mail.outbox.clear()
    c.get(link)

    owner.refresh_from_db()
    assert owner.email == "new2@example.org"
    notices = [m for m in mail.outbox if m.to == ["owner2@example.org"]]
    assert len(notices) == 1
    assert "new2@example.org" in notices[0].body


def test_phone_and_notifications_still_save_without_a_password():
    owner = UserFactory(username="owner3", email="owner3@example.org", password=PW)
    resp = _as(owner).post(
        reverse("account-settings"), {"email": "owner3@example.org", "phone": "555-0100", "email_notifications": ""}
    )
    owner.refresh_from_db()
    assert resp.status_code == 302
    assert owner.phone == "555-0100" and not owner.email_notifications


def test_printing_a_new_recovery_code_needs_the_current_password():
    owner = UserFactory(username="paperowner", email=None, email_confirmed_at=None, password=PW)
    _, paper = issue(owner, RC)
    c = _as(owner)

    refused = c.post(reverse("recovery-code-new"), REMOTE_ADDR="10.9.0.4")
    assert refused.status_code == 302
    live = RecoveryCredential.objects.filter(user=owner, purpose=RC, used_at__isnull=True, revoked_at__isnull=True)
    assert list(live.values_list("token_hash", flat=True)) == [hash_code(paper)]

    printed = c.post(reverse("recovery-code-new"), {"current_password": PW}, REMOTE_ADDR="10.9.0.4")
    assert printed.status_code == 200 and printed.context["code"]


# ── L49 ────────────────────────────────────────────────────────


def _redeem(username, code):
    return Client().post(reverse("recovery-code-redeem"), {"username": username, "code": code}, REMOTE_ADDR="10.8.0.1")


def test_an_email_account_gets_no_paper_code_from_a_coordinator_reset():
    coordinator = MemberFactory(role="coordinator")
    person = UserFactory(username="emailuser", email="emailuser@example.org")
    MemberFactory(community=coordinator.community, user=person)
    reset = _as(coordinator.user).post(
        reverse("member-reset", kwargs={"slug": coordinator.community.slug}), {"username": "emailuser"}
    )

    resp = _redeem("emailuser", reset.context["code"])

    assert resp.status_code == 302 and "/password/reset/" in resp["Location"]
    assert not RecoveryCredential.objects.filter(user=person, purpose=RC).exists()


def test_a_paper_account_still_gets_a_fresh_code_when_it_redeems_its_paper():
    person = UserFactory(username="paperonly", email=None, email_confirmed_at=None)
    _, paper = issue(person, RC)

    resp = _redeem("paperonly", paper)

    assert resp.status_code == 200 and resp.context["code"]
    assert resp.context["reset_url"]


# ── L50 ────────────────────────────────────────────────────────


def _unlock(actor, username):
    return _as(actor).post(reverse("staff-unlock"), {"username": username, "reason": "Locked out, ID checked"})


@pytest.mark.parametrize("target_flags", [{"is_staff": True, "is_superuser": True}, {"is_staff": True}])
def test_plain_staff_cannot_unlock_a_staff_or_superuser_account(target_flags):
    UserFactory(username="founder", **target_flags)
    helper = UserFactory(username="helper", is_staff=True)

    resp = _unlock(helper, "founder")

    assert not (resp.context and resp.context.get("code"))
    assert not RecoveryCredential.objects.filter(
        user__username="founder", purpose=RecoveryCredential.PURPOSE_ADMIN_UNLOCK
    ).exists()


def test_a_superuser_can_unlock_a_superuser():
    UserFactory(username="founder2", is_staff=True, is_superuser=True)
    other = UserFactory(username="cofounder", is_staff=True, is_superuser=True)
    assert _unlock(other, "founder2").context["code"]


def test_plain_staff_still_unlock_an_ordinary_account():
    UserFactory(username="neighbour")
    helper = UserFactory(username="helper2", is_staff=True)
    assert _unlock(helper, "neighbour").context["code"]


# ── L52 ────────────────────────────────────────────────────────


def _register(username, stamp, addr):
    Client().post(
        reverse("register"),
        {
            "website": "",
            "hp_ts": stamp,
            "username": username,
            "email": "",
            "password": "Str0ng-pass-word!",
            "password_confirm": "Str0ng-pass-word!",
        },
        REMOTE_ADDR=addr,
    )
    return User.objects.filter(username=username).exists()


def _stamp(seconds_ago):
    with mock.patch("time.time", return_value=time.time() - seconds_ago):
        return honeypot_timestamp()


def test_a_stamp_from_two_days_ago_trips_the_bot_check():
    assert not _register("latecomer", _stamp(2 * 86400), "10.6.0.1")


def test_a_stamp_works_once():
    stamp = _stamp(30)
    assert _register("first", stamp, "10.6.0.2")
    assert not _register("second", stamp, "10.6.0.3")


def test_an_ordinary_sign_up_still_works():
    assert _register("ordinary", _stamp(30), "10.6.0.4")


# ── L53 ────────────────────────────────────────────────────────


def _redeem_from(addr, n):
    return (
        Client()
        .post(reverse("recovery-code-redeem"), {"username": f"guess{n}", "code": "AAAA-BBBB-CCCC"}, REMOTE_ADDR=addr)
        .status_code
    )


def test_one_ipv6_slash64_shares_one_auth_bucket(limiter):
    codes = [_redeem_from(f"2001:db8:1:2::{n + 1:x}", n) for n in range(12)]
    assert 429 in codes


def test_neighbouring_slash64s_do_not_share_one(limiter):
    codes = [_redeem_from(f"2001:db8:1:{n + 1:x}::1", n) for n in range(12)]
    assert 429 not in codes


# ── L54 ────────────────────────────────────────────────────────


def test_the_setup_wizard_refuses_a_post_once_a_device_exists():
    from django_otp.oath import totp
    from django_otp.plugins.otp_totp.models import TOTPDevice

    owner = UserFactory(username="totpowner")
    stale = _as(owner)  # a session from before enrolment
    TOTPDevice.objects.create(user=owner, name="default", confirmed=True)
    setup = reverse("two_factor:setup")

    stale.post(setup, {"setup_view-current_step": "welcome"})
    secret = stale.session.get("django_two_factor-qr_secret_key")
    if secret:  # only reachable before the fix
        token = totp(b32decode(secret), step=30, t0=0, digits=6, drift=0)
        stale.post(setup, {"setup_view-current_step": "generator", "generator-token": str(token)})

    assert not secret
    assert TOTPDevice.objects.filter(user=owner).count() == 1
