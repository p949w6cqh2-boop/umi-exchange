"""A1 — the printed recovery code (docs/specs/account-recovery.md §B).

An account made without an email has no way back in if its password is forgotten: reset and
username recovery are both email-only. A1 gives that person a code on paper, shown once, that
STARTS a password reset (never grants a session) and is replaced the moment it is used.
"""

import logging
import re

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.accounts.credentials import hash_code, issue
from apps.accounts.models import RecoveryCredential, User
from apps.audit.models import AuditLog
from tests.conftest import register_payload
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

CODE_RE = re.compile(r"\b[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}\b")
PURPOSE = RecoveryCredential.PURPOSE_RECOVERY_CODE


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    """Every Client here posts from 127.0.0.1, so the auth limiter's shared buckets would
    429 later tests. Its behavior is tested in test_auth_hardening.py; this file only needs
    the redeem path to be registered with it (test_redemption_is_rate_limited_...)."""
    from django.core.cache import cache

    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _register(client, **fields):
    data = {"username": "martha", "email": "", "password": "Str0ng-pass-word!", "password_confirm": "Str0ng-pass-word!"}
    data.update(fields)
    return client.post(reverse("register"), register_payload(**data))


def _codes(response):
    return CODE_RE.findall(response.content.decode())


# ── Issued at registration, only when no email was given ───────


def test_registration_without_email_shows_a_code_once():
    client = Client()
    resp = _register(client)
    assert resp.status_code == 200
    shown = _codes(resp)
    assert len(set(shown)) == 1
    user = User.objects.get(username="martha")
    cred = RecoveryCredential.objects.get(user=user, purpose=PURPOSE)
    assert cred.token_hash == hash_code(shown[0])
    # The account exists and is signed in, exactly as before A1.
    assert client.session.get("_auth_user_id") == str(user.pk)


def test_registration_with_email_issues_no_code():
    resp = _register(Client(), email="martha@example.org")
    assert resp.status_code == 302
    assert not RecoveryCredential.objects.filter(user__username="martha").exists()


def test_code_page_is_printable_and_asks_for_confirmation():
    body = _register(Client()).content.decode()
    assert "@media print" in body
    assert "I have written this down" in body
    # The continue control cannot be used until the box is ticked.
    assert re.search(r'<input[^>]*type="checkbox"[^>]*required', body)


def test_issuance_is_audited_without_the_code():
    resp = _register(Client())
    code = _codes(resp)[0]
    row = AuditLog.objects.get(action="account.recovery_code.issued")
    assert code not in str(row.details) and code.replace("-", "") not in str(row.details)


def test_the_code_never_reaches_the_logs(caplog):
    with caplog.at_level(logging.DEBUG):
        resp = _register(Client())
    code = _codes(resp)[0]
    assert code not in caplog.text and code.replace("-", "") not in caplog.text


# ── Redemption starts a reset; it never signs anyone in ───────


def test_right_code_leads_to_a_password_reset_and_a_fresh_code():
    user = UserFactory(username="agnes", email=None, email_confirmed_at=None)
    _, code = issue(user, PURPOSE)
    client = Client()
    resp = client.post(reverse("recovery-code-redeem"), {"username": "agnes", "code": code})
    assert resp.status_code == 200
    assert "_auth_user_id" not in client.session  # no session granted
    body = resp.content.decode()
    new_codes = [c for c in _codes(resp) if c != code]
    assert len(set(new_codes)) == 1  # the replacement is offered immediately
    link = re.search(r'(?:href|action)="(/auth/password/reset/[^"]+/)"', body).group(1)
    assert client.get(link, follow=True).status_code == 200
    assert RecoveryCredential.objects.get(user=user, token_hash=hash_code(code)).used_at is not None
    assert RecoveryCredential.objects.filter(user=user, purpose=PURPOSE, used_at__isnull=True).count() == 1
    assert AuditLog.objects.filter(action="account.recovery_code.redeemed").count() == 1


def test_reset_link_actually_sets_the_password():
    user = UserFactory(username="agnes", email=None, email_confirmed_at=None)
    _, code = issue(user, PURPOSE)
    client = Client()
    body = client.post(reverse("recovery-code-redeem"), {"username": "agnes", "code": code}).content.decode()
    link = re.search(r'(?:href|action)="(/auth/password/reset/[^"]+/)"', body).group(1)
    form_page = client.get(link, follow=True)
    new_pw = "N3w-pass-phrase!"
    client.post(form_page.request["PATH_INFO"], {"new_password1": new_pw, "new_password2": new_pw})
    user.refresh_from_db()
    assert user.check_password("N3w-pass-phrase!")


def test_a_code_works_once():
    user = UserFactory(username="agnes")
    _, code = issue(user, PURPOSE)
    Client().post(reverse("recovery-code-redeem"), {"username": "agnes", "code": code})
    resp = Client().post(reverse("recovery-code-redeem"), {"username": "agnes", "code": code})
    assert resp.status_code == 200 and "/auth/password/reset/" not in resp.content.decode()


def test_wrong_code_and_unknown_user_get_the_same_answer():
    user = UserFactory(username="agnes")
    issue(user, PURPOSE)
    wrong = Client().post(reverse("recovery-code-redeem"), {"username": "agnes", "code": "AAAA-BBBB-CCCC"})
    nobody = Client().post(reverse("recovery-code-redeem"), {"username": "nobody-here", "code": "AAAA-BBBB-CCCC"})
    strip = lambda r: re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", r.content.decode())  # noqa: E731
    assert strip(wrong).replace("agnes", "X") == strip(nobody).replace("nobody-here", "X")
    assert "/auth/password/reset/" not in strip(wrong)


def test_redemption_is_rate_limited_on_ip_and_username():
    assert "/auth/recover/code/" in settings.RATELIMIT_AUTH_PATHS
    assert reverse("recovery-code-redeem").startswith("/auth/recover/code/")


def test_login_page_points_to_the_code_path():
    assert reverse("recovery-code-redeem") in Client().get(reverse("login")).content.decode()


# ── Re-issue from settings ─────────────────────────────────────


def test_signed_in_user_without_email_can_print_a_new_code_and_the_old_one_dies():
    user = UserFactory(username="agnes", email=None, email_confirmed_at=None)
    _, old = issue(user, PURPOSE)
    client = Client()
    client.force_login(user)
    assert reverse("recovery-code-new") in client.get(reverse("account-settings")).content.decode()
    resp = client.post(reverse("recovery-code-new"))
    assert resp.status_code == 200
    new = [c for c in _codes(resp) if c != old]
    assert len(set(new)) == 1
    assert (
        Client()
        .post(reverse("recovery-code-redeem"), {"username": "agnes", "code": old})
        .content.decode()
        .count("/auth/password/reset/")
        == 0
    )


def test_reissue_requires_sign_in_and_post():
    assert Client().post(reverse("recovery-code-new")).status_code == 302  # to login
    user = UserFactory()
    client = Client()
    client.force_login(user)
    assert client.get(reverse("recovery-code-new")).status_code == 405
