"""
Federation Stage A views: the public instance document, the two handshake
wire endpoints (§3.3), and the community-admin link-management page.

The wire endpoints are csrf_exempt: they are server-to-server, carry no
session/cookie auth, and authenticate via the signed JWS envelope (§3.2)
— CSRF protects cookie-authenticated browsers, which these are not.
"""

import json
import uuid
from datetime import timedelta

from django.conf import settings as dj_settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.ratelimit import check as ratelimit_check
from apps.accounts.ratelimit import rate_limit
from apps.audit.services import emit
from apps.common.state import TransitionConflict
from apps.communities.models import Community, Member

from . import client as client_mod
from . import crypto, matching, mirror
from .client import FederationClientError
from .crypto import FederationAuthError
from .discovery import redact
from .models import FederatedMatch, FederatedShare, FederationLink, FederationPeer, ShadowListing

MAX_BODY_BYTES = 10_000
PAIRING_TTL = timedelta(hours=24)

# M-2: §11 per-PEER wire caps (per hour). The by="ip" decorators are a cheap
# pre-auth flood guard; these are the real per-peer ceilings, checked INSIDE each
# view AFTER verify_signed_request resolves the peer (the peer identity isn't
# known before the view runs, and re-verifying in the decorator would consume the
# jti nonce twice and break replay protection). Named so the mechanism is testable.
FED_PEER_HOURLY_CAPS = {"discovery": 60, "proposals": 30, "revocations": 60, "events": 120, "sync": 120, "attest": 60}


def _peer_over_cap(endpoint, peer) -> bool:
    """True if this peer has exceeded its per-hour cap for `endpoint`."""
    allowed, _remaining, _reset = ratelimit_check(
        f"fed-{endpoint}:{peer.instance_id}", FED_PEER_HOURLY_CAPS[endpoint], 3600
    )
    return not allowed


class FederationGateMixin:
    """Defense in depth: routes are only registered when FEDERATION_ENABLED,
    and every view 404s independently when the flag is off."""

    def dispatch(self, request, *args, **kwargs):
        if not dj_settings.FEDERATION_ENABLED:
            raise Http404
        return super().dispatch(request, *args, **kwargs)


# ── Public instance document (§3.1) ──────────────────


class WellKnownView(FederationGateMixin, View):
    def get(self, request):
        resp = JsonResponse({"umi_federation": "1", "document": crypto.build_instance_document()})
        resp["Cache-Control"] = "public, max-age=3600"
        return resp


