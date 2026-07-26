"""
Audit-log PII hygiene (bug-hunt batch 10, #21).

AuditLog is append-only by design: the model refuses UPDATE/DELETE and Postgres
REVOKEs them on the table. Three sites copied unbounded member/coordinator free
text into it verbatim — a match note (matches/views.py) and a tag reject/revoke
reason (tags/models.py). Any PII typed there — an address, a name, DV detail —
landed permanently in the one table that can never be corrected, redacted, or
crypto-shredded, silently defeating the right-to-erasure guarantee.

The codebase's own discipline is casework/views.py's emergency-open audit:
record THAT text was provided, never the text — {"justification_provided": True}.
The free text stays on the redactable model field (Match.notes,
MemberTag.rejection_reason), where a shred can still reach it.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.matches.models import Match
from apps.tags.models import MemberTag, Tag
from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db

PII_NOTE = "Marta is at 14 Rowan Close this week, side door."


@pytest.fixture
def match_world():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community)
    need = NeedFactory(community=community, category=category, requester=requester, status="open")
    offer = OfferFactory(community=community, category=category, offerer=offerer)
    match = MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")
    return community, match, requester


def _accept_with_note(community, match, requester, note):
    client = Client()
    client.force_login(requester.user)
    resp = client.post(
        reverse("match-update", kwargs={"slug": community.slug, "pk": match.id}),
        {"status": "accepted", "notes": note},
    )
    assert resp.status_code in (200, 302)
    return AuditLog.objects.filter(action="update", resource_type="match", resource_id=match.id).latest("timestamp")


# ------------------------------------------------------------ match notes
def test_match_update_audit_carries_no_free_text(match_world):
    community, match, requester = match_world

    log = _accept_with_note(community, match, requester, PII_NOTE)

    assert PII_NOTE not in str(log.details), "free text must never reach the unshreddable log"
    assert "notes" not in log.details
    assert log.details["notes_provided"] is True
    assert log.details["status"] == "accepted"


def test_match_note_still_lands_on_the_redactable_model_field(match_world):
    """The note itself is wanted — on Match.notes, where a shred can reach it."""
    community, match, requester = match_world

    _accept_with_note(community, match, requester, PII_NOTE)

    assert Match.objects.get(pk=match.pk).notes == PII_NOTE


def test_match_update_without_a_note_says_so(match_world):
    community, match, requester = match_world

    log = _accept_with_note(community, match, requester, "")

    assert "notes" not in log.details
    assert "notes_provided" not in log.details, "blank input leaves notes untouched — nothing to record"


# ------------------------------------------------------------ tag reasons
@pytest.fixture
def tag_world():
    community = CommunityFactory()
    member = MemberFactory(community=community)
    coordinator = MemberFactory(community=community, role="coordinator")
    tag = Tag.objects.create(community=community, slug="visit-team", label="Visit team", tier="coordinator_verified")
    return member, coordinator, tag


def test_tag_reject_audit_carries_no_free_text(tag_world):
    member, coordinator, tag = tag_world
    mt = MemberTag.objects.create(member=member, tag=tag, status="pending")

    mt.reject(coordinator, reason=PII_NOTE)

    log = AuditLog.objects.filter(action="tag.rejected", resource_id=mt.id).latest("timestamp")
    assert PII_NOTE not in str(log.details)
    assert "reason" not in log.details
    assert log.details["reason_provided"] is True
    assert log.details["tag_slug"] == "visit-team"
    mt.refresh_from_db()
    assert mt.rejection_reason == PII_NOTE, "the reason itself stays on the redactable model field"


def test_tag_revoke_audit_carries_no_free_text(tag_world):
    member, coordinator, tag = tag_world
    mt = MemberTag.objects.create(member=member, tag=tag, status="verified", verified_by=coordinator)

    mt.revoke(coordinator, reason=PII_NOTE)

    log = AuditLog.objects.filter(action="tag.revoked", resource_id=mt.id).latest("timestamp")
    assert PII_NOTE not in str(log.details)
    assert "reason" not in log.details
    assert log.details["reason_provided"] is True
    assert log.details["revoked_by"] == str(coordinator.id)
    mt.refresh_from_db()
    assert mt.rejection_reason == PII_NOTE


def test_tag_reject_without_a_reason_says_so(tag_world):
    member, coordinator, tag = tag_world
    mt = MemberTag.objects.create(member=member, tag=tag, status="pending")

    mt.reject(coordinator, reason="")

    log = AuditLog.objects.filter(action="tag.rejected", resource_id=mt.id).latest("timestamp")
    assert log.details["reason_provided"] is False
