"""
Casework views (design §3.7). HTMX-first with plain-POST fallbacks; every
authorization decision goes through access.case_access(); every state change
goes through transition_to() and maps TransitionConflict → HTTP 409.
"""

import json
import time

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Case as SqlCase
from django.db.models import IntegerField, Q, Value, When
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.ratelimit import rate_limit
from apps.communities.models import Community
from apps.consent.models import Consent
from apps.people.models import Person

from . import access, audit
from .forms import AssignForm, CaseCreateForm, FollowUpForm, GrantForm, NoteForm, ReauthForm, VisitForm
from .middleware import mark_authenticated
from .models import CaseAccessGrant, CaseFile, CaseNote, FollowUp, WarmHandoff
from .notify import notify
from .state import TransitionConflict

VIEW_AUDIT_THROTTLE_SECONDS = 15 * 60  # case.viewed at most 1/15min/session/case


def _is_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _conflict(exc_or_msg) -> HttpResponse:
    msg = "; ".join(exc_or_msg.messages) if isinstance(exc_or_msg, TransitionConflict) else str(exc_or_msg)
    return HttpResponse(msg, status=409, content_type="text/plain")


def _forbidden(msg="You don't have access to this.") -> HttpResponse:
    return HttpResponseForbidden(msg)


class CommunityMixin(LoginRequiredMixin):
    """Resolves community + active membership for every casework view."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.community = get_object_or_404(Community, slug=kwargs["slug"], is_active=True)
        self.membership = access.get_membership(request.user, self.community)
        if self.membership is None:
            return _forbidden("You are not a member of this community.")
        return super().dispatch(request, *args, **kwargs)

    # ---- shared helpers -------------------------------------------------
    def get_case(self, pk) -> CaseFile:
        return get_object_or_404(
            CaseFile.objects.select_related("subject_person", "assigned_to", "opened_by", "consent"),
            pk=pk,
            community=self.community,
        )

    def contributable_cases(self):
        """Cases this member may ADD NOTES to (visit page + sync)."""
        m = self.membership
        qs = CaseFile.objects.filter(community=self.community, status__in=("open", "monitoring"))
        if not access.is_admin(m):
            now = timezone.now()
            grant_q = Q(grants__member=m, grants__role="contributor", grants__revoked_at__isnull=True) & (
                Q(grants__expires_at__isnull=True) | Q(grants__expires_at__gt=now)
            )
            role_q = Q(sensitivity="standard") if access.is_coordinator(m) else Q(pk=None)
            qs = qs.filter(Q(assigned_to=m) | Q(opened_by=m) | role_q | grant_q).distinct()
        return (
            qs.select_related("subject_person")
            .annotate(prio=SqlCase(When(assigned_to=m, then=Value(0)), default=Value(1), output_field=IntegerField()))
            .order_by("prio", "-updated_at")
        )

    def _consent_frozen(self, case) -> bool:
        """Revocation freeze (§3.6): consent was given but is no longer
        active → no new notes, no export. Emergency cases are exempt
        until consent is regularized."""
        return bool(case.consent_id) and not case.consent_is_active()


# ---------------------------------------------------------------------------
# Case list / create / detail
# ---------------------------------------------------------------------------
class CaseListView(CommunityMixin, View):
    def get(self, request, slug):
        if not access.is_coordinator(self.membership):
            return _forbidden("Case files are visible to coordinators and admins.")
        m, now = self.membership, timezone.now()
        qs = CaseFile.objects.filter(community=self.community).select_related("subject_person", "assigned_to")
        if not access.is_admin(m):
            grant_q = Q(grants__member=m, grants__revoked_at__isnull=True) & (
                Q(grants__expires_at__isnull=True) | Q(grants__expires_at__gt=now)
            )
            qs = qs.filter(Q(sensitivity="standard") | Q(assigned_to=m) | Q(opened_by=m) | grant_q).distinct()

        status = request.GET.get("status", "")
        if status in dict(CaseFile.STATUS_CHOICES):
            qs = qs.filter(status=status)
        if request.GET.get("mine") == "1":
            qs = qs.filter(assigned_to=m)

        cases = list(qs[:200])
        q = (request.GET.get("q") or "").strip()
        if q:  # encrypted names are unsearchable by design — code/paper ref only
            qu = q.upper()
            cases = [c for c in cases if qu in c.short_code or q.lower() in c.physical_ref.lower()]

        rows = [{"case": c, "name": c.subject_person.display_name or c.subject_person.short_code} for c in cases]
        template = "casework/_case_rows.html" if _is_htmx(request) else "casework/list.html"
        return render(
            request,
            template,
            {
                "community": self.community,
                "membership": m,
                "rows": rows,
                "status_filter": status,
                "q": q,
                "mine": request.GET.get("mine") == "1",
            },
        )


class CaseCreateView(CommunityMixin, View):
    def get(self, request, slug):
        if not access.is_coordinator(self.membership):
            return _forbidden("Only coordinators and admins can open cases.")
        form = CaseCreateForm(self.community, self.membership)
        return render(request, "casework/create.html", {"community": self.community, "form": form})

    def post(self, request, slug):
        if not access.is_coordinator(self.membership):
            return _forbidden("Only coordinators and admins can open cases.")
        form = CaseCreateForm(self.community, self.membership, request.POST)
        if not form.is_valid():
            return render(request, "casework/create.html", {"community": self.community, "form": form}, status=200)
        d = form.cleaned_data
        with transaction.atomic():
            person = d["person"]
            if not person:
                person = Person(created_in_community=self.community, created_by=self.membership)
                person.display_name = d["new_person_name"].strip()
                if d.get("new_person_contact"):
                    person.contact = {"raw": d["new_person_contact"].strip()}
                person.save()
                audit.emit("person.created", person, user=request.user, request=request)

            consent, emergency = None, False
            if d["consent_mode"] == "existing":
                consent = d["existing_consent"]
            elif d["consent_mode"] == "record":
                # A3: no-account subjects — coordinator stands as participant,
                # the paper/verbal record is the legal instrument.
                participant = person.linked_user if person.linked_user_id else request.user
                scope = ["case_records"] + (["case_export"] if d["include_export"] else [])
                consent = Consent.objects.create(
                    participant=participant,
                    granted_to=self.community.name[:200],
                    grantee_type="community",
                    grantee_id=self.community.id,
                    scope=scope,
                    purpose=f"Case records — {self.community.name}"[:500],
                    method=d["record_method"],
                    custom=({} if person.linked_user_id else {"on_behalf_person_id": str(person.id)}),
                )
            else:
                emergency = True

            case = CaseFile(
                community=self.community,
                subject_person=person,
                opened_by=self.membership,
                assigned_to=d["assigned_to"] or self.membership,
                sensitivity=d["sensitivity"],
                consent=consent,
                emergency_opened=emergency,
                emergency_justification=(d["emergency_justification"].strip() if emergency else ""),
                primary_needs=d["primary_needs"],
                intake_date=d["intake_date"],
                physical_ref=d["physical_ref"].strip(),
            )
            if d["summary"]:
                case.summary = d["summary"]
            case.save()

            if emergency:
                audit.emit(
                    "case.opened_emergency",
                    case,
                    user=request.user,
                    request=request,
                    details={"justification": case.emergency_justification[:500]},
                )
            else:
                audit.emit(
                    "case.opened", case, user=request.user, request=request, details={"consent_id": str(consent.pk)}
                )

            if case.assigned_to and case.assigned_to != self.membership:
                notify(
                    case.assigned_to.user,
                    "case_assigned",
                    f"Case {case.short_code} assigned to you",
                    "A new case file was assigned to you.",
                    reverse("casework:detail", kwargs={"slug": slug, "pk": case.pk}),
                )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class CaseDetailView(CommunityMixin, View):
    def get(self, request, slug, pk):
        case = self.get_case(pk)
        level = access.case_access(self.membership, case)
        if level == access.NONE:
            return _forbidden("You don't have access to this case.")

        # Warm-handoff gate (§3.6): the incoming member's FIRST screen is the
        # summary — no case data renders until they acknowledge.
        pending = case.handoffs.filter(to_member=self.membership, status="pending").first()
        if pending:
            return render(
                request, "casework/handoff_ack.html", {"community": self.community, "case": case, "handoff": pending}
            )

        # Read-access audit, throttled (§3.8)
        key, now = f"cw_viewed:{case.pk}", time.time()
        last = request.session.get(key)
        if not last or (now - last) > VIEW_AUDIT_THROTTLE_SECONDS:
            audit.emit("case.viewed", case, user=request.user, request=request)
            request.session[key] = now

        notes = case.notes.exclude(status=CaseNote.STATUS_DISCARDED).select_related("author", "co_visitor", "amends")
        visible_notes = [n for n in notes if n.status == CaseNote.STATUS_FINAL or n.author_id == self.membership.id]

        can_contribute = level >= access.CONTRIBUTOR
        can_assign = access.is_admin(self.membership) or case.assigned_to_id == self.membership.id
        can_export = (
            access.is_admin(self.membership)
            and case.consent_id
            and case.consent_is_active()
            and "case_export" in (case.consent.scope or [])
        )

        return render(
            request,
            "casework/detail.html",
            {
                "community": self.community,
                "membership": self.membership,
                "case": case,
                "level": level,
                "person_name": case.subject_person.display_name or case.subject_person.short_code,
                "notes": visible_notes,
                "followups": case.followups.filter(status="open").select_related("assigned_to"),
                "grants": case.grants.filter(revoked_at__isnull=True).select_related("member"),
                "handoffs": case.handoffs.select_related("from_member", "to_member")[:5],
                "note_form": NoteForm(self.community),
                "followup_form": FollowUpForm(self.community),
                "assign_form": AssignForm(self.community, exclude_member=case.assigned_to),
                "grant_form": GrantForm(self.community),
                "can_contribute": can_contribute,
                "can_assign": can_assign,
                "can_grant": can_assign,
                "can_export": can_export,
                "is_admin": access.is_admin(self.membership),
                "consent_frozen": self._consent_frozen(case),
            },
        )


# ---------------------------------------------------------------------------
# Status / assign / handoff
# ---------------------------------------------------------------------------
class CaseStatusView(CommunityMixin, View):
    def post(self, request, slug, pk):
        case = self.get_case(pk)
        if access.case_access(self.membership, case) < access.CONTRIBUTOR:
            return _forbidden("You can't change this case's status.")
        new = request.POST.get("status", "")
        if new not in dict(CaseFile.STATUS_CHOICES):
            return HttpResponse("Unknown status.", status=400)
        reopen = case.status == CaseFile.STATUS_CLOSED and new == CaseFile.STATUS_OPEN
        if reopen and not access.is_admin(self.membership):
            return _forbidden("Only admins can reopen a closed case.")
        try:
            if new == CaseFile.STATUS_OPEN:
                case.closed_at = None
                case.transition_to(new, extra_update_fields=("closed_at",))
            else:
                case.transition_to(new)
        except TransitionConflict as exc:
            return _conflict(exc)
        audit.emit(
            "case.reopened" if reopen else "case.status_changed",
            case,
            user=request.user,
            request=request,
            details={"to": new},
        )
        if _is_htmx(request):
            return render(
                request,
                "casework/_case_status.html",
                {"community": self.community, "case": case, "is_admin": access.is_admin(self.membership)},
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class CaseAssignView(CommunityMixin, View):
    def post(self, request, slug, pk):
        case = self.get_case(pk)
        if not (access.is_admin(self.membership) or case.assigned_to_id == self.membership.id):
            return _forbidden("Only an admin or the current assignee can hand off.")
        form = AssignForm(self.community, exclude_member=case.assigned_to, data=request.POST)
        if not form.is_valid():
            return HttpResponse(form.errors.as_text(), status=400)
        to_member = form.cleaned_data["to_member"]
        with transaction.atomic():
            ho = WarmHandoff(case=case, from_member=self.membership, to_member=to_member)
            ho.summary = form.cleaned_data["summary"]
            ho.save()
            sysnote = CaseNote(
                case=case,
                author=self.membership,
                kind="handoff",
                occurred_at=timezone.now(),
                status=CaseNote.STATUS_FINAL,
                finalized_at=timezone.now(),
            )
            sysnote.body = f"Case handed off from {self.membership.display_name} to {to_member.display_name}."
            sysnote.save()
            case.assigned_to = to_member
            case.save(update_fields=["assigned_to", "updated_at"])
            audit.emit(
                "case.assigned", case, user=request.user, request=request, details={"to_member": str(to_member.pk)}
            )
            notify(
                to_member.user,
                "handoff_pending",
                f"Case {case.short_code} handed to you",
                "Read the handoff summary — it's your first screen.",
                reverse("casework:detail", kwargs={"slug": slug, "pk": case.pk}),
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class HandoffAckView(CommunityMixin, View):
    def post(self, request, slug, pk, handoff_id):
        case = self.get_case(pk)
        handoff = get_object_or_404(WarmHandoff, pk=handoff_id, case=case)
        if handoff.to_member_id != self.membership.id:
            return _forbidden("Only the receiving visitor can acknowledge.")
        try:
            handoff.transition_to("acknowledged")
        except TransitionConflict as exc:
            return _conflict(exc)
        audit.emit("handoff.acknowledged", handoff, user=request.user, request=request)
        return redirect("casework:detail", slug=slug, pk=case.pk)


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
class NoteCreateView(CommunityMixin, View):
    def post(self, request, slug, pk):
        case = self.get_case(pk)
        if access.case_access(self.membership, case) < access.CONTRIBUTOR:
            return _forbidden("You can't add notes to this case.")
        if self._consent_frozen(case):
            return _forbidden("Consent was revoked — new notes are frozen; close the case via status instead.")
        form = NoteForm(self.community, request.POST)
        if not form.is_valid():
            return HttpResponse(form.errors.as_text(), status=400)
        d = form.cleaned_data
        note = CaseNote(
            case=case,
            author=self.membership,
            kind=d["kind"],
            occurred_at=d["occurred_at"],
            duration_minutes=d["duration_minutes"],
            location_kind=d["location_kind"],
            actions=d["actions"],
            aid_value_cents=form.aid_cents(),
            co_visitor=d["co_visitor"],
            client_uuid=d["client_uuid"] or None,
        )
        note.body = d["body"]
        try:
            note.save()
        except IntegrityError:  # client_uuid replay via the online form
            existing = CaseNote.objects.get(client_uuid=d["client_uuid"])
            return self._respond(request, slug, case, existing)
        if "finalize" in request.POST:
            note.transition_to(CaseNote.STATUS_FINAL)
            audit.emit("note.finalized", note, user=request.user, request=request)
        return self._respond(request, slug, case, note)

    def _respond(self, request, slug, case, note):
        if _is_htmx(request):
            return render(
                request,
                "casework/_note.html",
                {
                    "community": self.community,
                    "case": case,
                    "note": note,
                    "membership": self.membership,
                    "can_contribute": True,
                },
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class NoteFinalizeView(CommunityMixin, View):
    def post(self, request, slug, pk, note_id):
        case = self.get_case(pk)
        note = get_object_or_404(CaseNote, pk=note_id, case=case)
        if note.author_id != self.membership.id:
            return _forbidden("Only the author can finalize a draft.")
        try:
            note.transition_to(CaseNote.STATUS_FINAL)
        except TransitionConflict as exc:
            return _conflict(exc)
        action = "note.amended" if note.amends_id else "note.finalized"
        audit.emit(
            action,
            note,
            user=request.user,
            request=request,
            details=({"amends": str(note.amends_id)} if note.amends_id else None),
        )
        if _is_htmx(request):
            return render(
                request,
                "casework/_note.html",
                {
                    "community": self.community,
                    "case": case,
                    "note": note,
                    "membership": self.membership,
                    "can_contribute": True,
                },
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class NoteAmendView(CommunityMixin, View):
    def post(self, request, slug, pk, note_id):
        case = self.get_case(pk)
        if access.case_access(self.membership, case) < access.CONTRIBUTOR:
            return _forbidden("You can't amend notes on this case.")
        original = get_object_or_404(CaseNote, pk=note_id, case=case)
        if original.status != CaseNote.STATUS_FINAL:
            return _conflict("Only finalized notes can be amended (discard drafts instead).")
        body = (request.POST.get("body") or "").strip()
        if not body:
            return HttpResponse("Amendment text is required.", status=400)
        note = CaseNote(
            case=case,
            author=self.membership,
            kind=original.kind,
            occurred_at=timezone.now(),
            location_kind=original.location_kind,
            amends=original,
        )
        note.body = body
        note.save()
        if "finalize" in request.POST:
            note.transition_to(CaseNote.STATUS_FINAL)
            audit.emit("note.amended", note, user=request.user, request=request, details={"amends": str(original.pk)})
        if _is_htmx(request):
            return render(
                request,
                "casework/_note.html",
                {
                    "community": self.community,
                    "case": case,
                    "note": note,
                    "membership": self.membership,
                    "can_contribute": True,
                },
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class NoteDiscardView(CommunityMixin, View):
    def post(self, request, slug, pk, note_id):
        case = self.get_case(pk)
        note = get_object_or_404(CaseNote, pk=note_id, case=case)
        if note.author_id != self.membership.id:
            return _forbidden("Only the author can discard a draft.")
        try:
            note.transition_to(CaseNote.STATUS_DISCARDED)
        except TransitionConflict as exc:
            return _conflict(exc)
        if _is_htmx(request):
            return HttpResponse("")  # hx-swap=outerHTML removes the card
        return redirect("casework:detail", slug=slug, pk=case.pk)


# ---------------------------------------------------------------------------
# Visit capture + offline (item 4)
# ---------------------------------------------------------------------------
class VisitCaptureView(CommunityMixin, View):
    def get(self, request, slug):
        form = VisitForm(self.community, self.contributable_cases())
        return render(
            request,
            "casework/visit.html",
            {"community": self.community, "form": form, "saved": request.GET.get("saved", "")},
        )

    def post(self, request, slug):
        form = VisitForm(self.community, self.contributable_cases(), data=request.POST)
        if not form.is_valid():
            return render(request, "casework/visit.html", {"community": self.community, "form": form, "saved": ""})
        d = form.cleaned_data
        case = d["case"]
        if self._consent_frozen(case):
            return _forbidden("Consent was revoked — new notes are frozen.")
        note = CaseNote(
            case=case,
            author=self.membership,
            kind=d["kind"],
            occurred_at=d["occurred_at"],
            duration_minutes=d["duration_minutes"],
            location_kind=d["location_kind"],
            actions=d["actions"],
            aid_value_cents=form.aid_cents(),
            co_visitor=d["co_visitor"],
            client_uuid=d["client_uuid"] or None,
        )
        note.body = d["body"]
        try:
            note.save()
        except IntegrityError:
            return redirect(f"{reverse('casework:visit', kwargs={'slug': slug})}?saved={case.short_code}")
        if "finalize" in request.POST:
            note.transition_to(CaseNote.STATUS_FINAL)
            audit.emit("note.finalized", note, user=request.user, request=request)
        return redirect(f"{reverse('casework:visit', kwargs={'slug': slug})}?saved={case.short_code}")


class VisitManifestView(CommunityMixin, View):
    """Minimal offline case list: short codes + initials ONLY — never names,
    never bodies (design §3.6, deliberate deviation from the manual)."""

    def get(self, request, slug):
        cases = [
            {"id": str(c.id), "code": c.short_code, "initials": c.subject_person.initials}
            for c in self.contributable_cases()[:50]
        ]
        resp = JsonResponse({"cases": cases})
        resp["Cache-Control"] = "private, max-age=0"
        return resp


class ServiceWorkerView(CommunityMixin, TemplateView):
    """Serves the SW from /c/<slug>/cases/visit/sw.js so its scope is
    naturally limited to the visit routes — it can never cache the rest
    of the app."""

    template_name = "casework/sw.js"
    content_type = "text/javascript"


@method_decorator(rate_limit("cw-sync", 30, 60, by="user"), name="post")
class SyncView(CommunityMixin, View):
    """POST /c/<slug>/cases/sync/ — idempotent by client_uuid (item 4)."""

    def post(self, request, slug):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)
        results = []
        for item in (payload.get("drafts") or [])[:50]:
            results.append(self._one(request, slug, item))
        return JsonResponse({"results": results})

    def _one(self, request, slug, item):
        cu = item.get("client_uuid")
        if not cu:
            return {"client_uuid": None, "status": "error", "error": "client_uuid required"}
        existing = CaseNote.objects.filter(client_uuid=cu).first()
        if existing:
            return {"client_uuid": cu, "status": "duplicate", "note_id": str(existing.pk)}
        try:
            case = CaseFile.objects.select_related("consent", "subject_person").get(
                pk=item.get("case_id"), community=self.community
            )
        except (CaseFile.DoesNotExist, ValueError, TypeError):
            return {"client_uuid": cu, "status": "error", "error": "unknown case"}
        if access.case_access(self.membership, case) < access.CONTRIBUTOR:
            return {"client_uuid": cu, "status": "error", "error": "forbidden"}
        if self._consent_frozen(case):
            return {"client_uuid": cu, "status": "error", "error": "consent_revoked"}

        body = (item.get("body") or "").strip()
        if not body:
            return {"client_uuid": cu, "status": "error", "error": "body required"}
        occurred = parse_datetime((item.get("occurred_at") or "").replace("Z", "+00:00"))
        if occurred is None:
            occurred = timezone.now()
        elif timezone.is_naive(occurred):
            occurred = timezone.make_aware(occurred)
        kind = item.get("kind") if item.get("kind") in dict(CaseNote.KIND_CHOICES) else "visit"
        allowed_actions = {a for a, _ in CaseNote.ACTIONS}
        actions = [a for a in (item.get("actions") or []) if a in allowed_actions]
        try:
            duration = int(item["duration_minutes"]) if item.get("duration_minutes") else None
        except (ValueError, TypeError):
            duration = None
        try:
            aid_cents = int(item["aid_value_cents"]) if item.get("aid_value_cents") not in (None, "") else None
        except (ValueError, TypeError):
            aid_cents = None

        note = CaseNote(
            case=case,
            author=self.membership,
            kind=kind,
            occurred_at=occurred,
            duration_minutes=duration,
            actions=actions,
            aid_value_cents=aid_cents,
            location_kind=item.get("location_kind", "home")
            if item.get("location_kind") in dict(CaseNote.LOCATION_CHOICES)
            else "home",
            client_uuid=cu,
        )
        note.body = body[:8000]
        try:
            note.save()
        except IntegrityError:  # replay race on the unique client_uuid
            existing = CaseNote.objects.get(client_uuid=cu)
            return {"client_uuid": cu, "status": "duplicate", "note_id": str(existing.pk)}
        audit.emit("note.synced_offline", note, user=request.user, request=request, details={"client_uuid": str(cu)})
        if item.get("finalize", True):
            note.transition_to(CaseNote.STATUS_FINAL)
            audit.emit("note.finalized", note, user=request.user, request=request)
        return {
            "client_uuid": cu,
            "status": "created",
            "note_id": str(note.pk),
            "dup_warning": note.duplicate_suspects.exists(),
        }


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------
class FollowUpCreateView(CommunityMixin, View):
    def post(self, request, slug, pk):
        case = self.get_case(pk)
        if access.case_access(self.membership, case) < access.CONTRIBUTOR:
            return _forbidden("You can't add follow-ups to this case.")
        form = FollowUpForm(self.community, request.POST)
        if not form.is_valid():
            return HttpResponse(form.errors.as_text(), status=400)
        d = form.cleaned_data
        source = None
        if d.get("source_note"):
            source = CaseNote.objects.filter(pk=d["source_note"], case=case).first()
        fu = FollowUp(
            case=case,
            created_by=self.membership,
            assigned_to=d["assigned_to"],
            title=d["title"].strip(),
            due_date=d["due_date"],
            source_note=source,
        )
        if d.get("detail"):
            fu.detail = d["detail"]
        fu.save()
        audit.emit("followup.created", fu, user=request.user, request=request)
        if fu.assigned_to_id != self.membership.id:
            notify(
                fu.assigned_to.user,
                "followup_assigned",
                f"Follow-up on case {case.short_code}",
                fu.title,
                reverse("casework:followups-mine", kwargs={"slug": slug}),
            )
        if _is_htmx(request):
            return render(
                request,
                "casework/_followup_row.html",
                {"community": self.community, "fu": fu, "membership": self.membership},
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class FollowUpStatusView(CommunityMixin, View):
    def post(self, request, slug, pk):
        fu = get_object_or_404(
            FollowUp.objects.select_related("case", "assigned_to"), pk=pk, case__community=self.community
        )
        allowed = (
            fu.assigned_to_id == self.membership.id
            or fu.created_by_id == self.membership.id
            or access.is_admin(self.membership)
        )
        if not allowed:
            return _forbidden("Only the assignee, creator, or an admin can update this follow-up.")
        new = request.POST.get("status", "")
        if new not in ("done", "cancelled"):
            return HttpResponse("Unknown status.", status=400)
        try:
            fu.transition_to(new)
        except TransitionConflict as exc:
            return _conflict(exc)
        audit.emit(f"followup.{new}", fu, user=request.user, request=request)
        if _is_htmx(request):
            return render(
                request,
                "casework/_followup_row.html",
                {"community": self.community, "fu": fu, "membership": self.membership},
            )
        return redirect("casework:detail", slug=slug, pk=fu.case_id)


class MyFollowUpsView(CommunityMixin, View):
    def get(self, request, slug):
        items = (
            FollowUp.objects.filter(assigned_to=self.membership, status="open", case__community=self.community)
            .select_related("case")
            .order_by("due_date")
        )
        ctx = {
            "community": self.community,
            "membership": self.membership,
            "items": items,
            "today": timezone.localdate(),
        }
        if _is_htmx(request):
            return render(request, "casework/_followups_mine.html", ctx)
        return render(request, "casework/followups_mine.html", ctx)


# ---------------------------------------------------------------------------
# Grants / export / re-auth / validation
# ---------------------------------------------------------------------------
class GrantCreateView(CommunityMixin, View):
    def post(self, request, slug, pk):
        case = self.get_case(pk)
        if not (access.is_admin(self.membership) or case.assigned_to_id == self.membership.id):
            return _forbidden("Only an admin or the assignee can grant access.")
        form = GrantForm(self.community, request.POST)
        if not form.is_valid():
            return HttpResponse(form.errors.as_text(), status=400)
        target = form.cleaned_data["member"]
        if target.pk == self.membership.pk:
            return HttpResponse("You already have access.", status=400)
        try:
            grant = CaseAccessGrant.objects.create(
                case=case,
                member=target,
                role=form.cleaned_data["role"],
                granted_by=self.membership,
                reason=form.cleaned_data["reason"].strip(),
                expires_at=form.cleaned_data["expires_at"],
            )
        except IntegrityError:
            return _conflict("That member already has an active grant.")
        audit.emit(
            "grant.granted",
            grant,
            user=request.user,
            request=request,
            details={"member": str(target.pk), "role": grant.role, "case": str(case.pk)},
        )
        notify(
            target.user,
            "case_grant",
            f"Access granted: case {case.short_code}",
            f"{grant.role.title()} access — {grant.reason}",
            reverse("casework:detail", kwargs={"slug": slug, "pk": case.pk}),
        )
        if _is_htmx(request):
            return render(
                request, "casework/_grant_row.html", {"community": self.community, "case": case, "grant": grant}
            )
        return redirect("casework:detail", slug=slug, pk=case.pk)


class GrantRevokeView(CommunityMixin, View):
    def post(self, request, slug, pk, grant_id):
        case = self.get_case(pk)
        if not (access.is_admin(self.membership) or case.assigned_to_id == self.membership.id):
            return _forbidden("Only an admin or the assignee can revoke access.")
        grant = get_object_or_404(CaseAccessGrant, pk=grant_id, case=case)
        if grant.revoked_at:
            return _conflict("That grant is already revoked.")
        grant.revoked_at = timezone.now()
        grant.save(update_fields=["revoked_at"])
        audit.emit(
            "grant.revoked",
            grant,
            user=request.user,
            request=request,
            details={"member": str(grant.member_id), "case": str(case.pk)},
        )
        if _is_htmx(request):
            return HttpResponse("")
        return redirect("casework:detail", slug=slug, pk=case.pk)


@method_decorator(rate_limit("cw-export", 10, 3600, by="user"), name="get")
class CaseExportView(CommunityMixin, View):
    def get(self, request, slug, pk):
        case = self.get_case(pk)
        if not access.is_admin(self.membership):
            return _forbidden("Exports are admin-only.")
        if not (case.consent_id and case.consent_is_active() and "case_export" in (case.consent.scope or [])):
            return _forbidden("No active consent covering export (case_export).")
        p = case.subject_person
        lines = [
            f"CASE EXPORT — {case.short_code}",
            f"Community: {self.community.name}",
            f"Exported: {timezone.now().isoformat()} by {request.user}",
            "",
            "SUBJECT",
            f"  Name: {p.display_name or '—'}",
            f"  Contact: {p.contact or '—'}",
            f"  DOB: {p.dob or '—'}",
            "",
            "CASE",
            f"  Status: {case.status} · Sensitivity: {case.sensitivity}",
            f"  Opened: {case.intake_date} by {case.opened_by.display_name}",
            f"  Assigned: {case.assigned_to.display_name if case.assigned_to else '—'}",
            f"  Primary needs: {', '.join(case.primary_needs) or '—'}",
            f"  Paper ref: {case.physical_ref or '—'}",
            f"  Summary: {case.summary or '—'}",
            "",
            "NOTES (finalized)",
        ]
        for n in case.notes.filter(status=CaseNote.STATUS_FINAL).order_by("occurred_at").select_related("author"):
            aid = f" · aid ${n.aid_value_cents / 100:.2f}" if n.aid_value_cents else ""
            lines += [
                f"--- {n.occurred_at:%Y-%m-%d %H:%M} · {n.kind} · {n.author.display_name}{aid}",
                f"    actions: {', '.join(n.actions) or '—'}",
                f"    {n.body or ''}",
            ]
        lines += ["", "FOLLOW-UPS"]
        for fu in case.followups.all():
            lines.append(f"  [{fu.status}] {fu.title} — due {fu.due_date}")
        audit.emit("case.exported", case, user=request.user, request=request, details={"scope": case.consent.scope})
        resp = HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="case-{case.short_code}.txt"'
        return resp


@method_decorator(rate_limit("cw-reauth", 5, 60, by="ip"), name="post")
class ReauthView(CommunityMixin, View):
    """4-hour sensitive-session confirmation (§3.8)."""

    def get(self, request, slug):
        return render(
            request,
            "casework/reauth.html",
            {"community": self.community, "form": ReauthForm(), "next": request.GET.get("next", "")},
        )

    def post(self, request, slug):
        form = ReauthForm(request.POST)
        if form.is_valid() and request.user.check_password(form.cleaned_data["password"]):
            mark_authenticated(request)
            nxt = request.POST.get("next") or request.GET.get("next") or ""
            if nxt and url_has_allowed_host_and_scheme(
                nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(nxt)
            return redirect("casework:list", slug=slug)
        form.add_error("password", "That password didn't match.")
        return render(
            request,
            "casework/reauth.html",
            {"community": self.community, "form": form, "next": request.POST.get("next", "")},
            status=200,
        )


class ValidateFieldView(CommunityMixin, View):
    """Inline HTMX validation: returns the error list for one field."""

    FORMS = {"note": "note", "followup": "followup", "case": "case"}

    def post(self, request, slug):
        which = request.POST.get("form", "")
        field = request.POST.get("field", "")
        if which == "note":
            form = NoteForm(self.community, request.POST)
        elif which == "followup":
            form = FollowUpForm(self.community, request.POST)
        elif which == "case":
            form = CaseCreateForm(self.community, self.membership, request.POST)
        else:
            return HttpResponse("", status=400)
        form.is_valid()
        return render(request, "casework/_field_errors.html", {"errors": form.errors.get(field, [])})
