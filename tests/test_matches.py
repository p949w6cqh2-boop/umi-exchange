"""Tests for the Match state machine — the most critical protocol enforcement."""
import pytest
from django.core.exceptions import ValidationError
from .conftest import *


@pytest.mark.django_db
class TestMatchStateMachine:
    def test_propose_to_accept(self):
        match = MatchFactory()
        assert match.status == "proposed"
        match.transition_to("accepted")
        assert match.status == "accepted"
        assert match.accepted_at is not None
        assert match.need.status == "matched"

    def test_accept_to_fulfill(self):
        match = MatchFactory()
        match.transition_to("accepted")
        match.transition_to("fulfilled")
        assert match.status == "fulfilled"
        assert match.fulfilled_at is not None
        assert match.need.status == "fulfilled"

    def test_invalid_transition_raises(self):
        match = MatchFactory()
        with pytest.raises(ValidationError):
            match.transition_to("fulfilled")  # Can't go from proposed to fulfilled

    def test_cancel_from_accepted_reopens_need(self):
        match = MatchFactory()
        match.transition_to("accepted")
        assert match.need.status == "matched"
        match.transition_to("cancelled")
        assert match.status == "cancelled"
        assert match.need.status == "open"  # Re-opened

    def test_terminal_states_reject_transitions(self):
        match = MatchFactory()
        match.transition_to("accepted")
        match.transition_to("fulfilled")
        with pytest.raises(ValidationError):
            match.transition_to("cancelled")  # Fulfilled is terminal


@pytest.mark.django_db
class TestContactRevelation:
    def test_no_contact_before_acceptance(self):
        match = MatchFactory()
        member = match.need.requester
        info = match.get_contact_info_for(member)
        assert info is None  # Contact hidden before acceptance

    def test_contact_after_acceptance(self):
        match = MatchFactory()
        match.need.requester.user.email = "test@example.com"
        match.need.requester.user.save()
        match.need.contact_pref = "email"
        match.need.save()
        match.transition_to("accepted")
        offerer = match.offer.offerer
        info = match.get_contact_info_for(offerer)
        assert info is not None
        assert info["email"] == "test@example.com"

    def test_non_participant_gets_no_contact(self):
        match = MatchFactory()
        match.transition_to("accepted")
        outsider = MemberFactory(community=match.need.community)
        info = match.get_contact_info_for(outsider)
        assert info is None  # Non-participant, non-coordinator
