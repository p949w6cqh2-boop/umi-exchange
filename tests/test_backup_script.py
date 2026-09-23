"""
The nightly backup must be loud about every way the off-site (B2) copy can
silently not happen. Found in production: cron runs `scripts/backup.sh` with a
bare environment, so the B2 credentials in `.env` never reached it — and the
empty-creds path printed *nothing*, so eleven days of "backups" were local-only
with no line of output saying so.

Same pattern as test_dr_rehearsal.py: invoke the real script with a real shell.
Every subprocess case here is expected to abort in the preflight section, before
any docker/pg_dump runs — no database, no /var/backups, no network.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKUP = REPO / "scripts" / "backup.sh"


def _run(env=None, timeout=20):
    return subprocess.run(  # noqa: S603
        ["bash", str(BACKUP)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO),
        # ENV_FILE points nowhere so a developer's real .env cannot leak in:
        # unset vars fall back to the (absent) file and stay empty.
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "ENV_FILE": "/nonexistent/.env",
            **(env or {}),
        },
    )


def test_partial_b2_creds_fail_loudly():
    """Bucket set, keys missing: a state that can never upload anywhere. It used
    to print a WARNING and still exit 0; it must now be a hard error."""
    result = _run({"BACKUP_BUCKET": "umi-backups"})

    assert result.returncode != 0
    assert "PARTIALLY" in result.stdout + result.stderr


def test_partial_via_empty_string_also_fails():
    """A credential set to the empty string is the same misconfiguration as a
    missing one (exactly how the droplet's .env looked)."""
    result = _run({"BACKUP_BUCKET": "umi-backups", "BACKUP_ACCESS_KEY": "k", "BACKUP_SECRET_KEY": ""})

    assert result.returncode != 0
    assert "PARTIALLY" in result.stdout + result.stderr


def test_require_remote_with_no_creds_fails():
    """BACKUP_REQUIRE_REMOTE=1 declares 'a backup that is not off-site is a
    failure' — with zero credentials configured that must fail, not quietly
    succeed local-only forever."""
    result = _run({"BACKUP_REQUIRE_REMOTE": "1"})

    assert result.returncode != 0
    assert "BACKUP_REQUIRE_REMOTE" in result.stdout + result.stderr


# ---------------------------------------------------------------- static guards
def test_the_stale_pip_install_hint_is_gone():
    """Ubuntu 24.04 has no awscli apt package and pip refuses system installs;
    the install that works on the droplet is the classic snap."""
    body = BACKUP.read_text()

    assert "pip install awscli" not in body
    assert "snap install aws-cli --classic" in body


def test_it_reads_env_file_without_sourcing_it():
    """.env holds non-shell lines (DEFAULT_FROM_EMAIL=UMI Exchange <…>), so the
    script must grep values out of it, never `source` it."""
    body = BACKUP.read_text()

    assert "env_file_val" in body, "the .env fallback is what makes cron uploads happen"
    assert not any(line.strip().startswith(("source ", ". ")) and ".env" in line for line in body.splitlines()), (
        "must never source .env"
    )


def test_the_empty_creds_case_says_so_out_loud():
    """The fresh-install state (no B2 at all) used to print nothing; the script
    must now carry a NOTICE that the backup is local-only."""
    body = BACKUP.read_text()

    assert "NOTICE" in body
    assert "this machine ONLY" in body


# ── Heartbeat ────────────────────────────────────────────────────────────────
# Exiting nonzero is not an alert. Cron mails root on a failing job and root mail
# on the droplet goes nowhere, so a failing nightly backup is still silent — the
# same shape that let the host sit destroyed for eight days. The signal is
# therefore inverted: ping only on full success, and let the monitor alert on the
# ping's ABSENCE, which also covers the backup that never ran at all.


def test_unset_heartbeat_says_nobody_is_watching():
    """While BACKUP_HEARTBEAT_URL is unset, a failed or skipped backup reaches
    nobody. That gap must be visible in the log on every run, not remembered."""
    result = _run()

    assert "BACKUP_HEARTBEAT_URL not set" in result.stdout + result.stderr
    assert "alert NOBODY" in result.stdout + result.stderr


def test_plaintext_heartbeat_url_is_refused():
    """The URL is a bearer token: anyone who observes it can forge 'all clear'
    forever. Over http it is observable, so it is a hard error, not a warning."""
    result = _run({"BACKUP_HEARTBEAT_URL": "http://example.invalid/ping/abc"})

    assert result.returncode != 0
    assert "must be https" in result.stdout + result.stderr


def test_non_url_heartbeat_is_refused():
    """A typo'd value must fail in preflight, not after the backup has run and
    can no longer report."""
    result = _run({"BACKUP_HEARTBEAT_URL": "uptimerobot-heartbeat"})

    assert result.returncode != 0
    assert "not a URL" in result.stdout + result.stderr


def test_heartbeat_url_is_never_echoed():
    """A log line carrying the URL hands over the ability to forge 'all clear'.
    The script must never print it — not in the preflight, not on success, not in
    the failure warning."""
    secret = "https://heartbeat.invalid/ping/SEKRIT-TOKEN-9x2"
    result = _run({"BACKUP_HEARTBEAT_URL": secret})

    assert secret not in result.stdout + result.stderr
    assert "SEKRIT-TOKEN-9x2" not in result.stdout + result.stderr


def test_heartbeat_is_the_last_statement():
    """Reaching the ping is the proof of success, because `set -e` has already
    exited on any earlier failure. If anything ran after it, a later failure
    could leave the monitor green on a broken night."""
    body = BACKUP.read_text()
    # rindex, not index: the var is also read in the preflight near the top, and
    # matching that one silently tests nothing (it "passed" against a tail
    # containing the whole backup).
    tail = body[body.rindex("BACKUP_HEARTBEAT_URL:-") :]

    assert "pg_dump" not in tail
    assert "aws s3" not in tail
    assert tail.rstrip().endswith("fi")


def test_a_failed_heartbeat_does_not_fail_a_good_backup():
    """The tail must not wag the dog: a monitor being down cannot turn a
    successful backup into a failed run. It must still be loud about it."""
    body = BACKUP.read_text()

    assert "backup SUCCEEDED but the heartbeat could not be delivered" in body
    assert "curl -fsS" in body
