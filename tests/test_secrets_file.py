"""
Key material must reach the app as a FILE, never as container environment.

Docker writes a container's resolved environment into its own config on disk
(`/var/lib/docker/containers/<id>/config.v2.json`) and keeps it there for the
container's LIFETIME. So every key named in compose's `environment:` block was
sitting in plaintext on the droplet disk, readable by root, which is precisely
what ethics-gate box 3 says must end: "the key-encryption key no longer sits in
a plaintext file beside the database under the same root account."
`docs/key-custody-design.md` §Named residuals carried this as an open residual
from 2026-08-12, and §2026-10-18 widened it — the worker gets the same block, so
there were two copies of it.

The fix pinned here: `UMI_SECRETS_FILE` points at a key file on a tmpfs bind
mount. The container config then records the PATH, not the secret.

Honest limit, stated so no reader mistakes this for more than it is: the keys are
in RAM at a known root-readable path for the container's lifetime. That is
strictly better than on disk — tmpfs is cleared on reboot and never written to a
block device — and it is NOT the same as unreachable.
"""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMPOSE = (REPO / "docker" / "docker-compose.prod.yml").read_text()

KEY_NAMES = ["SECRET_KEY", "ENCRYPTION_KEY", "ENCRYPTION_KEYS", "BLIND_INDEX_KEY"]

KEYS_FILE_BODY = 'SECRET_KEY="{secret}"\nENCRYPTION_KEYS="{fernet}"\nBLIND_INDEX_KEY="{bidx}"\n'


@pytest.fixture
def keys_file(tmp_path):
    import secrets

    from cryptography.fernet import Fernet

    path = tmp_path / "keys.env"
    # A real-shaped SECRET_KEY: Django's security.W009 wants >=50 chars AND >=5
    # distinct characters, so "x" * 60 is long enough and still fails the check.
    path.write_text(
        KEYS_FILE_BODY.format(
            secret=secrets.token_urlsafe(48),
            fernet=Fernet.generate_key().decode(),
            bidx=Fernet.generate_key().decode(),
        )
    )
    path.chmod(0o600)
    return path


def _check_deploy(env):
    """`manage.py check --deploy` under production settings.

    Production fails fast on an empty SECRET_KEY / ENCRYPTION_KEY /
    BLIND_INDEX_KEY, so a clean run with the keys supplied ONLY by the file is
    itself the proof that the file was read.
    """
    return subprocess.run(  # noqa: S603
        [str(REPO / ".venv" / "bin" / "python"), "manage.py", "check", "--deploy"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO),
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "ALLOWED_HOSTS": "example.com",
            "REDIS_URL": "redis://127.0.0.1:6379/11",
            **env,
        },
    )


