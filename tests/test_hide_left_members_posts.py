"""
`manage.py hide_left_members_posts`: the one-time step for members who left before leaving hid
anything (the founder's call, 2026-10-13).

Since #218, leaving hides the leaver's open asks and active offers (hidden_on_leave_at), and
coming back lists them to put back or close. People who left before that still have their posts
on the board. This command hides those the same reversible way. It is a dry run unless given
--apply, it deletes nothing, sends nothing, and leaves matches in progress as they are (it only
counts them). He runs it on the server after deploying #218.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.needs.models import Need
from apps.notifications.models import Notification
from apps.offers.models import Offer
from tests.conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory, OfferFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_throttle(settings):
    settings.RATELIMIT_ENABLED = False


def _run(*args):
    out = StringIO()
    call_command("hide_left_members_posts", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def parish():
    community = CommunityFactory(slug="st-anne")
    cat = CategoryFactory(community=community)
    # Left before #218: the membership was switched off and nothing else happened.
    gone = MemberFactory(community=community, display_name="Gwen", is_active=False)
    need = NeedFactory(community=community, requester=gone, category=cat, title="Ride to the clinic")
    offer = OfferFactory(community=community, offerer=gone, category=cat, title="Can mend fences")
    stayer = MemberFactory(community=community, display_name="Stan")
    kept = NeedFactory(community=community, requester=stayer, category=cat, title="Stan needs soup")
    return community, cat, gone, need, offer, stayer, kept


def test_the_dry_run_counts_and_changes_nothing(parish):
    _community, _cat, _gone, need, offer, _stayer, _kept = parish
    out = _run()

    assert "Dry run" in out
    assert "st-anne: 1 member who left, 1 open ask, 1 active offer" in out
    need.refresh_from_db()
    offer.refresh_from_db()
    assert need.moderation_hidden is False and need.hidden_on_leave_at is None
    assert offer.moderation_hidden is False and offer.hidden_on_leave_at is None
    assert not AuditLog.objects.filter(action="member.left_posts_hidden").exists()


def test_apply_hides_them_the_way_leaving_does(parish):
    community, _cat, gone, need, offer, _stayer, kept = parish
    before = Notification.objects.count()
    out = _run("--apply")

    assert "Hidden: 1 open ask, 1 active offer" in out
    need.refresh_from_db()
    offer.refresh_from_db()
    kept.refresh_from_db()
    assert need.moderation_hidden is True and need.hidden_on_leave_at is not None
    assert offer.moderation_hidden is True and offer.hidden_on_leave_at is not None
    assert kept.moderation_hidden is False  # a member who stayed keeps their post
    assert Need.objects.filter(pk=need.pk).exists() and Offer.objects.filter(pk=offer.pk).exists()
    row = AuditLog.objects.get(action="member.left_posts_hidden", resource_id=gone.pk)
    assert row.details == {"needs_hidden": 1, "offers_hidden": 1, "backfill": True}
    assert Notification.objects.count() == before  # nobody is told anything

    # Coming back, they choose what returns, exactly as for someone who leaves today.
    c = Client()
    c.force_login(gone.user)
    c.post(reverse("community-join"), {"join_code": community.join_code})
    page = c.get(reverse("left-posts", kwargs={"slug": community.slug})).content.decode()
    assert "Ride to the clinic" in page and "Can mend fences" in page
    need.refresh_from_db()
    assert need.moderation_hidden is True  # rejoining reposted nothing


def test_it_leaves_everything_else_alone(parish):
    community, cat, _gone, _need, _offer, _stayer, _kept = parish
    removed = MemberFactory(community=community, is_active=False, removed_at=timezone.now())
    removed_need = NeedFactory(community=community, requester=removed, category=cat)
    gone2 = MemberFactory(community=community, is_active=False)
    coordinator_hid = NeedFactory(community=community, requester=gone2, category=cat, moderation_hidden=True)
    closed = NeedFactory(community=community, requester=gone2, category=cat, status="closed")
    matched_offer = OfferFactory(community=community, offerer=gone2, category=cat, status="matched")

    _run("--apply")

    for post in (removed_need, coordinator_hid, closed):
        post.refresh_from_db()
        assert post.hidden_on_leave_at is None
    matched_offer.refresh_from_db()
    assert matched_offer.moderation_hidden is False and matched_offer.hidden_on_leave_at is None
    removed_need.refresh_from_db()
    assert removed_need.moderation_hidden is False  # the removal path owns these; not this command


def test_matches_in_progress_are_counted_not_touched(parish):
    community, _cat, gone, need, _offer, stayer, _kept = parish
    match = MatchFactory(need=need, offer=None, proposed_by=stayer)
    out = _run("--apply")

    assert "1 match is still in progress with members who left. This command leaves matches as they are." in out
    match.refresh_from_db()
    assert match.status == "proposed"


def test_a_second_run_finds_nothing(parish):
    _run("--apply")
    out = _run("--apply")
    assert "Nothing to hide" in out


def test_one_community_at_a_time(parish):
    _community, _cat, _gone, need, _offer, _stayer, _kept = parish
    other = CommunityFactory(slug="st-joseph")
    other_gone = MemberFactory(community=other, is_active=False)
    other_need = NeedFactory(community=other, requester=other_gone, category=CategoryFactory(community=other))

    out = _run("--apply", "--community", "st-joseph")

    assert "st-anne" not in out
    need.refresh_from_db()
    other_need.refresh_from_db()
    assert need.hidden_on_leave_at is None
    assert other_need.hidden_on_leave_at is not None


def test_an_unknown_community_is_refused(parish):
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        _run("--community", "no-such-place")
