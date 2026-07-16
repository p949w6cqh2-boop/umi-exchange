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
