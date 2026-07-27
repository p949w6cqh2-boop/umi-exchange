"""
The incident/breach/legal-demand plan says the things it has to say
(ethics gate box 4 — docs/ethics-and-safety.md).

The box is specific about what the document must name:

  "who is notified and within what timebox when data is exposed, who decides to
   refuse an overbroad or unlawful demand for data (including a subpoena or an ICE
   request) and by what path that refusal is made, and how affected neighbours are
   told. It also has to cover a meeting that goes wrong in person and a report of a
   scammer or an abuser on the board: who a neighbour tells, who can freeze or
   remove that account, and what the coordinator does next."

A plan is not a document you write once and let quietly rot. These are cheap guards
against the load-bearing parts being trimmed later by someone tidying prose — most
of all the judicial-versus-administrative warrant distinction, which is the single
most actionable paragraph in it for a volunteer standing at a door.
"""

from pathlib import Path

import pytest

PLAN = Path(__file__).resolve().parent.parent / "docs" / "incident-response.md"


@pytest.fixture(scope="module")
def plan_text():
    assert PLAN.exists(), "gate item 4 requires this document to exist"
    return PLAN.read_text()


def test_it_says_it_is_not_legal_advice(plan_text):
    """Written by the people who run the board, not by counsel. Say so."""
    assert "not legal advice" in plan_text.lower()


def test_it_names_who_decides_to_refuse(plan_text):
    assert "Who decides to refuse" in plan_text
    assert "steward decides" in plan_text.lower()


def test_it_distinguishes_a_judicial_warrant_from_an_administrative_one(plan_text):
    """An ICE Form I-200 is signed by an immigration officer, not a judge, and does
    not authorise entry to a private space. Getting this wrong at a door is the
    difference between a lawful refusal and handing over a neighbour."""
    for anchor in ["I-200", "judge", "magistrate", "administrative warrant", "judicial warrant"]:
        assert anchor in plan_text, f"the warrant section must still mention {anchor}"


def test_it_gives_a_script_for_whoever_is_standing_there(plan_text):
    """A frightened volunteer needs words, not principles."""
    assert "holding sentence" in plan_text
    assert "not consenting to anything" in plan_text


def test_it_tells_people_to_stop_the_deletion_sweeps(plan_text):
    """Automatic deletion running over evidence is sanctionable even when nobody
    intended it. Our privacy feature is the hazard here."""
    assert "legal hold" in plan_text.lower() or "Stop the deletion sweeps" in plan_text
    for job in ["needs-shred-aged-pii", "casework-shred-aged-cases"]:
        assert job in plan_text, f"the hold section must name the actual job: {job}"


def test_it_names_a_notification_timebox(plan_text):
    assert "72 hours" in plan_text
    assert "24 hours" in plan_text


def test_it_covers_a_meeting_that_went_wrong(plan_text):
    assert "A meeting went wrong" in plan_text


def test_it_covers_an_abuser_on_the_board_including_a_coordinator(plan_text):
    assert "scammer or an abuser" in plan_text.lower()
    assert "coordinator" in plan_text.lower()


def test_it_admits_the_steward_is_the_single_point_of_failure(plan_text):
    """The plan must not read as though governance were solved. If the steward is
    the problem, there is no path today, and that stays visible until box 6."""
    assert "If the steward is the problem" in plan_text


def test_the_ethics_gate_points_at_it(plan_text):
    gate = (PLAN.parent / "ethics-and-safety.md").read_text()
    assert "incident-response.md" in gate, "the gate must link the plan it asked for"
