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
# Version 2 (SET=v2) stages what its scenes need before the camera rolls, on the scratch DB
# only: an invented 555-01xx number on Joe for the call-back scene. COMMUNION=1 (its own
# cycle, the two v2-16 scenes only) adds Aggie's number and an accepted Communion at home
# match, moved there through the model's own transition_to (never a raw status write). It
# gets its own cycle because an accepted match tops every hub feed, and the Communion
# chapter waits on a priest's read: it must not ride into the core scenes or the Shorts.
if [ "${SET:-}" = "v2" ]; then
DEBUG=1 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
from apps.offers.models import Offer

users = get_user_model().objects
joe = users.get(username="joe")
joe.phone = "555-0144"
joe.save(update_fields=["phone"])
# The connect scene's payoff: every seeded offer keeps the form's default, "in the app", so
# the reveal opened onto no contact at all. Dan chooses phone, as the offer form lets anyone.
dan = users.get(username="dan")
dan.phone = "555-0131"
dan.save(update_fields=["phone"])
changed = Offer.objects.filter(offerer__user=dan, title="I can drive Sunday mornings").update(contact_pref="phone")
assert changed == 1, f"expected Dan's one ride offer, changed {changed}"
PY
fi
if [ "${SET:-}" = "v2" ] && [ "${COMMUNION:-}" = "1" ]; then
DEBUG=1 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py shell <<'PY' | grep ^export >> /tmp/tutorial-work/tutorial-ids.env
from django.contrib.auth import get_user_model
from apps.communities.models import Category, Community, Member
from apps.matches.models import Match
from apps.needs.models import Need

parish = Community.objects.get(slug="st-brigids")
aggie_user = get_user_model().objects.get(username="aggie")
aggie_user.phone = "555-0172"
aggie_user.save(update_fields=["phone"])
aggie = Member.objects.get(community=parish, user__username="aggie")
frank = Member.objects.get(community=parish, user__username="frank")
need = Need.objects.create(
    community=parish,
    requester=aggie,
    category=Category.objects.get(community=parish, name="Communion at home"),
    title="Communion at home on Sundays",
    description="I can't get to Mass these days. A visit on a Sunday afternoon would mean a lot.",
)
match = Match.objects.create(need=need, proposed_by=frank)
match.transition_to("accepted")
match.refresh_from_db()
assert match.status == "accepted", match.status
print(f"export COMMUNION_MATCH={match.id}")
PY
grep -q '^export COMMUNION_MATCH=' /tmp/tutorial-work/tutorial-ids.env || { echo "FATAL: v2 staging exported no COMMUNION_MATCH"; exit 1; }
fi
# IDLE=<seconds> starts the server with a short idle sign-out, for the "Still there?" scene only.
# --insecure serves /static/ from the source tree, ahead of WhiteNoise. Without it a DEBUG=0
# server serves the collected staticfiles/ folder, which nothing here refreshes: on 2026-10-06
# it held the stylesheet collected 2026-08-05 and none of the eye, idle or reCAPTCHA scripts,
# so every recording since August showed an August look with today's pages.
env ${IDLE:+SESSION_IDLE_TIMEOUT_SECONDS=$IDLE} DEBUG=0 DATABASE_URL="sqlite:///$SCRATCH" .venv/bin/python manage.py runserver 8123 --noreload --insecure > "/tmp/tutorial-work/cycle-server.log" 2>&1 &
SPID=$!
trap 'kill $SPID 2>/dev/null || true' EXIT
# Verify OUR server owns the port before recording a single frame.
for i in $(seq 1 10); do
  sleep 1
  if ! kill -0 $SPID 2>/dev/null; then echo "FATAL: runserver died at boot (port busy?)"; exit 1; fi
  curl -sf -o /dev/null http://127.0.0.1:8123/health/ && break
  [ "$i" = 10 ] && { echo "FATAL: server never became healthy"; exit 1; }
done
# The page's own scripts must be the current ones (the eye, the idle warning), or the
# footage shows a board that no longer exists. Fail before a frame is recorded.
for js in password-toggle.js idle-timeout.js; do
  cmp -s <(curl -sf "http://127.0.0.1:8123/static/js/$js") "static/js/$js" \
    || { echo "FATAL: /static/js/$js is not the current source file"; exit 1; }
done
source /tmp/tutorial-work/tutorial-ids.env
# Login is throttled 5/min/IP and consecutive cycles share the window; a retried
# on-camera login ruins the S3 take. Guarantee a clear window before recording.
MARK=/tmp/tutorial-work/.last-cycle-start
NOW=$(date +%s); LAST=$(cat "$MARK" 2>/dev/null || echo 0); GAP=$(( NOW - LAST ))
if [ "$GAP" -lt 61 ]; then echo "throttle-window guard: sleeping $(( 61 - GAP ))s"; sleep $(( 61 - GAP )); fi
date +%s > "$MARK"
echo "cycle start: $(date +%T) aspect=$ASPECT ${SET:+set=$SET} ${2:+scene=$2} ${IDLE:+idle=${IDLE}s}"
DEBUG="$NODE_DEBUG_VAL" node docs/tutorial/record-tutorial.mjs "$ASPECT" ${SET:+--set=$SET} ${2:+--scene=$2}
RC=$?
date +%s > "$MARK"
echo "cycle end:   $(date +%T) rc=$RC"
kill $SPID 2>/dev/null || true
exit $RC
