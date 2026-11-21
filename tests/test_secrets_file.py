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

import json
import shutil
import subprocess
import sys
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
        [sys.executable, "manage.py", "check", "--deploy"],
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
        assert "/run/umi-keys/keys.env" in body, f"{service} does not mount the key file"


def test_the_mounted_key_file_is_read_only_in_the_container():
    """The app reads keys; it never writes them. A writable mount would let an
    app-level compromise rewrite what the next restart loads."""
    for service in ("app:", "worker:"):
        start = COMPOSE.index(f"  {service}")
        body = COMPOSE[start : start + 1800]
        mount = [ln for ln in body.splitlines() if "/run/umi-keys/keys.env" in ln]
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
    assert "shred -u /run/umi-keys/keys.env /run/umi-keys/full.env" not in RIG, (
        "the post-up shred still removes the mounted key file — the containers "
        "re-read it on every restart and would come back with no keys"
    )
    assert "shred -u /run/umi-keys/full.env" in RIG, "the merged env file must still be shredded"


def test_a_failed_deploy_still_shreds_the_keys():
    """The 2026-09-28 property must hold: plaintext never outlives a deploy that
    did not bring the app up. Keeping the file is conditional on reaching `up`."""
    assert "keep_keys=no" in RIG, "the keep flag must default to not keeping"
    assert 'keep_keys\\" = yes ] || shred -u /run/umi-keys/keys.env' in RIG or (
        'keep_keys" = yes ] || shred -u /run/umi-keys/keys.env' in RIG
    ), "the EXIT trap must shred the key file unless the deploy reached `up`"

    # And the flag must be set AFTER the up, never before it.
    assert RIG.index("keep_keys=yes") > RIG.index("up -d --force-recreate app"), (
        "keep_keys is set before `up -d app`, so a failed up would leave the keys behind"
    )


