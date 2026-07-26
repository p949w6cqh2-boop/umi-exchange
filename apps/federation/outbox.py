"""
Stage C2 outbox — signed match-event delivery with retry/backoff (§6.3), the
authority side of the §8.2 contact exchange (§6.2 steps 5-9), the §7
post-accept self-match backstop, and the §4.4 contact-retention sweep.

Queue rows are FederationEvent(direction="out"). Contact-bearing payloads are
envelope-encrypted at rest (under OUR keys) and shredded the moment the peer
acks; the plain payload column never holds PII. Delivery order per match is
FIFO — a newer event is never sent while an older one is still pending.
"""

import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.services import emit

from . import client as client_mod
from . import crypto
from .models import FederatedMatch, FederationEvent

logger = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 60  # §6.3: 1 min, ×4 per attempt …
BACKOFF_CAP_SECONDS = 4 * 3600  # … capped at 4 h …
GIVE_UP_HOURS = 72  # … give up after 72 h.
CONTACT_GRACE_HOURS = 72  # §4.4: contact lives until terminal + 72 h
MATCH_EVENT_KINDS = ("accepted", "fulfilled", "unfulfilled", "cancelled", "expired")


# ── queueing (authority side, §6.2 step 6) ───────────


def queue_match_event(match, event, *, fmatch=None):
    """Queue a lifecycle event for the peer mirroring this AUTHORITY match.
    No-op for purely local matches or when federation is disabled. `accepted`
    carries the requester's §8.2 contact dict, encrypted at rest."""
    if not getattr(settings, "FEDERATION_ENABLED", False):
        return None
    if event not in MATCH_EVENT_KINDS:
        return None
    if fmatch is None:
        fmatch = (
            FederatedMatch.objects.filter(match=match, role="authority")
            .select_related("link__peer", "match__need__requester__user")
            .first()
        )
    if fmatch is None:
        return None
    ev = FederationEvent(
        link=fmatch.link,
        direction="out",
        event_uuid=uuid.uuid4(),
        kind=event,
        payload={"match_uuid": str(match.pk), "event": event},
        next_attempt_at=timezone.now(),
    )
    if event == "accepted":
        need = match.need
        ev.secret_payload = {"contact": need.requester.contact_dict(need.contact_pref)}
    elif fmatch.contact_expires_at is None:
        # Terminal: start the §4.4 grace on the stored counterpart contact,
        # or it would never be swept.
        fmatch.contact_expires_at = timezone.now() + timedelta(hours=CONTACT_GRACE_HOURS)
        fmatch.save(update_fields=["contact_expires_at"])
    ev.save()
    return ev


def queue_cancel_request(fmatch):
    """Mirror → authority: ask the need's home to cancel (§6.2 step 9 — the
    responder withdrew, or the §7 backstop fired). The authority applies it
    under its own lock and echoes a `cancelled` event back."""
    if not getattr(settings, "FEDERATION_ENABLED", False):
        return None
    if fmatch.remote_match_uuid is None:
        return None  # nothing to address — a row would only retry into 404s
    return FederationEvent.objects.create(
        link=fmatch.link,
        direction="out",
        event_uuid=uuid.uuid4(),
        kind="cancel_requested",
        payload={"match_uuid": str(fmatch.remote_match_uuid), "event": "cancel_requested"},
        next_attempt_at=timezone.now(),
    )


def mark_link_unreachable(link):
    """§11: stamp the start of an unreachable episode (idempotent)."""
    if link.unreachable_since is None:
        link.unreachable_since = timezone.now()
        link.save(update_fields=["unreachable_since"])


def mark_link_reachable(link):
    """§11: any outbound success ends the episode."""
    if link.unreachable_since is not None:
        link.unreachable_since = None
        link.save(update_fields=["unreachable_since"])


# ── delivery (django-q2 entrypoint lives in tasks.py) ─


def deliver_due_events(now=None) -> int:
    """Deliver every due outbound event over active links, oldest first,
    FIFO per match. Returns the number acked this pass."""
    now = now or timezone.now()
    delivered = 0
    blocked = set()  # (link_id, match_uuid) — an older event is still pending
    due = (
        FederationEvent.objects.filter(
            direction="out", state="pending", next_attempt_at__lte=now, link__status="active"
        )
        .select_related("link__peer", "link__community")
        .order_by("created_at")
    )
    for ev in due:
        key = (ev.link_id, str(ev.payload.get("match_uuid", "")))
        if key in blocked or _older_pending_exists(ev):
            blocked.add(key)
            continue
        # Claim the row so a second django-q worker running this pass concurrently
        # can't also deliver it (double POST + duplicate fed.contact_disclosed +
        # raced attempts writes). skip_locked means the other worker skips it, not
        # blocks. No-op on SQLite (single writer); enforced on Postgres.
        with transaction.atomic():
            locked = (
                FederationEvent.objects.select_for_update(skip_locked=True)
                .filter(pk=ev.pk, direction="out", state="pending")
                .first()
            )
            if locked is None:
                continue  # another worker claimed it (or it's no longer pending)
            ok = _deliver_one(locked, now)
        if ok:
            delivered += 1
        else:
            blocked.add(key)
    return delivered


