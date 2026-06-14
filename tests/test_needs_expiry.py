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
        community=community, requester=requester, category=cat, status="open",
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
