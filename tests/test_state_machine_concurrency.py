"""
State-machine and sweep concurrency (bug-hunt batch 5, #8 #24).

#8  Match.transition_to() validated against the in-memory self.status, cascaded
    onto in-memory need/offer, and ended in a bare full-row save() — no lock, no
    atomic block, no snapshot re-check (unlike apps/common/state.py). MatchUpdateView
    locks first, but moderation/services.py remove_member and the federation revoke
    loop iterate unlocked snapshots. A coordinator removing a member concurrent with
    the requester fulfilling that member's match silently rewrote the committed
    'fulfilled' Match to 'cancelled' — erasing fulfilled_at and republishing the need.

#24 expire_stale_needs materialised the candidate set once, then blind-wrote
    status='expired' minutes later — no lock, no re-check — while each iteration did
    a synchronous notification send. A need accepted in the web UI while the sweep
    was still working through earlier rows got overwritten to 'expired': its accepted
    match orphaned, the requester told their need expired while a neighbour was on
    the way, and a false open->expired in the audit log.

Both races are simulated deterministically (direct DB writes behind a held instance;
a post_save/notification hook that mutates the next row mid-loop) rather than with
threads — the defect is a stale snapshot, and a stale snapshot needs no concurrency
to reproduce.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.db.models.signals import post_save
from django.utils import timezone

from apps.common.state import TransitionConflict
from apps.matches.models import Match
from apps.moderation.services import remove_member
from apps.needs.models import Need
from apps.needs.tasks import expire_stale_needs
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db


# -------------------------------------------------------------------------- #8
def test_transition_to_refuses_a_stale_snapshot():
    """The row moved under us — refuse, don't overwrite."""
    match = MatchFactory()
    stale = Match.objects.get(pk=match.pk)  # snapshot says 'proposed'
    Match.objects.filter(pk=match.pk).update(status="cancelled")

    with pytest.raises(TransitionConflict):
        stale.transition_to("accepted")

    match.refresh_from_db()
    assert match.status == "cancelled"


def test_transition_to_does_not_erase_a_committed_fulfilment():
    """The finding's concrete harm: a cancel off a stale 'accepted' snapshot
    rewriting a match somebody already fulfilled."""
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, category=category, requester=requester, status="matched")
    offer = OfferFactory(community=community, category=category, offerer=offerer, status="matched")
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="accepted")

    stale = Match.objects.get(pk=match.pk)  # snapshot says 'accepted'
    fulfilled_at = timezone.now()
    Match.objects.filter(pk=match.pk).update(status="fulfilled", fulfilled_at=fulfilled_at)
    Need.objects.filter(pk=need.pk).update(status="fulfilled")

    with pytest.raises(TransitionConflict):
        stale.transition_to("cancelled")

    match.refresh_from_db()
    need.refresh_from_db()
    assert match.status == "fulfilled"
    assert match.fulfilled_at is not None
    assert need.status == "fulfilled", "a lost race must not republish a fulfilled need"


def test_transition_to_still_moves_a_fresh_match():
    """The guard must not break the ordinary path."""
    match = MatchFactory()
    match.transition_to("accepted")

    match.refresh_from_db()
    match.need.refresh_from_db()
    match.offer.refresh_from_db()
    assert match.status == "accepted"
    assert match.accepted_at is not None
    assert match.need.status == "matched"
    assert match.offer.status == "matched"


