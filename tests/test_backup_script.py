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
