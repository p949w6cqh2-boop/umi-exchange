#!/usr/bin/env bash
# Brain ↔ STATE drift guard (C4 cadence) — REPORT-ONLY. Never fails the build.
#
# Compares umi-exchange/STATE.md (Lake 1's authoritative snapshot) against the
# Brain's last-reconciled copy. Drift just means "ground truth moved; a human
# should reconcile the Brain." After reconciling, refresh the snapshot:
#   cp <new STATE.md> cadence/drift-guard/STATE.snapshot.md  &&  git commit
#
# Config (env): UMI_EXCHANGE_REPO=owner/repo  (default below). For a PRIVATE
# Lake-1 repo, set GH_TOKEN to a read-only PAT with access to it.
set -uo pipefail

REPO="${UMI_EXCHANGE_REPO:-p949w6cqh2-boop/umi-exchange}"
BRANCH="${UMI_EXCHANGE_BRANCH:-main}"
SNAPSHOT="cadence/drift-guard/STATE.snapshot.md"
CURRENT="$(mktemp)"

# Fetch current STATE.md: prefer gh (handles private repos via GH_TOKEN), else raw URL.
if command -v gh >/dev/null 2>&1 && gh api "repos/$REPO/contents/STATE.md?ref=$BRANCH" \
      --jq '.content' 2>/dev/null | base64 -d > "$CURRENT" && [ -s "$CURRENT" ]; then
  :
elif curl -fsSL "https://raw.githubusercontent.com/$REPO/$BRANCH/STATE.md" -o "$CURRENT"; then
  :
else
  echo "::warning::drift-guard could not fetch STATE.md from $REPO@$BRANCH — skipping (report-only)."
  exit 0
fi

if diff -q "$SNAPSHOT" "$CURRENT" >/dev/null 2>&1; then
  echo "✅ No drift — the Brain's snapshot matches $REPO/STATE.md."
  exit 0
fi

echo "⚠️ DRIFT DETECTED — $REPO/STATE.md has changed since the Brain was last reconciled."
echo ""
echo "----- diff (Brain snapshot → current STATE.md) -----"
diff -u "$SNAPSHOT" "$CURRENT" || true
echo "----------------------------------------------------"
echo ""
echo "Action (Jasiah decides): review the diff, update the Brain's nodes to match,"
echo "then refresh the baseline:"
echo "    cp the new STATE.md to $SNAPSHOT  &&  git add + commit"
# Report-only: exit 0 so the scheduled run never 'fails'. Graduation to 'acting'
# (auto-open a sync PR) comes after 3 clean runs — see cadence/cadence.md.
exit 0
