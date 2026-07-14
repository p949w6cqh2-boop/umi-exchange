# Demo walkthrough — showing UMI Exchange to Father Mac

The board, alive and in hand. Eight screens at phone width (390px), in the order to demo them.
Everything below is the fictional St. Brigid's — no real people, no real parish specifics.

## Before the demo (five minutes)

```bash
# 1. Seed the fictional parish (idempotent; refuses to run in production)
python manage.py seed_demo_parish

# 2. Run the demo server with the real error pages (no Django debug screens)
DEBUG=0 python manage.py collectstatic --noinput
DEBUG=0 python manage.py runserver
```

Sign-ins (password `demo-parish` for all): **marta** (admin) · **tomas** (coordinator) ·
**nuala** (member).

## The demo, in order

Hand the phone over at step 3 — the hub is the screen that sells it.

### 1. The landing page — what a visitor sees
"Need a hand? Lend one." A quiet notice-board, and the door in.

![Landing](demo/01-landing.webp)

### 2. Two doors — join with a code, or start a board
The threshold print above the choice every parish makes once.

![Join](demo/02-join.webp)

### 3. The hub — a living parish
Nuala's morning: a greeting by name, one ask in the spotlight, the pulse of the week below.

![Hub](demo/03-hub.webp)

### 4. Posting an ask — a line or two is plenty
Categories as pictures, urgency in plain words, and the promise printed right on the form:
nothing about you is shared until you accept a match.

![Post an ask](demo/04-post-ask.webp)

### 5. The board — asks and offers side by side
Bread-and-butter mutual aid: a lift to Mass, two extra dinners, a retired teacher.

![The board](demo/05-board.webp)

### 6. One ask, up close
Nuala's lift to half-nine Mass — and Dan's offer already waiting beside it.

![Ask detail](demo/06-ask-detail.webp)

### 7. A match on the table
The coordinator proposed; both sides get a plain yes/no. Nothing is revealed yet.

![Match](demo/07-match.webp)

### 8. The connect — the reason all of this exists
Both said yes. The page settles, warms, and shares contact between the two of them alone.

![Connected](demo/08-connected.webp)

## If Father Mac pokes around

- A typo'd address gets the warm 404, not an error dump (that's why the demo runs `DEBUG=0`).
- A member opening a coordinators-only page gets a polite 403 in the same style.
- Empty screens invite the first action instead of apologising — notifications, resources,
  the tag queue, and a brand-new community all have warm empty states.

## Accessibility note

Focus rings, reduced-motion, and AA contrast are built into the design system (see DESIGN.md's
verified contrast table). An automated axe pass wasn't run for this gallery — the toolchain
isn't installed offline; screens were checked by eye against the token contrast table.
