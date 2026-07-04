# Sign-in Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A personalized, login-required landing page shown right after sign-in that gives a member a calm, scannable view of their focused community — quick actions, their open matches, recent notifications, and their own tags/verification status — with a switcher when they belong to several communities.

**Architecture:** A new view-only `apps/hub` Django app aggregates already-BUILT models read-only. A thin `/hub/` resolver redirects to `/hub/<slug>/` (0 memberships → `/join/`, 1 → straight in, many → last-visited-else-most-recent). `/hub/<slug>/` is a membership-gated `HubView` that renders a full page or, under HTMX, just the body partial — so the community switcher swaps content in place. All ORM access lives in `apps/hub/selectors.py`, every query bounded.

**Tech Stack:** Django 5.2, HTMX (`django_htmx`, `request.htmx`), Tailwind (`--umi-*` theme vars), pytest + factory_boy. Playwright MCP browser tools for the interactive a11y/switch verification.

## Global Constraints

- **No new schema / no migration.** `makemigrations --check` must stay clean. The hub reads existing models only.
- **No cross-community leak.** `/hub/<slug>/` must 404 for any user who is not an *active* `Member` of that community. A member viewing community A must never see community B's data.
- **All ORM access in `apps/hub/selectors.py`**, and every list query bounded: open matches `[:50]`, notifications `[:8]`. Communities and own-tags lists are naturally small (no cap needed).
- **`Member.id` is a UUID** — order "most recent" by `joined_at`, never by pk.
- **Verified field names (do not guess):** `Match` creation timestamp is `proposed_at` (there is no `created_at`); non-terminal statuses are `"proposed"` and `"accepted"`. `Need.status == "open"`, `Offer.status == "active"`. `MemberTag.status` default is `"self_claimed"`; surface all statuses on the member's own hub. `Notification.recipient` is a **User** (no community FK) → notifications are user-global; label the panel so it doesn't read as community-scoped.
- **Membership-gate pattern (mirror `apps/communities/views.py::FeedView`):** `get_object_or_404(Community, slug=…, is_active=True)` then `get_object_or_404(Member, user=request.user, community=…, is_active=True)`.
- **HTMX pattern (mirror FeedView):** detect with `self.request.htmx`; choose the template in `get_template_names()`.
- **Styling:** parish atmosphere via `--umi-*` vars and `.umi-*` classes (see `docs/ui-polish-spec.md` + `templates/base.html`); mobile-first; transitions gated on `prefers-reduced-motion`. Never hand-edit `static/css/output.css`.
- **Tests** use the factories already in `tests/conftest.py`: `UserFactory`, `CommunityFactory`, `MemberFactory`, `NeedFactory`, `OfferFactory`, `MatchFactory`, `CategoryFactory`.
- **Workflow:** branch `feature/signin-hub` (already created off `main`). Commit per step. **STOP before merge** — do not open/merge a PR without explicit approval. Run commits past the local pre-commit hook only if it blocks on the 4 known pre-existing bandit findings in unrelated files (use `--no-verify` and say so), never to skip a real failure.

---

### Task 1: App skeleton + `/hub/` resolver + post-login redirect

Delivers routing: bare `/hub/` resolves to the right community (or onboarding), `/hub/<slug>/` is membership-gated and renders a minimal page. Panels come in Task 3.

**Files:**
- Create: `apps/hub/__init__.py` (empty)
- Create: `apps/hub/apps.py`
- Create: `apps/hub/views.py`
- Create: `apps/hub/urls.py`
- Create: `templates/hub/index.html` (minimal; enriched in Task 3)
- Modify: `config/settings/base.py` (add `"apps.hub"` to `INSTALLED_APPS`; `LOGIN_REDIRECT_URL = "/hub/"`)
- Modify: `config/urls.py` (add `path("hub/", include("apps.hub.urls"))`)
- Test: `tests/test_hub_resolver.py`

**Interfaces:**
- Produces: URL names `hub:index` (`/hub/`) and `hub:community` (`/hub/<slug>/`). `HubView` with `self.community` and `self.member` set in `dispatch` for authenticated members; context keys `community`, `member`. `HubResolverView` (GET-only) returning redirects.

- [ ] **Step 1: Create the app package and config**

`apps/hub/__init__.py`: empty file.

