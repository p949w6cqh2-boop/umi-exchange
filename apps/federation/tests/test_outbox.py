"""
Stage C2 — outbox + §8.2 contact exchange, authority side
(docs/federation-design.md §6.2 steps 5-9, §6.3, §5.3, §7 backstop).
"""

import json
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.matches.models import Match

pytestmark = pytest.mark.django_db


# ── FederatedMatch contact payload (§5.3: envelope under OUR keys) ──


def test_contact_payload_roundtrip_is_envelope_encrypted(authority_match):
    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Bob", "preference": "email", "email": "bob@peer.test"}
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek"])
    fm.refresh_from_db()
    assert fm.contact_payload["email"] == "bob@peer.test"
    # never plaintext at rest
    assert b"bob@peer.test" not in bytes(fm.contact_payload_enc)


def test_contact_payload_none_when_unset(authority_match):
    assert authority_match.fmatch.contact_payload is None


def test_shred_contact_nulls_ciphertext_and_dek(authority_match):
    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Bob", "preference": "in_app"}
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek"])
    fm.shred_contact()
    fm.refresh_from_db()
    assert fm.contact_payload_enc is None and fm.contact_payload_dek is None
    assert fm.contact_payload is None


# ── FederationEvent model (§8: outbox/inbox + idempotency spine) ──


def test_federation_event_unique_per_link_and_uuid(authority_match):
    from django.db import IntegrityError, transaction

    from apps.federation.models import FederationEvent

    eid = uuid.uuid4()
    FederationEvent.objects.create(link=authority_match.link, direction="out", event_uuid=eid, kind="accepted")
    with pytest.raises(IntegrityError), transaction.atomic():
        FederationEvent.objects.create(link=authority_match.link, direction="in", event_uuid=eid, kind="accepted")


def test_federation_event_payload_encrypts_and_shreds(authority_match):
    from apps.federation.models import FederationEvent

    ev = FederationEvent.objects.create(
        link=authority_match.link, direction="out", event_uuid=uuid.uuid4(), kind="accepted"
    )
    ev.secret_payload = {"contact": {"email": "maria@example.test"}}
    ev.save(update_fields=["payload_enc", "payload_dek"])
    ev.refresh_from_db()
    assert ev.secret_payload["contact"]["email"] == "maria@example.test"
    assert b"maria@example.test" not in bytes(ev.payload_enc)
    ev.shred_payload()
    ev.refresh_from_db()
    assert ev.payload_enc is None and ev.payload_dek is None and ev.secret_payload is None


# ── queue_match_event (authority → outbox) ──────────────────────


def test_queue_accepted_event_carries_contact_encrypted(authority_match):
    from apps.federation import outbox
    from apps.federation.models import FederationEvent

    authority_match.match.transition_to("accepted")
    outbox.queue_match_event(authority_match.match, "accepted")
    ev = FederationEvent.objects.get(link=authority_match.link, direction="out", kind="accepted")
    assert ev.state == "pending"
    assert ev.payload["match_uuid"] == str(authority_match.match.id)
    # §8.2 payload rides encrypted; the plain JSON column holds no PII
    assert "contact" not in ev.payload and "maria" not in json.dumps(ev.payload)
    assert ev.secret_payload["contact"]["email"] == "maria@example.test"
    assert ev.next_attempt_at is not None


def test_queue_terminal_event_has_no_contact(authority_match):
    from apps.federation import outbox
    from apps.federation.models import FederationEvent

    outbox.queue_match_event(authority_match.match, "cancelled")
    ev = FederationEvent.objects.get(link=authority_match.link, direction="out", kind="cancelled")
    assert ev.payload_enc is None and ev.payload_dek is None


def test_queue_is_noop_for_local_match(authority_match, world):
    from apps.federation import outbox
    from apps.federation.models import FederationEvent
    from apps.needs.models import Need

    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=authority_match.need.category,
        title="local-only",
        expires_at=timezone.now() + timedelta(days=7),
    )
    local = Match.objects.create(need=need, offer=None, proposed_by=world.admin)
    outbox.queue_match_event(local, "accepted")
    assert not FederationEvent.objects.filter(kind="accepted").exists()


