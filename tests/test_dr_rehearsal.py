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


# ---------------------------------------------------------------- docker mode
# The droplet is dockerized and its db container publishes no ports, so the host-mode
# script could not run there at all — the 2026-07-29 rehearsal executed its documented
# steps through the containers by hand. Docker mode closes that. It also introduces a
# hazard host mode does not have: inside the db container `localhost` IS the production
# postgres server, so the database NAME is the entire separation between scratch and prod.


def test_docker_mode_needs_a_compose_file_it_can_find():
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@localhost:5432/umi_scratch",
            "DR_DOCKER": "1",
            "DR_COMPOSE_FILE": "docker/nope-does-not-exist.yml",
        }
    )

    assert result.returncode != 0
    assert "compose file not found" in result.stderr


def test_docker_mode_refuses_when_the_target_dbname_is_the_apps_own():
    """Host mode is saved by a wrong host failing to connect. Docker mode is not:
    localhost inside the db container resolves to prod, so the name is the guard."""
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@localhost:5432/umi_exchange",
            "DATABASE_URL": "postgres://umi:pw@db:5432/umi_exchange",
            "DR_DOCKER": "1",
        }
    )

    assert result.returncode != 0
    assert "is the app's own database" in result.stderr


def test_docker_mode_refuses_the_postgres_db_named_in_the_env_file(tmp_path):
    """The droplet's prod dbname lives in .env as POSTGRES_DB, and an operator copying
    the runbook command is far more likely to have that set than DATABASE_URL."""
    env_file = tmp_path / "dotenv"
    env_file.write_text("POSTGRES_DB=umi_exchange\nOTHER=x\n")
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@localhost:5432/umi_exchange",
            "DR_DOCKER": "1",
            "DR_ENV_FILE": str(env_file),
        }
    )

    assert result.returncode != 0
    assert "POSTGRES_DB" in result.stderr
    assert "that is prod, refusing" in result.stderr


def test_docker_mode_warns_when_the_target_does_not_look_like_scratch():
    """It does not refuse — DR_CONFIRM was given and the operator may have their own
    naming — but it must say out loud that it is about to DROP a schema."""
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@localhost:5432/rehearsal",
            "DR_DOCKER": "1",
            "DR_COMPOSE_FILE": "docker/nope-does-not-exist.yml",
        }
    )

    assert "does not look like a scratch database" in result.stdout


def test_host_mode_is_still_the_default_and_says_so():
    """Docker mode must be opt-in. A silent mode switch on a database-wiping script
    is its own hazard."""
    result = _run(
        {
            "DR_CONFIRM": "yes-restore-into-scratch",
            "DR_DATABASE_URL": "postgres://umi:pw@localhost:5433/umi_scratch_absent",
            "BACKUP_DIR": "/nonexistent-backup-dir",
        }
    )

    assert "mode: host" in result.stdout
    assert "mode: docker" not in result.stdout


def test_docker_mode_rewrites_the_db_host_for_the_app_container():
    """The bug the first real rehearsal found.

    psql runs inside the db container, where the server is `localhost`. manage.py runs inside the
    APP container, where `localhost` is the app itself. Sending the operator's URL unchanged to
    both made every docker-mode run fail its schema gate on "Connection refused"."""
    source = DR_SIM.read_text(encoding="utf-8")

    assert "APP_DB_URL=" in source, "docker mode must build a separate app-side URL"
    assert '-e DATABASE_URL="$APP_DB_URL"' in source, (
        "run_manage must send the rewritten app-side URL, not DR_DATABASE_URL"
    )
    assert "${DR_DATABASE_URL##*@}" in source, (
        "the host swap must split on the LAST '@' so a password containing '@' survives"
    )


def test_a_connection_failure_is_not_reported_as_pending_migrations():
    """Naming the failure correctly matters more than failing. Reporting 'pending migrations'
    when nothing could reach the database sends the operator to fix the wrong thing."""
    source = DR_SIM.read_text(encoding="utf-8")

    assert "could NOT CONNECT" in source
    assert "NOT a migration problem" in source
    for signature in ("connection refused", "authentication failed", "OperationalError"):
        assert signature in source, f"connection-failure detection must match {signature!r}"