def _older_pending_exists(ev) -> bool:
    return (
        FederationEvent.objects.filter(
            link=ev.link,
            direction="out",
            state="pending",
            created_at__lt=ev.created_at,
            payload__match_uuid=ev.payload.get("match_uuid"),
        )
        .exclude(pk=ev.pk)
        .exists()
    )


def _deliver_one(ev, now) -> bool:
    peer = ev.link.peer
    match_uuid = str(ev.payload.get("match_uuid", ""))
    item = {"event_uuid": str(ev.event_uuid), "event": ev.kind}
    secret = ev.secret_payload
    if isinstance(secret, dict):
        item.update(secret)
    body = {"events": [item]}
    url = client_mod.match_events_url(peer.base_url, match_uuid)
    signature = crypto.sign_request("POST", url, json.dumps(body).encode(), aud=peer.instance_id)
    try:
        resp = client_mod.post_match_events(peer.base_url, match_uuid, body, {"X-UMI-Signature": signature})
    except client_mod.FederationClientError as e:
        _record_failure(ev, now, str(e))
        return False

    results = resp.get("results") if isinstance(resp, dict) else None
    first = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    status = first.get("status")
    if status not in ("applied", "duplicate", "conflict"):
        # A reachable peer that refuses the item outright ("error"/malformed):
        # retry on the same backoff — transient on their side, or a version gap.
        _record_failure(ev, now, f"peer_status:{status}")
        return False

    # `duplicate` also carries the contact when the mirror already applied our
    # accepted event but our earlier ack was lost mid-crash (§6.3 idempotency).
    mark_link_reachable(ev.link)
    if ev.kind == "accepted" and isinstance(first.get("contact"), dict):
        _apply_responder_contact(ev, match_uuid, first["contact"])
    ev.state = "acked"
    ev.payload_enc = None
    ev.payload_dek = None
    ev.save(update_fields=["state", "payload_enc", "payload_dek"])
    emit(
        "fed.match_event_sent",
        ev,
        details={"event": ev.kind, "match": match_uuid, "peer_status": status, "link": str(ev.link_id)},
    )
    # A conflict answer means the peer's mirror re-syncs from us (§6.3) —
    # nothing further to deliver for this event.
    return True


def _record_failure(ev, now, reason: str):
    ev.attempts += 1
    gave_up = ev.created_at < now - timedelta(hours=GIVE_UP_HOURS)
    if gave_up:
        ev.state = "failed"
        ev.payload_enc = None  # PII never lingers in a dead outbox row
        ev.payload_dek = None
        ev.save(update_fields=["attempts", "state", "payload_enc", "payload_dek"])
        notify_coordinators(
            ev.link.community,
            "Federation delivery gave up",
            "A match update could not be delivered to a linked community for 72 hours. "
            "The mirror will re-sync when the peer returns; consider suspending the link.",
        )
    else:
        delay = min(BACKOFF_BASE_SECONDS * (4 ** (ev.attempts - 1)), BACKOFF_CAP_SECONDS)
        ev.next_attempt_at = now + timedelta(seconds=delay)
        ev.save(update_fields=["attempts", "next_attempt_at"])
    if ev.attempts == 1 or gave_up:
        emit(
            "fed.peer_unreachable",
            ev.link,
            details={"peer": ev.link.peer.instance_id, "error": reason[:100], "gave_up": gave_up},
        )
    mark_link_unreachable(ev.link)


# ── §8.2 responder contact + §7 backstop (authority) ─


def sanitize_contact(raw) -> dict:
    """Whitelist + cap an inbound wire contact dict to the §8.2 shape. Never
    trust peer-supplied keys/lengths."""
    clean = {}
    for key, cap in (("display_name", 200), ("preference", 10), ("email", 254), ("phone", 50)):
        value = raw.get(key)
        if isinstance(value, str) and value:
            clean[key] = value[:cap]
    return clean


