"""Layer C — coordinator-authored community pages (pipeline §C/§E/§F/§G/§H).

S2 (slice/pages-core): the model + state machine, the write-path renderer, and the
"Your pages" manager. Mirrors test_moderation.py's shape: module world fixture,
per-file helpers. Public/anon surfaces arrive in S3 and are NOT tested here."""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.common.state import TransitionConflict
from apps.pages.models import CommunityPage
from apps.pages.render import render_page_html
from tests.conftest import CommunityFactory, MemberFactory

pytestmark = pytest.mark.django_db


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def world():
    community = CommunityFactory()
    admin = MemberFactory(community=community, role="admin", display_name="Fr. Declan")
    coordinator = MemberFactory(community=community, role="coordinator", display_name="Anne Coordinator")
    member = MemberFactory(community=community, role="member", display_name="Nuala Member")
    return community, admin, coordinator, member


def _page(community, member, **kw):
    defaults = dict(
        community=community,
        title="Our story",
        slug="our-story",
        content_md="Hello neighbours.",
        created_by=member,
    )
    defaults.update(kw)
    return CommunityPage.objects.create(**defaults)


# ---------------------------------------------------------------------------
# §C — the model: state machine, slug promises, visibility predicate
# ---------------------------------------------------------------------------


class TestPageModel:
    def test_draft_publish_archive_restore_walk(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        assert page.status == "draft"

        page.publish(by=admin)
        assert page.status == "published"
        assert page.published_at is not None
        assert page.first_published_at is not None
        assert page.published_by == admin

        first = page.first_published_at
        page.transition_to("draft")  # live fix goes back through draft
        page.publish(by=admin)
        assert page.first_published_at == first  # set once, forever

        page.transition_to("archived")
        assert page.archived_at is not None

        page.restore()
        assert page.status == "draft"

    def test_illegal_transitions_conflict(self, world):
        community, _, coordinator, _ = world
        page = _page(community, coordinator)
        with pytest.raises(TransitionConflict):
            page.transition_to("draft")  # draft → draft is not a move
        page.transition_to("archived")
        with pytest.raises(TransitionConflict):
            page.transition_to("published")  # archived pages come back as drafts

    def test_slug_freezes_at_first_publish(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        page.slug = "renamed-freely"
        page.save()  # drafts may rename

        page.publish(by=admin)
        page.slug = "broken-promise"
        with pytest.raises(ValidationError):
            page.save()

    def test_archived_releases_slug_but_restore_is_blocked_if_retaken(self, world):
        community, admin, coordinator, _ = world
        first = _page(community, coordinator)
        first.publish(by=admin)
        first.transition_to("archived")

        second = _page(community, coordinator, title="Our story, again")  # same slug — released
        assert second.slug == first.slug

        with pytest.raises(ValidationError) as exc:
            first.restore()
        assert "another page" in str(exc.value).lower()  # warm words, no jargon
        first.refresh_from_db()
        assert first.status == "archived"  # unchanged, no silent rename

    def test_duplicate_live_slug_refused(self, world):
        community, _, coordinator, _ = world
        _page(community, coordinator)
        with pytest.raises(Exception):  # IntegrityError or ValidationError — never a second live row
            _page(community, coordinator, title="Twin")

    def test_member_visible_predicate(self, world):
        community, admin, coordinator, _ = world
        live = _page(community, coordinator, slug="live")
        live.publish(by=admin)
        _page(community, coordinator, slug="draft")
        hidden = _page(community, coordinator, slug="hidden")
        hidden.publish(by=admin)
        hidden.moderation_hidden = True
        hidden.save()

        visible = set(CommunityPage.objects.member_visible(community).values_list("slug", flat=True))
        assert visible == {"live"}

    def test_pre_auth_predicate_respects_landing_and_privacy(self, world):
        community, admin, coordinator, _ = world
        community.visibility = "public"  # factory default is private — the safe default
        community.save()
        on_landing = _page(community, coordinator, slug="front", show_on_landing=True)
        on_landing.publish(by=admin)
        members_only = _page(community, coordinator, slug="inside")
        members_only.publish(by=admin)

        pre_auth = set(CommunityPage.objects.pre_auth_visible(community).values_list("slug", flat=True))
        assert pre_auth == {"front"}

        community.visibility = "private"
        community.save()
        assert not CommunityPage.objects.pre_auth_visible(community).exists()

        community.visibility = "public"
        community.is_active = False
        community.save()
        assert not CommunityPage.objects.pre_auth_visible(community).exists()


# ---------------------------------------------------------------------------
# §G — the wall: what the renderer admits and refuses (red-team table)
# ---------------------------------------------------------------------------


class TestRenderer:
    def test_renders_on_save(self, world):
        community, _, coordinator, _ = world
        page = _page(community, coordinator, content_md="# Top\n\nA *warm* line.")
        assert "<h2" in page.content_html  # h1 demotes — the page chrome owns its h1
        assert "<em>warm</em>" in page.content_html

    def test_script_and_platform_clothes_are_refused(self):
        md = '<script>alert(1)</script>\n\n<form><input></form>\n\n<div class="umi-card">boxed</div>'
        html = render_page_html(md)
        assert "<script" not in html
        assert "<form" not in html
        assert "<input" not in html
        assert "<div" not in html
        assert "umi-card" not in html
        assert "boxed" in html  # words survive; costumes don't

    def test_javascript_and_data_schemes_are_stripped(self):
        html = render_page_html("[click](javascript:alert(1)) and ![pic](data:image/png;base64,AAAA)")
        assert "javascript:" not in html
        assert "data:" not in html

    def test_images_become_links(self):
        html = render_page_html("![Our patron](https://example.org/patron.jpg)")
        assert "<img" not in html
        assert '<a href="https://example.org/patron.jpg"' in html
        assert "Our patron" in html

    def test_headings_demote_into_the_page_band(self):
        html = render_page_html("# One\n\n##### Five\n\n###### Six")
        assert "<h1" not in html
        assert "<h5" not in html
        assert "<h6" not in html
        assert html.count("<h2") == 1
        assert html.count("<h4") == 2

    def test_links_carry_rel(self):
        html = render_page_html("[out](https://example.org/)")
        assert 'rel="nofollow noopener noreferrer"' in html

    def test_allowed_grammar_survives(self):
        md = "## Mass times\n\n- Sunday 8:00\n- Sunday 10:30\n\n> Come as you are.\n\n`quiet code` and [a link](https://example.org/x)."
        html = render_page_html(md)
        for token in ("<h2", "<ul>", "<li>", "<blockquote>", "<code>", "<a href="):
            assert token in html


# ---------------------------------------------------------------------------
# §E/§F — the "Your pages" manager: who may browse, who may write, who signs
# ---------------------------------------------------------------------------

from django.urls import reverse  # noqa: E402

from apps.audit.models import AuditLog  # noqa: E402


def _manage(community):
    return reverse("pages:manage", kwargs={"slug": community.slug})


def _actions(page):
    k = {"slug": page.community.slug, "pk": page.pk}
    return {name: reverse(f"pages:{name}", kwargs=k) for name in ("publish", "unpublish", "archive", "restore")}


class TestManagerAuthz:
    def test_anonymous_gets_login_redirect(self, world):
        community, *_ = world
        resp = Client().get(_manage(community))
        assert resp.status_code == 302
        assert "login" in resp["Location"]

    def test_non_member_gets_404(self, world):
        community, *_ = world
        stranger = MemberFactory()  # different community
        resp = _login(stranger).get(_manage(community))
        assert resp.status_code == 404

    def test_member_gets_soft_redirect(self, world):
        community, _, _, member = world
        resp = _login(member).get(_manage(community), follow=True)
        assert resp.redirect_chain  # bounced, not shown
        assert "coordinator" in resp.content.decode().lower()

    def test_coordinator_sees_the_list_with_chips(self, world):
        community, admin, coordinator, _ = world
        live = _page(community, coordinator, slug="live", title="Live page")
        live.publish(by=admin)
        _page(community, coordinator, slug="drafted", title="Drafted page")
        body = _login(coordinator).get(_manage(community)).content.decode()
        assert "Live page" in body and "Drafted page" in body
        assert "Draft" in body  # a chip names the state

    def test_empty_state_speaks(self, world):
        community, _, coordinator, _ = world
        body = _login(coordinator).get(_manage(community)).content.decode()
        assert "Your story is worth telling" in body


class TestEditorWorkflow:
    def _create_payload(self, **kw):
        data = {"title": "Mass times", "slug": "mass-times", "content_md": "Sundays 8:00.", "sort_order": 1}
        data.update(kw)
        return data

    def test_coordinator_creates_a_draft(self, world):
        community, _, coordinator, _ = world
        resp = _login(coordinator).post(
            reverse("pages:create", kwargs={"slug": community.slug}), self._create_payload()
        )
        assert resp.status_code == 302
        page = CommunityPage.objects.get(community=community, slug="mass-times")
        assert page.status == "draft"
        assert page.created_by == coordinator
        assert AuditLog.objects.filter(action="page.created", details__slug="mass-times").exists()

    def test_member_cannot_reach_the_editor(self, world):
        community, _, _, member = world
        _login(member).post(
            reverse("pages:create", kwargs={"slug": community.slug}), self._create_payload(), follow=True
        )
        assert not CommunityPage.objects.filter(community=community, slug="mass-times").exists()

    def test_edit_updates_draft_and_stamps_updated_by(self, world):
        community, _, coordinator, _ = world
        page = _page(community, coordinator)
        url = reverse("pages:edit", kwargs={"slug": community.slug, "pk": page.pk})
        resp = _login(coordinator).post(
            url, self._create_payload(title="Our story", slug=page.slug, content_md="New words.")
        )
        assert resp.status_code == 302
        page.refresh_from_db()
        assert "New words." in page.content_md
        assert page.updated_by == coordinator
        assert AuditLog.objects.filter(action="page.updated", details__slug=page.slug).exists()

    def test_published_page_is_never_edited_in_place(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        page.publish(by=admin)
        url = reverse("pages:edit", kwargs={"slug": community.slug, "pk": page.pk})
        resp = _login(coordinator).post(url, self._create_payload(slug=page.slug, content_md="sneaky"))
        assert resp.status_code == 403
        page.refresh_from_db()
        assert "sneaky" not in page.content_md
        # reading it is fine — read-only, with the way back named
        body = _login(admin).get(url).content.decode()
        assert "unpublish" in body.lower()

    def test_body_cap_20k(self, world):
        community, _, coordinator, _ = world
        resp = _login(coordinator).post(
            reverse("pages:create", kwargs={"slug": community.slug}),
            self._create_payload(content_md="x" * 20001),
        )
        assert resp.status_code == 200  # form re-rendered with the error
        assert not CommunityPage.objects.filter(community=community, slug="mass-times").exists()

    def test_preview_renders_without_persisting(self, world):
        community, _, coordinator, _ = world
        before = CommunityPage.objects.count()
        resp = _login(coordinator).post(
            reverse("pages:preview", kwargs={"slug": community.slug}), {"content_md": "A *warm* preview."}
        )
        assert resp.status_code == 200
        assert "<em>warm</em>" in resp.content.decode()
        assert CommunityPage.objects.count() == before


class TestPublishGate:
    def test_coordinator_cannot_publish(self, world):
        community, _, coordinator, _ = world
        page = _page(community, coordinator)
        resp = _login(coordinator).post(_actions(page)["publish"])
        assert resp.status_code == 403
        page.refresh_from_db()
        assert page.status == "draft"
        assert not AuditLog.objects.filter(action="page.published").exists()

    def test_admin_publishes_and_it_is_audited(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        resp = _login(admin).post(_actions(page)["publish"])
        assert resp.status_code == 302
        page.refresh_from_db()
        assert page.status == "published"
        assert page.published_by == admin
        assert AuditLog.objects.filter(action="page.published", details__slug=page.slug).exists()

    def test_unpublish_is_admin_only(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        page.publish(by=admin)
        assert _login(coordinator).post(_actions(page)["unpublish"]).status_code == 403
        assert _login(admin).post(_actions(page)["unpublish"]).status_code == 302
        page.refresh_from_db()
        assert page.status == "draft"
        assert AuditLog.objects.filter(action="page.unpublished", details__slug=page.slug).exists()

    def test_archiving_published_is_admin_only_but_drafts_are_coordinator_work(self, world):
        community, admin, coordinator, _ = world
        live = _page(community, coordinator, slug="live")
        live.publish(by=admin)
        assert _login(coordinator).post(_actions(live)["archive"]).status_code == 403
        assert _login(admin).post(_actions(live)["archive"]).status_code == 302

        draft = _page(community, coordinator, slug="drafted")
        assert _login(coordinator).post(_actions(draft)["archive"]).status_code == 302
        draft.refresh_from_db()
        assert draft.status == "archived"
        assert AuditLog.objects.filter(action="page.archived", details__slug="drafted").exists()

    def test_restore_and_its_warm_refusal(self, world):
        community, admin, coordinator, _ = world
        first = _page(community, coordinator)
        first.transition_to("archived")
        resp = _login(coordinator).post(_actions(first)["restore"])
        assert resp.status_code == 302
        first.refresh_from_db()
        assert first.status == "draft"
        assert AuditLog.objects.filter(action="page.restored", details__slug=first.slug).exists()

        first.transition_to("archived")
        _page(community, coordinator, title="Retaker")  # takes the slug
        resp = _login(coordinator).post(_actions(first)["restore"], follow=True)
        assert "another page" in resp.content.decode().lower()
        first.refresh_from_db()
        assert first.status == "archived"

    def test_stale_double_publish_is_a_409(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        page.publish(by=admin)
        resp = _login(admin).post(_actions(page)["publish"])
        assert resp.status_code == 409


class TestLandingToggle:
    def test_coordinator_flips_landing_and_it_is_audited(self, world):
        community, admin, coordinator, _ = world
        page = _page(community, coordinator)
        page.publish(by=admin)
        url = reverse("pages:toggle-landing", kwargs={"slug": community.slug, "pk": page.pk})
        resp = _login(coordinator).post(url)
        assert resp.status_code == 302
        page.refresh_from_db()
        assert page.show_on_landing is True
        assert AuditLog.objects.filter(action="page.updated", details__slug=page.slug).exists()


class TestSettingsEntry:
    def test_settings_page_links_your_pages(self, world):
        community, admin, _, _ = world
        body = _login(admin).get(reverse("community-settings", kwargs={"slug": community.slug})).content.decode()
        assert "Your pages" in body


# ---------------------------------------------------------------------------
# S3 §I — the front door: no-oracle landing, the index, page views, tombstone
# ---------------------------------------------------------------------------

from django.contrib.auth.views import redirect_to_login  # noqa: E402


def _index(community):
    return reverse("pages:index", kwargs={"slug": community.slug})


def _view(community, page_slug):
    return reverse("pages:view", kwargs={"slug": community.slug, "page_slug": page_slug})


def _feed(community_slug):
    return reverse("community-feed", kwargs={"slug": community_slug})


def _login_redirect_for(path):
    """What LoginRequiredMixin answers for this path — the no-oracle reference.
    Every anonymous non-renderable case must equal this, byte for byte, so DB
    state (missing vs private vs quiet) never shows through the redirect."""
    return redirect_to_login(path)["Location"]


def _open_world(world):
    """Make the world's community public with one landing page + one members-only page."""
    community, admin, coordinator, member = world
    community.visibility = "public"
    community.save(update_fields=["visibility"])
    landing = _page(community, coordinator, show_on_landing=True)  # "Our story"
    landing.publish(by=admin)
    quiet = _page(community, coordinator, title="Mass times", slug="mass-times")
    quiet.publish(by=admin)
    return landing, quiet


class TestPreAuthLanding:
    def test_anon_feed_302s_to_pages_index_when_eligible(self, world):
        community, *_ = world
        _open_world(world)
        resp = Client().get(_feed(community.slug))
        assert resp.status_code == 302
        assert resp["Location"] == _index(community)

    def test_anon_feed_no_oracle_across_private_missing_and_quiet(self, world):
        community, admin, coordinator, _ = world
        # Private community WITH a landing-marked page: still invisible.
        landing = _page(community, coordinator, show_on_landing=True)
        landing.publish(by=admin)
        # Public community with nothing marked for landing: nothing to show.
        open_c = CommunityFactory(visibility="public")
        for path in (_feed(community.slug), _feed("no-such-community"), _feed(open_c.slug)):
            resp = Client().get(path)
            assert resp.status_code == 302
            assert resp["Location"] == _login_redirect_for(path)

    def test_member_feed_unchanged(self, world):
        community, _, _, member = world
        _open_world(world)
        assert _login(member).get(_feed(community.slug)).status_code == 200


class TestPagesIndex:
    def test_anon_sees_landing_pages_and_join_door_only(self, world):
        community, *_ = world
        landing, quiet = _open_world(world)
        body = Client().get(_index(community)).content.decode()
        assert landing.title in body
        assert quiet.title not in body
        assert reverse("community-join") in body
        assert reverse("pages:manage", kwargs={"slug": community.slug}) not in body

    def test_member_sees_all_published_without_join_door(self, world):
        community, _, _, member = world
        landing, quiet = _open_world(world)
        body = _login(member).get(_index(community)).content.decode()
        assert landing.title in body and quiet.title in body
        assert reverse("community-join") not in body

    def test_member_empty_state_speaks(self, world):
        community, _, _, member = world
        body = _login(member).get(_index(community)).content.decode()
        assert "haven&#x27;t written any pages yet" in body or "haven't written any pages yet" in body

    def test_coordinator_sees_chip_rows_for_the_unpublished(self, world):
        community, admin, coordinator, _ = world
        _open_world(world)
        _page(community, coordinator, title="Drafted page", slug="drafted")
        arch = _page(community, coordinator, title="Old bulletin", slug="old-bulletin")
        arch.transition_to("archived")
        body = _login(coordinator).get(_index(community)).content.decode()
        assert "Drafted page" in body and "Old bulletin" in body
        assert "Draft" in body and "Archived" in body

    def test_coordinator_with_only_a_draft_is_not_told_nothing_is_written(self, world):
        community, _, coordinator, _ = world
        _page(community, coordinator, title="Drafted page", slug="drafted")
        body = _login(coordinator).get(_index(community)).content.decode()
        assert "Drafted page" in body  # the chip row carries it
        assert "written any pages yet" not in body  # the empty line would contradict it

    def test_anon_ineligible_index_is_the_login_redirect(self, world):
        community, *_ = world  # private by default, no pages
        path = _index(community)
        resp = Client().get(path)
        assert resp.status_code == 302
        assert resp["Location"] == _login_redirect_for(path)

    def test_stranger_sees_public_render_when_eligible_else_404(self, world):
        community, *_ = world
        stranger = MemberFactory()  # a member of some other community
        assert _login(stranger).get(_index(community)).status_code == 404
        landing, quiet = _open_world(world)
        body = _login(stranger).get(_index(community)).content.decode()
        assert landing.title in body and quiet.title not in body
        assert reverse("community-join") in body

    def test_unlisted_link_is_a_capability(self, world):
        community, *_ = world
        _open_world(world)
        community.visibility = "unlisted"
        community.save(update_fields=["visibility"])
        assert Client().get(_index(community)).status_code == 200

    def test_index_orders_by_sort_order_then_title(self, world):
        community, admin, coordinator, member = world
        _open_world(world)  # "Mass times", "Our story" — both sort_order 0
        third = _page(community, coordinator, title="Weekday ministries", slug="ministries", sort_order=5)
        third.publish(by=admin)
        body = _login(member).get(_index(community)).content.decode()
        assert body.index("Mass times") < body.index("Our story") < body.index("Weekday ministries")


class TestPageView:
    def test_member_reads_published_page_with_byline_and_flag_panel(self, world):
        community, _, _, member = world
        _, quiet = _open_world(world)
        body = _login(member).get(_view(community, quiet.slug)).content.decode()
        assert quiet.title in body
        assert f"Written by the coordinators of {community.name}" in body
        assert "Something wrong with this page?" in body

    def test_draft_404_for_member_banner_for_coordinator(self, world):
        community, _, coordinator, member = world
        _page(community, coordinator, title="Drafted page", slug="drafted")
        assert _login(member).get(_view(community, "drafted")).status_code == 404
        body = _login(coordinator).get(_view(community, "drafted")).content.decode()
        assert "Draft" in body and "members can" in body

    def test_hidden_404_for_member_banner_for_coordinator(self, world):
        community, _, coordinator, member = world
        _, quiet = _open_world(world)
        quiet.moderation_hidden = True
        quiet.save(update_fields=["moderation_hidden"])
        assert _login(member).get(_view(community, quiet.slug)).status_code == 404
        body = _login(coordinator).get(_view(community, quiet.slug)).content.decode()
        assert "Hidden after a report" in body

    def test_anon_reads_landing_page_with_join_door_and_no_flag_control(self, world):
        community, *_ = world
        landing, _ = _open_world(world)
        body = Client().get(_view(community, landing.slug)).content.decode()
        assert landing.title in body
        assert f"Written by the coordinators of {community.name}" in body
        assert reverse("community-join") in body
        assert "Something wrong with this page?" not in body

    def test_anon_failures_all_wear_the_same_login_redirect(self, world):
        community, admin, coordinator, _ = world
        landing, quiet = _open_world(world)  # quiet is not landing-marked
        _page(community, coordinator, title="Drafted page", slug="drafted")
        landing.moderation_hidden = True
        landing.save(update_fields=["moderation_hidden"])
        for page_slug in (quiet.slug, "drafted", landing.slug, "no-such-page"):
            path = _view(community, page_slug)
            resp = Client().get(path)
            assert resp.status_code == 302
            assert resp["Location"] == _login_redirect_for(path)

    def test_stranger_reads_eligible_page_else_404(self, world):
        community, *_ = world
        stranger = MemberFactory()
        landing, quiet = _open_world(world)
        assert _login(stranger).get(_view(community, landing.slug)).status_code == 200
        assert _login(stranger).get(_view(community, quiet.slug)).status_code == 404


class TestTombstone:
    def _archived(self, world):
        community, _, coordinator, _ = world
        page = _page(community, coordinator, title="Old bulletin", slug="old-bulletin")
        page.transition_to("archived")
        return page

    def test_member_gets_warm_tombstone_without_the_title(self, world):
        community, _, _, member = world
        self._archived(world)
        resp = _login(member).get(_view(community, "old-bulletin"))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "put this page away" in body
        assert "Old bulletin" not in body  # put away, not teased
        assert "ever deleted" in body
        assert "My tags" in body  # the member keeps their header nav here too

    def test_coordinator_sees_the_restore_pointer(self, world):
        community, _, coordinator, _ = world
        self._archived(world)
        body = _login(coordinator).get(_view(community, "old-bulletin")).content.decode()
        assert "Restore it from Your pages" in body

    def test_anon_gets_the_no_oracle_redirect_never_the_tombstone(self, world):
        community, *_ = world
        self._archived(world)
        community.visibility = "public"
        community.save(update_fields=["visibility"])
        path = _view(community, "old-bulletin")
        resp = Client().get(path)
        assert resp.status_code == 302
        assert resp["Location"] == _login_redirect_for(path)

    def test_stranger_404(self, world):
        community, *_ = world
        self._archived(world)
        assert _login(MemberFactory()).get(_view(community, "old-bulletin")).status_code == 404

    def test_live_draft_owns_the_slug_over_the_archived(self, world):
        community, _, coordinator, member = world
        self._archived(world)
        _page(community, coordinator, title="New bulletin", slug="old-bulletin")  # draft retakes the slug
        assert _login(member).get(_view(community, "old-bulletin")).status_code == 404


class TestReservedSlug:
    def test_restore_cannot_revive_a_reserved_slug(self, world):
        # Legacy data path: an archived page holding "manage" (created before the
        # reservation) must not restore into a URL the manager shadows.
        community, _, coordinator, _ = world
        page = _page(community, coordinator, title="Old manager", slug="manage")
        page.transition_to("archived")
        resp = _login(coordinator).post(
            reverse("pages:restore", kwargs={"slug": community.slug, "pk": page.pk}), follow=True
        )
        page.refresh_from_db()
        assert page.status == "archived"
        assert "reserved" in resp.content.decode()

    def test_manage_is_not_a_page_address(self, world):
        community, _, coordinator, _ = world
        resp = _login(coordinator).post(
            reverse("pages:create", kwargs={"slug": community.slug}),
            {"title": "Manage", "slug": "manage", "content_md": "x", "sort_order": 0},
        )
        assert resp.status_code == 200  # form re-rendered with the warm refusal
        assert "reserved" in resp.content.decode()
        assert not CommunityPage.objects.filter(community=community, slug="manage").exists()


# ---------------------------------------------------------------------------
# S3 §H — one moderation model: pages are flaggable, hide is reversible
# ---------------------------------------------------------------------------

from apps.moderation.models import Flag  # noqa: E402


def _flag_page(client, community, page, reason="unsafe"):
    return client.post(
        reverse("moderation:flag", kwargs={"slug": community.slug}),
        {"target_type": "page", "target_id": str(page.pk), "reason": reason, "detail": ""},
    )


class TestPageFlags:
    def test_member_flags_a_published_page(self, world):
        community, _, _, member = world
        _, quiet = _open_world(world)
        resp = _flag_page(_login(member), community, quiet)
        assert resp.status_code == 302
        assert resp["Location"] == _view(community, quiet.slug)
        assert Flag.objects.filter(community=community, target_type="page", target_id=quiet.pk).exists()

    def test_duplicate_open_flag_stays_single(self, world):
        community, _, _, member = world
        _, quiet = _open_world(world)
        client = _login(member)
        _flag_page(client, community, quiet)
        _flag_page(client, community, quiet)
        assert Flag.objects.filter(target_type="page", target_id=quiet.pk).count() == 1

    def test_queue_shows_page_row_with_md_excerpt_never_html(self, world):
        community, admin, coordinator, member = world
        _open_world(world)
        page = _page(
            community,
            coordinator,
            title="Ministries",
            slug="ministries",
            content_md="We carry **meals** to the housebound every Friday. " + "More words. " * 30,
        )
        page.publish(by=admin)
        _flag_page(_login(member), community, page)
        body = _login(admin).get(reverse("moderation:queue", kwargs={"slug": community.slug})).content.decode()
        assert "Ministries" in body
        assert "We carry **meals** to the housebound" in body  # raw markdown, escaped as text
        assert "<strong>" not in body  # content_html never reaches the queue
        # The row links the EDITOR by pk: a slug link would open the tombstone
        # once the page is archived — or a different page entirely if the slug
        # was reclaimed. The pk always names the flagged row.
        assert reverse("pages:edit", kwargs={"slug": community.slug, "pk": page.pk}) in body

    def test_queue_names_the_conflict_when_the_author_reviews(self, world):
        community, admin, coordinator, member = world
        _, quiet = _open_world(world)  # authored by the coordinator
        _flag_page(_login(member), community, quiet)
        body = _login(admin).get(reverse("moderation:queue", kwargs={"slug": community.slug})).content.decode()
        assert "reviewer of this queue" in body

    def test_hide_pulls_the_page_from_every_surface(self, world):
        community, admin, coordinator, member = world
        community.visibility = "public"
        community.save(update_fields=["visibility"])
        # A distinct title — "Our story" would collide with the footer's mission nav.
        landing = _page(community, coordinator, title="Parish festival", slug="festival", show_on_landing=True)
        landing.publish(by=admin)
        _flag_page(_login(member), community, landing)
        flag = Flag.objects.get(target_type="page", target_id=landing.pk)
        resp = _login(admin).post(
            reverse("moderation:resolve", kwargs={"slug": community.slug, "pk": flag.pk}),
            {"action": "hide"},
        )
        assert resp.status_code == 302
        landing.refresh_from_db()
        assert landing.moderation_hidden is True
        assert AuditLog.objects.filter(action="content.hidden", details__target_type="page").exists()
        # Member surfaces: view 404s, index no longer lists it.
        assert _login(member).get(_view(community, landing.slug)).status_code == 404
        index_body = _login(member).get(_index(community)).content.decode()
        assert landing.title not in index_body
        # Anonymous surfaces: it was the only landing page — the front door closes
        # back to the identical login redirect.
        for path in (_feed(community.slug), _index(community), _view(community, landing.slug)):
            resp = Client().get(path)
            assert resp.status_code == 302
            assert resp["Location"] == _login_redirect_for(path)

    def test_flag_on_a_later_archived_page_still_resolves(self, world):
        community, admin, coordinator, member = world
        _, quiet = _open_world(world)
        _flag_page(_login(member), community, quiet)
        quiet.transition_to("archived")
        flag = Flag.objects.get(target_type="page", target_id=quiet.pk)
        queue = _login(admin).get(reverse("moderation:queue", kwargs={"slug": community.slug}))
        assert queue.status_code == 200
        resp = _login(admin).post(
            reverse("moderation:resolve", kwargs={"slug": community.slug, "pk": flag.pk}),
            {"action": "dismiss"},
        )
        assert resp.status_code == 302
        flag.refresh_from_db()
        assert flag.status == "dismissed"

    def test_coordinator_unhides_and_the_page_returns(self, world):
        community, admin, coordinator, member = world
        _, quiet = _open_world(world)
        quiet.moderation_hidden = True
        quiet.save(update_fields=["moderation_hidden"])
        resp = _login(coordinator).post(reverse("pages:unhide", kwargs={"slug": community.slug, "pk": quiet.pk}))
        assert resp.status_code == 302
        quiet.refresh_from_db()
        assert quiet.moderation_hidden is False
        assert AuditLog.objects.filter(action="content.unhidden", details__slug=quiet.slug).exists()
        assert _login(member).get(_view(community, quiet.slug)).status_code == 200

    def test_hidden_banner_offers_unhide_to_coordinators(self, world):
        community, _, coordinator, _ = world
        _, quiet = _open_world(world)
        quiet.moderation_hidden = True
        quiet.save(update_fields=["moderation_hidden"])
        body = _login(coordinator).get(_view(community, quiet.slug)).content.decode()
        assert reverse("pages:unhide", kwargs={"slug": community.slug, "pk": quiet.pk}) in body


# ---------------------------------------------------------------------------
# S3 §I — nav anchors: the hub pill and the footer column
# ---------------------------------------------------------------------------


class TestPagesNav:
    def test_hub_gains_the_pages_pill_when_something_is_published(self, world):
        community, _, _, member = world
        hub = reverse("hub:community", kwargs={"slug": community.slug})
        body = _login(member).get(hub).content.decode()
        assert ">Pages</a>" not in body  # nothing published yet
        _open_world(world)
        body = _login(member).get(hub).content.decode()
        assert ">Pages</a>" in body
        assert _index(community) in body

    def test_hidden_only_pages_do_not_light_the_pill(self, world):
        community, _, _, member = world
        landing, quiet = _open_world(world)
        for p in (landing, quiet):
            p.moderation_hidden = True
            p.save(update_fields=["moderation_hidden"])
        body = _login(member).get(reverse("hub:community", kwargs={"slug": community.slug})).content.decode()
        assert ">Pages</a>" not in body

    def test_footer_lists_member_visible_pages_capped_at_six(self, world):
        community, admin, coordinator, member = world
        _open_world(world)  # "Our story" + "Mass times"
        for i in range(6):
            p = _page(community, coordinator, title=f"Extra page {i}", slug=f"extra-{i}")
            p.publish(by=admin)
        body = _login(member).get(_feed(community.slug)).content.decode()
        assert "All pages" in body
        assert _index(community) in body
        # Eight published, capped at six: the extras (alphabetically first) fill
        # the column; "Mass times" falls past the cap.
        assert body.count("/p/extra-") == 6
        assert "Mass times" not in body

    def test_anon_footer_shows_only_preauth_pages(self, world):
        community, admin, coordinator, _ = world
        community.visibility = "public"
        community.save(update_fields=["visibility"])
        landing = _page(community, coordinator, title="Parish festival", slug="festival", show_on_landing=True)
        landing.publish(by=admin)
        quiet = _page(community, coordinator, title="Mass times", slug="mass-times")
        quiet.publish(by=admin)
        body = Client().get(_index(community)).content.decode()
        assert "Parish festival" in body
        assert "Mass times" not in body

    def test_footer_column_absent_off_community_and_when_empty(self, world):
        community, _, _, member = world
        # A community surface with nothing published: no column.
        body = _login(member).get(_feed(community.slug)).content.decode()
        assert "All pages" not in body
        # A mission page carries no community at all: no column.
        body = Client().get(reverse("about")).content.decode()
        assert "All pages" not in body


class TestFederationGuard:
    def test_pages_never_cross_the_wire(self):
        """§I not-do: local-only v1 — no federation serialization of pages.
        The guard is a source scan: the federation app must never name the
        pages app, its model, or its content column."""
        from pathlib import Path

        fed = Path("apps/federation")
        offenders = [
            str(p)
            for p in fed.rglob("*.py")
            if any(marker in p.read_text() for marker in ("CommunityPage", "apps.pages", "content_md"))
        ]
        assert offenders == []