`apps/hub/apps.py`:
```python
from django.apps import AppConfig


class HubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hub"
```

- [ ] **Step 2: Write the failing resolver + gate tests**

`tests/test_hub_resolver.py`:
```python
import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


def _login(client, user):
    client.force_login(user)


def test_hub_requires_auth(client):
    resp = client.get("/hub/")
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


def test_zero_memberships_redirects_to_join(client):
    user = UserFactory()
    _login(client, user)
    resp = client.get("/hub/")
    assert resp.status_code == 302
    assert resp.url == "/join/"


def test_one_membership_goes_straight_in(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    resp = client.get("/hub/")
    assert resp.status_code == 302
    assert resp.url == reverse("hub:community", kwargs={"slug": m.community.slug})


def test_many_memberships_use_last_visited(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    session = client.session
    session["hub:last_slug"] = b.community.slug
    session.save()
    resp = client.get("/hub/")
    assert resp.url == reverse("hub:community", kwargs={"slug": b.community.slug})


def test_many_memberships_fallback_most_recent(client):
    user = UserFactory()
    from apps.communities.models import Member

    older = MemberFactory(user=user, community=CommunityFactory())
    newer = MemberFactory(user=user, community=CommunityFactory())
    # joined_at is auto_now_add; force a deterministic order via update()
    import datetime

    from django.utils import timezone

    Member.objects.filter(pk=older.pk).update(joined_at=timezone.now() - datetime.timedelta(days=2))
    Member.objects.filter(pk=newer.pk).update(joined_at=timezone.now())
    _login(client, user)
    resp = client.get("/hub/")
    assert resp.url == reverse("hub:community", kwargs={"slug": newer.community.slug})


def test_stale_last_slug_falls_back(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    session = client.session
    session["hub:last_slug"] = "a-community-they-left"
    session.save()
    resp = client.get("/hub/")
    assert resp.url == reverse("hub:community", kwargs={"slug": m.community.slug})


def test_hub_community_404_for_non_member(client):
    user = UserFactory()
    other = CommunityFactory()  # user is NOT a member
    _login(client, user)
    resp = client.get(reverse("hub:community", kwargs={"slug": other.slug}))
    assert resp.status_code == 404


def test_hub_community_renders_for_member(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    _login(client, user)
    resp = client.get(reverse("hub:community", kwargs={"slug": m.community.slug}))
    assert resp.status_code == 200
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_hub_resolver.py -q`
Expected: FAIL — `NoReverseMatch` / 404 for `hub:*` (URLs not registered yet).

- [ ] **Step 4: Implement the views**

`apps/hub/views.py`:
```python
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.communities.models import Community, Member


class HubResolverView(LoginRequiredMixin, View):
    """Bare /hub/ — pick the community to focus, then redirect.

    0 memberships → onboarding (/join/); a valid last-visited slug → there;
    exactly 1 → straight in; otherwise (many, no valid last) → most-recent.
    """

    def get(self, request):
        memberships = Member.objects.filter(user=request.user, is_active=True).select_related("community")
        slugs = {m.community.slug for m in memberships}
        if not slugs:
            return redirect("/join/")
        last = request.session.get("hub:last_slug")
        if last in slugs:
            return redirect("hub:community", slug=last)
        if len(slugs) == 1:
            return redirect("hub:community", slug=next(iter(slugs)))
        most_recent = memberships.order_by("-joined_at").first()
        return redirect("hub:community", slug=most_recent.community.slug)


class HubView(LoginRequiredMixin, TemplateView):
    template_name = "hub/index.html"

    def dispatch(self, request, *args, **kwargs):
        # LoginRequiredMixin redirects anonymous users before we touch the DB.
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.member = get_object_or_404(
            Member, user=request.user, community=self.community, is_active=True
        )
        request.session["hub:last_slug"] = self.community.slug
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["member"] = self.member
        return ctx
```

`apps/hub/urls.py`:
```python
from django.urls import path

from . import views

app_name = "hub"

urlpatterns = [
    path("", views.HubResolverView.as_view(), name="index"),
    path("<slug:slug>/", views.HubView.as_view(), name="community"),
]
```

