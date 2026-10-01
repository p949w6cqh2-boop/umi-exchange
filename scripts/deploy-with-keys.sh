#!/usr/bin/env bash
# deploy-with-keys.sh — the key-custody deploy rig (docs/key-custody-design.md).
#
# The contract this script keeps:
#   * key material at rest is ciphertext only (age), on the laptop AND the droplet;
#   * decryption happens here, on the steward's laptop, and the plaintext travels
#     only through an ssh pipe into droplet tmpfs (/dev/shm), which is shredded
#     the moment the container is up;
#   * the repository never holds keys in any form — secrets/ is gitignored, and
#     the default ciphertext path lives OUTSIDE the repo;
#   * refuse loudly when half-armed (no identity, no recipients, no ciphertext).
#
# Modes:
#   encrypt <plaintext-env-file>   age-encrypt key material -> $UMI_KEYS_AGE (armored: printable)
#   deploy                         decrypt -> ssh -> tmpfs merge -> compose up -> shred -> migrate,
#                                  then copy-ciphertext
#   copy-ciphertext                copy the CIPHERTEXT (never plaintext) to the droplet's backup
#                                  dir, so backup.sh carries it beside every dump
#   check                          prove the droplet .env holds no plaintext keys
#   check --local-file <file>      same proof against a local file (used by tests)
#
# Config (env, all optional):
#   UMI_AGE_IDENTITY   age identity file        (default ~/.config/umi/age-identity.txt)
#   UMI_AGE_RECIPIENTS age recipients file      (default ~/.config/umi/age-recipients.txt)
#   UMI_KEYS_AGE       ciphertext path          (default ~/.config/umi/keys.env.age)
#   UMI_DROPLET        ssh target               (REQUIRED for deploy/check/copy-ciphertext — no default)
#   UMI_REMOTE_DIR     compose dir on droplet   (default /opt/umi-exchange)
#   UMI_REMOTE_KEYS_COPY  ciphertext copy on the droplet (default /var/backups/umi/keys.env.age)
#   DRY_RUN=1          print the plan, run nothing remote

set -euo pipefail

CONF_HOME="${HOME:-/nonexistent}"
IDENTITY="${UMI_AGE_IDENTITY:-$CONF_HOME/.config/umi/age-identity.txt}"
RECIPIENTS="${UMI_AGE_RECIPIENTS:-$CONF_HOME/.config/umi/age-recipients.txt}"
KEYS_AGE="${UMI_KEYS_AGE:-$CONF_HOME/.config/umi/keys.env.age}"
# No baked-in default. The old one named a droplet destroyed 2026-09-05 whose IP has
# returned to DigitalOcean's pool — a silent default that would deploy at a stranger.
# Checked lazily by need_droplet(), because encrypt and `check --local-file` need none.
DROPLET="${UMI_DROPLET:-}"
REMOTE_DIR="${UMI_REMOTE_DIR:-/opt/umi-exchange}"
# Outside the repo on purpose: the image is built with `COPY . .`, and .dockerignore does
# not exclude secrets/, so a copy inside the checkout would be baked into every image.
REMOTE_KEYS_COPY="${UMI_REMOTE_KEYS_COPY:-/var/backups/umi/keys.env.age}"
COMPOSE="docker compose --env-file /dev/shm/umi-full.env -f docker/docker-compose.prod.yml"

# The names that must never sit in plaintext on the droplet (key-custody design).
KEY_NAMES='ENCRYPTION_KEYS?|BLIND_INDEX_KEY|SECRET_KEY'

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'  # the whole header comment, however long it grows
  exit "${1:-0}"
}

need_age() { command -v age >/dev/null || die "age binary not found (install age)"; }
need_droplet() {
  [ -n "$DROPLET" ] || die "set UMI_DROPLET=root@<droplet-ip> — there is no default (the previous one outlived its droplet)"
}

