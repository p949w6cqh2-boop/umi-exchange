"""Key custody rig — scripts/deploy-with-keys.sh (docs/key-custody-design.md, keyed build).

The design's contract, pinned here:
  - the droplet at rest holds only ciphertext (secrets/keys.env.age);
  - decryption happens from the steward's laptop, plaintext travels only over ssh
    into a root-owned 0700 tmpfs dir (/run/umi-keys); the merged env is shredded after `up`;
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
    # plaintext lands only under /run/umi-keys (tmpfs, root-owned 0700) on the droplet, never a disk path
    assert "/run/umi-keys/" in plan
    assert "/dev/shm/umi" not in plan, "keys written into world-writable /dev/shm"
    assert "shred" in plan
    # the compose invocation matches the deploy runbook's, fed from tmpfs
    assert "--env-file /run/umi-keys/" in plan
    assert "docker/docker-compose.prod.yml" in plan
    assert "up -d --force-recreate app" in plan
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


COMPOSE_PROD = Path(__file__).resolve().parent.parent / "docker" / "docker-compose.prod.yml"


def _service(name):
    """One service of the prod compose file as compose sees it: YAML anchors resolved, so a
    shared environment block counts for every service that uses it."""
    import yaml

    return yaml.safe_load(COMPOSE_PROD.read_text())["services"][name]


def test_compose_passes_key_material_into_the_container():
    """Defect 2, and the one that actually took the site down.

    `docker compose --env-file X` feeds compose's ${...} substitution. It injects
    NOTHING into the container. The app reads `env_file: ../.env` — so once the rig
    strips the key lines from .env (which it requires, and checks for), the app boots
    with no keys unless compose gets them in by SOME route.

    Observed before the first fix: ImproperlyConfigured: SECRET_KEY must be set.

    ⚖️ REWRITTEN 2026-11-02, and the route changed. From 2026-09-11 that route was
    `environment:`, which fixed the boot and created the residue ethics-gate box 3
    is about: Docker writes a container's resolved environment to its own on-disk
    config and keeps it for the container's lifetime. The keys now arrive as a FILE
    on a tmpfs bind mount. **The lesson this test was written for is unchanged — the
    keys must actually REACH the container — only the mechanism it pins is new.**
    """
    for name in ("app", "worker"):
        service = _service(name)
        env = service["environment"]

        assert any(str(item).startswith("UMI_SECRETS_FILE=") for item in env), (
            f"the {name} container has no UMI_SECRETS_FILE, so it has no route to the keys "
            "at all: the rig removes them from .env and nothing else supplies them."
        )

        mounts = [str(v) for v in service["volumes"] if "/run/umi-keys/keys.env" in str(v)]
        assert mounts, f"the {name} container does not mount the key file named by UMI_SECRETS_FILE"
        assert mounts[0].endswith(":ro"), f"the {name} container mounts the key file writable"

        for key in ("SECRET_KEY", "ENCRYPTION_KEY", "ENCRYPTION_KEYS", "BLIND_INDEX_KEY"):
            assert not any(str(item).startswith(f"{key}=") for item in env), (
                f"{key} is back in the {name} container's environment — Docker will write it "
                "to the container config on disk, which is the residue box 3 exists to close."
            )


def test_compose_passes_the_key_list_so_rotation_can_reach_production():
    """The same defect, found again by the first real rotation (2026-10-01).

    Rotation stages ENCRYPTION_KEYS=<new>,<old> (docs/key-custody-design.md, the rotation
    line). The compose file passed only the single ENCRYPTION_KEY, so the container booted
    with no key at all and the site served 502 until the old key file was put back.

    ⚖️ REWRITTEN 2026-11-02 with the mechanism (see the test above). The key LIST now
    reaches the container because the rig writes the whole key file verbatim and the
    app reads every name in it — so a rotation needs no compose change at all, which
    is the property that cost an outage to learn.
    """
    assert "ENCRYPTION_KEYS" in KEYS_SAMPLE, "the rig's key file must be able to carry the list"
    env = _service("app")["environment"]
    assert any(str(item) == "UMI_SECRETS_FILE=/run/umi/keys.env" for item in env), (
        "the app must read its keys from the file the rig writes, or a rotation has no route into the container again"
    )


# ── The worker, 2026-10-18 ────────────────────────────────────────────────────
#
# Every recurring job the app registers (expiry of needs, offers and proposals; the
# retention shreds; the casework digest) needs a django-q cluster to run it, and the
# stack had none: the image runs gunicorn only. Read on the droplet 2026-10-18: zero
# tasks had ever run, and every schedule's next_run still sat at the 10-13 deploy.


def test_the_worker_runs_qcluster_from_the_app_image():
    worker, app = _service("worker"), _service("app")
    assert worker["image"] == app["image"], "the worker must run the code the app runs"
    assert "qcluster" in str(worker["command"])
    assert worker["restart"] == "unless-stopped", "a crashed worker must come back on its own"
    assert worker["depends_on"]["db"]["condition"] == "service_healthy"
    # The image's HEALTHCHECK probes the app's HTTP port, which the worker never serves:
    # left on, it would mark a working worker "unhealthy" forever.
    assert worker["healthcheck"] == {"disable": True}


def test_the_worker_gets_the_apps_environment_keys_included():
    """The sweeps decrypt and shred, and production settings refuse to load without the
    keys, so the worker needs exactly what the app gets, through the same lines."""
    worker, app = _service("worker"), _service("app")
    assert worker["environment"] == app["environment"]
    assert worker["env_file"] == app["env_file"]


def test_the_worker_logs_where_the_app_does():
    # production.py writes rotating log files under /app/logs; the app keeps them on a volume.
    assert "app_logs:/app/logs" in _service("worker")["volumes"]


# ── The migrate step, 2026-09-28 ──────────────────────────────────────────────
#
# Nothing in this stack migrates on its own: the image runs gunicorn and nothing else,
# and the rig stopped at `up -d app`. #174 shipped accounts.0006, so migrate had to be
# run by hand straight after the rig, or the new code would have queried a column the
# old schema did not have.


def test_deploy_migrates_after_up_and_after_the_shred(age_home):
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
            "UMI_DROPLET": "root@198.51.100.7",
            "DRY_RUN": "1",
        },
    )
    assert r.returncode == 0, r.stderr
    plan = r.stdout
    up = plan.index("up -d --force-recreate app")
    # The standalone shred LINE, not the trap, which carries the same words earlier.
    # ⚖️ 2026-11-02: only the MERGE file is shredded here now. The key file is mounted
    # into the containers, so it stays — and `docker exec` below starts a fresh process
    # that re-reads settings, which means it needs that file present, where before it
    # relied on the container's stored environment (the on-disk residue box 3 closes).
    shred = plan.index("\nshred -u /run/umi-keys/full.env\n")
    migrate = plan.index("manage.py migrate --noinput")
    assert up < shred < migrate
    # The container id is resolved on the droplet, not expanded on the laptop.
    assert "app_id=$(" in plan
    assert 'docker exec "$app_id"' in plan
    # A failed migrate must say what state it left behind, not just exit non-zero.
    assert "MIGRATE FAILED" in plan


# ── The shred trap, 2026-09-28 ────────────────────────────────────────────────
#
# The remote script runs under `set -e`, and its shred was an ordinary line after `up`.
# So a failed `up -d app` exited BEFORE the shred and left the decrypted keys sitting in
# /dev/shm until the droplet next rebooted. A trap on EXIT shreds them on every path.


def _dry_run_plan(age_home):
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
            "UMI_DROPLET": "root@198.51.100.7",
            "DRY_RUN": "1",
        },
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.split("\n", 1)[1]  # drop the "== DRY RUN ... ==" banner


def test_deploy_plan_traps_the_shred_before_any_plaintext_lands(age_home):
    plan = _dry_run_plan(age_home)
    trap = next((ln for ln in plan.splitlines() if ln.startswith("trap ")), None)
    assert trap, "the remote script sets no trap: a failed step leaves the keys in tmpfs"
    assert "EXIT" in trap
    assert "/run/umi-keys/keys.env" in trap and "/run/umi-keys/full.env" in trap
    assert plan.index(trap) < plan.index("cat > /run/umi-keys/keys.env")


def test_a_failed_up_still_shreds_the_keys(age_home, tmp_path):
    """Run the real remote script against a fake droplet: the tmpfs key dir and the compose dir
    rewritten into tmp, and a `docker` that fails on `up`. The keys file must be gone."""
    shm = tmp_path / "shm"
    repo = tmp_path / "repo"
    bindir = tmp_path / "bin"
    for d in (shm, repo, bindir):
        d.mkdir()
    (repo / ".env").write_text("DEBUG=False\n")  # key-free, as the rig requires
    docker = bindir / "docker"
    # The rig reads the image's runtime uid before `up` (2026-11-02: the key file is
    # bind-mounted and the container is not root), so the stub must answer that too
    # or the script refuses before it ever reaches the `up` this test is about.
    docker.write_text(
        "#!/bin/sh\n"
        'case " $* " in\n'
        + REAL_DOCKER_RUN_ID
        + REAL_COMPOSE_IMAGES
        + REAL_COMPOSE_JSON
        + '  *" up "*) echo "up failed" >&2; exit 1;;\n'
        "esac\n"
        "exit 0\n"
    )
    docker.chmod(0o755)
    _fake_chown(bindir)

    plan = _dry_run_plan(age_home).replace("/run/umi-keys", str(shm)).replace("cd /opt/umi-exchange", f"cd {repo}")
    r = subprocess.run(
        ["bash", "-c", plan],
        input=KEYS_SAMPLE,
        capture_output=True,
        text=True,
        env={"PATH": f"{bindir}:/usr/bin:/bin"},
        timeout=30,
    )
    assert r.returncode != 0, "the fake `up` should have failed the deploy"
    assert "up failed" in r.stderr
    assert not (shm / "keys.env").exists(), "decrypted keys left in tmpfs after a failed up"
    assert not (shm / "full.env").exists(), "merged env left in tmpfs after a failed up"


# ── The key file travels with the backups, 2026-10-01 ─────────────────────────
#
# keys.env.age existed only on the steward's laptop, and backup.sh never copied it, so a
# backup restored without that laptop had its sensitive columns locked for good, and an
# envelope holding only the printed identity recovered nothing (key-custody-design.md,
# Fifth entry). The founder's key "6": the ciphertext is printable, the rig copies it to
# the droplet's backup directory, and backup.sh carries it beside every dump.


def test_encrypt_writes_printable_armored_ciphertext(age_home):
    out = age_home["dir"] / "keys.env.age"
    r = run(
        ["encrypt", str(age_home["plain"])],
        env={"UMI_AGE_RECIPIENTS": str(age_home["recipients"]), "UMI_KEYS_AGE": str(out)},
    )
    assert r.returncode == 0, r.stderr
    text = out.read_text()  # armored age is plain ASCII: it can be printed for the envelope
    assert text.startswith("-----BEGIN AGE ENCRYPTED FILE-----")
    dec = subprocess.run(["age", "-d", "-i", str(age_home["identity"]), str(out)], capture_output=True, text=True)
    assert dec.stdout == KEYS_SAMPLE


def test_deploy_plan_says_it_copies_the_ciphertext_never_the_plaintext(age_home):
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
            "UMI_DROPLET": "root@198.51.100.7",
            "DRY_RUN": "1",
        },
    )
    assert r.returncode == 0, r.stderr
    banner = r.stdout.splitlines()[0]
    assert "/var/backups/umi/keys.env.age" in banner
    assert "ciphertext" in banner.lower()
    assert "k1-abc" not in r.stdout


def test_copy_ciphertext_refuses_a_file_that_is_not_age_ciphertext(age_home):
    r = run(
        ["copy-ciphertext"],
        env={"UMI_KEYS_AGE": str(age_home["plain"]), "UMI_DROPLET": "root@198.51.100.7", "DRY_RUN": "1"},
    )
    assert r.returncode != 0
    assert "not age ciphertext" in (r.stderr + r.stdout)


def test_copy_ciphertext_lands_the_file_with_owner_only_permissions(age_home, tmp_path):
    """Run the real copy through a fake ssh that executes the remote command locally."""
    out = age_home["dir"] / "keys.env.age"
    run(
        ["encrypt", str(age_home["plain"])],
        env={"UMI_AGE_RECIPIENTS": str(age_home["recipients"]), "UMI_KEYS_AGE": str(out)},
    )
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    ssh = bindir / "ssh"
    ssh.write_text('#!/bin/sh\nshift\nexec bash -c "$*"\n')  # drop the host, run the command here
    ssh.chmod(0o755)
    target = tmp_path / "droplet" / "backups" / "keys.env.age"
    r = subprocess.run(
        ["bash", str(SCRIPT), "copy-ciphertext"],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": f"{bindir}:/usr/bin:/bin:/usr/local/bin:" + str(Path.home() / ".local/bin"),
            "UMI_KEYS_AGE": str(out),
            "UMI_DROPLET": "root@198.51.100.7",
            "UMI_REMOTE_KEYS_COPY": str(target),
        },
    )
    assert r.returncode == 0, r.stderr
    assert target.read_bytes() == out.read_bytes()
    assert (target.stat().st_mode & 0o777) == 0o600
    assert not target.with_name("keys.env.age.tmp").exists()


# ── check over ssh must prove something or fail (2026-10-13) ─────────────────
#
# `check` was run on the droplet itself during the 2026-10-13 deploy: its ssh to the droplet was
# refused ("Permission denied (publickey)"), and it still printed "clean". Every non-match fell
# through to clean: grep's no-match (1), a missing .env (2) and ssh's own failure (255) alike.
# A check that could not look must fail. And when it does find key lines, it names them without
# echoing their values onto the laptop's terminal.


def _fake_tool(tmp_path, name, body):
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    tool = bindir / name
    tool.write_text("#!/bin/sh\n" + body)
    tool.chmod(0o755)
    return bindir


def _fake_ssh(tmp_path, body):
    return _fake_tool(tmp_path, "ssh", body)


def _fake_chown(bindir, calls=None):
    """A no-op chown for the fake droplet.

    The rig chowns the bind-mounted key file to the image's runtime uid, which on
    the real droplet runs as root. A test user cannot give a file away to another
    uid, and the contract under test is that the rig ASKS for it — not that this
    machine's kernel permits it.
    """
    tool = bindir / "chown"
    tool.write_text("#!/bin/sh\n" + (f'echo "chown $*" >> {calls}\n' if calls else "") + "exit 0\n")
    tool.chmod(0o755)
    return bindir


# How Docker and Compose v5.5.1 ACTUALLY answer the calls the rig makes before `up`,
# MEASURED on the droplet 2026-11-03. The first version of these stubs answered with what
# was EXPECTED, and the real deploy then failed with `docker: invalid reference format`:
#   * `compose config --images app` IGNORES the service name and prints every image;
#   * `docker run ... <ref>` refuses any reference that is not exactly one image name.
# A stub that echoes the expectation proves nothing about the tool. These echo the tool.
REAL_COMPOSE_IMAGES = '  *"config --images"*) printf "%s\\n" postgres:16-alpine redis:7-alpine umi-exchange:local ;;\n'
REAL_COMPOSE_JSON = (
    '  *"config --format json"*) echo \'{"services": {"app": {"image": "umi-exchange:local"},'
    ' "worker": {"image": "umi-exchange:local"}}}\' ;;\n'
)
REAL_DOCKER_RUN_ID = (
    '  *"--entrypoint id"*) [ "$5" = umi-exchange:local ] '
    '|| { echo "docker: invalid reference format" >&2; exit 125; }; echo 10001 ;;\n'
)


def _check_over_ssh(bindir, remote_dir):
    return subprocess.run(
        ["bash", str(SCRIPT), "check"],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": f"{bindir}:/usr/bin:/bin:/usr/local/bin",
            "UMI_DROPLET": "root@198.51.100.7",
            "UMI_REMOTE_DIR": str(remote_dir),
        },
    )


def test_check_fails_when_ssh_cannot_reach_the_droplet(tmp_path):
    bindir = _fake_ssh(tmp_path, 'echo "root@198.51.100.7: Permission denied (publickey)." >&2\nexit 255\n')
    r = _check_over_ssh(bindir, tmp_path)
    assert r.returncode != 0
    assert "clean" not in r.stdout
    assert "could not check" in r.stderr


def test_check_fails_when_the_droplet_has_no_env_file(tmp_path):
    bindir = _fake_ssh(tmp_path, 'shift\nexec bash -c "$*"\n')  # run the remote command here
    r = _check_over_ssh(bindir, tmp_path / "no-such-checkout")
    assert r.returncode != 0
    assert "clean" not in r.stdout
    assert "could not check" in r.stderr


def test_check_passes_a_clean_droplet_env_over_ssh(tmp_path):
    remote = tmp_path / "opt-umi"
    remote.mkdir()
    (remote / ".env").write_text("DEBUG=False\nALLOWED_HOSTS=reciprocalaid.network\n")
    bindir = _fake_ssh(tmp_path, 'shift\nexec bash -c "$*"\n')
    r = _check_over_ssh(bindir, remote)
    assert r.returncode == 0, r.stderr
    assert "clean: droplet .env holds no plaintext key material" in r.stdout


def test_check_names_found_keys_without_printing_their_values(tmp_path):
    remote = tmp_path / "opt-umi"
    remote.mkdir()
    (remote / ".env").write_text("DEBUG=False\nSECRET_KEY=s3cr3t-value-do-not-print\n")
    bindir = _fake_ssh(tmp_path, 'shift\nexec bash -c "$*"\n')
    r = _check_over_ssh(bindir, remote)
    assert r.returncode != 0
    assert "SECRET_KEY" in r.stdout + r.stderr
    assert "s3cr3t-value-do-not-print" not in r.stdout + r.stderr


def test_local_check_names_found_keys_without_printing_their_values(age_home):
    dirty = age_home["dir"] / "droplet.env"
    dirty.write_text("DEBUG=False\nBLIND_INDEX_KEY=bidx-value-do-not-print\n")
    r = run(["check", "--local-file", str(dirty)])
    assert r.returncode != 0
    assert "BLIND_INDEX_KEY" in r.stdout + r.stderr
    assert "bidx-value-do-not-print" not in r.stdout + r.stderr


def test_local_check_fails_when_the_file_cannot_be_read(tmp_path):
    # The local branch had the same hole: grep's 2 (could not read the file) fell through to
    # "clean". Root reads any file, so a stand-in grep fails the way an unreadable file makes it.
    env_file = tmp_path / "droplet.env"
    env_file.write_text("DEBUG=False\n")
    bindir = _fake_tool(tmp_path, "grep", 'echo "grep: $3: Permission denied" >&2\nexit 2\n')
    r = subprocess.run(
        ["bash", str(SCRIPT), "check", "--local-file", str(env_file)],
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": f"{bindir}:/usr/bin:/bin:/usr/local/bin"},
    )
    assert r.returncode != 0
    assert "clean" not in r.stdout
    assert "could not check" in r.stderr


# ── The rig creates the worker with its keys and starts it after migrate (2026-10-18) ──
#
# The keys exist on the droplet only in tmpfs, and only while the rig runs, so the worker
# is CREATED then, beside the app. It is STARTED only after migrate succeeds: every
# overdue schedule fires within seconds of a cluster starting, and a sweep run against
# the previous schema could fail or half-apply. A failed migrate leaves it stopped.


def test_deploy_creates_the_worker_with_its_keys_and_starts_it_after_migrate(age_home):
    plan = _dry_run_plan(age_home)
    create = plan.index("create --force-recreate worker")
    up = plan.index("up -d --force-recreate app")
    worker_id = plan.index("worker_id=$(")
    shred = plan.index("\nshred -u /run/umi-keys/full.env\n")
    migrate = plan.index("manage.py migrate --noinput")
    start = plan.index('docker start "$worker_id"')
    # Created while the keys are in tmpfs, and before the new app comes up, which also
    # stops the previous worker before it can run against the new schema. Started last.
    assert create < up < shred < migrate < start
    assert worker_id < shred, "the worker's id must be read while compose can still read its env file"
    # The worker mounts the same key file as the app (2026-10-18's lesson, kept through
    # the 2026-11-02 change): a key that reached one and not the other boots it with none.
    assert any("/run/umi-keys/keys.env" in str(v) for v in _service("worker")["volumes"])
    assert "ps -a -q worker" in plan, "a created worker is not running yet, so plain `ps -q` would not list it"


def _run_remote(
    age_home,
    tmp_path,
    migrate_rc=0,
    worker_id="workerid456",
    services="app worker db redis caddy",
    stale_dir=False,
    live_keys=None,
    dirty_env=False,
    stream=KEYS_SAMPLE,
):
    """Run the real remote script against a fake droplet whose `docker` records every call."""
    shm, repo, bindir = tmp_path / "shm", tmp_path / "repo", tmp_path / "bin"
    for d in (shm, repo, bindir):
        d.mkdir()
    if stale_dir:
        (shm / "keys.env").mkdir()
    if live_keys is not None:
        (shm / "keys.env").write_text(live_keys)
    (repo / ".env").write_text("DEBUG=False\n")  # key-free, as the rig requires
    if dirty_env:
        (repo / ".env").write_text("DEBUG=False\nSECRET_KEY=left-behind\n")
    calls = tmp_path / "docker-calls.log"
    docker = bindir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> {calls}\n'
        'case "$*" in\n'
        f'  *" config --services") printf "%s\\n" {services} ;;\n'
        # The runtime uid of the image, read before `up` so the bind-mounted key
        # file can be chowned to the non-root user the container runs as.
        + REAL_COMPOSE_IMAGES
        + REAL_COMPOSE_JSON
        + REAL_DOCKER_RUN_ID
        + '  *" ps -q app") echo appid123 ;;\n'
        f'  *" ps -a -q worker") echo "{worker_id}" ;;\n'
        f'  "exec appid123 python manage.py migrate --noinput") exit {migrate_rc} ;;\n'
        "esac\n"
        "exit 0\n"
    )
    docker.chmod(0o755)
    _fake_chown(bindir, calls)
    plan = _dry_run_plan(age_home).replace("/run/umi-keys", str(shm)).replace("cd /opt/umi-exchange", f"cd {repo}")
    r = subprocess.run(
        ["bash", "-c", plan],
        input=stream,
        capture_output=True,
        text=True,
        env={"PATH": f"{bindir}:/usr/bin:/bin"},
        timeout=30,
    )
    log = calls.read_text().splitlines() if calls.exists() else []
    return r, log, shm


def test_a_deploy_starts_the_worker_only_after_migrate(age_home, tmp_path):
    r, log, shm = _run_remote(age_home, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr

    def at(fragment):
        return next(i for i, call in enumerate(log) if fragment in call)

    assert (
        at("create --force-recreate worker")
        < at("up -d --force-recreate app")
        < at("python manage.py migrate")
        < at("start workerid456")
    )
    assert r.stdout.rstrip().endswith("worker started; deploy done")
    # ⚖️ CHANGED 2026-11-02: the key file now SURVIVES a successful deploy, because the
    # containers bind-mount it and re-read it on every restart. Its old absence here was
    # the thing that put the keys in the container config on disk instead.
    assert (shm / "keys.env").exists(), "the mounted key file must outlive the deploy"
    assert not (shm / "full.env").exists(), "the merged env file must still be shredded"


def test_a_failed_migrate_leaves_the_worker_stopped(age_home, tmp_path):
    r, log, shm = _run_remote(age_home, tmp_path, migrate_rc=1)
    assert r.returncode == 3
    assert "MIGRATE FAILED" in r.stdout
    assert not any(call.startswith("start ") for call in log), "a worker was started on a schema it does not match"
    # The app DID come up here; only migrate failed. So the keys stay — the running
    # container is mounting them, and shredding them would break its next restart.
    assert (shm / "keys.env").exists()
    assert not (shm / "full.env").exists()


def test_a_deploy_with_no_worker_container_says_so(age_home, tmp_path):
    r, log, _ = _run_remote(age_home, tmp_path, worker_id="")
    assert r.returncode == 4
    assert "WORKER NOT STARTED" in r.stdout


def test_a_rollback_to_a_compose_file_without_a_worker_still_deploys_the_app(age_home, tmp_path):
    """A rollback rebuilds an older commit, whose compose file may predate the worker. The rig
    on the laptop is the current one, so `create worker` would fail under `set -e` before the
    app came up, and the rollback would stop half-done."""
    r, log, shm = _run_remote(age_home, tmp_path, services="app db redis caddy")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not any("worker" in call for call in log if "config --services" not in call)
    assert "no worker service" in r.stdout
    assert any("python manage.py migrate" in call for call in log)
    assert (shm / "keys.env").exists()
    assert not (shm / "full.env").exists()


# ── Two defects found on 2026-11-03, reading the rig before a key rotation ────
#
# Both came from moving the keys out of compose's `environment:` into a bind-mounted file
# (#232), and no test caught either, because the stubs only ever saw the first deploy.


def test_a_reboot_leaves_a_directory_and_the_rig_still_recovers(age_home, tmp_path):
    """The recovery path itself. A reboot clears tmpfs; when the container then tries to
    start, Docker creates a DIRECTORY at the missing bind source (measured on a real daemon,
    29.1.3). `rm -f` cannot remove a directory, so under `set -e` the rig aborted, and the
    one documented way back from a server reboot did not work."""
    r, _, shm = _run_remote(age_home, tmp_path, stale_dir=True)

    assert r.returncode == 0, r.stdout + r.stderr
    assert (shm / "keys.env").is_file(), "the directory Docker left must be replaced by the key file"
    assert (shm / "keys.env").read_text() == KEYS_SAMPLE


def test_a_keys_only_change_still_recreates_both_containers(age_home, tmp_path):
    """With the keys in a mounted file, a rotation changes nothing compose can see. Its dry
    run on the droplet read `Container docker-app-1 Running`: no recreate, so the app would
    keep its old keys in memory and its old inode in the mount while the rig reported
    success, and `rotate_keks` through `docker exec` would see the old keys too."""
    r, log, _ = _run_remote(age_home, tmp_path)

    assert r.returncode == 0, r.stdout + r.stderr
    assert any("up -d --force-recreate app" in call for call in log)
    assert any("create --force-recreate worker" in call for call in log)


LIVE_KEYS = 'SECRET_KEY="the-keys-the-running-app-is-using"\n'


def test_a_refused_run_leaves_the_live_key_file_alone(age_home, tmp_path):
    """The containers mount this file. A run that stops before the swap must not touch it,
    or the app keeps serving from memory and its next restart fails. Before this, the rig
    deleted the live file first and its trap shredded whatever was there."""
    r, log, shm = _run_remote(age_home, tmp_path, live_keys=LIVE_KEYS, dirty_env=True)

    assert r.returncode != 0
    assert "REFUSING" in r.stdout
    assert (shm / "keys.env").read_text() == LIVE_KEYS, "a refused run must not touch the live key file"
    assert not (shm / "keys.env.new").exists(), "the staged keys must not outlive a refused run"
    assert not (shm / "full.env").exists()
    assert not any(" up " in f" {call} " for call in log), "a refused run must not reach up"


def test_a_successful_rerun_replaces_the_live_key_file(age_home, tmp_path):
    """The rotation path: new keys in place, nothing staged left behind."""
    r, _, shm = _run_remote(age_home, tmp_path, live_keys=LIVE_KEYS)

    assert r.returncode == 0, r.stdout + r.stderr
    assert (shm / "keys.env").read_text() == KEYS_SAMPLE
    assert not (shm / "keys.env.new").exists()
    assert not (shm / "full.env").exists()


def _assert_refused_untouched(r, log, shm):
    assert r.returncode != 0
    assert "REFUSING" in r.stdout
    assert (shm / "keys.env").read_text() == LIVE_KEYS, "a refused run must not touch the live key file"
    assert not (shm / "keys.env.new").exists(), "the staged keys must not outlive a refused run"
    assert not any(" up " in f" {call} " for call in log), "a refused run must not reach up"
    assert not any("--force-recreate" in call for call in log), "a refused run must not recreate anything"


def test_an_empty_key_stream_refuses_before_anything_changes(age_home, tmp_path):
    """A failed `age -d` on the laptop reaches the droplet as an EMPTY stream, and `cat`
    succeeds on it. With --force-recreate that would replace a healthy app with one that
    cannot boot, because a keys-only run now always recreates."""
    r, log, shm = _run_remote(age_home, tmp_path, live_keys=LIVE_KEYS, stream="")

    _assert_refused_untouched(r, log, shm)


@pytest.mark.parametrize("missing", ["SECRET_KEY", "BLIND_INDEX_KEY", "ENCRYPTION_KEYS"])
def test_a_partial_key_set_refuses_and_names_what_is_missing(age_home, tmp_path, missing):
    stream = "".join(f"{line}\n" for line in KEYS_SAMPLE.splitlines() if not line.startswith(missing))

    r, log, shm = _run_remote(age_home, tmp_path, live_keys=LIVE_KEYS, stream=stream)

    _assert_refused_untouched(r, log, shm)
    assert missing in r.stdout
    for value in ("k1-abc", "bidx-xyz", "django-secret"):
        assert value not in r.stdout + r.stderr, "a refusal names keys, never their values"


@pytest.mark.parametrize("name", ["SECRET_KEY", "BLIND_INDEX_KEY", "ENCRYPTION_KEYS"])
def test_a_blank_key_value_counts_as_missing(age_home, tmp_path, name):
    lines = [f'{name}=""' if line.startswith(name) else line for line in KEYS_SAMPLE.splitlines()]

    r, log, shm = _run_remote(age_home, tmp_path, live_keys=LIVE_KEYS, stream="\n".join(lines) + "\n")

    _assert_refused_untouched(r, log, shm)


def test_the_single_encryption_key_spelling_is_still_a_complete_set(age_home, tmp_path):
    """Settings accept either spelling (apps/people/crypto.py), so the guard must too."""
    stream = KEYS_SAMPLE.replace("ENCRYPTION_KEYS=", "ENCRYPTION_KEY=")

    r, _, shm = _run_remote(age_home, tmp_path, stream=stream)

    assert r.returncode == 0, r.stdout + r.stderr
    assert (shm / "keys.env").read_text() == stream


# ── `encrypt` on a laptop with no battery ─────────────────────────────────────
#
# The ciphertext can be the only copy on a machine that loses power without warning, and a
# power cut mid-write leaves a zero-byte file (measured 2026-11-03). A rotation is the first
# thing that ever re-runs `encrypt` over a live ciphertext.


def _encrypt_env(age_home, recipients=None):
    return {
        "UMI_AGE_RECIPIENTS": str(recipients or age_home["recipients"]),
        "UMI_AGE_IDENTITY": str(age_home["identity"]),
        "UMI_KEYS_AGE": str(age_home["dir"] / "keys.env.age"),
    }


def _other_recipient(age_home):
    other = age_home["dir"] / "other-identity.txt"
    keygen = subprocess.run(["age-keygen", "-o", str(other)], capture_output=True, text=True)
    recipients = age_home["dir"] / "other-recipients.txt"
    recipients.write_text(keygen.stderr.strip().split()[-1] + "\n")
    return recipients


def test_encrypt_keeps_the_previous_ciphertext_when_it_replaces_it(age_home):
    target = age_home["dir"] / "keys.env.age"
    assert run(["encrypt", str(age_home["plain"])], env=_encrypt_env(age_home)).returncode == 0
    previous = target.read_text()
    rotated = KEYS_SAMPLE.replace("django-secret", "rotated-secret")
    age_home["plain"].write_text(rotated)

    r = run(["encrypt", str(age_home["plain"])], env=_encrypt_env(age_home))

    assert r.returncode == 0, r.stderr
    archives = list(age_home["dir"].glob("keys.env.age.2*"))
    assert len(archives) == 1, "the key the old backups need must survive the rotation"
    assert archives[0].read_text() == previous
    opened = subprocess.run(["age", "-d", "-i", str(age_home["identity"]), str(target)], capture_output=True, text=True)
    assert opened.stdout == rotated
    assert not list(age_home["dir"].glob("keys.env.age.new.*")), "no temporary ciphertext left behind"
    assert target.stat().st_mode & 0o077 == 0, "the ciphertext stays private to its owner"


def test_encrypt_refuses_to_replace_a_ciphertext_with_one_that_does_not_open(age_home):
    """A wrong recipients file would otherwise swap the only copy for a file nobody can read."""
    target = age_home["dir"] / "keys.env.age"
    assert run(["encrypt", str(age_home["plain"])], env=_encrypt_env(age_home)).returncode == 0
    previous = target.read_text()

    r = run(["encrypt", str(age_home["plain"])], env=_encrypt_env(age_home, recipients=_other_recipient(age_home)))

    assert r.returncode != 0
    assert "nothing was replaced" in r.stderr
    assert target.read_text() == previous, "the working ciphertext must survive a refused encrypt"
    assert not list(age_home["dir"].glob("keys.env.age.2*")), "a refused encrypt archives nothing"
    assert not list(age_home["dir"].glob("keys.env.age.new.*")), "no temporary ciphertext left behind"


def test_encrypt_refuses_to_replace_a_ciphertext_it_cannot_check(age_home):
    target = age_home["dir"] / "keys.env.age"
    assert run(["encrypt", str(age_home["plain"])], env=_encrypt_env(age_home)).returncode == 0
    previous = target.read_text()
    env = _encrypt_env(age_home)
    env["UMI_AGE_IDENTITY"] = str(age_home["dir"] / "missing-identity.txt")

    r = run(["encrypt", str(age_home["plain"])], env=env)

    assert r.returncode != 0
    assert "nothing was replaced" in r.stderr
    assert target.read_text() == previous
