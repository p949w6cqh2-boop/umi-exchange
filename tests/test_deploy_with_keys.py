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
            "DRY_RUN": "1",
        },
    )
    assert r.returncode != 0


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
