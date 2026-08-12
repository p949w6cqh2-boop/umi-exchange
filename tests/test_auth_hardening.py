"""
Auth-hardening regressions (bug-hunt batch 3, #5 #6 #26 #27).

#5  AuthRateLimitMiddleware derived the per-account identifier as
    (POST['login'] or username or email). No form here uses a 'login' field
    (LoginForm's field is 'username'), so attaching a fresh login=<random> per
    request minted a new account bucket every time — the 20/hr per-account
    throttle never advanced, enabling distributed credential-stuffing.
#6  /admin/login/ was absent from RATELIMIT_AUTH_PATHS, so the highest-privilege
    login surface had zero brute-force protection.
#26 The per-account bucket was keyed only on the identifier, not the action, so
    login/register/reset shared one counter — flooding /register/ with a victim's
    name locked that victim out of /login/.
#27 RegistrationForm.clean() ran validate_password(pw, self.instance), but a
    ModelForm's instance isn't populated until _post_clean() (after clean()), so
    UserAttributeSimilarityValidator saw an empty username and a password equal
    to the username was accepted.

IP note: both views carry django_ratelimit(key="ip") decorators (register 3/m,
login 5/m); multi-POST tests rotate REMOTE_ADDR so those per-IP guards never fire
and the per-account middleware behaviour is what's under test.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.accounts.ratelimit import AUTH_ACCT_LIMIT, AUTH_IP_LIMIT
from tests.conftest import register_payload

User = get_user_model()
pytestmark = pytest.mark.django_db


def _ip(tag, i):
    """A distinct client IP per request, so per-IP throttles don't mask the
    per-account behaviour under test."""
    return f"10.{tag}.{i // 256}.{i % 256}"


# ------------------------------------------------------------------------ #27
def test_registration_rejects_password_equal_to_username(client):
    """Password identical to the username must be refused (#27). Username is
    11 chars so MinimumLengthValidator passes — this isolates the similarity
    check that was inert."""
    resp = client.post(
        reverse("register"),
        register_payload(username="alexandria9", email="", password="alexandria9", password_confirm="alexandria9"),
    )
    assert resp.status_code == 200  # re-rendered with an error, not a redirect
    assert not User.objects.filter(username="alexandria9").exists()


# ------------------------------------------------------------------------- #5
def test_decoy_login_field_does_not_bypass_account_throttle():
    """A fake 'login' POST field must not reset the per-account counter (#5)."""
    User.objects.create_user(username="martadecoy", password="pw-Str0ng!pass")
    last = None
    for i in range(AUTH_ACCT_LIMIT + 1):  # 21 attempts on one account
        last = Client().post(
            reverse("login"),
            {"username": "martadecoy", "password": "wrong", "login": f"decoy-{i}"},
            REMOTE_ADDR=_ip(11, i),  # fresh IP each time → per-IP guards stay clear
        )
    assert last.status_code == 429  # the account throttle still bites despite the decoy


# ------------------------------------------------------------------------- #6
def test_admin_login_is_rate_limited():
    """The admin login surface must be brute-force throttled (#6)."""
    last = None
    for _ in range(AUTH_IP_LIMIT + 1):  # 6 attempts from one IP
        last = Client().post(reverse("admin:login"), {"username": "root", "password": "x"}, REMOTE_ADDR="10.6.6.6")
    assert last.status_code == 429


# ------------------------------------------------------------------------ #26
def test_register_flood_does_not_lock_victim_out_of_login():
    """Flooding /register/ with a victim's name must not 429 their own login (#26)."""
    User.objects.create_user(username="victim26", password="pw-Str0ng!pass")
    for i in range(AUTH_ACCT_LIMIT + 1):  # fill the register bucket for "victim26"
        Client().post(
            reverse("register"),
            register_payload(username="victim26", email="", password="x", password_confirm="x"),
            REMOTE_ADDR=_ip(26, i),
        )
    # The victim's own login, from a clean IP, must not be throttled by that flood.
    resp = Client().post(
        reverse("login"), {"username": "victim26", "password": "pw-Str0ng!pass"}, REMOTE_ADDR="10.27.0.1"
    )
    assert resp.status_code != 429


# a cheap config pin alongside the behavioural test, mirroring the batch-1 style
def test_admin_login_path_registered_for_throttling():
    assert "/admin/login/" in settings.RATELIMIT_AUTH_PATHS
