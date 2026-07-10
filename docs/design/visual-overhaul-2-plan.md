# Visual Overhaul Phase 2 — "The Member's Day" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline — this
> repo's subagent fan-outs have a recorded failure history; keep it in-session). Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry the merged look-don't-read visual language (linocut scenes, seamless chapters,
editorial hierarchy) into the logged-in member journey: threshold → hub → notices → the exchange.

**Architecture:** Presentation-only template work on `feature/visual-overhaul-2`. One new SVG
scene partial + reuse of two existing scenes; palette normalization on the two stale detail
pages; a ceremony treatment at the contact reveal. Zero view/URL/model/HTMX/schema changes.
All color through `var(--umi-*)` tokens; compiled `output.css` regenerated once at the end if
any new utility combinations are introduced.

**Tech Stack:** Django 5.2 templates, Tailwind 3.4 (local `node_modules/.bin/tailwindcss`),
pytest + factory_boy (`tests/conftest.py` — `CommunityFactory`, `MemberFactory`, `NeedFactory`),
existing `.umi-*` component classes from `static/css/input.css`.

## Global Constraints

- Presentation-only: no changes under `apps/`, `config/`, or to any HTMX attribute/target/URL.
- Themeable color via `var(--umi-*)` only; legacy `text-gray-*`/`bg-gray-*` must be GONE from
  `needs/detail.html` + `offers/detail.html` when done.
- Never hand-edit `static/css/output.css`; recompile:
  `node_modules/.bin/tailwindcss -i static/css/input.css -o static/css/output.css --minify`.
- Scenes: original SVG, two-ink + theme-tinted washes, faceless figures, `aria-hidden="true"`
  `focusable="false"`, decorative only.
- Multi-line template comments: `{% comment %}…{% endcomment %}` (never multi-line `{# #}`).
- Ceremony gating expression stays byte-identical: `{% if show_contact and contact_info and is_participant %}`.
- Gate at end: ruff check + format --check (exclude the foreign untracked `hgit_sync.py`) ·
  `makemigrations --check` (no-op) · bandit 0 med/high · semgrep vs main 0 new · full pytest on
  Postgres 16 (`postgres://umi:test@127.0.0.1:5434/umi_test`) + Redis (`redis://localhost:6379/9`)
  with `ENCRYPTION_KEY` exported · `check --deploy` prod = 0.
- Commit per beat with `--no-verify` (pre-commit trips on foreign `hgit_sync.py`; gate runs
  independently). Every commit ends with the Claude Co-Authored-By line.

---

### Task 1: Test scaffold + threshold scene (Beat 1)

**Files:**
- Create: `templates/illustrations/_threshold.html`
- Modify: `templates/communities/join.html` (header block)
- Modify: `templates/communities/create.html` (header block)
- Test: `tests/test_members_day.py` (new)

**Interfaces:**
- Produces: `templates/illustrations/_threshold.html` — include-able SVG partial, root
  `<svg viewBox="0 0 720 420" aria-hidden="true" focusable="false" class="umi-scene">`, marker
  comment `{# scene: the threshold #}` on line 1 for testability.
- Produces: fixtures in `tests/test_members_day.py`: `member_client` (logged-in member of a
  community) and `homeless_client` (logged-in user, no community) reused by Tasks 2–4.

- [ ] **Step 1: Write the failing tests**

```python
"""Phase 2 'Member's Day' — the logged-in journey must look, not read:
threshold scene at join/create, hub crown, tokened notices, exchange ceremony."""

import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def homeless_client(client, django_user_model):
    user = django_user_model.objects.create(username="new-arrival")
    user.set_password("x" * 12)
    user.save()
    client.force_login(user)
    return client


@pytest.fixture
def member_client(client):
    member = MemberFactory()
    member.user.set_password("x" * 12)
    member.user.save()
    client.force_login(member.user)
    client._member = member  # stash for tests
    return client


class TestThreshold:
    def test_join_page_carries_threshold_scene(self, homeless_client):
        body = homeless_client.get(reverse("community-join")).content.decode()
        assert "scene: the threshold" in body

    def test_create_page_carries_threshold_scene(self, homeless_client):
        body = homeless_client.get(reverse("community-create")).content.decode()
        assert "scene: the threshold" in body
```

