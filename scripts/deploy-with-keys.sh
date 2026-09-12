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
#   encrypt <plaintext-env-file>   age-encrypt key material -> $UMI_KEYS_AGE
#   deploy                         decrypt -> ssh -> tmpfs merge -> compose up -> shred
#   check                          prove the droplet .env holds no plaintext keys
#   check --local-file <file>      same proof against a local file (used by tests)
#
# Config (env, all optional):
#   UMI_AGE_IDENTITY   age identity file        (default ~/.config/umi/age-identity.txt)
#   UMI_AGE_RECIPIENTS age recipients file      (default ~/.config/umi/age-recipients.txt)
#   UMI_KEYS_AGE       ciphertext path          (default ~/.config/umi/keys.env.age)
#   UMI_DROPLET        ssh target               (REQUIRED for deploy/check — no default)
#   UMI_REMOTE_DIR     compose dir on droplet   (default /opt/umi-exchange)
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
COMPOSE="docker compose --env-file /dev/shm/umi-full.env -f docker/docker-compose.prod.yml"

# The names that must never sit in plaintext on the droplet (key-custody design).
KEY_NAMES='ENCRYPTION_KEYS?|BLIND_INDEX_KEY|SECRET_KEY'

die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
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
  age -e -R "$RECIPIENTS" -o "$KEYS_AGE" < "$plain"
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
  local remote_script
  remote_script=$(cat <<REMOTE
set -euo pipefail
umask 077
cat > /dev/shm/umi-keys.env
cd $REMOTE_DIR
grep -Eq '^($KEY_NAMES)=' .env && { echo 'REFUSING: droplet .env still carries plaintext key lines — finish the migration (docs/key-custody-design.md)'; shred -u /dev/shm/umi-keys.env; exit 1; }
cat .env /dev/shm/umi-keys.env > /dev/shm/umi-full.env
$COMPOSE up -d app
$COMPOSE ps app
shred -u /dev/shm/umi-keys.env /dev/shm/umi-full.env
echo 'tmpfs shredded; deploy done'
REMOTE
)

  if [ "${DRY_RUN:-0}" = "1" ]; then
    echo "== DRY RUN: would decrypt $KEYS_AGE with $IDENTITY and pipe it to the STDIN of: ssh $DROPLET bash -c <the script below> =="
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
  check)   shift; cmd_check   "$@" ;;
  -h|--help|"") usage 0 ;;
  *) die "unknown mode: $1 (encrypt|deploy|check)" ;;
esac