# ── Wire endpoints (§3.3) ────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-handshake", 5, 3600, by="ip"), name="post")
class HandshakeView(FederationGateMixin, View):
    """Inbound link request. Unauthenticated by design (the requester is not
    yet a peer); rate-limited; stores only a pending peer + pairing material.
    Nothing is shared and nothing activates without a human admin (§3.3)."""

    def post(self, request):
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"error": "too_large"}, status=400)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        try:
            doc = crypto.verify_instance_document(str(payload.get("document", "")))
        except FederationAuthError:
            return JsonResponse({"error": "bad_document"}, status=400)

        pairing = payload.get("pairing") or {}
        salt = str(pairing.get("salt", ""))[:64]
        code_hash = str(pairing.get("hash", ""))[:64]
        community = payload.get("community") or {}
        if not (salt and code_hash):
            return JsonResponse({"error": "bad_pairing"}, status=400)

        peer = FederationPeer.objects.filter(instance_id=doc["instance_id"]).first()
        if peer is not None and peer.status == "blocked":
            return JsonResponse({"error": "blocked"}, status=403)
        if peer is None:
            peer = FederationPeer(instance_id=doc["instance_id"], jwk=doc["jwk"], status="pending")
        if peer.status == "pending":
            # Identity material may only change while unapproved; an active
            # peer's pinned JWK is never overwritten by this endpoint.
            peer.jwk = doc["jwk"]
            peer.base_url = str(doc.get("base_url", ""))[:200]
            peer.locality = str(doc.get("locality", ""))[:100]
            peer.capabilities = doc.get("capabilities") or []
        peer.pairing_salt = salt
        peer.pairing_hash = code_hash
        peer.pairing_expires_at = timezone.now() + PAIRING_TTL
        peer.requested_communities = [
            {"uuid": str(community.get("uuid", ""))[:36], "label": str(community.get("label", ""))[:200]}
        ]
        # M-1: the local community the requester wants to link to (OUR slug), so
        # the pending list can be scoped to that community's admins.
        peer.target_community_slug = str(payload.get("target_community", ""))[:64]
        peer.save()
        emit("fed.link_requested", peer, request=request, details={"origin": "inbound"})
        return JsonResponse({"status": "pending"})


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-confirm", 30, 3600, by="ip"), name="post")
class HandshakeConfirmView(FederationGateMixin, View):
    """Signed completion of a handshake WE initiated: the peer's admin entered
    the pairing code we minted; possession, carried inside a signed request,
    activates the link (§3.3 steps 7-8)."""

    def post(self, request):
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"error": "too_large"}, status=400)
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        # Normalize like the minting/entry sides (mint is uppercase; the admin
        # form .upper()s) so a peer forwarding a raw lowercase entry still matches.
        code = str(payload.get("code", "")).strip().upper()[:32]
        # local_code_hash is deterministic (SECRET_KEY-salted, not per-link), so
        # match the hash directly in the DB instead of scanning every pending link.
        link = (
            FederationLink.objects.select_related("community")
            .filter(peer=peer, status="pending", requested_by_us=True, pairing_code_hash=crypto.local_code_hash(code))
            .first()
        )
        if link is None or not link.pairing_code_hash or link.is_pairing_expired():
            return JsonResponse({"error": "bad_pairing"}, status=403)

        remote_c = payload.get("community") or {}
        try:
            remote_uuid = uuid.UUID(str(remote_c.get("uuid", "")))
        except ValueError:
            return JsonResponse({"error": "invalid"}, status=400)

        link.remote_community_uuid = remote_uuid
        link.remote_community_label = str(remote_c.get("label", ""))[:200]
        link.pairing_pepper = crypto.derive_link_pepper(code, crypto.my_instance_id(), peer.instance_id)
        link.pairing_code_hash = ""  # one-time: consumed
        link.approved_at = timezone.now()
        try:
            link.transition_to(
                "active",
                extra_update_fields=(
                    "remote_community_uuid",
                    "remote_community_label",
                    "pairing_pepper",
                    "pairing_code_hash",
                    "approved_at",
                ),
            )
        except TransitionConflict:
            return JsonResponse({"error": "conflict"}, status=409)
        if peer.status != "active":
            peer.status = "active"
            peer.save(update_fields=["status", "updated_at"])
        emit("fed.link_approved", link, request=request, details={"origin": "confirm"})
        return JsonResponse(
            {"status": "active", "community": {"uuid": str(link.community.id), "label": link.community.name}}
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-discovery", 60, 3600, by="ip"), name="get")
class DiscoveryView(FederationGateMixin, View):
    """Signed GET (§2.1 pull): returns REDACTED rows (§2.2) for every active
    share on an active link to the requesting peer. No PII — redact() is the
    single gate on what crosses. An unreachable peer just polls again later."""

    def get(self, request):
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        if _peer_over_cap("discovery", peer):
            return JsonResponse({"error": "rate_limited"}, status=429)
        shares = FederatedShare.objects.filter(link__peer=peer, link__status="active", status="active").select_related(
            "link__community", "need__category", "offer__category"
        )
        listings = [redact(s) for s in shares]
        emit("fed.discovery_served", peer, request=request, details={"count": len(listings)})
        return JsonResponse({"listings": listings})


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-revocations", 60, 3600, by="ip"), name="post")
class ConsentRevocationsView(FederationGateMixin, View):
    """Signed inbound delete-requests (§4.3): a peer asks us to shred our shadow
    of a share it revoked. We SHOULD honor it (cooperative erasure) — the shadow
    is a non-PII cache row, so we just delete it and audit both events."""

    def post(self, request):
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"error": "too_large"}, status=400)
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        if _peer_over_cap("revocations", peer):
            return JsonResponse({"error": "rate_limited"}, status=429)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        results = []
        for item in (payload.get("revocations") or [])[:50]:
            if not isinstance(item, dict):
                results.append({"status": "error", "error": "invalid item"})
                continue
            try:
                remote_uuid = uuid.UUID(str(item.get("remote_uuid", "")))
            except (ValueError, TypeError):
                results.append({"status": "error", "error": "invalid remote_uuid"})
                continue
            # Match only shadows sourced from THIS peer (the verified sender).
            shadow = (
                ShadowListing.objects.filter(link__peer=peer, remote_uuid=remote_uuid).select_related("link").first()
            )
            if shadow is None:
                results.append({"remote_uuid": str(remote_uuid), "status": "unknown"})
                continue
            link = shadow.link
            emit("fed.consent_revoke_received", link, request=request, details={"remote_uuid": str(remote_uuid)})
            shadow.delete()
            emit("fed.shadow_shredded", link, request=request, details={"remote_uuid": str(remote_uuid)})
            results.append({"remote_uuid": str(remote_uuid), "status": "shredded"})
        return JsonResponse({"results": results})


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-proposals", 30, 3600, by="ip"), name="post")
class ProposalsView(FederationGateMixin, View):
    """Signed inbound proposals (§6.2): a peer proposes against a Need we shared.
    We are the need's home, so we create the AUTHORITATIVE Match under the §8.7
    lock, preserve §8.6 via the blind token, and stay idempotent on
    proposal_uuid. PII-free wire — the proposer is referenced only by a token."""

    def post(self, request):
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"error": "too_large"}, status=400)
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        if _peer_over_cap("proposals", peer):
            return JsonResponse({"error": "rate_limited"}, status=429)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        results = []
        for item in (payload.get("proposals") or [])[:50]:
            if not isinstance(item, dict):
                results.append({"status": "error", "error": "invalid item"})
                continue
            try:
                need_remote_uuid = uuid.UUID(str(item.get("need_remote_uuid", "")))
                proposal_uuid = uuid.UUID(str(item.get("proposal_uuid", "")))
            except (ValueError, TypeError):
                results.append({"status": "error", "error": "invalid uuid"})
                continue
            result = matching.receive_proposal(
                peer,
                need_remote_uuid=need_remote_uuid,
                proposal_uuid=proposal_uuid,
                blind_token=item.get("blind_token"),
            )
            result["proposal_uuid"] = str(proposal_uuid)
            results.append(result)
        return JsonResponse({"results": results})