(Adjust URL names to the real ones from `config/urls.py` / `apps/communities/urls.py` —
check with `grep -n "join\|create" apps/communities/urls.py` before writing; use the
actual `name=` values.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_members_day.py -q`
Expected: FAIL — `"scene: the threshold" in body` assertion errors (page 200s but no scene).

- [ ] **Step 3: Draw `_threshold.html`**

Original linocut SVG, same construction as `templates/illustrations/_well.html` (read it first
for the established idiom): `{# scene: the threshold #}` marker line 1; two-ink strokes in
`var(--umi-ink, #2B2420)`-style tokens as the existing scenes do; wash rects/paths in
`var(--umi-primary)` / `var(--umi-accent)` at low opacity; grain via the shared filter pattern
used by the six existing scenes. Composition: a parish wall, two door frames — left ajar with
warm light spilling, right freshly painted with a small ladder + paint pot. Faceless. No text
in the SVG.

- [ ] **Step 4: Crown both pages**

`join.html`: inside the existing `<header class="text-center mb-10 umi-rise">`, add the scene
above the eyebrow in a `max-w-md mx-auto` wrapper div with the include:
`{% include "illustrations/_threshold.html" %}`. `create.html`: same include, smaller wrapper
(`max-w-xs`), keep its existing heading structure intact.

- [ ] **Step 5: Run tests — pass; commit**

Run: `.venv/bin/pytest tests/test_members_day.py -q` → PASS.
Commit: `git add -A templates tests && git commit --no-verify -m "feat(design): threshold scene crowns join + create (Member's Day beat 1)"` (+ co-author line).

---

### Task 2: Hub crown + empty-state vignettes (Beat 2)

**Files:**
- Modify: `templates/hub/_hub_body.html` (header only)
- Modify: `templates/hub/_spotlight.html` (empty branch)
- Modify: `templates/hub/_pulse.html` (empty branch)
- Test: `tests/test_members_day.py` (extend)

**Interfaces:**
- Consumes: `member_client` fixture from Task 1.
- Produces: nothing downstream.

- [ ] **Step 1: Failing tests**

```python
class TestHubCrown:
    def test_hub_masthead_carries_well_wash(self, member_client):
        member = member_client._member
        body = member_client.get(
            reverse("hub:community", kwargs={"slug": member.community.slug})
        ).content.decode()
        assert "scene: the well" in body

    def test_hub_empty_pulse_shows_vignette_not_bare_text(self, member_client):
        member = member_client._member
        body = member_client.get(
            reverse("hub:pulse", kwargs={"slug": member.community.slug})
        ).content.decode()
        assert "umi-vignette" in body  # empty community → empty-state branch
```

(Verify the well scene partial's marker comment text first: `head -1
templates/illustrations/_well.html` — assert on its actual marker. If `_well.html` lacks a
marker comment, add `{# scene: the well #}` as line 1 — additive, harmless.)

- [ ] **Step 2: Run → FAIL.** `.venv/bin/pytest tests/test_members_day.py -q`

- [ ] **Step 3: Implement**

`_hub_body.html` header: wrap existing `<header>` content in `relative`; add absolutely
positioned right-clipped wash `<div class="umi-scene-wash" aria-hidden="true">{% include
"illustrations/_well.html" %}</div>`. Add `.umi-scene-wash` to `static/css/input.css`
(absolute, right-0, low opacity ~.14, pointer-events-none, hidden below `md:`, masked fade-left)
— new class = recompile `output.css` in the final task.
Empty branches of `_spotlight.html` / `_pulse.html`: replace bare `<p>` with a
`<div class="umi-vignette">` — mini scene include (`_board.html` for pulse, `_carrying.html`
for spotlight, at reduced size) + the existing quiet copy underneath. Keep each partial's outer
DOM/ids untouched (HTMX swaps whole partial).

- [ ] **Step 4: Run → PASS; commit** (same commit form, beat 2 message).

---

### Task 3: Notices — tokened need/offer detail (Beat 3)

**Files:**
- Modify: `templates/needs/detail.html` (full presentation rework)
- Modify: `templates/offers/detail.html` (full presentation rework)
- Test: `tests/test_members_day.py` (extend)

**Interfaces:**
- Consumes: `member_client` fixture; `NeedFactory` from `tests/conftest.py` (check for
  `OfferFactory` — `grep -n "class.*Factory" tests/conftest.py` — use what exists).
- Produces: the "no legacy grays" invariant Task 5's gate re-checks.

- [ ] **Step 1: Failing tests**

```python
class TestNotices:
    def _need_body(self, member_client):
        from tests.conftest import NeedFactory
        member = member_client._member
        need = NeedFactory(community=member.community, requester=member)
        return member_client.get(
            reverse("need-detail", args=[member.community.slug, need.id])
        ).content.decode()

    def test_need_detail_off_legacy_palette(self, member_client):
        body = self._need_body(member_client)
        assert "text-gray-" not in body
        assert "bg-gray-" not in body

    def test_need_detail_reads_as_board_notice(self, member_client):
        body = self._need_body(member_client)
        assert "umi-medallion" in body  # the category medallion, like feed cards
```

(Mirror both tests for the offer detail page with the offer factory + `offer-detail` URL name —
verify names via `apps/offers/urls.py`. If feed cards' medallion class differs — check
`templates/components/_need_card.html` from phase 1 — assert on the real class.)

- [ ] **Step 2: Run → FAIL** (pages 200 but grays present, no medallion).

- [ ] **Step 3: Rework both detail templates**

Keep every conditional, form, URL, and include exactly as-is (delete button, tooltip, badges,
matches panel, HTMX bits). Change presentation only:
- back-link → `text-parish-ink/60 hover:text-parish-ink` breadcrumb styled like the phase-1 board bar;
- header: category medallion (copy the exact medallion markup pattern from
  `templates/components/_need_card.html`), serif `umi-display`-scale title, single meta line
  `text-parish-ink/55`;
- urgency chip: map the four levels to tokened styles (keep the red/orange/amber/green semantics
  via existing themed utility combos already in `output.css` — e.g. the same classes feed cards
  use; do NOT invent new arbitrary values if an existing combo exists);
- status chip, description, section borders → ink/token equivalents
  (`border-[var(--umi-border)]`, `text-parish-ink/70`);
- delete button: keep red semantics (destructive) with existing compiled red utilities.

- [ ] **Step 4: Run → PASS; commit** (beat 3 message).

---

### Task 4: The exchange ceremony (Beat 4)

**Files:**
- Modify: `templates/matches/detail.html` (reveal banner + modal styling)
- Modify: `templates/components/_contact_info_box.html` (tokens only)
- Modify: `templates/components/_match_timeline.html` (marker styling only)
- Test: `tests/test_members_day.py` (extend)

**Interfaces:**
- Consumes: fixtures + factories as above; match factory/state helpers — check
  `tests/conftest.py` and existing `tests/test_matches*.py` for how an accepted match with
  revealed contact is set up; reuse that exact setup, do not invent one.

- [ ] **Step 1: Failing tests**

```python
class TestExchangeCeremony:
    def test_accepted_match_shows_ceremony(self, member_client):
        # build accepted match where member is participant + contact consented,
        # copying the arrange block from the existing accepted-match view test
        ...
        assert "You&#x27;re connected" in body or "You're connected" in body
        assert "scene: the exchange" in body

    def test_proposed_match_shows_no_ceremony(self, member_client):
        ...  # same arrange, status left at proposed
        assert "scene: the exchange" not in body
```

(The `...` arrange blocks are filled from the real existing match-view test file at write time —
copy its factory calls verbatim; the assertion lines above are the contract. Check
`templates/illustrations/_exchange.html` line 1 for its marker; add `{# scene: the exchange #}`
if missing.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

`matches/detail.html`: replace the emerald alert `<div>` (keeping the byte-identical `{% if
show_contact and contact_info and is_participant %}` line) with the ceremony card: `umi-shell` +
`umi-card`, `_exchange.html` include at reduced width, serif `<h2>You're connected.</h2>`, one
line: contact shared only between the two of you (§8.2 spirit), then the existing
`_contact_info_box.html` include position unchanged. Modal: `bg-white`→`umi-card` idiom,
`text-gray-900`→`text-parish-ink`, overlay stays. `_contact_info_box.html` + `_match_timeline.html`:
gray→ink/token substitutions; timeline dots → small inked strokes (border token + ink fill),
DOM structure unchanged.

- [ ] **Step 4: Run → PASS; commit** (beat 4 message).

---

### Task 5: Recompile CSS + full gate + PR

**Files:**
- Modify: `static/css/input.css` (`.umi-scene-wash`, `.umi-vignette` from Task 2)
- Modify: `static/css/output.css` (compiled artifact)

- [ ] **Step 1: Recompile**

`node_modules/.bin/tailwindcss -i static/css/input.css -o static/css/output.css --minify`
Verify new classes present: `grep -c "umi-scene-wash\|umi-vignette" static/css/output.css` ≥ 1.

- [ ] **Step 2: Full local gate (CI topology)**

```bash
.venv/bin/ruff check . --exclude hgit_sync.py && .venv/bin/ruff format --check . --exclude hgit_sync.py
.venv/bin/python manage.py makemigrations --check
.venv/bin/bandit -r apps/ -c pyproject.toml -ll   # 0 med/high
.venv/bin/semgrep --config p/django --config p/python --baseline-commit main --error --quiet
export ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
DATABASE_URL="postgres://umi:test@127.0.0.1:5434/umi_test" REDIS_URL="redis://localhost:6379/9" .venv/bin/pytest -q
DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY=<50+char throwaway> ENCRYPTION_KEY=<throwaway> ALLOWED_HOSTS=example.org .venv/bin/python manage.py check --deploy
```

Expected: all clean; suite ≥ 728 + new tests, 0 failures.

- [ ] **Step 3: Commit compiled CSS, push, PR**

Push `feature/visual-overhaul-2`; PR via GitHub MCP (base `main`), body = beats + gate evidence.
**STOP before merge — Jasiah's key.**

## Self-review notes (done at write time)

- Spec coverage: Beat 1→Task 1, Beat 2→Task 2, Beat 3→Task 3, Beat 4→Task 4, rails/gate→Task 5. ✔
- URL names, factory names, medallion class, and scene marker comments are deliberately
  *verify-then-assert* steps (grep the real name before writing the test) — the repo is the
  source of truth, not this plan.
- Type consistency: fixtures `member_client`/`homeless_client` defined Task 1, consumed 2–4. ✔