def contact_matches_user(contact: dict, user) -> bool:
    """§7 backstop bit: the revealed contact belongs to OUR party — the same
    human on both sides of the boundary."""
    email = str(contact.get("email", "")).strip().lower()
    if email and email == (getattr(user, "email", "") or "").strip().lower():
        return True

    def _digits(s):
        return "".join(ch for ch in str(s) if ch.isdigit())

    phone = _digits(contact.get("phone", ""))
    user_phone = _digits(getattr(user, "phone", "") or "")
    return bool(phone) and phone == user_phone


def _apply_responder_contact(ev, match_uuid, raw_contact):
    fmatch = (
        FederatedMatch.objects.filter(link=ev.link, role="authority", match__pk=match_uuid)
        .select_related("match__need__requester__user", "link__community")
        .first()
    )
    if fmatch is None:
        return
    contact = sanitize_contact(raw_contact)
    match = fmatch.match
    if contact_matches_user(contact, match.need.requester.user):
        emit("fed.selfmatch_detected", fmatch, details={"side": "authority", "link": str(ev.link_id)})
        _cancel_match_locally(match)
        notify_coordinators(
            ev.link.community,
            "Federated match auto-cancelled",
            "A cross-community match was cancelled automatically: the responder appears to be "
            "the same person as the requester (§8.6). No contact details were stored.",
        )
        return
    fmatch.contact_payload = contact
    fmatch.save(update_fields=["contact_payload_enc", "contact_payload_dek"])
    emit("fed.contact_disclosed", fmatch, details={"direction": "inbound", "link": str(ev.link_id)})


def _cancel_match_locally(match):
    """Cancel via the normal §8.7 discipline: lock Match + Need, then the
    state machine; the cancel event flows back to the peer via the outbox."""
    from apps.matches.models import Match
    from apps.needs.models import Need

    with transaction.atomic():
        locked = Match.objects.select_for_update(of=("self",)).select_related("need").get(pk=match.pk)
        locked.need = Need.objects.select_for_update().get(pk=locked.need_id)
        try:
            locked.transition_to("cancelled")
        except ValidationError:
            return  # already terminal — nothing to cancel
        # Inside the transaction: the cancel event commits WITH the transition,
        # or neither does — a crash can't leave the mirror unaware forever.
        queue_match_event(locked, "cancelled")


def notify_coordinators(community, title, body):
    from apps.communities.models import Member
    from apps.notifications.adapter import NotificationAdapter

    members = Member.objects.filter(
        community=community, is_active=True, role__in=("coordinator", "admin")
    ).select_related("user")
    for member in members:
        try:
            NotificationAdapter.send(member.user, "federation_alert", title, body)
        except Exception:  # noqa: BLE001  # nosec B110 — notify must never break delivery
            logger.exception("federation coordinator notification failed")


# ── §4.4 contact retention sweep ─────────────────────


def sweep_expired_contacts(now=None) -> int:
    """Shred contact payloads past their post-terminal grace (§4.4). Applies
    to both roles — authority and mirror hold the peer party's dict."""
    now = now or timezone.now()
    shredded = 0
    for fmatch in FederatedMatch.objects.filter(contact_expires_at__lt=now, contact_payload_enc__isnull=False):
        fmatch.shred_contact()
        emit("fed.contact_shredded", fmatch, details={"role": fmatch.role})
        shredded += 1
    return shredded


def shred_link_event_payloads(link) -> int:
    """Shred the contact payloads of every still-pending outbound event on this
    link. Called when a link is suspended or revoked: delivery is gated on
    link__status='active', so from that moment the row can never be delivered,
    acked, or given up on — and both of the normal clears sit behind that same
    gate. Without this the requester's name+email stay decryptable under the
    instance KEK forever (§4.4)."""
    shredded = 0
    for ev in FederationEvent.objects.filter(link=link, direction="out", payload_enc__isnull=False).exclude(
        state__in=("acked", "failed")
    ):
        ev.shred_payload()
        emit("fed.event_payload_shredded", ev, details={"reason": "link_inactive", "link": str(link.pk)})
        shredded += 1
    return shredded


def sweep_stale_event_payloads(now=None) -> int:
    """Backstop for the same PII, independent of link status AND of the feature
    flag. An event older than the give-up window can never legitimately deliver,
    so its contact payload has no reason to exist — whatever happened to the
    link, and whether or not federation is still switched on. Turning the
    feature off must not be a way to strand decryptable PII."""
    now = now or timezone.now()
    cutoff = now - timedelta(hours=GIVE_UP_HOURS)
    shredded = 0
    for ev in FederationEvent.objects.filter(created_at__lt=cutoff, payload_enc__isnull=False):
        ev.shred_payload()
        emit("fed.event_payload_shredded", ev, details={"reason": "retention", "link": str(ev.link_id)})
        shredded += 1
    return shredded