def _resolve_event_fmatch(peer, match_uuid):
    """The FederatedMatch this wire uuid addresses, for the verified sender
    only: our authoritative match's own uuid, or a mirror keyed by the
    authority's uuid. Suspended/revoked links resolve nothing (§3.3)."""
    from django.db.models import Q

    return (
        FederatedMatch.objects.filter(link__peer=peer, link__status="active")
        .filter(Q(role="authority", match__pk=match_uuid) | Q(role="mirror", remote_match_uuid=match_uuid))
        .select_related("link__peer", "link__community", "match__need__requester__user", "offer__offerer__user")
        .first()
    )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-events", 120, 3600, by="ip"), name="post")
class MatchEventsView(FederationGateMixin, View):
    """Signed match lifecycle events (§6.2 steps 6-9, §6.3). The authority
    sends accepted/terminal events to the mirror (accepted carries the §8.2
    contact both ways); the mirror may only REQUEST a cancel — the need's
    home keeps the lock (§6.1). Per-item envelope, idempotent on event_uuid."""

    def post(self, request, match_uuid):
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"error": "too_large"}, status=400)
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        if _peer_over_cap("events", peer):
            return JsonResponse({"error": "rate_limited"}, status=429)
        fmatch = _resolve_event_fmatch(peer, match_uuid)
        if fmatch is None:
            return JsonResponse({"error": "unknown_match"}, status=404)

        results = []
        for item in (payload.get("events") or [])[:50]:
            if not isinstance(item, dict):
                results.append({"status": "error", "error": "invalid item"})
                continue
            try:
                event_uuid = uuid.UUID(str(item.get("event_uuid", "")))
            except (ValueError, TypeError):
                results.append({"status": "error", "error": "invalid event_uuid"})
                continue
            kind = str(item.get("event", ""))[:32]
            if fmatch.role == "authority":
                # A peer never drives OUR match state (§6.1) — it may only ask.
                if kind == "cancel_requested":
                    result = matching.apply_cancel_request(fmatch, event_uuid=event_uuid)
                else:
                    result = {"status": "error", "error": "invalid_event"}
            else:
                contact = item.get("contact") if isinstance(item.get("contact"), dict) else None
                result = mirror.apply_match_event(fmatch, event_uuid=event_uuid, kind=kind, contact=contact)
            result["event_uuid"] = str(event_uuid)
            results.append(result)
        return JsonResponse({"results": results})


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-sync", 120, 3600, by="ip"), name="get")
class MatchSyncView(FederationGateMixin, View):
    """Signed authoritative match state for mirror re-sync (§6.3). Answers
    only the peer on the match's own active link, and only for matches we
    hold authority over; the JWS lets the mirror trust the snapshot itself."""

    def get(self, request, match_uuid):
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        if _peer_over_cap("sync", peer):
            return JsonResponse({"error": "rate_limited"}, status=429)
        fmatch = (
            FederatedMatch.objects.filter(
                link__peer=peer, link__status="active", role="authority", match__pk=match_uuid
            )
            .select_related("match")
            .first()
        )
        if fmatch is None:
            return JsonResponse({"error": "unknown_match"}, status=404)
        return JsonResponse({"match": crypto.sign_match_state(str(fmatch.match_id), fmatch.match.status)})