def test_keys_can_arrive_entirely_from_the_secrets_file(keys_file):
    """No key is in the environment; all three come from the file."""
    result = _check_deploy({"UMI_SECRETS_FILE": str(keys_file)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no issues" in result.stdout + result.stderr


def test_a_missing_secrets_file_fails_loudly(tmp_path):
    """Set-but-absent is the dangerous state: it looks configured and supplies
    nothing. It must name the variable, not fail somewhere downstream."""
    result = _check_deploy({"UMI_SECRETS_FILE": str(tmp_path / "not-here.env")})

    assert result.returncode != 0
    assert "UMI_SECRETS_FILE" in result.stdout + result.stderr


def test_the_secrets_file_wins_over_a_stale_environment_key(keys_file):
    """The rig may run against a droplet whose .env still carries an old key.
    The file is the authority, or a rotation could silently use the old one."""
    result = _check_deploy(
        {
            "UMI_SECRETS_FILE": str(keys_file),
            "SECRET_KEY": "dev-only-insecure-key-change-in-production-please",
        }
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_compose_no_longer_names_key_material_in_the_environment_block():
    """The whole point: a key named here lands in the container's on-disk config.

    Guards against the fix being reverted by someone re-fixing the 2026-09-11 and
    2026-10-01 boot failures the old way.
    """
    anchor = COMPOSE[COMPOSE.index("x-app-environment:") : COMPOSE.index("services:")]
    for name in KEY_NAMES:
        assert f"- {name}=" not in anchor, (
            f"{name} is back in compose's environment block — Docker will write it to "
            "the container config on disk. Supply it through UMI_SECRETS_FILE instead."
        )


def test_compose_points_both_app_and_worker_at_the_secrets_file():
    """2026-10-18's lesson: the worker takes the same block as the app. A fix that
    reached only the app would leave the second copy of the residue in place."""
    anchor = COMPOSE[COMPOSE.index("x-app-environment:") : COMPOSE.index("services:")]

    assert "UMI_SECRETS_FILE=" in anchor, "the shared block must carry the path"
    # Both services must mount it, or one of them boots with no keys at all.
    for service in ("app:", "worker:"):
        start = COMPOSE.index(f"  {service}")
        body = COMPOSE[start : start + 1800]
        assert "umi-keys.env" in body, f"{service} does not mount the key file"


def test_the_mounted_key_file_is_read_only_in_the_container():
    """The app reads keys; it never writes them. A writable mount would let an
    app-level compromise rewrite what the next restart loads."""
    for service in ("app:", "worker:"):
        start = COMPOSE.index(f"  {service}")
        body = COMPOSE[start : start + 1800]
        mount = [ln for ln in body.splitlines() if "umi-keys.env" in ln]
        assert mount, f"{service} has no key-file mount line"
        assert mount[0].rstrip().endswith(":ro"), f"{service} mounts the key file writable"


# ── The deploy rig's half ────────────────────────────────────────────────────
# Source assertions, so these run without the `age` binary (the rig's own test
# module is skipped wholesale where it is absent, and this contract is too
# important to only be checked on the steward's laptop).

RIG = (REPO / "scripts" / "deploy-with-keys.sh").read_text()


def test_the_rig_keeps_the_mounted_key_file_after_a_successful_deploy():
    """Before 2026-11-02 the rig shredded the key file right after `up`, because
    the container had its own copy in its stored environment. That copy was the
    residue box 3 names, so the file is now the only source and must survive."""
    assert "shred -u /dev/shm/umi-keys.env /dev/shm/umi-full.env" not in RIG, (
        "the post-up shred still removes the mounted key file — the containers "
        "re-read it on every restart and would come back with no keys"
    )
    assert "shred -u /dev/shm/umi-full.env" in RIG, "the merged env file must still be shredded"


def test_a_failed_deploy_still_shreds_the_keys():
    """The 2026-09-28 property must hold: plaintext never outlives a deploy that
    did not bring the app up. Keeping the file is conditional on reaching `up`."""
    assert "keep_keys=no" in RIG, "the keep flag must default to not keeping"
    assert 'keep_keys\\" = yes ] || shred -u /dev/shm/umi-keys.env' in RIG or (
        'keep_keys" = yes ] || shred -u /dev/shm/umi-keys.env' in RIG
    ), "the EXIT trap must shred the key file unless the deploy reached `up`"

    # And the flag must be set AFTER the up, never before it.
    assert RIG.index("keep_keys=yes") > RIG.index("up -d app"), (
        "keep_keys is set before `up -d app`, so a failed up would leave the keys behind"
    )


def test_the_rig_makes_the_key_file_readable_by_the_image_user():
    """The image runs as USER umi, not root. A root-owned 0600 mount is
    unreadable inside the container and the app boots with no keys."""
    assert "config --images app" in RIG, "the runtime uid must come from the app image"
    assert 'chown "\\$app_uid" /dev/shm/umi-keys.env' in RIG, "the key file must be chowned to it"
    # Deliberately NOT chmod 400: ':ro' on the mount is what makes it read-only to
    # the container, and clearing the owner write bit only breaks the failure-path shred.
    assert "chmod 400 /dev/shm/umi-keys.env" not in RIG


def test_the_rig_refuses_a_non_numeric_uid():
    """If the image cannot be inspected, chown would silently take a garbage
    argument. Fail before touching the running stack."""
    assert "REFUSING: could not read a numeric runtime uid" in RIG
