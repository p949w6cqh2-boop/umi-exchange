"""Need-expiry task: expiring a need must audit each expired match (§8.3).

Regression test for the previously-silent bulk .update() that flipped proposed
matches to 'expired' with no audit entry.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.needs.tasks import expire_stale_needs

from .conftest import CategoryFactory, CommunityFactory, MatchFactory, MemberFactory, NeedFactory, OfferFactory


@pytest.mark.django_db
def test_expiry_audits_each_expired_match():
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(
        community=community,
        requester=requester,
        category=cat,
        status="open",
        expires_at=timezone.now() - timedelta(days=1),
    )
    offer = OfferFactory(community=community, offerer=offerer, category=cat)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")

    expire_stale_needs()

    need.refresh_from_db()
    match.refresh_from_db()
    assert need.status == "expired"
    assert match.status == "expired"
    # The fix: each expired match leaves an audit entry (was silently bulk-updated).
    assert AuditLog.objects.filter(action="match.expired", resource_id=match.id).exists()


@pytest.mark.django_db
def test_register_schedule_creates_hourly_sweep():
    """H-3: expire_stale_needs exists but was never scheduled — no deployment
    actually ran it. register_schedule must create the hourly Schedule row,
    mirroring the sibling task modules."""
    from django_q.models import Schedule

    from apps.needs.tasks import register_schedule

    register_schedule()

    sched = Schedule.objects.get(name="needs-expire-stale")
    assert sched.func == "apps.needs.tasks.expire_stale_needs"
    assert sched.schedule_type == Schedule.HOURLY
    assert sched.repeats == -1


@pytest.mark.django_db
def test_register_schedule_is_idempotent():
    from django_q.models import Schedule

    from apps.needs.tasks import register_schedule

    register_schedule()
    register_schedule()
    assert Schedule.objects.filter(name="needs-expire-stale").count() == 1


@pytest.mark.django_db
def test_need_with_accepted_match_is_never_expired():
    """§4.1 invariant, now that the sweep is scheduled: a past-due need with an
    accepted match must NOT be expired. Locks the existing guard against
    regression now that the task actually runs."""
    community = CommunityFactory()
    cat = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(
        community=community,
        requester=requester,
        category=cat,
        status="open",
        expires_at=timezone.now() - timedelta(days=1),
    )
    offer = OfferFactory(community=community, offerer=offerer, category=cat)
    MatchFactory(need=need, offer=offer, proposed_by=offerer, status="accepted")

    expire_stale_needs()

    need.refresh_from_db()
    assert need.status == "open"  # protected by the accepted match