def test_remove_member_leaves_a_match_fulfilled_mid_loop():
    """remove_member cancels every in-flight match of the removed member. If one
    of them is fulfilled after the queryset is built, the loop must re-read and
    leave it alone rather than cancel a committed fulfilment."""
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    coordinator = MemberFactory(community=community, role="coordinator")
    leaving = MemberFactory(community=community)
    other = MemberFactory(community=community)

    def _in_flight_match(status):
        need = NeedFactory(community=community, category=category, requester=leaving, status="matched")
        offer = OfferFactory(community=community, category=category, offerer=other, status="matched")
        return MatchFactory(need=need, offer=offer, proposed_by=other, status=status)

    first = _in_flight_match("accepted")
    second = _in_flight_match("accepted")
    both = {first.pk, second.pk}

    fulfilled_at = timezone.now()
    fulfilled = []

    def fulfil_the_other(sender, instance, **kwargs):
        """Stand-in for the requester pressing 'fulfilled' in the web UI while
        the removal is still working through the earlier match. Fires on the
        first cancellation, whichever row the loop reached first."""
        if instance.status != "cancelled" or fulfilled:
            return
        other = both - {instance.pk}
        Match.objects.filter(pk__in=other, status="accepted").update(status="fulfilled", fulfilled_at=fulfilled_at)
        fulfilled.extend(other)

    post_save.connect(fulfil_the_other, sender=Match)
    try:
        remove_member(leaving, by=coordinator)
    finally:
        post_save.disconnect(fulfil_the_other, sender=Match)

    assert fulfilled, "the hook must have fired on the first cancellation"
    survivor = Match.objects.get(pk=fulfilled[0])
    cancelled = Match.objects.get(pk=next(iter(both - set(fulfilled))))
    assert cancelled.status == "cancelled", "the untouched in-flight match is still cancelled"
    assert survivor.status == "fulfilled", "a fulfilment committed mid-loop must survive the removal"
    assert survivor.fulfilled_at is not None


# ------------------------------------------------------------------------- #24
def _stale_need(community, category, requester):
    need = NeedFactory(community=community, category=category, requester=requester, status="open")
    Need.objects.filter(pk=need.pk).update(expires_at=timezone.now() - timedelta(days=1))
    need.refresh_from_db()
    return need


@pytest.fixture
def sweep_world():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    first = _stale_need(community, category, requester)
    second = _stale_need(community, category, requester)
    return community, category, offerer, first, second


def test_expire_skips_a_need_accepted_after_the_candidate_query(sweep_world):
    """The sweep is mid-send on the first need when a neighbour's match on the
    other one is accepted. That need must not be expired out from under them."""
    community, category, offerer, first, second = sweep_world
    accepted = []

    def accept_the_pending_need(user, kind, *args, **kwargs):
        """Whichever candidate the sweep hasn't reached yet gets accepted."""
        if kind != "need_expired" or accepted:
            return
        pending = Need.objects.filter(pk__in=(first.pk, second.pk), status="open").first()
        if pending is None:
            return
        offer = OfferFactory(community=community, category=category, offerer=offerer, status="matched")
        MatchFactory(need=pending, offer=offer, proposed_by=offerer, status="accepted")
        Need.objects.filter(pk=pending.pk).update(status="matched")
        accepted.append(pending.pk)

    with mock.patch("apps.needs.tasks.NotificationAdapter.send", side_effect=accept_the_pending_need):
        expire_stale_needs()

    assert accepted, "the hook must have fired while a candidate was still pending"
    rescued = Need.objects.get(pk=accepted[0])
    swept = Need.objects.get(pk=next(p for p in (first.pk, second.pk) if p != accepted[0]))
    assert swept.status == "expired"
    assert rescued.status == "matched", "a need accepted mid-sweep must not be expired"
    assert rescued.matches.filter(status="accepted").exists(), "its accepted match must not be orphaned"


def test_expire_skips_a_need_reposted_mid_sweep(sweep_world):
    """Same shape, non-match edit: the requester pushes the expiry date out
    while the sweep is running. The stale candidate must be re-checked."""
    community, category, offerer, first, second = sweep_world
    extended = timezone.now() + timedelta(days=7)
    reposted = []

    def extend_the_pending_need(user, kind, *args, **kwargs):
        if kind != "need_expired" or reposted:
            return
        pending = Need.objects.filter(pk__in=(first.pk, second.pk), status="open").first()
        if pending is None:
            return
        Need.objects.filter(pk=pending.pk).update(expires_at=extended)
        reposted.append(pending.pk)

    with mock.patch("apps.needs.tasks.NotificationAdapter.send", side_effect=extend_the_pending_need):
        expire_stale_needs()

    assert reposted, "the hook must have fired while a candidate was still pending"
    rescued = Need.objects.get(pk=reposted[0])
    swept = Need.objects.get(pk=next(p for p in (first.pk, second.pk) if p != reposted[0]))
    assert swept.status == "expired"
    assert rescued.status == "open", "a need whose expiry moved mid-sweep must stay open"


def test_expire_still_expires_a_plainly_stale_need(sweep_world):
    """The guard must not stop the sweep doing its job."""
    community, category, offerer, first, second = sweep_world

    result = expire_stale_needs()

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == "expired"
    assert second.status == "expired"
    assert "2" in result
