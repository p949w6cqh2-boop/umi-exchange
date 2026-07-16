"""The "Your pages" manager (§E) behind the §F gates: coordinators draft and
edit; ONLY admins publish — the priest signs, and signs again after every fix.
Browsable surfaces soft-redirect plain members (settings precedent); POST-only
role gates raise PermissionDenied (403); state races map to 409.

S3 adds the read surfaces (§I): the /p/ index and page views. The anonymous
no-oracle rule governs every logged-out failure — missing community, private
community, draft, hidden, archived, or no such page all answer with the one
identical login redirect. Nothing about the database shows through it."""

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.audit.services import emit
from apps.common.state import TransitionConflict
from apps.communities.models import Community, Member

from .forms import CommunityPageForm
from .models import CommunityPage
from .render import render_page_html


class ManagerAccessMixin:
    """Community + member resolution for the manage surfaces: anonymous →
    login redirect; strangers → 404; members → warm bounce to the feed (§F)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.member = get_object_or_404(Member, user=request.user, community=self.community, is_active=True)
        if self.member.role not in ("admin", "coordinator"):
            messages.error(request, "Only coordinators and admins manage community pages.")
            return redirect("community-feed", slug=self.community.slug)
        return super().dispatch(request, *args, **kwargs)

    def _get_page(self, pk):
        return get_object_or_404(CommunityPage, community=self.community, pk=pk)


class ManageListView(ManagerAccessMixin, View):
    def get(self, request, slug):
        pages = CommunityPage.objects.filter(community=self.community)
        return render(
            request,
            "community_pages/manage.html",
            {"community": self.community, "member": self.member, "pages": pages},
        )


class _EditorBase(ManagerAccessMixin, View):
    def _render_form(self, request, form, page=None, status=200):
        return render(
            request,
            "community_pages/editor.html",
            {"community": self.community, "member": self.member, "form": form, "page": page},
            status=status,
        )


class PageCreateView(_EditorBase):
    def get(self, request, slug):
        return self._render_form(request, CommunityPageForm(community=self.community))

    def post(self, request, slug):
        form = CommunityPageForm(request.POST, community=self.community)
        if not form.is_valid():
            return self._render_form(request, form)
        page = form.save(commit=False)
        page.community = self.community
        page.created_by = self.member
        page.updated_by = self.member
        page.save()
        emit("page.created", page, user=request.user, request=request, details={"slug": page.slug})
        messages.success(request, "Draft saved. Shape it freely — an admin publishes it when it's ready.")
        return redirect("pages:edit", slug=slug, pk=page.pk)


class PageEditView(_EditorBase):
    def get(self, request, slug, pk):
        page = self._get_page(pk)
        form = CommunityPageForm(instance=page, community=self.community)
        return self._render_form(request, form, page=page)

    def post(self, request, slug, pk):
        page = self._get_page(pk)
        if page.status != "draft":
            # §F: "edit published in place" is not an action that exists; archived
            # pages come back through restore first.
            raise PermissionDenied("Live pages aren't edited in place. Unpublish to draft first.")
        form = CommunityPageForm(request.POST, instance=page, community=self.community)
        if not form.is_valid():
            return self._render_form(request, form, page=page)
        page = form.save(commit=False)
        page.updated_by = self.member
        page.save()
        emit("page.updated", page, user=request.user, request=request, details={"slug": page.slug})
        messages.success(request, "Saved.")
        return redirect("pages:edit", slug=slug, pk=page.pk)


class PreviewView(ManagerAccessMixin, View):
    """Server-rendered preview of UNSAVED text — the identical pipeline, POST
    body only, never persisted (§E)."""

    def post(self, request, slug):
        html = render_page_html(request.POST.get("content_md", ""))
        return render(request, "community_pages/_preview.html", {"preview_html": html})


class _ActionView(ManagerAccessMixin, View):
    admin_only = False
    audit_action = ""
    done_message = ""

    def post(self, request, slug, pk):
        page = self._get_page(pk)
        if self.admin_only and self.member.role != "admin":
            raise PermissionDenied("Only admins publish — that's the community's signature.")
        try:
            self.act(request, page)
        except TransitionConflict as e:
            return HttpResponse(str(e.message), status=409)
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
            return redirect("pages:manage", slug=slug)
        emit(self.audit_action, page, user=request.user, request=request, details={"slug": page.slug})
        if self.done_message:
            messages.success(request, self.done_message.format(title=page.title))
        return redirect("pages:manage", slug=slug)


class PublishView(_ActionView):
    admin_only = True
    audit_action = "page.published"
    done_message = "“{title}” is live."

    def act(self, request, page):
        page.publish(by=self.member)


class UnpublishView(_ActionView):
    admin_only = True
    audit_action = "page.unpublished"
    done_message = "“{title}” is back in draft. Fix it, and publish again when it's right."

    def act(self, request, page):
        page.transition_to("draft")


class ArchiveView(_ActionView):
    audit_action = "page.archived"
    done_message = "“{title}” is put away. Nothing here is ever deleted."

    def act(self, request, page):
        if page.status == "published" and self.member.role != "admin":
            raise PermissionDenied("Taking a live page down is an admin's call.")
        page.transition_to("archived")


class RestoreView(_ActionView):
    audit_action = "page.restored"
    done_message = "“{title}” is back as a draft."

    def act(self, request, page):
        page.restore()


class ToggleLandingView(_ActionView):
    audit_action = "page.updated"
    done_message = ""

    def act(self, request, page):
        page.show_on_landing = not page.show_on_landing
        page.save()


class UnhideView(_ActionView):
    """Reverses a moderation hide (§H) — the same reversible boolean the queue
    flips, offered from the coordinator's hidden-banner (wireframe 05)."""

    audit_action = "content.unhidden"
    done_message = "“{title}” is back on the board."

    def act(self, request, page):
        page.moderation_hidden = False
        page.save(update_fields=["moderation_hidden"])