def test_queue_is_noop_when_flag_off(authority_match, settings):
    from apps.federation import outbox
    from apps.federation.models import FederationEvent

    settings.FEDERATION_ENABLED = False
    outbox.queue_match_event(authority_match.match, "accepted")
    assert not FederationEvent.objects.exists()


# ── deliver_due_events (§6.3: signed POST, ack-shred, backoff, give-up) ──


def _accepted_and_queued(authority_match):
    from apps.federation import outbox

    authority_match.match.transition_to("accepted")
    outbox.queue_match_event(authority_match.match, "accepted")
    from apps.federation.models import FederationEvent

    return FederationEvent.objects.get(direction="out", kind="accepted")


def test_deliver_posts_signed_body_and_acks_and_shreds(authority_match, monkeypatch):
    from apps.federation import outbox

    ev = _accepted_and_queued(authority_match)
    calls = {}

    def fake_post(base_url, match_uuid, payload, headers):
        calls["base_url"] = base_url
        calls["match_uuid"] = match_uuid
        calls["payload"] = payload
        calls["headers"] = headers
        item = payload["events"][0]
        return {"results": [{"event_uuid": item["event_uuid"], "status": "applied"}]}

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", fake_post)
    assert outbox.deliver_due_events() == 1

    assert calls["match_uuid"] == str(authority_match.match.id)
    assert "X-UMI-Signature" in calls["headers"]
    sent = calls["payload"]["events"][0]
    assert sent["event"] == "accepted"
    assert sent["contact"]["email"] == "maria@example.test"  # §8.2 crosses post-accept only

    ev.refresh_from_db()
    assert ev.state == "acked"
    assert ev.payload_enc is None and ev.payload_dek is None  # shredded on ack
    assert AuditLog.objects.filter(action="fed.match_event_sent").exists()


def test_deliver_stores_responder_contact_encrypted(authority_match, monkeypatch):
    from apps.federation import outbox

    _accepted_and_queued(authority_match)

    def fake_post(base_url, match_uuid, payload, headers):
        item = payload["events"][0]
        return {
            "results": [
                {
                    "event_uuid": item["event_uuid"],
                    "status": "applied",
                    "contact": {"display_name": "Bob", "preference": "email", "email": "bob@peer.test"},
                }
            ]
        }

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", fake_post)
    outbox.deliver_due_events()
    authority_match.fmatch.refresh_from_db()
    assert authority_match.fmatch.contact_payload["email"] == "bob@peer.test"
    assert AuditLog.objects.filter(action="fed.contact_disclosed").exists()


def test_deliver_backstop_cancels_self_match(authority_match, monkeypatch):
    """§7 backstop: the responder's revealed contact matches OUR requester —
    same human on both sides. Auto-cancel + audit; contact never stored."""
    from apps.federation import outbox

    _accepted_and_queued(authority_match)

    def fake_post(base_url, match_uuid, payload, headers):
        item = payload["events"][0]
        return {
            "results": [
                {
                    "event_uuid": item["event_uuid"],
                    "status": "applied",
                    "contact": {"display_name": "M", "preference": "email", "email": "MARIA@example.test"},
                }
            ]
        }

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", fake_post)
    outbox.deliver_due_events()
    authority_match.match.refresh_from_db()
    authority_match.fmatch.refresh_from_db()
    assert authority_match.match.status == "cancelled"
    assert authority_match.fmatch.contact_payload is None
    assert AuditLog.objects.filter(action="fed.selfmatch_detected").exists()


