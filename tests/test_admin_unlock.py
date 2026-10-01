"""A4: the audited admin unlock that is not Django /admin/ (docs/specs/account-recovery.md §A4).

A last resort for the board's staff: exact username, a required reason, and the result is a
one-hour unlock CODE the person redeems themselves at /auth/recover/code/. It never sets a
password. Every use is audited and emailed to every superuser, including the one who did it.
"""

import pytest
from django.core import mail
from django.test import Client
from django.urls import reverse

from apps.accounts.credentials import hash_code
from apps.accounts.models import RecoveryCredential
from apps.audit.models import AuditLog
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

URL = "/staff/unlock/"
REASON = "Called the office, identity confirmed by the pastor in person."


@pytest.fixture(autouse=True)
def _mail_and_no_throttle(settings):
    from django.core.cache import cache

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_ENABLED = False
    cache.clear()


@pytest.fixture
def staff():
    return UserFactory(username="steward", is_staff=True, is_superuser=True, email="steward@example.org")


def _as(user):
    client = Client()
    client.force_login(user)
    return client


def test_url_is_named_and_outside_community_surfaces():
    assert reverse("staff-unlock") == URL


def test_anonymous_goes_to_login():
    resp = Client().get(URL)
    assert resp.status_code == 302 and "/auth/login/" in resp["Location"]


def test_non_staff_is_refused():
    assert _as(UserFactory()).get(URL).status_code == 403
    assert _as(UserFactory()).post(URL, {"username": "x", "reason": REASON}).status_code == 403


def test_staff_sees_the_form(staff):
    body = _as(staff).get(URL).content.decode()
    assert 'name="username"' in body and 'name="reason"' in body


def test_reason_is_required(staff):
    target = UserFactory(username="lost")
    resp = _as(staff).post(URL, {"username": "lost", "reason": ""})
    assert resp.status_code == 200
    assert not RecoveryCredential.objects.filter(user=target).exists()


def test_unknown_username_issues_nothing(staff):
    resp = _as(staff).post(URL, {"username": "nobody", "reason": REASON})
    assert resp.status_code == 200
    assert not RecoveryCredential.objects.exists()


def test_lookup_is_exact_not_a_search(staff):
    UserFactory(username="Martha")
    _as(staff).post(URL, {"username": "martha", "reason": REASON})
    assert not RecoveryCredential.objects.exists()


def test_unlock_issues_a_one_hour_code_and_never_touches_the_password(staff):
    target = UserFactory(username="lost")
    before = target.password
    resp = _as(staff).post(URL, {"username": "lost", "reason": REASON})
    assert resp.status_code == 200
    cred = RecoveryCredential.objects.get(user=target, purpose=RecoveryCredential.PURPOSE_ADMIN_UNLOCK)
    target.refresh_from_db()
    assert target.password == before
    assert cred.issued_by_label == "steward"
    assert cred.note == REASON  # the reason lives on the redactable row
    code = resp.context["code"]
    assert cred.token_hash == hash_code(code)
    assert code in resp.content.decode()


def test_audit_records_that_a_reason_was_given_never_the_reason(staff):
    UserFactory(username="lost")
    _as(staff).post(URL, {"username": "lost", "reason": REASON})
    row = AuditLog.objects.get(action="account.unlock.admin")
    assert row.user == staff
    assert row.details == {"reason_provided": True}
    assert REASON not in str(row.details)


def test_every_superuser_is_emailed_including_the_one_who_did_it(staff):
    other = UserFactory(username="second", is_staff=True, is_superuser=True, email="second@example.org")
    UserFactory(username="lost")
    _as(staff).post(URL, {"username": "lost", "reason": REASON})
    recipients = sorted(r for m in mail.outbox for r in m.to)
    assert recipients == sorted([staff.email, other.email])
    body = mail.outbox[0].body
    assert "lost" in body and "steward" in body
    assert REASON not in body  # the reason stays on the row, not in inboxes


def test_person_redeems_the_unlock_code_at_the_recovery_page(staff):
    UserFactory(username="lost")
    code = _as(staff).post(URL, {"username": "lost", "reason": REASON}).context["code"]
    resp = Client().post(reverse("recovery-code-redeem"), {"username": "lost", "code": code})
    body = resp.content.decode()
    assert "/auth/password/reset/" in body
    assert RecoveryCredential.objects.get(purpose=RecoveryCredential.PURPOSE_ADMIN_UNLOCK).used_at is not None


def test_unlock_code_dies_after_an_hour(staff):
    from datetime import timedelta

    from django.utils import timezone

    UserFactory(username="lost")
    code = _as(staff).post(URL, {"username": "lost", "reason": REASON}).context["code"]
    RecoveryCredential.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    resp = Client().post(reverse("recovery-code-redeem"), {"username": "lost", "code": code})
    assert "/auth/password/reset/" not in resp.content.decode()