# ── Community-admin UI (§3.3 human approval) ─────────


class FederationSettingsView(LoginRequiredMixin, FederationGateMixin, View):
    """Admin-only (mirrors the role gate at apps/communities/views.py): list
    links + inbound requests, initiate/approve/suspend/resume/revoke."""

    template_name = "federation/settings.html"

    def _admin_member(self, request, slug):
        self.community = get_object_or_404(Community, slug=slug, is_active=True)
        return Member.objects.filter(user=request.user, community=self.community, is_active=True, role="admin").first()

    def get(self, request, slug):
        member = self._admin_member(request, slug)
        if member is None:
            messages.error(request, "Only community admins can manage federation.")
            return redirect("community-feed", slug=slug)
        return render(request, self.template_name, self._context(request))

    def post(self, request, slug):
        member = self._admin_member(request, slug)
        if member is None:
            messages.error(request, "Only community admins can manage federation.")
            return redirect("community-feed", slug=slug)
        action = request.POST.get("action", "")
        handler = {
            "initiate": self._initiate,
            "approve": self._approve,
            "suspend": self._transition,
            "resume": self._transition,
            "revoke": self._transition,
        }.get(action)
        if handler is None:
            messages.error(request, "Unknown action.")
        else:
            handler(request, member, action)
        return redirect("federation_admin:settings", slug=slug)

    def _context(self, request=None):
        # M-1: scope pending inbound requests to THIS community — a peer that
        # named a target community only shows to that community's admins. Empty
        # target (unspecified/legacy) still shows to all (backward-compat).
        inbound = (
            FederationPeer.objects.filter(status="pending")
            .exclude(pairing_hash="")
            .filter(Q(target_community_slug=self.community.slug) | Q(target_community_slug=""))
        )
        # Pinned one-time pairing codes for links this admin just initiated
        # (session-popped: rendered exactly once, on this page, not a toast).
        pairing_reveals = []
        if request is not None:
            for link in FederationLink.objects.filter(
                community=self.community, status="pending", requested_by_us=True
            ).select_related("peer"):
                code = request.session.pop(f"fed_pairing_code_{link.pk}", None)
                if code:
                    pairing_reveals.append({"link": link, "code": code})
        return {
            "community": self.community,
            "pairing_reveals": pairing_reveals,
            "instance_id": crypto.my_instance_id(),
            "links": FederationLink.objects.filter(community=self.community).select_related("peer"),
            "inbound_peers": inbound,
        }

    def _initiate(self, request, member, _action):
        base_url = str(request.POST.get("base_url", "")).strip()[:200]
        if not base_url:
            messages.error(request, "Peer URL is required.")
            return
        try:
            doc = crypto.verify_instance_document(client_mod.fetch_instance_document(base_url))
        except (FederationClientError, FederationAuthError) as e:
            messages.error(request, f"Could not fetch a valid instance document: {e}")
            return
        peer = FederationPeer.objects.filter(instance_id=doc["instance_id"]).first()
        if peer is None:
            peer = FederationPeer.objects.create(
                instance_id=doc["instance_id"],
                jwk=doc["jwk"],
                base_url=str(doc.get("base_url", base_url))[:200],
                locality=str(doc.get("locality", ""))[:100],
                capabilities=doc.get("capabilities") or [],
                status="pending",
            )
        elif peer.status == "blocked":
            messages.error(request, "That instance is blocked.")
            return
        code = crypto.mint_pairing_code()
        salt = uuid.uuid4().hex
        link = FederationLink.objects.create(
            peer=peer,
            community=self.community,
            requested_by_us=True,
            pairing_code_hash=crypto.local_code_hash(code),
            pairing_expires_at=timezone.now() + PAIRING_TTL,
        )
        # Pin the one-time code to the settings page (session-popped there)
        # instead of a vanishing toast — the dark-launch rehearsal nearly
        # lost it mid-ceremony.
        request.session[f"fed_pairing_code_{link.pk}"] = code
        try:
            client_mod.post_handshake(
                base_url,
                {
                    "document": crypto.build_instance_document(),
                    "pairing": {"salt": salt, "hash": crypto.remote_code_hash(code, salt)},
                    "community": {"uuid": str(self.community.id), "label": self.community.name},
                    # M-1: name the peer's community we're targeting (their slug),
                    # so their pending list scopes to that community's admins.
                    "target_community": str(request.POST.get("target_community", "")).strip()[:64],
                },
            )
        except FederationClientError as e:
            messages.error(request, f"Handshake request failed: {e}")
            return
        emit("fed.link_requested", peer, user=request.user, request=request, details={"origin": "outbound"})
        messages.success(request, "Link requested — the one-time pairing code is pinned below.")

    def _approve(self, request, member, _action):
        peer = get_object_or_404(FederationPeer, pk=request.POST.get("peer_id"), status="pending")
        code = str(request.POST.get("code", "")).strip().upper()[:32]
        if peer.is_pairing_expired() or not crypto.codes_match(
            peer.pairing_hash, crypto.remote_code_hash(code, peer.pairing_salt)
        ):
            messages.error(request, "Pairing code did not match (or expired). Nothing was approved.")
            return
        # M-1: refuse to bind a peer to a community it did not target (empty
        # target = unspecified/legacy, allowed for backward-compat).
        if peer.target_community_slug and peer.target_community_slug != self.community.slug:
            messages.error(request, "This request was addressed to a different community.")
            return
        requested = (peer.requested_communities or [{}])[0]
        try:
            remote_uuid = uuid.UUID(str(requested.get("uuid", "")))
        except ValueError:
            remote_uuid = None
        try:
            link = FederationLink.objects.create(
                peer=peer,
                community=self.community,
                remote_community_uuid=remote_uuid,
                remote_community_label=str(requested.get("label", ""))[:200],
                requested_by_us=False,
                approved_by=member,
                approved_at=timezone.now(),
                pairing_pepper=crypto.derive_link_pepper(code, crypto.my_instance_id(), peer.instance_id),
            )
            link.transition_to("active")
        except (IntegrityError, TransitionConflict):
            # Concurrent double-approve of the same pending peer — the loser
            # sees the link already handled rather than a 500.
            messages.error(request, "That peer was already being approved. Nothing was changed.")
            return
        payload = {"code": code, "community": {"uuid": str(self.community.id), "label": self.community.name}}
        signature = crypto.sign_request(
            "POST", client_mod.confirm_url(peer.base_url), json.dumps(payload).encode(), aud=peer.instance_id
        )
        try:
            client_mod.post_confirm(peer.base_url, payload, {"X-UMI-Signature": signature})
        except FederationClientError as e:
            messages.warning(request, f"Link approved locally, but confirming to the peer failed: {e}")
        peer.status = "active"
        peer.pairing_salt = ""
        peer.pairing_hash = ""
        peer.pairing_expires_at = None
        peer.approved_by = member
        peer.save(
            update_fields=["status", "pairing_salt", "pairing_hash", "pairing_expires_at", "approved_by", "updated_at"]
        )
        emit("fed.link_approved", link, user=request.user, request=request, details={"origin": "admin"})
        messages.success(request, "Peer approved — the link is active.")

    # resume adds one action name beyond the design's §10 inventory — flagged in the PR
    TRANSITION_ACTIONS = {
        "suspend": ("suspended", "fed.link_suspended"),
        "resume": ("active", "fed.link_resumed"),
        "revoke": ("revoked", "fed.link_revoked"),
    }

    def _transition(self, request, member, action):
        target, audit_action = self.TRANSITION_ACTIONS[action]
        link = get_object_or_404(FederationLink, pk=request.POST.get("link_id"), community=self.community)
        try:
            with transaction.atomic():
                link.transition_to(target)
                if target == "active" and link.unreachable_since is not None:
                    # A resumed link starts a clean episode — otherwise the
                    # §11 daily sweep would re-suspend it before the next
                    # successful contact clears the old timestamp.
                    link.unreachable_since = None
                    link.save(update_fields=["unreachable_since"])
                # Revoke is terminal: cascade the link's live shares to revoked in
                # the SAME transaction, so they can never be served or matched
                # again even by a future call site that forgets the link__status
                # gate (defense in depth beyond DiscoveryView / receive_proposal).
                # Suspend is a temporary pause — the link__status="active" gate
                # already stops serving while suspended, and resume restores the
                # still-active shares, so suspend deliberately leaves them.
                if target == "revoked":
                    link.shares.filter(status="active").update(status="revoked", revoked_at=timezone.now())
                    # Cancel in-flight authoritative Matches created via this link:
                    # once the peer is cut, a federated match can't proceed, so we
                    # tear them down (not just stop new proposals). transition_to
                    # cascades the Need/Offer back to open/active.
                    for fm in link.matches.select_related("match").filter(match__status__in=("proposed", "accepted")):
                        try:
                            fm.match.transition_to("cancelled")
                        except ValidationError:
                            continue  # raced to a terminal state; nothing to cancel
                        emit(
                            "fed.match_cancelled_on_revoke",
                            fm,
                            user=request.user,
                            details={"match": str(fm.match_id)},
                        )
        except TransitionConflict as e:
            messages.error(request, str(e.message))
            return
        emit(audit_action, link, user=request.user, request=request, details={"action": action})
        messages.success(request, f"Link {target}.")