def test_deliver_failure_backs_off_and_audits_first_failure(authority_match, monkeypatch):
    from apps.federation import client as client_mod
    from apps.federation import outbox

    ev = _accepted_and_queued(authority_match)

    def boom(*a, **k):
        raise client_mod.FederationClientError("down")

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", boom)
    assert outbox.deliver_due_events() == 0
    ev.refresh_from_db()
    assert ev.state == "pending" and ev.attempts == 1
    assert ev.next_attempt_at > timezone.now() + timedelta(seconds=30)
    assert AuditLog.objects.filter(action="fed.peer_unreachable").count() == 1

    # not due yet → untouched; force due → second failure backs off further, no re-audit
    assert outbox.deliver_due_events() == 0
    type(ev).objects.filter(pk=ev.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    assert outbox.deliver_due_events() == 0
    ev.refresh_from_db()
    assert ev.attempts == 2
    assert AuditLog.objects.filter(action="fed.peer_unreachable").count() == 1


def test_deliver_gives_up_after_72h(authority_match, monkeypatch):
    from apps.federation import client as client_mod
    from apps.federation import outbox
    from apps.federation.models import FederationEvent

    ev = _accepted_and_queued(authority_match)
    FederationEvent.objects.filter(pk=ev.pk).update(created_at=timezone.now() - timedelta(hours=73))

    def boom(*a, **k):
        raise client_mod.FederationClientError("down")

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", boom)
    outbox.deliver_due_events()
    ev.refresh_from_db()
    assert ev.state == "failed"
    assert ev.payload_enc is None  # PII never lingers in a dead outbox row


def test_deliver_skips_suspended_link(authority_match, monkeypatch):
    from apps.federation import outbox

    ev = _accepted_and_queued(authority_match)
    authority_match.link.transition_to("suspended")

    called = []
    monkeypatch.setattr(
        "apps.federation.outbox.client_mod.post_match_events", lambda *a, **k: called.append(1) or {"results": []}
    )
    assert outbox.deliver_due_events() == 0
    assert not called
    ev.refresh_from_db()
    assert ev.state == "pending"  # resumes when the link does


def test_deliver_preserves_per_match_ordering(authority_match, monkeypatch):
    """accepted must land before fulfilled: while an older event for the same
    match is still pending, a newer one is not sent this pass."""
    from apps.federation import client as client_mod
    from apps.federation import outbox

    ev1 = _accepted_and_queued(authority_match)
    authority_match.match.transition_to("fulfilled")
    outbox.queue_match_event(authority_match.match, "fulfilled")

    def boom(*a, **k):
        raise client_mod.FederationClientError("down")

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", boom)
    outbox.deliver_due_events()  # accepted fails, stays pending

    sent_kinds = []

    def ok(base_url, match_uuid, payload, headers):
        item = payload["events"][0]
        sent_kinds.append(item["event"])
        return {"results": [{"event_uuid": item["event_uuid"], "status": "applied"}]}

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", ok)
    type(ev1).objects.filter(pk=ev1.pk).update(next_attempt_at=timezone.now() - timedelta(seconds=1))
    outbox.deliver_due_events()
    assert sent_kinds and sent_kinds[0] == "accepted"


# ── contact retention sweep (§4.4: terminal + 72 h) ─────────────


def test_sweep_expired_contacts_shreds_past_grace(authority_match):
    from apps.federation import outbox

    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Bob", "preference": "in_app"}
    fm.contact_expires_at = timezone.now() - timedelta(minutes=1)
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek", "contact_expires_at"])
    assert outbox.sweep_expired_contacts() == 1
    fm.refresh_from_db()
    assert fm.contact_payload is None
    assert AuditLog.objects.filter(action="fed.contact_shredded").exists()
    # idempotent
    assert outbox.sweep_expired_contacts() == 0


def test_sweep_leaves_live_contacts(authority_match):
    from apps.federation import outbox

    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Bob", "preference": "in_app"}
    fm.contact_expires_at = timezone.now() + timedelta(hours=71)
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek", "contact_expires_at"])
    assert outbox.sweep_expired_contacts() == 0
    fm.refresh_from_db()
    assert fm.contact_payload is not None


# ── authority hooks: view + expiry sweep queue events ───────────


def test_match_accept_via_view_queues_accepted_event(authority_match, client, world):
    from apps.federation.models import FederationEvent

    client.force_login(world.plain_u)  # the requester accepts
    resp = client.post(f"/c/{world.community.slug}/matches/{authority_match.match.id}/update/", {"status": "accepted"})
    assert resp.status_code == 302
    ev = FederationEvent.objects.get(direction="out", kind="accepted")
    assert ev.secret_payload["contact"]["email"] == "maria@example.test"


def test_match_cancel_via_view_queues_event_without_contact(authority_match, client, world):
    from apps.federation.models import FederationEvent

    client.force_login(world.plain_u)
    client.post(f"/c/{world.community.slug}/matches/{authority_match.match.id}/update/", {"status": "cancelled"})
    ev = FederationEvent.objects.get(direction="out", kind="cancelled")
    assert ev.payload_enc is None


def test_local_match_update_queues_nothing(authority_match, client, world):
    from django.utils import timezone as tz

    from apps.federation.models import FederationEvent
    from apps.needs.models import Need
    from apps.offers.models import Offer

    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=authority_match.need.category,
        title="local",
        expires_at=tz.now() + timedelta(days=7),
    )
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.admin,
        category=authority_match.need.category,
        title="help",
        expires_at=tz.now() + timedelta(days=30),
    )
    local = Match.objects.create(need=need, offer=offer, proposed_by=world.admin)
    client.force_login(world.plain_u)
    client.post(f"/c/{world.community.slug}/matches/{local.id}/update/", {"status": "accepted"})
    local.refresh_from_db()
    assert local.status == "accepted"
    assert not FederationEvent.objects.exists()


