"""
Enforce enrolled 2FA at login (bug-hunt batch 11, #4).

ENABLE_2FA is True in every real install (django-otp + two-factor ship in
requirements and are auto-detected), the settings page says "Your account is
protected with TOTP two-factor authentication" — and none of it gated login.
LOGIN_URL resolves to UMILoginView, a bare DjangoLoginView: password alone
yielded a full session, no view anywhere checked is_verified(). 2FA provided
zero authentication protection while claiming it.

The fix keeps /auth/login/ (and all its hardening: LoginForm, the IP throttle,
the per-account middleware) and adds the OTP step inside it: an enrolled user's
password POST does NOT log in — it stashes the pending user in the session and
redirects to the token step, which verifies via django_otp.match_token (TOTP
and static recovery codes, device-level throttling built in) before the session
is established. Un-enrolled users are untouched.
"""

import time

import pytest
from django.urls import reverse
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.views import OTP_PENDING_SESSION_KEY

pytestmark = pytest.mark.django_db

PASSWORD = "pw-Str0ng!pass"

_ip_counter = iter(range(1, 250))


@pytest.fixture
def ip():
    """A distinct client IP per test: login and the OTP step are both
    IP-throttled at 5/m, and the ratelimit cache outlives a test."""
    return f"10.99.0.{next(_ip_counter)}"


def _user():
    """create_user hashes the password properly (same shape as the casework
    conftest); a raw set_password on a factory user trips the semgrep audit."""
    from django.contrib.auth import get_user_model

    handle = f"otpuser{next(_ip_counter)}x{next(_ip_counter)}"
    return get_user_model().objects.create_user(username=handle, email=f"{handle}@example.test", password=PASSWORD)


def _enrol_totp(user):
    return TOTPDevice.objects.create(user=user, name="phone", confirmed=True)


def _valid_token(device):
    return f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):0{device.digits}d}"


def _post_login(client, user, ip, **extra):
    return client.post(reverse("login"), {"username": user.username, "password": PASSWORD, **extra}, REMOTE_ADDR=ip)


# ------------------------------------------------------------ the gate
def test_enrolled_user_gets_no_session_on_password_alone(client, ip):
    user = _user()
    _enrol_totp(user)

    resp = _post_login(client, user, ip)

    assert resp.status_code == 302
    assert resp["Location"] == reverse("login-otp")
    assert "_auth_user_id" not in client.session, "password alone must not establish a session"


def test_unenrolled_user_logs_straight_in(client, ip):
    """The gate must not touch neighbours who never set 2FA up."""
    user = _user()

    resp = _post_login(client, user, ip)

    assert resp.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_valid_totp_token_completes_login_verified(client, ip):
    user = _user()
    device = _enrol_totp(user)
    _post_login(client, user, ip)

    resp = client.post(reverse("login-otp"), {"token": _valid_token(device)}, REMOTE_ADDR=ip)

    assert resp.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)
    assert client.session[DEVICE_ID_SESSION_KEY] == device.persistent_id, "session must be OTP-verified"
    assert OTP_PENDING_SESSION_KEY not in client.session


def test_wrong_token_refuses_and_grants_nothing(client, ip):
    user = _user()
    _enrol_totp(user)
    _post_login(client, user, ip)

    resp = client.post(reverse("login-otp"), {"token": "000000"}, REMOTE_ADDR=ip)

    assert resp.status_code == 200, "re-rendered with an error"
    assert "_auth_user_id" not in client.session


def test_static_recovery_token_also_completes_login(client, ip):
    """match_token spans device types — a lost phone must not mean a lost account."""
    user = _user()
    _enrol_totp(user)
    static = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
    StaticToken.objects.create(device=static, token="rescue12")
    _post_login(client, user, ip)

    resp = client.post(reverse("login-otp"), {"token": "rescue12"}, REMOTE_ADDR=ip)

    assert resp.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_otp_step_without_a_pending_login_bounces_to_login(client, ip):
    resp_get = client.get(reverse("login-otp"))
    resp_post = client.post(reverse("login-otp"), {"token": "123456"}, REMOTE_ADDR=ip)

    assert resp_get.status_code == 302 and resp_get["Location"] == reverse("login")
    assert resp_post.status_code == 302 and resp_post["Location"] == reverse("login")
    assert "_auth_user_id" not in client.session


def test_stale_pending_login_expires(client, ip):
    user = _user()
    device = _enrol_totp(user)
    _post_login(client, user, ip)
    session = client.session
    session[OTP_PENDING_SESSION_KEY]["ts"] = time.time() - 3600
    session.save()

    resp = client.post(reverse("login-otp"), {"token": _valid_token(device)}, REMOTE_ADDR=ip)

    assert resp.status_code == 302 and resp["Location"] == reverse("login")
    assert "_auth_user_id" not in client.session


def test_next_param_survives_the_otp_step(client, ip):
    user = _user()
    device = _enrol_totp(user)
    _post_login(client, user, ip, next="/account/settings/")

    resp = client.post(reverse("login-otp"), {"token": _valid_token(device)}, REMOTE_ADDR=ip)

    assert resp.status_code == 302
    assert resp["Location"] == "/account/settings/"
