"""Registration under option C (docs/specs/email-confirmation.md, "Registration") and #171.

Registration no longer writes the address. It rides inside a signed link, and the click
writes it, proves it and verifies the account in one save, through the same view #169
built for adding an email later. Two holes close with it: anyone could register with YOUR
address and so lock you out of it (User.email is unique), and the form told any stranger
whether an address already had an account here, which password reset and username
recovery both refuse to do.
"""

import re
import time

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core import mail, signing
from django.urls import reverse
from django.utils import timezone

from apps.accounts.verification import HONEYPOT_TS_SALT

User = get_user_model()
STRONG = "Str0ng-p4ss!x9-neighbor"
CONFIRM_LINK = re.compile(r"https?://\S+/auth/email/confirm/[^\s/]+/")


def _register(client, n, username, email=""):
    """POST the register form like a human: honeypot empty, form age past the minimum."""
    ts = signing.dumps(time.time() - 30, salt=HONEYPOT_TS_SALT)
    return client.post(
        reverse("register"),
        {
            "username": username,
            "email": email,
            "password": STRONG,
            "password_confirm": STRONG,
            "website": "",
            "hp_ts": ts,
        },
        REMOTE_ADDR=f"10.171.0.{n}",
    )


def _confirm_link(message):
    found = CONFIRM_LINK.search(message.body)
    assert found, message.body
    return found.group(0)


def _flashes(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


@pytest.mark.django_db
class TestRegistrationWritesNothingUntilTheClick:
    def test_the_address_is_not_on_the_account_after_registering(self, client):
        resp = _register(client, 1, "nuala", "nuala@example.org")
        assert resp.status_code == 302
        user = User.objects.get(username="nuala")
        assert user.email is None
        assert user.email_confirmed_at is None
        assert [m.to for m in mail.outbox] == [["nuala@example.org"]]
        _confirm_link(mail.outbox[0])

    def test_the_click_writes_proves_and_verifies_in_one_step(self, client):
        _register(client, 2, "marta", "marta@example.org")
        client.logout()  # the link works signed out, from a phone's mail app
        client.get(_confirm_link(mail.outbox[0]))
        user = User.objects.get(username="marta")
        assert user.email == "marta@example.org"
        assert user.email_confirmed_at is not None
        assert user.verified_at is not None
        assert user.verified_via == "email"

    def test_an_unclicked_registration_cannot_squat_your_address(self, client):
        _register(client, 3, "squatter", "owner@example.org")  # never clicked
        client.logout()
        mail.outbox.clear()
        _register(client, 4, "owner", "owner@example.org")
        client.logout()
        client.get(_confirm_link(mail.outbox[0]))
        assert User.objects.get(username="owner").email == "owner@example.org"
        assert User.objects.get(username="squatter").email is None

    def test_registering_without_an_email_sends_nothing(self, client):
        _register(client, 5, "pewneighbor")
        assert mail.outbox == []
        assert "pending_email" not in client.session


@pytest.mark.django_db
class TestATakenAddressIsNotAnOracle:
    """#171: the answer must not depend on whether the address has an account."""

    def _holder(self, email="taken@example.org"):
        return User.objects.create_user("holder", email=email, password=STRONG, email_confirmed_at=timezone.now())

    def test_a_taken_address_gets_the_same_answer_as_a_fresh_one(self, client):
        self._holder()
        fresh = _register(client, 6, "newcomer1", "fresh@example.org")
        fresh_flashes = _flashes(fresh)
        client.logout()
        taken = _register(client, 7, "newcomer2", "taken@example.org")
        assert fresh.status_code == taken.status_code == 302
        assert fresh.url == taken.url
        assert _flashes(taken) == fresh_flashes
        assert "already in use" not in taken.content.decode()
        assert User.objects.get(username="newcomer2").email is None
        assert User.objects.get(username="holder").email == "taken@example.org"

    @pytest.mark.parametrize("typed", ["taken@example.org", "Taken@Example.ORG"])
    def test_its_owner_gets_a_notice_that_names_no_account(self, client, typed):
        self._holder()
        _register(client, 8, "newcomer", typed)
        assert len(mail.outbox) == 1
        notice = mail.outbox[0]
        assert notice.to == [typed]
        assert not CONFIRM_LINK.search(notice.body)
        assert "/auth/verify/" not in notice.body
        assert "holder" not in notice.body
        assert "newcomer" not in notice.body


@pytest.mark.django_db
class TestThePendingAddressIsReachable:
    def test_the_waiting_page_says_where_the_link_went(self, client):
        _register(client, 9, "aggie", "aggie@example.org")
        body = client.get(reverse("verify-pending")).content.decode()
        assert "aggie@example.org" in body
        assert "Add an email" not in body

    def test_resend_reaches_the_pending_address(self, client):
        _register(client, 10, "dan", "dan@example.org")
        mail.outbox.clear()
        client.post(reverse("verify-send"), REMOTE_ADDR="10.171.1.10")
        assert [m.to for m in mail.outbox] == [["dan@example.org"]]
        _confirm_link(mail.outbox[0])

    def test_confirming_clears_the_pending_address(self, client):
        _register(client, 11, "brigid", "brigid@example.org")
        client.get(_confirm_link(mail.outbox[0]))
        assert "pending_email" not in client.session
