"""
Match propose/accept must honor moderation-hide and blocks (bug-hunt batch 2, #2 + #3).

#2 MatchProposeView/MatchUpdateView gated on need/offer *status* but never on
   moderation_hidden, so a coordinator-hidden (or removed-member's) need stayed
   matchable and its owner's email+phone got disclosed on accept. Mirrors the
   read gate at needs/views.py (hidden ⇒ 404 for non-coordinators).
#3 A block was checked at propose time but NOT re-checked on accept, so a match
   already sitting in 'proposed' when a block was created could still be flipped
   to 'accepted' — unlocking the blocker's contact, the exact recall the block
   promised. The check is party-based (requester ↔ offering member), no actor
   exemption, mirroring the propose-time block guard.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.matches.models import Match
from apps.moderation.models import Block

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)


def _client_for(member):
    client = Client()
    client.force_login(member.user)
    return client


def _propose_url(community):
    return reverse("match-propose", kwargs={"slug": community.slug})


def _update_url(community, match):
    return reverse("match-update", kwargs={"slug": community.slug, "pk": match.id})


def _proposed_scenario(need_status="open"):
    """A community with an open need, an offer, and a proposed match (requester
    is the need owner; offerer owns the offer and proposed it)."""
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=category, status=need_status)
    offer = OfferFactory(community=community, offerer=offerer, category=category)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")
    return community, category, need, offer, match, requester, offerer


# --------------------------------------------------------------- #2 propose
@pytest.mark.django_db
def test_cannot_propose_on_moderation_hidden_need():
    """An ordinary member may not propose a match against a hidden need (#2)."""
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    proposer = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=requester, category=category, status="open")
    need.moderation_hidden = True
    need.save(update_fields=["moderation_hidden"])
    offer = OfferFactory(community=community, offerer=proposer, category=category)

    resp = _client_for(proposer).post(_propose_url(community), {"need_id": str(need.id), "offer_id": str(offer.id)})

    assert resp.status_code == 404
    assert not Match.objects.filter(need=need).exists()  # no match created against a hidden need


# ---------------------------------------------------------------- #2 accept
@pytest.mark.django_db
def test_cannot_accept_match_on_since_hidden_need():
    """A match on a need hidden AFTER proposal must not be acceptable (#2)."""
    community, category, need, offer, match, requester, offerer = _proposed_scenario()
    need.moderation_hidden = True
    need.save(update_fields=["moderation_hidden"])

    resp = _client_for(requester).post(_update_url(community, match), {"status": "accepted"})

    assert resp.status_code == 409
    match.refresh_from_db()
    need.refresh_from_db()
    assert match.status == "proposed"  # unchanged
    assert need.status == "open"  # not matched
    assert match.get_contact_info_for(requester) is None  # no contact disclosed


# ------------------------------------------------------------------ #3 block
@pytest.mark.django_db
def test_blocked_pair_cannot_accept_pending_match():
    """A block created after proposal must stop the accept that would disclose
    the blocker's contact (#3)."""
    community, category, need, offer, match, requester, offerer = _proposed_scenario()
    Block.objects.create(community=community, blocker=requester, blocked=offerer)

    resp = _client_for(requester).post(_update_url(community, match), {"status": "accepted"})

    assert resp.status_code == 409
    match.refresh_from_db()
    assert match.status == "proposed"  # unchanged
    assert match.get_contact_info_for(requester) is None  # blocker's contact stays sealed


# --------------------------------------------- coordinator exemption (design pin)
@pytest.mark.django_db
def test_coordinator_may_still_accept_hidden_need():
    """The hide guard mirrors the read gate: a coordinator keeps oversight and
    may still act on a hidden need (pins the exemption against an over-fix)."""
    community, category, need, offer, match, requester, offerer = _proposed_scenario()
    coordinator = MemberFactory(community=community, role="coordinator")
    need.moderation_hidden = True
    need.save(update_fields=["moderation_hidden"])

    resp = _client_for(coordinator).post(_update_url(community, match), {"status": "accepted"})

    assert resp.status_code in (200, 302)
    match.refresh_from_db()
    assert match.status == "accepted"