def test_expiry_sweep_queues_expired_event(authority_match, world):
    from apps.federation.models import FederationEvent
    from apps.matches.tasks import expire_stale_proposals

    world.community.settings = {"match_expiry_days": 1}
    world.community.save(update_fields=["settings"])
    Match.objects.filter(pk=authority_match.match.pk).update(proposed_at=timezone.now() - timedelta(days=2))
    assert expire_stale_proposals() == 1
    ev = FederationEvent.objects.get(direction="out", kind="expired")
    assert ev.payload["match_uuid"] == str(authority_match.match.id)


# ── §8.2 reveal on the authority's match detail ─────────────────


def _store_remote_contact(authority_match):
    authority_match.match.transition_to("accepted")
    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Bob", "preference": "email", "email": "bob@peer.test"}
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek"])


def test_match_detail_reveals_remote_contact_to_requester(authority_match, client, world):
    _store_remote_contact(authority_match)
    client.force_login(world.plain_u)
    resp = client.get(f"/c/{world.community.slug}/matches/{authority_match.match.id}/")
    assert resp.status_code == 200
    assert resp.context["contact_info"]["email"] == "bob@peer.test"


def test_match_detail_coordinator_sees_remote_party(authority_match, client, world):
    _store_remote_contact(authority_match)
    client.force_login(world.admin_u)
    resp = client.get(f"/c/{world.community.slug}/matches/{authority_match.match.id}/")
    parties = resp.context["contact_info"]["parties"]
    assert any(p.get("email") == "bob@peer.test" for p in parties)


def test_match_detail_before_exchange_shows_proxy(authority_match, client, world):
    authority_match.match.transition_to("accepted")  # no contact stored yet
    client.force_login(world.plain_u)
    resp = client.get(f"/c/{world.community.slug}/matches/{authority_match.match.id}/")
    assert resp.status_code == 200
    assert "(federated)" in resp.context["contact_info"]["display_name"]


# ── django-q2 entrypoints + schedules ───────────────────────────


def test_register_schedule_includes_c2_jobs(authority_match):
    from django_q.models import Schedule

    from apps.federation.tasks import register_schedule

    register_schedule()
    names = set(Schedule.objects.values_list("name", flat=True))
    assert {"federation-deliver-events", "federation-sweep-contacts"} <= names


def test_deliver_task_noop_when_flag_off(authority_match, settings, monkeypatch):
    from apps.federation import tasks

    _accepted_and_queued(authority_match)
    settings.FEDERATION_ENABLED = False
    called = []
    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", lambda *a, **k: called.append(1))
    assert tasks.deliver_pending_events() == 0
    assert not called


def test_contact_sweep_task_runs_even_when_flag_off(authority_match, settings):
    """Retention is a privacy guarantee — it survives the flag being turned
    off with residual payloads at rest."""
    from apps.federation import tasks

    fm = authority_match.fmatch
    fm.contact_payload = {"display_name": "Bob", "preference": "in_app"}
    fm.contact_expires_at = timezone.now() - timedelta(minutes=1)
    fm.save(update_fields=["contact_payload_enc", "contact_payload_dek", "contact_expires_at"])
    settings.FEDERATION_ENABLED = False
    assert tasks.sweep_expired_contacts() == 1
