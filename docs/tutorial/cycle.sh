#!/bin/bash
# One recording cycle: fresh scratch DB -> seed -> ids -> server -> record one aspect -> teardown.
mkdir -p /tmp/tutorial-work
set -o pipefail
NODE_DEBUG_VAL="${DEBUG:-}"
unset DEBUG
set -e
cd /home/umi/umi-exchange
ASPECT="$1"
# A leaked server from a crashed cycle silently absorbs all traffic (stale DB,
# saturated in-memory rate counters). Clear the port first, always.
pkill -f "runserver 8123" 2>/dev/null || true
sleep 1
SCRATCH=/tmp/tutorial-work/tutorial-scratch.sqlite3
rm -f "$SCRATCH"
DEBUG=1 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py migrate --verbosity 0
DEBUG=1 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py seed_demo_parish | tail -1
DEBUG=1 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py shell <<'PY' | grep ^export > /tmp/tutorial-work/tutorial-ids.env
from apps.needs.models import Need
from apps.matches.models import Match
lift = Need.objects.get(title__contains="9:30 Mass")
print(f"export LIFT={lift.id}")
print(f"export PROPOSED={Match.objects.get(need=lift).id}")
PY
DEBUG=0 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py runserver 8123 --noreload > "/tmp/tutorial-work/cycle-server.log" 2>&1 &
SPID=$!
trap 'kill $SPID 2>/dev/null || true' EXIT
# Verify OUR server owns the port before recording a single frame.
for i in $(seq 1 10); do
  sleep 1
  if ! kill -0 $SPID 2>/dev/null; then echo "FATAL: runserver died at boot (port busy?)"; exit 1; fi
  curl -sf -o /dev/null http://127.0.0.1:8123/health/ && break
  [ "$i" = 10 ] && { echo "FATAL: server never became healthy"; exit 1; }
done
source /tmp/tutorial-work/tutorial-ids.env
# Login is throttled 5/min/IP and consecutive cycles share the window; a retried
# on-camera login ruins the S3 take. Guarantee a clear window before recording.
MARK=/tmp/tutorial-work/.last-cycle-start
NOW=$(date +%s); LAST=$(cat "$MARK" 2>/dev/null || echo 0); GAP=$(( NOW - LAST ))
if [ "$GAP" -lt 61 ]; then echo "throttle-window guard: sleeping $(( 61 - GAP ))s"; sleep $(( 61 - GAP )); fi
date +%s > "$MARK"
echo "cycle start: $(date +%T) aspect=$ASPECT ${2:+scene=$2}"
DEBUG="$NODE_DEBUG_VAL" node docs/tutorial/record-tutorial.mjs "$ASPECT" ${2:+--scene=$2}
RC=$?
date +%s > "$MARK"
echo "cycle end:   $(date +%T) rc=$RC"
kill $SPID 2>/dev/null || true
exit $RC