# ── Member-facing federation UI (Stage C slice 3) ─────


def _active_member_or_none(request, slug):
    community = get_object_or_404(Community, slug=slug, is_active=True)
    member = Member.objects.filter(user=request.user, community=community, is_active=True).first()
    return community, member


class FederatedListingsView(LoginRequiredMixin, FederationGateMixin, View):
    """The board beyond this community (§6.2 step 1): every live need shadow
    pulled from active links, redacted-by-construction — category, urgency,
    locality, freshness. No identity, no free text, ever (§2.2)."""

    template_name = "federation/listings.html"

    def get(self, request, slug):
        community, member = _active_member_or_none(request, slug)
        if member is None:
            messages.error(request, "Join this community to see its shared board.")
            return redirect("community-feed", slug=slug)
        shadows = (
            ShadowListing.objects.filter(
                link__community=community, link__status="active", kind="need", expires_at__gt=timezone.now()
            )
            .select_related("link__peer")
            .order_by("-fetched_at")
        )
        from apps.offers.models import Offer

        my_open_offers = Offer.objects.filter(community=community, offerer=member, status="active").count()
        return render(
            request,
            self.template_name,
            {
                "community": community,
                "member": member,
                "shadows": shadows,
                "my_open_offers": my_open_offers,
            },
        )


