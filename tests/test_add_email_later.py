"""Adding an email to an account that started without one.

Email is optional at registration by design — the protocol serves participants who
have no address, and `human-verification.md` refused a CAPTCHA for the same reason.
But password reset and username recovery are both email-only, so an account created
without an address has NO recovery path: `set_password` appears twice in the
codebase and neither is a view, so not even a coordinator can help. The only repair
is a superuser in Django admin.

The lockout therefore lands on exactly the people the optional-email decision was
made for. Spec: docs/specs/account-recovery.md §A.

Three properties these tests pin, each of which was a way to get this wrong:

  1. `User.email` is NEVER written before the address is confirmed. It is
     unique=True, so an unconfirmed write lets anyone squat an address they do
     not control — and squatting it also denies it to its real owner forever.
  2. A collision answers EXACTLY like success. Password reset and username
     recovery both refuse to reveal whether an address has an account here, and
     digest #4 says so in public. A third endpoint that leaks it undoes both.
  3. Confirming an email NEVER overwrites `verified_via="coordinator"`. That
     vouch is a human act performed at church, in front of a witness. It is not
     ours to overwrite with a weaker machine fact.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.verification import make_add_email_token, make_email_token

User = get_user_model()
pytestmark = pytest.mark.django_db

STRONG = "Str0ng-p4ss!x9"
NEW = "later@example.org"


@pytest.fixture
def no_email_user():
    """The account this whole feature exists for: registered with no address."""
    return User.objects.create_user(username="nomail", password=STRONG, email=None)


def _login(client, user):
    client.force_login(user)
    return client


def _request_email(client, address):
    """The surface is ACCOUNT SETTINGS — the page people already look at for
    this — not a new route. Phone must ride along because it is the same form."""
    return client.post(reverse("account-settings"), {"email": address, "phone": ""})


# ── requesting ───────────────────────────────────────────────────────────────


def test_requesting_does_not_write_the_address(client, no_email_user):
    """The whole point. email is unique=True, so writing it unconfirmed lets
    anyone squat an address they do not control."""
    _login(client, no_email_user)

    _request_email(client, NEW)

    no_email_user.refresh_from_db()
    assert no_email_user.email in (None, "")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [NEW]


def test_anonymous_cannot_request(client):
    resp = _request_email(client, NEW)

    assert resp.status_code in (302, 403)
    assert len(mail.outbox) == 0


# ── non-enumeration ──────────────────────────────────────────────────────────


def test_a_taken_address_answers_exactly_like_success(client, no_email_user):
    """Same status, same redirect, no mail. If the two cases differ in any way a
    stranger can observe, this endpoint becomes the enumeration oracle that
    password reset and username recovery were built to refuse."""
    User.objects.create_user(username="owner", password=STRONG, email=NEW)
    _login(client, no_email_user)

    taken = _request_email(client, NEW)
    mail.outbox.clear()
    free = _request_email(client, "free@example.org")

    assert taken.status_code == free.status_code
    assert taken.url == free.url
    assert taken.content == free.content


def test_a_taken_address_sends_nothing_to_its_owner(client, no_email_user):
    """Mailing the existing owner would tell a stranger the address is
    registered here, by using the owner's own inbox as the oracle."""
    User.objects.create_user(username="owner", password=STRONG, email=NEW)
    _login(client, no_email_user)

    _request_email(client, NEW)

    assert len(mail.outbox) == 0


# ── confirming ───────────────────────────────────────────────────────────────


def test_confirming_writes_the_address(client, no_email_user):
    token = make_add_email_token(no_email_user, NEW)

    client.get(reverse("account-confirm-email", args=[token]))

    no_email_user.refresh_from_db()
    assert no_email_user.email == NEW


def test_confirming_verifies_an_unverified_account(client, no_email_user):
    """No verified_at yet: this is a first verification, so email is the honest
    value for verified_via."""
    assert no_email_user.verified_at is None
    token = make_add_email_token(no_email_user, NEW)

    client.get(reverse("account-confirm-email", args=[token]))

    no_email_user.refresh_from_db()
    assert no_email_user.verified_at is not None
    assert no_email_user.verified_via == "email"


def test_a_coordinator_vouch_survives_confirming_an_email(client, no_email_user):
    """The load-bearing one. A coordinator vouched for this person in front of a
    witness at church. Adding an email later must not quietly downgrade that
    record to a machine fact."""
    no_email_user.verified_at = timezone.now()
    no_email_user.verified_via = "coordinator"
    no_email_user.save(update_fields=["verified_at", "verified_via"])
    vouched_at = no_email_user.verified_at
    token = make_add_email_token(no_email_user, NEW)

    client.get(reverse("account-confirm-email", args=[token]))

    no_email_user.refresh_from_db()
    assert no_email_user.email == NEW
    assert no_email_user.verified_via == "coordinator"
    assert no_email_user.verified_at == vouched_at


def test_an_address_taken_after_the_link_was_sent_is_refused(client, no_email_user):
    """The race: someone else registers this address between the send and the
    click. unique=True would raise at save time, so the collision is re-checked
    at confirm and the write refused."""
    token = make_add_email_token(no_email_user, NEW)
    User.objects.create_user(username="faster", password=STRONG, email=NEW)

    client.get(reverse("account-confirm-email", args=[token]))

    no_email_user.refresh_from_db()
    assert no_email_user.email in (None, "")
    assert User.objects.get(username="faster").email == NEW


def test_a_registration_token_cannot_confirm_an_arbitrary_address(client, no_email_user):
    """Salt separation. The register flow's token carries only a uid. If both
    flows shared a salt, any old registration link could be replayed here to
    attach an address of the attacker's choosing."""
    registration_token = make_email_token(no_email_user)

    client.get(reverse("account-confirm-email", args=[registration_token]))

    no_email_user.refresh_from_db()
    assert no_email_user.email in (None, "")


def test_a_garbage_token_writes_nothing(client, no_email_user):
    client.get(reverse("account-confirm-email", args=["not-a-real-token"]))

    no_email_user.refresh_from_db()
    assert no_email_user.email in (None, "")