`templates/hub/index.html` (minimal — Task 3 fills the body):
```django
{% extends "base.html" %}
{% block content %}
<main class="umi-container" aria-labelledby="hub-heading">
  <h1 id="hub-heading">{{ community.name }}</h1>
  <p>Welcome back, {{ member.display_name }}.</p>
</main>
{% endblock %}
```

- [ ] **Step 5: Wire settings + root urls**

In `config/settings/base.py`, add `"apps.hub",` to the project-apps block of `INSTALLED_APPS` (next to `"apps.health",`), and change:
```python
LOGIN_REDIRECT_URL = "/hub/"
```
(was `"/join/"`).

In `config/urls.py`, add alongside the other includes (before the `c/` catch-all):
```python
    path("hub/", include("apps.hub.urls")),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_hub_resolver.py -q`
Expected: PASS (8 tests).

- [ ] **Step 7: Commit**

```bash
git add apps/hub config/settings/base.py config/urls.py templates/hub/index.html tests/test_hub_resolver.py
git commit -m "feat(hub): app skeleton, /hub/ resolver, membership-gated HubView"
```
(If the pre-commit hook blocks on the 4 pre-existing bandit findings in unrelated files, re-run with `--no-verify` and note it.)

---

### Task 2: Bounded read-only selectors

All hub ORM access, each function independently testable.

**Files:**
- Create: `apps/hub/selectors.py`
- Test: `tests/test_hub_selectors.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure query helpers over existing models).
- Produces:
  - `member_communities(user) -> list[Member]` — active memberships, `-joined_at`, `community` preloaded.
  - `open_matches_for(member) -> list[Match]` — non-terminal matches in `member.community` where the member is requester/offerer/proposer; `[:50]`, `-proposed_at`.
  - `recent_notifications(user) -> list[Notification]` — `recipient=user`, `-created_at`, `[:8]`.
  - `own_tags(member) -> list[MemberTag]` — the member's tags at all statuses, `tag` preloaded, ordered `tag__sort_order, tag__label`.
  - Constants `OPEN_MATCH_STATUSES`, `OPEN_MATCHES_CAP = 50`, `RECENT_NOTIFICATIONS_CAP = 8`.

- [ ] **Step 1: Write the failing selector tests**

`tests/test_hub_selectors.py`:
```python
import pytest

