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
#   UMI_DROPLET        ssh target               (default root@143.244.167.7)
#   UMI_REMOTE_DIR     compose dir on droplet   (default /opt/umi-exchange)
#   DRY_RUN=1          print the plan, run nothing remote

set -euo pipefail

CONF_HOME="${HOME:-/nonexistent}"
IDENTITY="${UMI_AGE_IDENTITY:-$CONF_HOME/.config/umi/age-identity.txt}"
RECIPIENTS="${UMI_AGE_RECIPIENTS:-$CONF_HOME/.config/umi/age-recipients.txt}"
KEYS_AGE="${UMI_KEYS_AGE:-$CONF_HOME/.config/umi/keys.env.age}"
DROPLET="${UMI_DROPLET:-root@143.244.167.7}"
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
    echo "== DRY RUN: would decrypt $KEYS_AGE with $IDENTITY and pipe into: ssh $DROPLET bash -s =="
    echo "$remote_script"
    return 0
  fi

  age -d -i "$IDENTITY" "$KEYS_AGE" | ssh "$DROPLET" "bash -s" <<< "$remote_script" \
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