class FederatedOfferPickerView(LoginRequiredMixin, FederationGateMixin, View):
    """HTMX partial: the member's own open offers to send against a peer's
    ask. Agency stays with the offerer — only their offers appear (H-2)."""

    template_name = "federation/_offer_picker.html"

    def get(self, request, slug, shadow_id):
        community, member = _active_member_or_none(request, slug)
        if member is None:
            raise Http404
        shadow = get_object_or_404(
            ShadowListing, pk=shadow_id, link__community=community, link__status="active", kind="need"
        )
        from apps.offers.models import Offer

        offers = Offer.objects.filter(community=community, offerer=member, status="active").select_related("category")
        return render(request, self.template_name, {"community": community, "shadow": shadow, "offers": offers})


# ProposalError reasons → warm, non-technical copy. Unknown reasons fall back.
PROPOSE_ERROR_COPY = {
    "gone": "That ask has already been answered or withdrawn on their side.",
    "not_shared": "That ask is no longer shared with this community.",
    "self_match": "This looks like it may be your own ask on the linked community — it can't be matched to itself.",
    "too_many_open": "That ask already has several offers waiting. Maybe try another one.",
    "peer unreachable": "Their community can't be reached right now, so your offer wasn't sent. Try again later.",
    "link is not active": "This community link isn't active right now.",
}