def test_the_rig_makes_the_key_file_readable_by_the_image_user():
    """The image runs as USER umi, not root. A root-owned 0600 mount is
    unreadable inside the container and the app boots with no keys."""
    # From the JSON config, never `config --images <service>`: Compose v5.5.1 ignores the
    # service name there and prints every image, which failed the first real deploy.
    assert "config --format json" in RIG and '["services"]["app"]["image"]' in RIG, (
        "the runtime uid must come from the APP's image, named unambiguously"
    )
    # Commands only: the rig's own comment names the call in order to explain avoiding it.
    commands = [ln for ln in RIG.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert not [ln for ln in commands if "config --images" in ln], (
        "a command still uses config --images, which cannot filter by service on Compose v5"
    )
    assert 'chown "\\$app_uid" /run/umi-keys/keys.env.new' in RIG, "the key file must be chowned to it"
    # Deliberately NOT chmod 400: ':ro' on the mount is what makes it read-only to
    # the container, and clearing the owner write bit only breaks the failure-path shred.
    assert "chmod 400 /run/umi-keys/keys.env" not in RIG


def test_the_rig_refuses_a_non_numeric_uid():
    """If the image cannot be inspected, chown would silently take a garbage
    argument. Fail before touching the running stack."""
    assert "REFUSING: could not read a numeric runtime uid" in RIG


# ── Security review, 2026-11-02 ──────────────────────────────────────────────
# The first version wrote the key file into /dev/shm and read it with
# read_env(overwrite=True). An automated review flagged both, and both were real:
#   * /dev/shm is mode 1777. Any local user can pre-create the path, or plant a
#     symlink there, and root's write lands in a file THEY own.
#   * read_env honours ANY name. A writable key file was therefore config
#     injection — DATABASE_URL, DJANGO_SETTINGS_MODULE — not just key disclosure.


def _settings_probe(env, code):
    """Load production settings with `env`, then run `code` in the shell."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "manage.py", "shell", "-c", code],
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


def test_a_symlink_at_the_secrets_path_is_refused(keys_file, tmp_path):
    """A symlink planted at the path is the /dev/shm attack's read-side twin."""
    link = tmp_path / "planted.env"
    link.symlink_to(keys_file)

    result = _check_deploy({"UMI_SECRETS_FILE": str(link)})

    assert result.returncode != 0
    assert "SYMLINK" in result.stdout + result.stderr


def test_a_key_file_readable_beyond_its_owner_is_refused(keys_file):
    keys_file.chmod(0o644)

    result = _check_deploy({"UMI_SECRETS_FILE": str(keys_file)})

    assert result.returncode != 0
    assert "0644" in result.stdout + result.stderr


def test_the_key_file_cannot_set_anything_but_the_keys(keys_file):
    """The config-injection half. Whatever writes this file must not be able to
    point the app at another database."""
    keys_file.write_text(keys_file.read_text() + 'DATABASE_URL="postgres://attacker@evil.example/stolen"\n')
    keys_file.chmod(0o600)

    result = _settings_probe(
        {"UMI_SECRETS_FILE": str(keys_file)},
        "import os; print('DBURL=' + os.environ.get('DATABASE_URL', 'unset'))",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "attacker" not in result.stdout, "a non-key name in the key file was honoured"


def test_a_key_file_with_no_key_in_it_is_refused(tmp_path):
    """Empty or malformed is a failed deploy, not a quiet fallback to defaults."""
    path = tmp_path / "keys.env"
    path.write_text("DEBUG=True\n")
    path.chmod(0o600)

    result = _check_deploy({"UMI_SECRETS_FILE": str(path)})

    assert result.returncode != 0
    assert "set none of" in result.stdout + result.stderr


def test_the_rig_writes_keys_into_a_root_owned_0700_dir_not_dev_shm():
    """/run is root-owned 0755, so a non-root user cannot create anything in it;
    the rig then locks its own directory down to root 0700."""
    commands = [ln for ln in RIG.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert not [ln for ln in commands if "/dev/shm" in ln], "a command still writes into world-writable /dev/shm"

    assert "mkdir -p /run/umi-keys" in RIG
    assert "chown root:root /run/umi-keys" in RIG
    assert "chmod 700 /run/umi-keys" in RIG
    assert RIG.index("chmod 700 /run/umi-keys") < RIG.index("cat > /run/umi-keys/keys.env"), (
        "the directory must be locked down BEFORE any plaintext lands in it"
    )


def test_the_rig_never_writes_through_an_existing_key_file():
    """`cat >` into a path that already exists writes into whatever is there.
    Remove first, so the write always creates a fresh file root owns."""
    assert "rm -rf /run/umi-keys/keys.env.new" in RIG
    assert RIG.index("rm -rf /run/umi-keys/keys.env.new") < RIG.index("cat > /run/umi-keys/keys.env.new")


def test_compose_mounts_the_key_file_from_the_locked_directory():
    for service in ("app:", "worker:"):
        start = COMPOSE.index(f"  {service}")
        body = COMPOSE[start : start + 2400]
        assert "- /run/umi-keys/keys.env:/run/umi/keys.env:ro" in body, f"{service} mounts the wrong source"
        assert "- /dev/shm/" not in body, f"{service} still mounts from world-writable /dev/shm"


# Source assertions on purpose: the rig's own module is skipped wherever `age` is absent,
# which includes CI, and these two are what a rotation and a reboot recovery depend on.


def test_a_rig_rerun_recreates_both_containers_when_only_the_keys_changed():
    """A keys-only change is invisible to compose now, so `up -d` alone leaves the app on
    its old keys while reporting success. Found 2026-11-03 before a rotation relied on it."""
    assert "up -d --force-recreate app" in RIG
    assert "create --force-recreate worker" in RIG


def test_the_rig_clears_the_directory_docker_leaves_after_a_reboot():
    """After a reboot Docker creates a directory at the missing bind source, and `rm -f`
    cannot remove one. This line is the difference between a recovery and an abort. The
    newline matters: without it `rm -rf .../keys.env.new` would satisfy this too."""
    clear = "[ ! -d /run/umi-keys/keys.env ] || rm -rf /run/umi-keys/keys.env\n"
    assert clear in RIG
    assert RIG.index(clear) < RIG.index("mv -f /run/umi-keys/keys.env.new /run/umi-keys/keys.env")


def test_the_rig_checks_the_keys_that_arrived_before_it_replaces_the_live_file():
    """A failed decrypt on the laptop arrives as an empty stream, and every run recreates."""
    guard = RIG.index("the keys that arrived")
    assert RIG.index("cat > /run/umi-keys/keys.env.new") < guard
    assert guard < RIG.index("mv -f /run/umi-keys/keys.env.new /run/umi-keys/keys.env")


def test_encrypt_never_overwrites_the_ciphertext_in_place():
    """The ciphertext can be the only copy on a laptop that loses power without warning."""
    encrypt = RIG[RIG.index("cmd_encrypt() {") : RIG.index("cmd_deploy() {")]
    assert '-o "$KEYS_AGE"' not in encrypt
    assert 'cmp -s - "$plain"' in encrypt, "the new ciphertext must be proven to open first"
    assert 'mv -f "$tmp" "$KEYS_AGE"' in encrypt


# ── The off-site backup credential ────────────────────────────────────────────
#
# `env_file: ../.env` hands every line of .env to the app and the worker, and Docker writes
# them into config.v2.json. The backup credential is in .env for scripts/backup.sh, on the
# host. Nothing in apps/ or config/ reads it, so a compromised app held the key to the
# off-site backups for no reason. Found 2026-11-03 while checking the rotated keys were gone.

BACKUP_CREDENTIAL = ["BACKUP_ACCESS_KEY", "BACKUP_SECRET_KEY"]


def _compose_available():
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0


def test_compose_blanks_the_backup_credential_in_the_block_both_services_share():
    anchor = COMPOSE[COMPOSE.index("x-app-environment:") : COMPOSE.index("services:")]
    for name in BACKUP_CREDENTIAL:
        assert f"  - {name}=\n" in anchor, f"{name} must be blank here, or env_file hands it to the app"
    assert COMPOSE.count("environment: *app-environment") == 2, "the app and the worker must both take the block"


@pytest.mark.skipif(not _compose_available(), reason="needs docker compose")
def test_real_compose_resolves_the_credential_to_blank_in_both_containers(tmp_path):
    """`environment:` beating `env_file:` is compose's behaviour, so ask compose. A text
    search would pass on a spelling where the blank does not win."""
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "docker-compose.prod.yml").write_text(COMPOSE)
    env = tmp_path / ".env"
    env.write_text("BACKUP_ACCESS_KEY=fake-access\nBACKUP_SECRET_KEY=fake-secret\nBACKUP_BUCKET=fake-bucket\n")

    r = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env),
            "-f",
            "docker/docker-compose.prod.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert r.returncode == 0, r.stderr
    services = json.loads(r.stdout)["services"]
    for service in ("app", "worker"):
        environment = services[service]["environment"]
        assert environment["BACKUP_BUCKET"] == "fake-bucket", "control: env_file must still reach this service"
        for name in BACKUP_CREDENTIAL:
            assert environment[name] == "", f"{service} still receives {name}"


def test_nothing_in_the_app_reads_the_backup_credential():
    """What makes blanking it safe. If this ever fails, the new reader needs a route of its
    own, not the credential back in the container."""
    readers = [
        str(path.relative_to(REPO))
        for root in ("apps", "config")
        for path in (REPO / root).rglob("*.py")
        if "tests" not in path.parts and any(name in path.read_text() for name in BACKUP_CREDENTIAL)
    ]
    assert readers == []


def test_the_backup_script_reads_the_credential_from_the_host_env_file():
    """The other half. The job that does need it runs on the host, and gets it from .env."""
    script = (REPO / "scripts" / "backup.sh").read_text()
    for name in BACKUP_CREDENTIAL:
        assert f"$(env_file_val {name})" in script, f"backup.sh no longer loads {name} from .env itself"