# ---------------------------------------------------------------------------
# §I — the read surfaces: index, page, tombstone. Anonymous failure = the one
# identical login redirect (no-oracle); authenticated failure = 404.
# ---------------------------------------------------------------------------


def _membership(request, community):
    """The viewer's Member row in this community, or None (stranger)."""
    if not request.user.is_authenticated:
        return None
    return Member.objects.filter(user=request.user, community=community, is_active=True).first()


class _PublicSurface(View):
    """Shared resolution for the read surfaces. Sets self.community and
    self.member (None = stranger or anonymous)."""

    def dispatch(self, request, *args, **kwargs):
        self.community = Community.objects.filter(slug=kwargs["slug"], is_active=True).first()
        if self.community is None:
            return self.refuse(request)
        self.member = _membership(request, self.community)
        return super().dispatch(request, *args, **kwargs)

    @property
    def is_coordinator(self):
        return self.member is not None and self.member.is_coordinator

    def refuse(self, request):
        """The §I refusal: anonymous eyes get the login redirect, signed-in ones a 404."""
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        raise Http404


class PagesIndexView(_PublicSurface):
    """/c/<slug>/p/ — the index (§I, wireframe 07): anonymous and strangers see
    landing-marked pages with the join door; members see everything published;
    coordinators also see chip rows for drafts, archived, and hidden."""

    def get(self, request, slug):
        chips = None
        if self.member is None:
            pages = CommunityPage.objects.pre_auth_visible(self.community).order_by("sort_order", "title")
            if not pages.exists():
                return self.refuse(request)
        else:
            pages = CommunityPage.objects.member_visible(self.community).order_by("sort_order", "title")
            if self.is_coordinator:
                chips = (
                    CommunityPage.objects.filter(community=self.community)
                    .exclude(status="published", moderation_hidden=False)
                    .order_by("sort_order", "title")
                )
        return render(
            request,
            "community_pages/index.html",
            {"community": self.community, "pages": pages, "member": self.member, "chips": chips},
        )


class PageView(_PublicSurface):
    """/c/<slug>/p/<page_slug>/ — one page (§I, wireframes 05/06/09). A live row
    (draft or published) owns its slug; the tombstone answers only when nothing
    lives there and something archived did."""

    def get(self, request, slug, page_slug):
        if self.member is None:
            # Anonymous and strangers: only the pre-auth-eligible page renders.
            page = CommunityPage.objects.pre_auth_visible(self.community).filter(slug=page_slug).first()
            if page is None:
                return self.refuse(request)
            return render(request, "community_pages/page_public.html", {"community": self.community, "page": page})

        live = CommunityPage.objects.filter(community=self.community, slug=page_slug).exclude(status="archived").first()
        if live is not None:
            if (live.status == "draft" or live.moderation_hidden) and not self.is_coordinator:
                raise Http404
            return render(
                request,
                "community_pages/page.html",
                {"community": self.community, "page": live, "member": self.member},
            )

        archived_here = CommunityPage.objects.filter(
            community=self.community, slug=page_slug, status="archived"
        ).exists()
        if archived_here:
            # Put away, not teased: the tombstone never carries the title (wireframe 09).
            return render(
                request,
                "community_pages/tombstone.html",
                {"community": self.community, "member": self.member, "is_coordinator": self.is_coordinator},
            )
        raise Http404
