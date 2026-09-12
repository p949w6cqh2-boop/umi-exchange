"""Key custody rig — scripts/deploy-with-keys.sh (docs/key-custody-design.md, keyed build).

The design's contract, pinned here:
  - the droplet at rest holds only ciphertext (secrets/keys.env.age);
  - decryption happens from the steward's laptop, plaintext travels only over ssh
    into tmpfs (/dev/shm) and is shredded after `up`;
  - the repository never holds key material in any form;
  - the script refuses to run half-armed (no identity, no recipients, no age binary).

Tests run the script in DRY_RUN mode (prints its command plan, touches nothing remote)
and against throwaway age keypairs in tmp. Skipped wholesale when `age` is absent
(CI runners don't carry it; the rig is laptop-side tooling, not app code).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("age") is None, reason="age binary not installed")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "deploy-with-keys.sh"

KEYS_SAMPLE = 'ENCRYPTION_KEYS="k1-abc,k2-def"\nBLIND_INDEX_KEY="bidx-xyz"\nSECRET_KEY="django-secret"\n'


def run(args, env=None, cwd=None):
    base = {"PATH": "/usr/bin:/bin:/usr/local/bin:" + str(Path.home() / ".local/bin")}
    if env:
        base.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=base,
        cwd=cwd,
        timeout=30,
    )


@pytest.fixture()
def age_home(tmp_path):
    """Throwaway age identity + recipients + plaintext keys file."""
    identity = tmp_path / "identity.txt"
    keygen = subprocess.run(["age-keygen", "-o", str(identity)], capture_output=True, text=True)
    recipient = keygen.stderr.strip().split()[-1]  # "Public key: age1..."
    recipients = tmp_path / "recipients.txt"
    recipients.write_text(recipient + "\n")
    plain = tmp_path / "keys.env"
    plain.write_text(KEYS_SAMPLE)
    return {"identity": identity, "recipients": recipients, "plain": plain, "dir": tmp_path}


def test_script_exists_and_is_executable():
    assert SCRIPT.exists(), "scripts/deploy-with-keys.sh missing"
    assert SCRIPT.stat().st_mode & 0o111, "script not executable"


def test_encrypt_roundtrip(age_home):
    out = age_home["dir"] / "keys.env.age"
    r = run(
        ["encrypt", str(age_home["plain"])],
        env={
            "UMI_AGE_RECIPIENTS": str(age_home["recipients"]),
            "UMI_KEYS_AGE": str(out),
        },
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    # ciphertext, not a copy
    assert b"ENCRYPTION_KEYS" not in out.read_bytes()
    dec = subprocess.run(
        ["age", "-d", "-i", str(age_home["identity"]), str(out)],
        capture_output=True,
        text=True,
    )
    assert dec.stdout == KEYS_SAMPLE


def test_encrypt_refuses_without_recipients(age_home):
    r = run(
        ["encrypt", str(age_home["plain"])],
        env={
            "UMI_AGE_RECIPIENTS": str(age_home["dir"] / "nope.txt"),
            "UMI_KEYS_AGE": str(age_home["dir"] / "keys.env.age"),
        },
    )
    assert r.returncode != 0
    assert "recipients" in (r.stderr + r.stdout).lower()


def test_deploy_dry_run_plan_keeps_plaintext_in_tmpfs_and_shreds(age_home):
    out = age_home["dir"] / "keys.env.age"
    run(
        ["encrypt", str(age_home["plain"])],
        env={"UMI_AGE_RECIPIENTS": str(age_home["recipients"]), "UMI_KEYS_AGE": str(out)},
    )
    r = run(
        ["deploy"],
        env={
            "UMI_AGE_IDENTITY": str(age_home["identity"]),
            "UMI_KEYS_AGE": str(out),
            "UMI_DROPLET": "root@198.51.100.7",  # TEST-NET-2; no default exists since 2026-09-11
            "DRY_RUN": "1",
        },
    )
    assert r.returncode == 0, r.stderr
    plan = r.stdout
    # plaintext lands only under /dev/shm on the droplet, never a disk path
    assert "/dev/shm/" in plan
    assert "shred" in plan
    # the compose invocation matches the deploy runbook's, fed from tmpfs
    assert "--env-file /dev/shm/" in plan
    assert "docker/docker-compose.prod.yml" in plan
    assert "up -d app" in plan
    # decrypted material must never appear in the printed plan
    assert "k1-abc" not in plan
    # no scp of a plaintext file from the laptop: decrypt streams over the ssh pipe
    assert "scp" not in plan


def test_deploy_refuses_missing_identity(age_home):
    out = age_home["dir"] / "keys.env.age"
    run(
        ["encrypt", str(age_home["plain"])],
        env={"UMI_AGE_RECIPIENTS": str(age_home["recipients"]), "UMI_KEYS_AGE": str(out)},
    )
    r = run(
        ["deploy"],
        env={
            "UMI_AGE_IDENTITY": str(age_home["dir"] / "missing-identity.txt"),
            "UMI_KEYS_AGE": str(out),
            "UMI_DROPLET": "root@198.51.100.7",
            "DRY_RUN": "1",
        },
    )
    assert r.returncode != 0
    assert "identity" in (r.stderr + r.stdout).lower()


def test_deploy_refuses_missing_ciphertext(age_home):
    r = run(
        ["deploy"],
        env={
            "UMI_AGE_IDENTITY": str(age_home["identity"]),
            "UMI_KEYS_AGE": str(age_home["dir"] / "missing.age"),
            "UMI_DROPLET": "root@198.51.100.7",
            "DRY_RUN": "1",
        },
    )
    assert r.returncode != 0
    # Assert on the REASON, not just the exit code. Without a target set, this test
    # passed on need_droplet's refusal instead — green for the wrong reason.
    assert "ciphertext" in (r.stderr + r.stdout).lower()


def test_check_flags_plaintext_keys_in_env_file(age_home):
    dirty = age_home["dir"] / "droplet.env"
    dirty.write_text("DEBUG=False\nENCRYPTION_KEYS=oops\n")
    r = run(["check", "--local-file", str(dirty)])
    assert r.returncode != 0
    assert "ENCRYPTION_KEYS" in r.stdout + r.stderr


def test_check_passes_clean_env_file(age_home):
    clean = age_home["dir"] / "droplet.env"
    clean.write_text("DEBUG=False\nALLOWED_HOSTS=reciprocalaid.network\nEMAIL_HOST=smtp.x\n")
    r = run(["check", "--local-file", str(clean)])
    assert r.returncode == 0, r.stderr


# ── The two defects the first real rehearsal found, 2026-09-11 ────────────────
#
# The suite above proved encrypt, the refusals, check, and the TEXT of the dry-run
# plan. It never executed a deploy — and both defects lived in the two lines the dry
# run deliberately skips. These tests exist so that gap cannot reopen.
# See docs/key-custody-design.md §Second correction.


def test_deploy_does_not_feed_ssh_a_here_string():
    """Defect 1: the keys were silently discarded on every run since #147.

    `age -d ... | ssh HOST "bash -s" <<< "$script"` makes the pipe and the here-string
    contend for ssh's stdin. The here-string wins, `bash -s` consumes it as the script,
    and the script's own `cat > /dev/shm/umi-keys.env` then reads an exhausted stream.
    The plaintext never arrives, and nothing says so.
    """
    body = SCRIPT.read_text()
    deploy = body[body.index("cmd_deploy()") : body.index("cmd_check()")]
    ssh_lines = [ln for ln in deploy.splitlines() if "ssh " in ln and not ln.strip().startswith("#")]
    assert ssh_lines, "cmd_deploy no longer invokes ssh — this test guards how it does"
    for ln in ssh_lines:
        piped = "age -d" in ln or "|" in ln
        if piped:
            assert "<<<" not in ln, (
                "cmd_deploy pipes plaintext into ssh AND feeds a here-string: both claim "
                f"stdin, the here-string wins, and the keys are discarded.\n  {ln.strip()}"
            )


def test_deploy_passes_the_remote_script_as_an_argument():
    """The positive half of the rule above: stdin must stay free for the key material,
    so the script has to travel as an argument."""
    body = SCRIPT.read_text()
    deploy = body[body.index("cmd_deploy()") : body.index("cmd_check()")]
    assert "bash -c" in deploy, "the remote script must be passed as an argument, not on stdin"


def test_no_hardcoded_droplet_default():
    """A baked-in default outlived its droplet: the old value named a host destroyed
    2026-09-05 whose IP returned to DigitalOcean's pool. Deploying at a stranger is a
    worse failure than refusing to deploy."""
    body = SCRIPT.read_text()
    assert "UMI_DROPLET:-root@" not in body, "UMI_DROPLET must not carry a hardcoded host default"
    assert "need_droplet" in body, "a missing UMI_DROPLET must be refused explicitly"


def test_deploy_refuses_without_a_droplet_target(age_home):
    r = run(
        ["deploy"],
        env={
            "UMI_AGE_IDENTITY": str(age_home["identity"]),
            "UMI_KEYS_AGE": str(age_home["dir"] / "keys.env.age"),
            "HOME": str(age_home["dir"]),
        },
    )
    assert r.returncode != 0
    assert "UMI_DROPLET" in r.stderr


def test_compose_passes_key_material_into_the_container():
    """Defect 2, and the one that actually took the site down.

    `docker compose --env-file X` feeds compose's ${...} substitution. It injects
    NOTHING into the container. The app reads `env_file: ../.env` — so once the rig
    strips the key lines from .env (which it requires, and checks for), the app boots
    with no keys unless the compose file names them in `environment:`.

    Observed before the fix: ImproperlyConfigured: SECRET_KEY must be set.
    """
    compose = (Path(__file__).resolve().parent.parent / "docker" / "docker-compose.prod.yml").read_text()
    app = compose[compose.index("  app:") : compose.index("  db:")]
    for name in ("SECRET_KEY", "ENCRYPTION_KEY", "BLIND_INDEX_KEY"):
        assert f"- {name}=${{{name}}}" in app, (
            f"{name} is not passed into the app container. The custody rig removes it from "
            ".env, and --env-file only does ${...} substitution — so the app will boot "
            "without it and production will refuse to start."
        )