cmd_encrypt() {
  local plain="${1:-}"
  [ -n "$plain" ] || die "usage: deploy-with-keys.sh encrypt <plaintext-env-file>"
  [ -f "$plain" ] || die "plaintext file not found: $plain"
  [ -f "$RECIPIENTS" ] || die "recipients file not found: $RECIPIENTS (age-keygen first; see docs/key-custody-design.md)"
  need_age
  grep -Eq "^($KEY_NAMES)=" "$plain" || die "$plain carries none of: ENCRYPTION_KEYS, BLIND_INDEX_KEY, SECRET_KEY — wrong file?"
  case "$plain" in
    "$PWD"/secrets/*|secrets/*) : ;;  # allowed staging spot (gitignored)
    *) : ;;
  esac
  mkdir -p "$(dirname "$KEYS_AGE")"
  # Armored (-a): plain ASCII, so the envelope can carry it on paper as well as a USB drive.
  age -e -a -R "$RECIPIENTS" -o "$KEYS_AGE" < "$plain"
  echo "encrypted -> $KEYS_AGE"
  echo "NOW SHRED THE PLAINTEXT: shred -u '$plain'  (ciphertext is the only copy that should remain)"
}

cmd_deploy() {
  need_droplet
  [ -f "$IDENTITY" ] || die "age identity not found: $IDENTITY — this rig deploys from the steward's laptop only"
  [ -f "$KEYS_AGE" ] || die "ciphertext not found: $KEYS_AGE (run encrypt first)"
  need_age

  # Everything the droplet runs, in one heredoc: read plaintext from stdin straight
  # into tmpfs, merge with the (key-free) .env, bring the app up, shred both tmpfs
  # files. Plaintext never touches droplet disk; nothing is scp'd.
  # The shred is also TRAPPED on exit, set before any plaintext lands: under `set -e` a
  # failed `up` used to exit before the shred line and leave the keys in tmpfs until
  # the next reboot.
  # Then migrate, through the container that is already running: it holds its keys in
  # its own config, so this step never needs the tmpfs file and runs after the shred.
  # Nothing else in the stack migrates (the image runs gunicorn only), so a deploy that
  # carries a migration served new code against the old schema until this was added.
  local remote_script
  remote_script=$(cat <<REMOTE
set -euo pipefail
umask 077
trap 'shred -u /dev/shm/umi-keys.env /dev/shm/umi-full.env 2>/dev/null || true' EXIT
cat > /dev/shm/umi-keys.env
cd $REMOTE_DIR
grep -Eq '^($KEY_NAMES)=' .env && { echo 'REFUSING: droplet .env still carries plaintext key lines — finish the migration (docs/key-custody-design.md)'; shred -u /dev/shm/umi-keys.env; exit 1; }
cat .env /dev/shm/umi-keys.env > /dev/shm/umi-full.env
$COMPOSE up -d app
$COMPOSE ps app
app_id=\$($COMPOSE ps -q app || true)
shred -u /dev/shm/umi-keys.env /dev/shm/umi-full.env
echo 'tmpfs shredded'
[ -n "\$app_id" ] || { echo 'MIGRATE FAILED: no app container after up, so nothing was migrated. Check: docker ps'; exit 3; }
docker exec "\$app_id" python manage.py migrate --noinput || { echo 'MIGRATE FAILED: the new app is running on a schema it does not match. Read the error above, fix it, and re-run: docker exec <app container> python manage.py migrate. The backup taken before this deploy is the fallback.'; exit 3; }
echo 'migrations applied; deploy done'
REMOTE
)

  if [ "${DRY_RUN:-0}" = "1" ]; then
    # One banner line (the tests run everything below it as the remote script).
    echo "== DRY RUN: would decrypt $KEYS_AGE with $IDENTITY and pipe it to the STDIN of: ssh $DROPLET bash -c <the script below>, then copy the ciphertext (never plaintext) to $DROPLET:$REMOTE_KEYS_COPY =="
    echo "$remote_script"
    return 0
  fi

  # The script goes in as an ARGUMENT, not on stdin. Piping the plaintext while also
  # feeding the script as a here-string makes both contend for ssh's stdin: the
  # here-string wins, `bash -s` consumes it as the script, and the script's own
  # `cat > /dev/shm/umi-keys.env` then reads an exhausted stream — so the decrypted
  # keys were silently discarded on every run from #147 until 2026-09-11.
  # printf %q quotes the script for the remote shell, leaving stdin free for the data.
  age -d -i "$IDENTITY" "$KEYS_AGE" | ssh "$DROPLET" "bash -c $(printf '%q' "$remote_script")" \
    || die "deploy failed — plaintext was confined to the pipe and tmpfs; re-run after fixing"
  # shellcheck disable=SC2181
  # Every deploy refreshes the droplet's ciphertext copy, so after a key rotation the
  # next nightly backup carries the new key file without anyone remembering to.
  cmd_copy_ciphertext || die "deploy done, but the ciphertext copy failed: backups will not carry the key file until 'copy-ciphertext' succeeds"
}

# Binary or armored age, by the file's first bytes. Anything else, above all a plaintext
# keys file in the wrong place, is never copied anywhere.
is_age_ciphertext() {
  local head
  head=$(LC_ALL=C head -c 21 "$1" | tr -d '\0')
  [ "$head" = "age-encryption.org/v1" ] || [ "$head" = "-----BEGIN AGE ENCRYP" ]
}

cmd_copy_ciphertext() {
  need_droplet
  [ -f "$KEYS_AGE" ] || die "ciphertext not found: $KEYS_AGE"
  is_age_ciphertext "$KEYS_AGE" || die "$KEYS_AGE is not age ciphertext — refusing to copy it anywhere"
  local dir
  dir=$(dirname "$REMOTE_KEYS_COPY")
  if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "== DRY RUN: would copy the ciphertext (never plaintext) $KEYS_AGE to $DROPLET:$REMOTE_KEYS_COPY, mode 600 =="
    return 0
  fi
  # Written beside the target, then renamed: a dropped connection never leaves a half file
  # where backup.sh would pick it up.
  ssh "$DROPLET" "umask 077 && mkdir -p $(printf '%q' "$dir") && cat > $(printf '%q' "$REMOTE_KEYS_COPY.tmp") && mv $(printf '%q' "$REMOTE_KEYS_COPY.tmp") $(printf '%q' "$REMOTE_KEYS_COPY")" < "$KEYS_AGE" \
    || die "could not copy the ciphertext to $DROPLET:$REMOTE_KEYS_COPY"
  echo "ciphertext copied -> $DROPLET:$REMOTE_KEYS_COPY (backup.sh now carries it beside every dump)"
}

cmd_check() {
  if [ "${1:-}" = "--local-file" ]; then
    local f="${2:-}"
    [ -f "$f" ] || die "no such file: $f"
    if grep -E "^($KEY_NAMES)=" "$f"; then
      die "plaintext key material present in $f"
    fi
    echo "clean: no plaintext key lines in $f"
    return 0
  fi
  need_droplet
  if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "== DRY RUN: would run on $DROPLET: grep -E '^($KEY_NAMES)=' $REMOTE_DIR/.env =="
    return 0
  fi
  if ssh "$DROPLET" "grep -E '^($KEY_NAMES)=' $REMOTE_DIR/.env"; then
    die "droplet .env still carries plaintext key lines"
  fi
  echo "clean: droplet .env holds no plaintext key material"
}

case "${1:-}" in
  encrypt) shift; cmd_encrypt "$@" ;;
  deploy)  shift; cmd_deploy  "$@" ;;
  copy-ciphertext) shift; cmd_copy_ciphertext ;;
  check)   shift; cmd_check   "$@" ;;
  -h|--help|"") usage 0 ;;
  *) die "unknown mode: $1 (encrypt|deploy|check)" ;;
esac
