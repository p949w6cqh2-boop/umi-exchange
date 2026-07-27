"""
The disaster-recovery rehearsal refuses the dangerous things and fails the empty ones
(ethics gate box 2 — docs/ethics-and-safety.md).

`scripts/dr_sim.sh` restores a backup into a SCRATCH database and checks it. Two
classes of bug matter here and neither shows up in ordinary use:

1. **It must never touch production.** A DR script that restores over the live
   database on a mistyped variable is worse than no DR script. The guards are the
   feature; these tests run them.
2. **It must not call an empty restore a success.** It used to count only query
   *errors*, so a database that restored zero rows answered every count with 0 and
   reported PASS. That is precisely the failure you discover on the day you need
   the backup.

These invoke the real script with a real shell. They never reach a database — every
case here is expected to abort in the guard section, before any psql runs.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DR_SIM = REPO / "scripts" / "dr_sim.sh"


def _run(env=None, timeout=20):
    return subprocess.run(  # noqa: S603
        ["bash", str(DR_SIM)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", **(env or {})},
    )


def test_it_refuses_to_run_by_default():
    """No flags, no restore. The default answer to 'shall I wipe a database' is no."""
    result = _run()

    assert result.returncode != 0
    assert "refusing by default" in result.stderr


def test_it_refuses_without_an_explicit_scratch_target():
    """There is deliberately no fallback to the app's own DATABASE_URL."""
    result = _run({"DR_CONFIRM": "yes-restore-into-scratch"})

    assert result.returncode != 0
    assert "DR_DATABASE_URL" in result.stderr
    assert "no fallback to prod" in result.stderr


def test_it_refuses_when_the_scratch_target_is_the_live_database():
    """The single most likely fatal typo."""
    live = "postgres://umi:pw@db:5432/umi_exchange"
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": live,
            "DATABASE_URL": live,
        }
    )

    assert result.returncode != 0
    assert "that is prod, refusing" in result.stderr


def test_it_refuses_a_target_matching_the_prod_host_blocklist():
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@prod-db.internal:5432/scratch",
            "PROD_DB_HOST": "prod-db.internal",
        }
    )

    assert result.returncode != 0
    assert "PROD_DB_HOST" in result.stderr


def test_it_can_rehearse_without_b2_configured():
    """It used to hard-require B2 credentials, so an instance without a bucket could
    not rehearse at all — the backup stayed untested for want of a bucket. It should
    now reach the local-backup path and complain about missing BACKUPS, not creds."""
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@localhost:5433/umi_scratch_absent",
            "BACKUP_DIR": "/nonexistent-backup-dir",
        }
    )

    assert result.returncode != 0
    assert "DR_BUCKET" not in result.stderr, "must not demand B2 creds as the only path"
    assert "nothing to rehearse" in result.stderr


# ---------------------------------------------------------------- static guards
def test_an_empty_restore_is_a_failed_restore():
    """Pins the fix: zero communities or zero members must fail, not pass."""
    body = DR_SIM.read_text()

    assert "an empty restore is a failed restore" in body
    assert "-lt 1" in body, "the count check must be a threshold, not just an error check"


def test_it_can_assert_a_known_record_survived():
    """Counts prove the tables are not empty; a known slug proves the specific thing
    you expected to survive actually did."""
    body = DR_SIM.read_text()

    assert "DR_EXPECT_SLUG" in body
    assert "MISSING from the restore" in body


def test_it_still_runs_the_schema_health_gate():
    """migrate --check must stay, and must never report PASS when manage.py is absent."""
    body = DR_SIM.read_text()

    assert "migrate --check" in body
    assert "cannot verify schema health" in body


def test_the_rehearsal_is_documented_where_an_operator_would_look():
    """A DR script nobody knows about is not a DR capability. It was referenced in
    zero documents when the gate item was written."""
    runbook = (REPO / "docs" / "deploy" / "vps-runbook.md").read_text()
    checklist = (REPO / "docs" / "deployment-checklist.md").read_text()

    assert "dr_sim.sh" in runbook, "the VPS runbook must tell the operator how to rehearse"
    assert "dr_sim.sh" in checklist
