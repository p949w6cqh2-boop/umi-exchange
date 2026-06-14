import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.casework.models import CaseFile, CaseNote, FollowUp, WarmHandoff
from apps.casework.state import TransitionConflict

pytestmark = pytest.mark.django_db


def _fu(world, status="open"):
    return FollowUp.objects.create(
        case=world.case, created_by=world.coordinator,
        assigned_to=world.coordinator, title="Check in re: utility bill",
        due_date=timezone.localdate(), status=status)


def _ho(world, status="pending"):
    ho = WarmHandoff(case=world.case, from_member=world.coordinator,
                     to_member=world.coordinator2, status=status)
    ho.summary = "Context for the next visitor."
    ho.save()
    return ho


# ---- illegal transitions: the full 409 matrix --------------------------
@pytest.mark.parametrize("start,target", [
    ("open", "open"), ("monitoring", "monitoring"),
    ("closed", "closed"), ("closed", "monitoring"),
])
def test_casefile_illegal_transitions(world, start, target):
    world.case.status = start
    world.case.save(update_fields=["status"])
    case = CaseFile.objects.get(pk=world.case.pk)
    with pytest.raises(TransitionConflict):
        case.transition_to(target)


@pytest.mark.parametrize("start,target", [
    ("final", "draft"), ("final", "discarded"),
    ("discarded", "draft"), ("discarded", "final"), ("draft", "draft"),
])
def test_casenote_illegal_transitions(world, make_note, start, target):
    note = make_note(status=start)
    with pytest.raises(TransitionConflict):
        note.transition_to(target)


@pytest.mark.parametrize("start,target", [
    ("done", "open"), ("cancelled", "open"),
    ("done", "cancelled"), ("open", "open"),
])
def test_followup_illegal_transitions(world, start, target):
    fu = _fu(world, status=start)
    with pytest.raises(TransitionConflict):
        fu.transition_to(target)


@pytest.mark.parametrize("start,target", [
    ("acknowledged", "pending"), ("pending", "pending"),
])
def test_handoff_illegal_transitions(world, start, target):
    ho = _ho(world, status=start)
    with pytest.raises(TransitionConflict):
        ho.transition_to(target)


def test_transition_conflict_is_validation_error(world):
    case = CaseFile.objects.get(pk=world.case.pk)
    case.status = "closed"
    case.save(update_fields=["status"])
    with pytest.raises(ValidationError):
        case.transition_to("monitoring")


# ---- race: the stale snapshot loses with 409 ----------------------------
def test_status_race_stale_snapshot_conflicts(world):
    first = CaseFile.objects.get(pk=world.case.pk)
    second = CaseFile.objects.get(pk=world.case.pk)
    first.transition_to("monitoring")
    with pytest.raises(TransitionConflict):
        second.transition_to("closed")  # snapshot says "open" — stale


# ---- timestamp side-effects ---------------------------------------------
def test_transition_timestamps(world, make_note):
    case = CaseFile.objects.get(pk=world.case.pk)
    case.transition_to("closed")
    assert case.closed_at is not None

    note = make_note(status="draft")
    note.transition_to("final")
    assert note.finalized_at is not None

    fu = _fu(world)
    fu.transition_to("done")
    assert fu.done_at is not None

    ho = _ho(world)
    ho.transition_to("acknowledged")
    assert ho.acknowledged_at is not None


# ---- finalized-note immutability (A7) ------------------------------------
def test_final_note_is_immutable(world, make_note):
    note = make_note(status="draft")
    note.transition_to("final")

    note.body = "Tampered"
    with pytest.raises(ValidationError):
        note.save()

    with pytest.raises(ValidationError):
        note.delete()


def test_draft_note_is_deletable(world, make_note):
    note = make_note(status="draft")
    note.delete()
    assert not CaseNote.objects.filter(pk=note.pk).exists()