class FederatedProposeView(LoginRequiredMixin, FederationGateMixin, View):
    """POST: send one of my offers against a peer's ask (§6.2 step 2) via
    mirror.send_proposal. Ownership/link/offer-state rules live in the
    service; this view translates outcomes into human words."""

    def post(self, request, slug, shadow_id):
        from apps.offers.models import Offer

        community, member = _active_member_or_none(request, slug)
        if member is None:
            raise Http404
        shadow = get_object_or_404(
            ShadowListing, pk=shadow_id, link__community=community, link__status="active", kind="need"
        )
        offer = get_object_or_404(Offer, pk=request.POST.get("offer_id"), community=community)
        try:
            mirror.send_proposal(shadow, offer, actor_user=request.user)
        except mirror.ProposalError as e:
            messages.error(request, PROPOSE_ERROR_COPY.get(str(e), "That offer couldn't be sent right now."))
        else:
            messages.success(
                request,
                f"Your offer went to {shadow.link.remote_community_label or 'the linked community'}. "
                "If they accept, contact details are shared both ways.",
            )
        return redirect("federation_admin:listings", slug=slug)


class FederatedMatchesView(LoginRequiredMixin, FederationGateMixin, View):
    """Across-communities tracking: members follow their own offers abroad
    (mirror side) and see the requester's §8.2 dict once accepted; community
    coordinators oversee ALL federated activity on their links — the same
    oversight §8.2 grants them locally. Every reveal is audited."""

    template_name = "federation/matches.html"

    STATUS_COPY = {
        "proposed": "Waiting for their community",
        "accepted": "Accepted — contact shared",
        "fulfilled": "Fulfilled",
        "unfulfilled": "Not fulfilled",
        "cancelled": "Cancelled",
        "expired": "Expired",
    }

    def get(self, request, slug):
        from apps.audit.models import AuditLog

        community, member = _active_member_or_none(request, slug)
        if member is None:
            messages.error(request, "Join this community to see its shared board.")
            return redirect("community-feed", slug=slug)

        base = FederatedMatch.objects.filter(link__community=community).select_related(
            "link__peer", "offer__category", "offer__offerer", "match__need"
        )
        mine = base.filter(role="mirror", offer__offerer=member).order_by("-created_at")
        oversight = base.order_by("-created_at") if member.is_coordinator else []

        def row(fm, *, reveal):
            status = fm.mirror_status if fm.role == "mirror" else fm.match.status
            contact = None
            if reveal and fm.role == "mirror" and status in ("accepted", "fulfilled"):
                contact = fm.contact_payload
                if contact:
                    AuditLog.log(request.user, "read", "match_contact", fm.pk, request=request)
            return {
                "fm": fm,
                "status": status,
                "status_copy": self.STATUS_COPY.get(status, status),
                "contact": contact,
            }

        my_rows = [row(fm, reveal=True) for fm in mine]
        seen = {r["fm"].pk for r in my_rows}
        oversight_rows = [row(fm, reveal=member.is_coordinator) for fm in oversight if fm.pk not in seen]
        verifiable_tags = []
        if member.is_coordinator:
            from apps.tags.models import Tag

            verifiable_tags = list(Tag.objects.filter(community=community).exclude(tier="self_serve").order_by("label"))
        return render(
            request,
            self.template_name,
            {
                "community": community,
                "member": member,
                "my_rows": my_rows,
                "oversight_rows": oversight_rows,
                "verifiable_tags": verifiable_tags,
            },
        )


