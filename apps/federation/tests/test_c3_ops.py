"""
Stage C slice 3 — operational hardening: §11 link auto-suspend after 7 days
unreachable, and the M-2 per-peer caps extended to the C2 wire endpoints.
"""

import json
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.conf import settings as dj_settings
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.federation.models import FederatedMatch, FederationEvent

pytestmark = pytest.mark.django_db


# ── unreachable_since plumbing + auto-suspend (§11) ─────────────


@pytest.fixture
def queued_event(authority_match):
    from apps.federation import outbox

    authority_match.match.transition_to("accepted")
    outbox.queue_match_event(authority_match.match, "accepted")
    return FederationEvent.objects.get(direction="out", kind="accepted")


def test_delivery_failure_marks_link_unreachable(authority_match, queued_event, monkeypatch):
    from apps.federation import client as client_mod
    from apps.federation import outbox

    def boom(*a, **k):
        raise client_mod.FederationClientError("down")

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", boom)
    outbox.deliver_due_events()
    authority_match.link.refresh_from_db()
    assert authority_match.link.unreachable_since is not None


def test_delivery_success_clears_unreachable(authority_match, queued_event, monkeypatch):
    from apps.federation import outbox

    type(authority_match.link).objects.filter(pk=authority_match.link.pk).update(
        unreachable_since=timezone.now() - timedelta(days=2)
    )

    def ok(base_url, match_uuid, payload, headers):
        item = payload["events"][0]
        return {"results": [{"event_uuid": item["event_uuid"], "status": "applied"}]}

    monkeypatch.setattr("apps.federation.outbox.client_mod.post_match_events", ok)
    outbox.deliver_due_events()
    authority_match.link.refresh_from_db()
    assert authority_match.link.unreachable_since is None


def test_poll_failure_and_success_toggle_unreachable(fed_settings, active_link, monkeypatch):
    from apps.federation import client as client_mod
    from apps.federation import polling

    def boom(*a, **k):
        raise client_mod.FederationClientError("down")

    monkeypatch.setattr("apps.federation.polling.client_mod.get_discovery", boom)
    polling.poll_link(active_link)
    active_link.refresh_from_db()
    assert active_link.unreachable_since is not None

    monkeypatch.setattr("apps.federation.polling.client_mod.get_discovery", lambda *a, **k: {"listings": []})
    polling.poll_link(active_link)
    active_link.refresh_from_db()
    assert active_link.unreachable_since is None


def test_auto_suspend_after_seven_days(fed_settings, active_link):
    from apps.federation import tasks

    type(active_link).objects.filter(pk=active_link.pk).update(
        unreachable_since=timezone.now() - timedelta(days=7, hours=1)
    )
    assert tasks.auto_suspend_unreachable_links() == 1
    active_link.refresh_from_db()
    assert active_link.status == "suspended"
    assert AuditLog.objects.filter(action="fed.link_suspended").exists()


def test_auto_suspend_leaves_recent_and_healthy_links(fed_settings, active_link):
    from apps.federation import tasks

    # healthy (never unreachable)
    assert tasks.auto_suspend_unreachable_links() == 0
    # unreachable but under the threshold
    type(active_link).objects.filter(pk=active_link.pk).update(unreachable_since=timezone.now() - timedelta(days=6))
    assert tasks.auto_suspend_unreachable_links() == 0
    active_link.refresh_from_db()
    assert active_link.status == "active"


def test_auto_suspend_noop_when_flag_off(fed_settings, active_link, settings):
    from apps.federation import tasks

    type(active_link).objects.filter(pk=active_link.pk).update(unreachable_since=timezone.now() - timedelta(days=8))
    settings.FEDERATION_ENABLED = False
    assert tasks.auto_suspend_unreachable_links() == 0


def test_register_schedule_includes_auto_suspend(fed_settings, db):
    from django_q.models import Schedule

    from apps.federation.tasks import register_schedule

    register_schedule()
    assert Schedule.objects.filter(name="federation-auto-suspend").exists()


# ── per-peer caps on the C2 endpoints (M-2 pattern) ─────────────


@pytest.fixture
def wired_mirror(fed_settings, active_link, world):
    from apps.communities.models import Category
    from apps.offers.models import Offer

    cat = Category.objects.create(community=world.community, name="Food")
    offer = Offer.objects.create(
        community=world.community,
        offerer=world.plain,
        category=cat,
        title="help",
        expires_at=timezone.now() + timedelta(days=30),
    )
    fmatch = FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        remote_need_uuid=uuid.uuid4(),
        mirror_status="proposed",
        offer=offer,
    )
    return SimpleNamespace(fmatch=fmatch, link=active_link)


def _signed_events_post(client, remote, fed_settings, match_uuid, events):
    path = f"/federation/v1/matches/{match_uuid}/events"
    body = json.dumps({"events": events}).encode()
    sig = remote.sign("POST", dj_settings.SITE_URL.rstrip("/") + path, body, fed_settings.instance_id)
    return client.post(path, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_events_endpoint_enforces_per_peer_cap(client, fed_settings, remote, wired_mirror, monkeypatch):
    from apps.federation import views

    monkeypatch.setitem(views.FED_PEER_HOURLY_CAPS, "events", 1)
    first = _signed_events_post(
        client,
        remote,
        fed_settings,
        wired_mirror.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "cancelled"}],
    )
    assert first.status_code == 200
    second = _signed_events_post(
        client,
        remote,
        fed_settings,
        wired_mirror.fmatch.remote_match_uuid,
        [{"event_uuid": str(uuid.uuid4()), "event": "expired"}],
    )
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_sync_endpoint_enforces_per_peer_cap(client, fed_settings, remote, authority_match, monkeypatch):
    from apps.federation import views

    monkeypatch.setitem(views.FED_PEER_HOURLY_CAPS, "sync", 1)
    path = f"/federation/v1/matches/{authority_match.match.id}"

    def _get():
        sig = remote.sign("GET", dj_settings.SITE_URL.rstrip("/") + path, b"", fed_settings.instance_id)
        return client.get(path, HTTP_X_UMI_SIGNATURE=sig)

    assert _get().status_code == 200
    assert _get().status_code == 429


@pytest.mark.urls("apps.federation.tests.urls_enabled")
def test_admin_resume_clears_unreachable_episode(client, fed_settings, active_link, world):
    """Resuming a link must clear unreachable_since, or the daily sweep
    re-suspends it before the next successful contact."""
    active_link.transition_to("suspended")
    type(active_link).objects.filter(pk=active_link.pk).update(unreachable_since=timezone.now() - timedelta(days=8))
    client.force_login(world.admin_u)
    client.post(
        f"/c/{world.community.slug}/federation/",
        {"action": "resume", "link_id": str(active_link.pk)},
    )
    active_link.refresh_from_db()
    assert active_link.status == "active"
    assert active_link.unreachable_since is None
