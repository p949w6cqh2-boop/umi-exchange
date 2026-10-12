"""Batch-3 regression (2026-10 bug hunt, account security).

1. A coordinator's reset code must never reach an account that holds power anywhere else: a
   coordinator, admin or intake helper of another community, or a staff or superuser account.
   The reset is scoped to "a plain member of THIS community", but the code it mints opens the
   whole account (docs/specs/account-recovery.md §C: a reset must never be a way to climb).
2. The two-factor package's own LoginView (/account/login/) was a second password door beside
   UMILoginView (/auth/login/), outside the auth rate limiter and without the OTP diversion.
3. Vouching marks an account as a real person. An unverified account could create a community,
   become its admin and vouch for itself (or anyone), stepping around the verification gate.
"""

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import RecoveryCredential
from tests.factories import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db
RESET = RecoveryCredential.PURPOSE_COORDINATOR_RESET


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_ENABLED = False
    cache.clear()


def _reset(issuer, username):
    client = Client()
    client.force_login(issuer.user)
    return client.post(reverse("member-reset", kwargs={"slug": issuer.community.slug}), {"username": username})


def _issued(user):
    return RecoveryCredential.objects.filter(user=user, purpose=RESET).count()


# ── 1. The reset never climbs ──────────────────────────────────


@pytest.mark.parametrize("elsewhere_role", ["admin", "coordinator", "intake"])
def test_reset_refuses_a_plain_member_who_holds_a_role_elsewhere(elsewhere_role):
    x_coordinator = MemberFactory(role="coordinator")
    person = UserFactory(username="twohats")
    MemberFactory(community=x_coordinator.community, user=person, role="member")
    MemberFactory(community=CommunityFactory(), user=person, role=elsewhere_role)

    resp = _reset(x_coordinator, "twohats")

    assert resp.status_code == 200
    assert resp.context["code"] is None
    assert _issued(person) == 0


def test_reset_refuses_a_role_held_in_a_membership_they_left():
    """Rejoining with an unrotated code restores a left member's role, so a past coordinator
    seat is still power: the reset must not reach it."""
    x_coordinator = MemberFactory(role="coordinator")
    person = UserFactory(username="formercoord")
    MemberFactory(community=x_coordinator.community, user=person, role="member")
    MemberFactory(community=CommunityFactory(), user=person, role="coordinator", is_active=False)

    assert _reset(x_coordinator, "formercoord").context["code"] is None
    assert _issued(person) == 0


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_reset_refuses_staff_and_superuser_accounts(flag):
    x_coordinator = MemberFactory(role="coordinator")
    person = UserFactory(username="boardstaff", **{flag: True})
    MemberFactory(community=x_coordinator.community, user=person, role="member")

    assert _reset(x_coordinator, "boardstaff").context["code"] is None
    assert _issued(person) == 0


def test_reset_still_works_for_a_plain_member_everywhere():
    x_coordinator = MemberFactory(role="coordinator")
    person = UserFactory(username="plainperson")
    MemberFactory(community=x_coordinator.community, user=person, role="member")
    MemberFactory(community=CommunityFactory(), user=person, role="member")

    assert _reset(x_coordinator, "plainperson").context["code"]
    assert _issued(person) == 1


# ── 2. One password door ───────────────────────────────────────


def test_two_factor_login_view_is_not_mounted():
    client = Client()
    assert client.get("/account/login/").status_code == 404
    assert client.post("/account/login/", {"auth-username": "x", "auth-password": "y"}).status_code == 404
    with pytest.raises(NoReverseMatch):
        reverse("two_factor:login")


def test_two_factor_setup_pages_are_still_mounted():
    assert reverse("two_factor:setup") == "/account/two_factor/setup/"
    assert reverse("two_factor:profile") == "/account/two_factor/"


# ── 3. Only a verified person can vouch ────────────────────────


def _vouch(voucher, username):
    client = Client()
    client.force_login(voucher.user)
    return client.post(reverse("member-vouch", kwargs={"slug": voucher.community.slug}), {"username": username})


def test_unverified_admin_cannot_vouch_for_themselves():
    newcomer = UserFactory(username="selfmade", verified_at=None, verified_via="")
    admin = MemberFactory(user=newcomer, role="admin")  # what CommunityCreateView makes

    resp = _vouch(admin, "selfmade")

    assert resp.status_code == 403
    newcomer.refresh_from_db()
    assert newcomer.verified_at is None


def test_unverified_admin_cannot_vouch_for_someone_else():
    admin = MemberFactory(user=UserFactory(verified_at=None, verified_via=""), role="admin")
    other = UserFactory(username="botfriend", verified_at=None, verified_via="")

    assert _vouch(admin, "botfriend").status_code == 403
    other.refresh_from_db()
    assert other.verified_at is None


def test_verified_coordinator_still_vouches():
    coordinator = MemberFactory(role="coordinator")
    neighbour = UserFactory(username="metinperson", verified_at=None, verified_via="")

    assert _vouch(coordinator, "metinperson").status_code in (301, 302)
    neighbour.refresh_from_db()
    assert neighbour.verified_via == "coordinator"


@override_settings(RATELIMIT_ENABLE=True)
def test_vouching_is_rate_limited_per_voucher():
    coordinator = MemberFactory(role="coordinator")
    for i in range(31):
        UserFactory(username=f"pew{i}", verified_at=None, verified_via="")
    codes = [_vouch(coordinator, f"pew{i}").status_code for i in range(31)]
    assert all(c in (301, 302) for c in codes[:30])
    assert codes[30] in (403, 429)