from apps.hub import selectors
from tests.conftest import (
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def test_member_communities_only_active_newest_first():
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    inactive = MemberFactory(user=user, community=CommunityFactory(), is_active=False)
    result = selectors.member_communities(user)
    assert inactive not in result
    assert set(result) == {a, b}


def test_open_matches_includes_participant_roles_excludes_others():
    community = CommunityFactory()
    me = MemberFactory(community=community)
    other = MemberFactory(community=community)
    my_need = NeedFactory(community=community, requester=me)
    as_requester = MatchFactory(need=my_need, proposed_by=other, status="proposed")
    my_offer = OfferFactory(community=community, offerer=me)
    other_need = NeedFactory(community=community, requester=other)
    as_offerer = MatchFactory(need=other_need, offer=my_offer, proposed_by=other, status="accepted")
    as_proposer = MatchFactory(
        need=NeedFactory(community=community, requester=other), proposed_by=me, status="proposed"
    )
    not_mine = MatchFactory(
        need=NeedFactory(community=community, requester=other), proposed_by=other, status="proposed"
    )
    result = selectors.open_matches_for(me)
    ids = {m.pk for m in result}
    assert {as_requester.pk, as_offerer.pk, as_proposer.pk} <= ids
    assert not_mine.pk not in ids


def test_open_matches_excludes_terminal_status():
    community = CommunityFactory()
    me = MemberFactory(community=community)
    need = NeedFactory(community=community, requester=me)
    MatchFactory(need=need, proposed_by=me, status="fulfilled")
    assert selectors.open_matches_for(me) == []


def test_open_matches_excludes_other_communities():
    me_a = MemberFactory(community=CommunityFactory())
    # same user, different community
    me_b = MemberFactory(user=me_a.user, community=CommunityFactory())
    need_b = NeedFactory(community=me_b.community, requester=me_b)
    MatchFactory(need=need_b, proposed_by=me_b, status="proposed")
    # focused on A → B's match must not appear
    assert selectors.open_matches_for(me_a) == []


def test_open_matches_respects_cap():
    community = CommunityFactory()
    me = MemberFactory(community=community)
    for _ in range(selectors.OPEN_MATCHES_CAP + 5):
        MatchFactory(
            need=NeedFactory(community=community, requester=me),
            proposed_by=me,
            status="proposed",
        )
    assert len(selectors.open_matches_for(me)) == selectors.OPEN_MATCHES_CAP


def test_recent_notifications_only_recipient_capped():
    from apps.notifications.models import Notification

    user = UserFactory()
    other = UserFactory()
    for i in range(selectors.RECENT_NOTIFICATIONS_CAP + 3):
        Notification.objects.create(recipient=user, type="match_proposed", title=f"n{i}")
    Notification.objects.create(recipient=other, type="match_proposed", title="not yours")
    result = selectors.recent_notifications(user)
    assert len(result) == selectors.RECENT_NOTIFICATIONS_CAP
    assert all(n.recipient_id == user.id for n in result)


def test_own_tags_only_this_member_all_statuses():
    from apps.tags.models import MemberTag, Tag

    community = CommunityFactory()
    me = MemberFactory(community=community)
    other = MemberFactory(community=community)
    tag = Tag.objects.create(community=community, slug="driver", label="Driver")
    mine = MemberTag.objects.create(member=me, tag=tag, status="self_claimed")
    theirs = MemberTag.objects.create(member=other, tag=tag, status="verified")
    result = selectors.own_tags(me)
    assert mine in result
    assert theirs not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hub_selectors.py -q`
Expected: FAIL — `ModuleNotFoundError: apps.hub.selectors`.

- [ ] **Step 3: Implement the selectors**

`apps/hub/selectors.py`:
```python
"""Read-only, bounded query helpers for the hub — the only place hub touches the ORM."""

from django.db.models import Q

from apps.communities.models import Member
from apps.matches.models import Match
from apps.notifications.models import Notification
from apps.tags.models import MemberTag

OPEN_MATCH_STATUSES = ("proposed", "accepted")
OPEN_MATCHES_CAP = 50
RECENT_NOTIFICATIONS_CAP = 8


def member_communities(user):
    """The user's active memberships, newest first, with community preloaded."""
    return list(
        Member.objects.filter(user=user, is_active=True)
        .select_related("community")
        .order_by("-joined_at")
    )


def open_matches_for(member):
    """Non-terminal matches in the member's focused community where they're a
    participant (requester, offerer, or proposer). Bounded, newest first."""
    return list(
        Match.objects.filter(
            Q(need__requester=member) | Q(offer__offerer=member) | Q(proposed_by=member),
            need__community=member.community,
            status__in=OPEN_MATCH_STATUSES,
        )
        .select_related("need", "offer")
        .order_by("-proposed_at")
        .distinct()[:OPEN_MATCHES_CAP]
    )


def recent_notifications(user):
    """The user's most recent notifications. User-global (no community FK)."""
    return list(
        Notification.objects.filter(recipient=user).order_by("-created_at")[:RECENT_NOTIFICATIONS_CAP]
    )


def own_tags(member):
    """The member's own tags at ALL statuses (their verification state)."""
    return list(
        MemberTag.objects.filter(member=member)
        .select_related("tag")
        .order_by("tag__sort_order", "tag__label")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hub_selectors.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/hub/selectors.py tests/test_hub_selectors.py
git commit -m "feat(hub): bounded read-only selectors for hub panels"
```

---

### Task 3: HubView panels + templates + HTMX body partial

Wire the selectors into the page; render the four panels; serve just the body under HTMX.

**Files:**
- Modify: `apps/hub/views.py` (`HubView.get_context_data` + `get_template_names`)
- Modify: `templates/hub/index.html` (wrap body in `#hub-body`, include partial)
- Create: `templates/hub/_hub_body.html`
- Test: `tests/test_hub_view.py`

**Interfaces:**
- Consumes: all four `apps.hub.selectors` functions (Task 2).
- Produces: context keys `communities`, `open_matches`, `notifications`, `member_tags`; HTMX requests render `hub/_hub_body.html` only.

- [ ] **Step 1: Write the failing view tests**

`tests/test_hub_view.py`:
```python
import pytest
from django.urls import reverse

from tests.conftest import (
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def _hub_url(community):
    return reverse("hub:community", kwargs={"slug": community.slug})


def test_renders_panels_for_member(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    need = NeedFactory(community=m.community, requester=m, title="Ride to clinic")
    MatchFactory(need=need, proposed_by=m, status="proposed")
    client.force_login(user)
    resp = client.get(_hub_url(m.community))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Ride to clinic" in body
    assert "Post a need" in body  # quick action label


def test_requires_auth(client):
    m = MemberFactory(community=CommunityFactory())
    resp = client.get(_hub_url(m.community))
    assert resp.status_code == 302
    assert "/auth/login/" in resp.url


def test_no_cross_community_match_leak(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory())
    b = MemberFactory(user=user, community=CommunityFactory())
    need_b = NeedFactory(community=b.community, requester=b, title="Secret B need")
    MatchFactory(need=need_b, proposed_by=b, status="proposed")
    client.force_login(user)
    resp = client.get(_hub_url(a.community))  # focused on A
    assert "Secret B need" not in resp.content.decode()


def test_htmx_returns_body_partial_only(client):
    user = UserFactory()
    m = MemberFactory(user=user, community=CommunityFactory())
    client.force_login(user)
    resp = client.get(_hub_url(m.community), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    # body partial only: no <html>/base chrome
    assert b"<html" not in resp.content
    assert b'id="hub-body"' in resp.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hub_view.py -q`
Expected: FAIL — quick-action label / panel content absent; HTMX returns full page.

- [ ] **Step 3: Extend `HubView`**

In `apps/hub/views.py`, add the import and replace `HubView.get_context_data`, and add `get_template_names`:
```python
from apps.hub import selectors
```
```python
    def get_template_names(self):
        if self.request.htmx:
            return ["hub/_hub_body.html"]
        return ["hub/index.html"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["community"] = self.community
        ctx["member"] = self.member
        ctx["communities"] = selectors.member_communities(self.request.user)
        ctx["open_matches"] = selectors.open_matches_for(self.member)
        ctx["notifications"] = selectors.recent_notifications(self.request.user)
        ctx["member_tags"] = selectors.own_tags(self.member)
        return ctx
```

- [ ] **Step 4: Build the templates**

`templates/hub/index.html` (replace the Task 1 minimal version):
```django
{% extends "base.html" %}
{% block content %}
<div id="hub-body">
  {% include "hub/_hub_body.html" %}
</div>
{% endblock %}
```

`templates/hub/_hub_body.html`:
```django
{% load static %}
<main class="umi-container hub" aria-labelledby="hub-heading">
  <h1 id="hub-heading" class="umi-h1">{{ community.name }}</h1>
  <p class="umi-muted">Welcome back, {{ member.display_name }}.</p>

  <section class="umi-card" aria-labelledby="hub-actions-h">
    <h2 id="hub-actions-h" class="umi-h2">Quick actions</h2>
    <nav class="umi-actions" aria-label="Quick actions">
      <a class="umi-pill" href="{% url 'communities:need-create' slug=community.slug %}">Post a need</a>
      <a class="umi-pill" href="{% url 'communities:offer-create' slug=community.slug %}">Post an offer</a>
      <a class="umi-pill" href="{% url 'communities:community-feed' slug=community.slug %}">Browse the feed</a>
    </nav>
  </section>

  <section class="umi-card" aria-labelledby="hub-matches-h">
    <h2 id="hub-matches-h" class="umi-h2">Your open matches</h2>
    {% if open_matches %}
      <ul class="umi-list">
        {% for match in open_matches %}
          <li><a href="{{ match.need.get_absolute_url }}">{{ match.need.title }}</a>
            <span class="umi-badge">{{ match.get_status_display }}</span></li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="umi-empty">No open matches right now.</p>
    {% endif %}
  </section>

  <section class="umi-card" aria-labelledby="hub-notifs-h">
    <h2 id="hub-notifs-h" class="umi-h2">Recent notifications</h2>
    <p class="umi-muted umi-small">Across all your communities.</p>
    {% if notifications %}
      <ul class="umi-list">
        {% for n in notifications %}
          <li>{% if n.link %}<a href="{{ n.link }}">{{ n.title }}</a>{% else %}{{ n.title }}{% endif %}</li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="umi-empty">Nothing new.</p>
    {% endif %}
  </section>

  <section class="umi-card" aria-labelledby="hub-tags-h">
    <h2 id="hub-tags-h" class="umi-h2">Your tags &amp; verification</h2>
    {% if member_tags %}
      <ul class="umi-tags">
        {% for mt in member_tags %}
          <li>{% include "tags/_badge.html" with member_tag=mt %}</li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="umi-empty">You haven't claimed any tags yet.</p>
    {% endif %}
  </section>
</main>
```

> NOTE for the implementer: verify the exact `{% include %}` variable name `tags/_badge.html` expects (open the partial). If it differs from `member_tag`, match it. If the badge partial needs a viewer/visibility arg for the owner's own view, pass the member's own context so all statuses render.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_hub_view.py -q`
Expected: PASS (4 tests). Then `pytest tests/test_hub_resolver.py -q` still green.

- [ ] **Step 6: Commit**

```bash
git add apps/hub/views.py templates/hub/index.html templates/hub/_hub_body.html tests/test_hub_view.py
git commit -m "feat(hub): render four panels + HTMX body partial"
```

---

### Task 4: Community switcher (HTMX swap + no-JS fallback)

**Files:**
- Modify: `templates/hub/_hub_body.html` (add switcher at top, inside `#hub-body` re-render scope)
- Test: `tests/test_hub_switcher.py`

**Interfaces:**
- Consumes: `communities` context (Task 3). Switch links target `hub:community`; HTMX swaps `#hub-body`.

- [ ] **Step 1: Write the failing switcher tests**

`tests/test_hub_switcher.py`:
```python
import pytest
from django.urls import reverse

from tests.conftest import CommunityFactory, MemberFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_switcher_lists_only_my_communities(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    b = MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    not_mine = CommunityFactory(name="Gamma")
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": a.community.slug}))
    body = resp.content.decode()
    assert "Alpha" in body and "Beta" in body
    assert "Gamma" not in body


def test_switcher_marks_focused_community(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": a.community.slug}))
    assert 'aria-current="page"' in resp.content.decode()


def test_switch_to_other_membership_renders_that_community(client):
    user = UserFactory()
    a = MemberFactory(user=user, community=CommunityFactory(name="Alpha"))
    b = MemberFactory(user=user, community=CommunityFactory(name="Beta"))
    client.force_login(user)
    resp = client.get(reverse("hub:community", kwargs={"slug": b.community.slug}), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200
    assert "Beta" in resp.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hub_switcher.py -q`
Expected: FAIL — switcher markup / `aria-current` absent.

- [ ] **Step 3: Add the switcher to `_hub_body.html`**

Insert immediately after the opening `<main ...>` tag, before the `<h1>`:
```django
  {% if communities|length > 1 %}
  <nav class="umi-switcher" aria-label="Your communities">
    <ul>
      {% for mem in communities %}
        <li>
          <a href="{% url 'hub:community' slug=mem.community.slug %}"
             hx-get="{% url 'hub:community' slug=mem.community.slug %}"
             hx-target="#hub-body" hx-push-url="true"
             {% if mem.community_id == community.id %}aria-current="page"{% endif %}>
            {{ mem.community.name }}
          </a>
        </li>
      {% endfor %}
    </ul>
  </nav>
  {% endif %}
```

> The switcher lives *inside* `#hub-body`, so each HTMX swap re-renders it with the correct `aria-current`. Plain `href` is the no-JS fallback; `hx-get` + `hx-push-url` upgrade it to an in-place swap.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hub_switcher.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add templates/hub/_hub_body.html tests/test_hub_switcher.py
git commit -m "feat(hub): community switcher (HTMX swap + no-JS fallback)"
```

---

### Task 5: Styling polish, accessibility audit, and full verification gate

Make the hub match the parish atmosphere, confirm WCAG-AA, walk the switcher in a real browser, and run the project's full gate. This task is verification-heavy; its "tests" are the audit + gate, not new unit tests.

**Files:**
- Modify: `static/css/input.css` (only if new `.umi-*` hub classes are needed beyond `ui-polish-spec.md`)
- Regenerate: `static/css/output.css` (via the tailwind CLI — never hand-edit)
- Possibly modify: `templates/hub/_hub_body.html` (a11y fixes the audit surfaces)

- [ ] **Step 1: Align classes with the design system**

Read `docs/ui-polish-spec.md` and `templates/base.html`. Ensure every class used in `_hub_body.html` (`umi-container`, `umi-card`, `umi-pill`, `umi-h1/h2`, `umi-list`, `umi-empty`, `umi-switcher`, etc.) either already exists or is added to `static/css/input.css` following the spec's tokens (paper grain, shadow lift, rails, pills). Mobile-first; wrap any motion in `@media (prefers-reduced-motion: no-preference)`.

- [ ] **Step 2: Recompile Tailwind**

Run: `npx tailwindcss@3.4.14 -i static/css/input.css -o static/css/output.css --minify`
Expected: rebuild succeeds; `git diff --stat static/css/output.css` shows only generated changes.

- [ ] **Step 3: Run the dev server for browser verification**

Run (background): `python manage.py runserver` with a seeded multi-community member (use `manage.py shell` or an existing seed). Note the login creds and two community slugs.

- [ ] **Step 4: Accessibility audit (Playwright MCP + axe-core)**

Using the Playwright MCP browser tools: navigate to the login page, sign in, go to `/hub/<slug>/`. Inject axe-core and run it:
- `browser_navigate` to the hub URL (after login).
- `browser_evaluate` to load axe and run: fetch `https://cdn.jsdelivr.net/npm/axe-core/axe.min.js`, inject, then `await axe.run(document, {runOnly: ['wcag2a','wcag2aa']})` and return `results.violations`.
Expected: **zero** `critical`/`serious` violations. Fix any in `_hub_body.html` (labels, landmarks, contrast, focus order) and re-run until clean.

- [ ] **Step 5: Switcher walk-through (Playwright MCP)**

With the multi-community member: `browser_navigate` to `/hub/<slugA>/`; `browser_snapshot` to confirm panels + switcher; `browser_click` the other community in the switcher; `browser_wait_for` the heading to change; confirm the URL pushed to `/hub/<slugB>/` and panels now show community B. Take a `browser_take_screenshot` of each for the record.

- [ ] **Step 6: Full verification gate**

Run each and confirm:
```bash
ruff check . && ruff format --check .
python manage.py makemigrations --check --dry-run      # expect: No changes detected
bandit -q -r apps config -x '*/tests/*,*/migrations/*' # no NEW findings vs main
semgrep ci --config p/django --config p/python --baseline-commit main  # no new
# full suite on Postgres (throwaway):
DATABASE_URL=postgres://umi:umi@127.0.0.1:5434/umi_test \
  ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())') \
  pytest -q
DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(50))')" \
  ENCRYPTION_KEY=… ALLOWED_HOSTS=example.com python manage.py check --deploy   # 0 issues
```
Expected: all green; no new migration; deploy check 0.

- [ ] **Step 7: `/audit-context`**

Run the `audit-context` skill; if the hub introduced a load-bearing pattern worth recording (e.g. the `/hub/` resolver convention), propose the CLAUDE.md/STATE.md delta (do not commit doc changes into this feature branch unless trivial).

- [ ] **Step 8: Commit**

```bash
git add static/css/input.css static/css/output.css templates/hub/_hub_body.html
git commit -m "feat(hub): parish-atmosphere styling + WCAG-AA a11y pass"
```

**STOP before merge.** Report results and await approval to open a PR.

---

## Self-Review (completed by plan author)

- **Spec coverage:** resolver branching (T1), four panels + bounded selectors (T2/T3), multi-community switcher (T4), `LOGIN_REDIRECT_URL` (T1), isolation/auth/no-leak tests (T1/T3), HTMX partial (T3/T4), styling + a11y + Playwright walk + verification gate + audit-context (T5). Notifications user-global labelling (T3 template). No-new-schema enforced by the gate (T5). All spec sections map to a task.
- **Placeholder scan:** no TBD/TODO; every code step shows real code; the one NOTE (badge-partial variable name) is a verify-and-match instruction with a concrete fallback, not a placeholder.
- **Type/name consistency:** selector names and signatures defined in T2 are used verbatim in T3; context keys (`communities`, `open_matches`, `notifications`, `member_tags`) consistent between T3 view and template; URL names `hub:index`/`hub:community` consistent T1→T4; verified field names (`proposed_at`, `self_claimed`, `is_active`, `joined_at`) used throughout.
