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
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.accounts.ratelimit import rate_limit
from apps.audit.services import emit
from apps.common.state import TransitionConflict
from apps.communities.models import Community, Member

from . import client as client_mod
from . import crypto
from .client import FederationClientError
from .crypto import FederationAuthError
from .models import FederationLink, FederationPeer

MAX_BODY_BYTES = 10_000
PAIRING_TTL = timedelta(hours=24)


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
        return render(request, self.template_name, self._context())

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

    def _context(self):
        return {
            "community": self.community,
            "instance_id": crypto.my_instance_id(),
            "links": FederationLink.objects.filter(community=self.community).select_related("peer"),
            "inbound_peers": FederationPeer.objects.filter(status="pending").exclude(pairing_hash=""),
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
        FederationLink.objects.create(
            peer=peer,
            community=self.community,
            requested_by_us=True,
            pairing_code_hash=crypto.local_code_hash(code),
            pairing_expires_at=timezone.now() + PAIRING_TTL,
        )
        try:
            client_mod.post_handshake(
                base_url,
                {
                    "document": crypto.build_instance_document(),
                    "pairing": {"salt": salt, "hash": crypto.remote_code_hash(code, salt)},
                    "community": {"uuid": str(self.community.id), "label": self.community.name},
                },
            )
        except FederationClientError as e:
            messages.error(request, f"Handshake request failed: {e}")
            return
        emit("fed.link_requested", peer, user=request.user, request=request, details={"origin": "outbound"})
        messages.success(
            request,
            f"Link requested. Read the peer admin your key thumbprint ({crypto.my_instance_id()}) and this "
            f"one-time pairing code: {code} — it is shown only once and expires in 24 hours.",
        )

    def _approve(self, request, member, _action):
        peer = get_object_or_404(FederationPeer, pk=request.POST.get("peer_id"), status="pending")
        code = str(request.POST.get("code", "")).strip().upper()[:32]
        if peer.is_pairing_expired() or not crypto.codes_match(
            peer.pairing_hash, crypto.remote_code_hash(code, peer.pairing_salt)
        ):
            messages.error(request, "Pairing code did not match (or expired). Nothing was approved.")
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
            link.transition_to(target)
        except TransitionConflict as e:
            messages.error(request, str(e.message))
            return
        emit(audit_action, link, user=request.user, request=request, details={"action": action})
        messages.success(request, f"Link {target}.")