class FederatedShareToggleView(LoginRequiredMixin, FederationGateMixin, View):
    """POST: the owner shares/unshares one record on one link (§2.3/§4.1).
    Sharing IS the digital consent capture — one action creates (or reuses)
    the covering Consent, mints the FederatedShare + signed receipt, and
    flips the record's share_scope. Unsharing revokes the share and sends
    the peer a signed delete-request (§4.3); the consent itself stays the
    member's to revoke from their consent page."""

    def post(self, request, slug):
        from apps.needs.models import Need
        from apps.offers.models import Offer

        from . import sharing as sharing_mod

        community, member = _active_member_or_none(request, slug)
        if member is None:
            raise Http404
        kind = request.POST.get("kind")
        model = {"need": Need, "offer": Offer}.get(kind)
        if model is None:
            return JsonResponse({"error": "invalid kind"}, status=400)
        record = get_object_or_404(model, pk=request.POST.get("record_id"), community=community)
        owner_user_id = record.requester.user_id if kind == "need" else record.offerer.user_id
        if owner_user_id != request.user.id:
            raise Http404  # only the person whose record it is may share it
        link = get_object_or_404(FederationLink, pk=request.POST.get("link_id"), community=community)
        action = request.POST.get("action")

        if action == "share":
            if link.status != "active":
                messages.error(request, "That community link isn't active right now.")
            else:
                consent = sharing_mod.find_share_consent(record, link)
                if consent is None:
                    from apps.consent.models import Consent

                    Consent.objects.create(
                        participant=request.user,
                        granted_to=link.remote_community_label or link.peer.label or "Linked community",
                        grantee_type="community",
                        grantee_id=link.remote_community_uuid,
                        scope=[sharing_mod.FEDERATED_SHARE_SCOPE],
                        purpose="Share this ask/offer with the linked community",
                        method="digital",
                    )
                try:
                    sharing_mod.share_record(record, link, actor_user=request.user)
                except sharing_mod.ShareError as e:
                    messages.error(request, f"Couldn't share: {e}")
                else:
                    messages.success(
                        request,
                        f"Shared with {link.remote_community_label or 'the linked community'}. Only the outline "
                        "travels — never your name or contact details, until a match is accepted.",
                    )
        elif action == "unshare":
            field = {"need": "need", "offer": "offer"}[kind]
            share = FederatedShare.objects.filter(link=link, status="active", **{field: record}).first()
            if share is not None:
                sharing_mod.revoke_share(share, actor_user=request.user)
                if not FederatedShare.objects.filter(status="active", **{field: record}).exists():
                    record.share_scope = "local"
                    record.save(update_fields=["share_scope", "updated_at"])
            messages.info(request, "No longer shared. The linked community has been asked to drop its copy.")
        else:
            return JsonResponse({"error": "invalid action"}, status=400)

        detail = "need-detail" if kind == "need" else "offer-detail"
        return redirect(detail, slug=slug, pk=record.pk)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(rate_limit("fed-attest", 60, 3600, by="ip"), name="post")
class AttestationsQueryView(FederationGateMixin, View):
    """Signed §5.4 queries: is this match's party's tag verified? Capability-
    gated (withdrawing "attestation" from FEDERATION_CAPABILITIES is the
    per-feature rollback); per-item envelope; answers are signed, match-bound,
    24h-TTL claims — never portable credentials."""

    def post(self, request):
        if len(request.body) > MAX_BODY_BYTES:
            return JsonResponse({"error": "too_large"}, status=400)
        try:
            peer, _claims = crypto.verify_signed_request(request)
        except FederationAuthError as e:
            return JsonResponse({"error": e.code}, status=403)
        if "attestation" not in getattr(dj_settings, "FEDERATION_CAPABILITIES", []):
            return JsonResponse({"error": "capability_unsupported"}, status=403)
        if _peer_over_cap("attest", peer):
            return JsonResponse({"error": "rate_limited"}, status=429)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid JSON"}, status=400)

        results = []
        for item in (payload.get("queries") or [])[:50]:
            if not isinstance(item, dict):
                results.append({"status": "error", "error": "invalid item"})
                continue
            try:
                match_uuid = uuid.UUID(str(item.get("match_uuid", "")))
            except (ValueError, TypeError):
                results.append({"status": "error", "error": "invalid match_uuid"})
                continue
            tag_slug = str(item.get("tag", ""))[:50]
            result = matching.serve_attestation_query(peer, match_uuid=match_uuid, tag_slug=tag_slug)
            result["match_uuid"] = str(match_uuid)
            result["tag"] = tag_slug
            results.append(result)
        return JsonResponse({"results": results})


class FederatedAttestView(LoginRequiredMixin, FederationGateMixin, View):
    """Coordinator-only HTMX control: live-ask the peer whether the remote
    party's tag is verified. Result renders inline; nothing is stored —
    §5.4 claims are ephemeral and match-bound by design."""

    template_name = "federation/_attestation_result.html"

    def get(self, request, slug, fmatch_id):
        community, member = _active_member_or_none(request, slug)
        if member is None or not member.is_coordinator:
            raise Http404
        fmatch = get_object_or_404(
            FederatedMatch.objects.select_related("link__peer"), pk=fmatch_id, link__community=community
        )
        tag_slug = str(request.GET.get("tag", ""))[:50]
        if not tag_slug:
            return JsonResponse({"error": "tag required"}, status=400)
        result = matching.request_attestation(fmatch, tag_slug)
        return render(request, self.template_name, {"result": result, "tag": tag_slug})
