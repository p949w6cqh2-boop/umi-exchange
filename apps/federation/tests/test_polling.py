"""Inbound discovery poller + TTL sweep (Stage B slice 2)."""

import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.federation import polling, tasks
from apps.federation.client import FederationClientError
from apps.federation.models import ShadowListing

pytestmark = pytest.mark.django_db


def _row(kind="need", **kw):
    r = {
        "kind": kind,
        "remote_uuid": str(uuid.uuid4()),
        "category": "Food",
        "locality": "Testville",
        "freshness": "2026-W27",
    }
    r["urgency" if kind == "need" else "radius_km"] = "high" if kind == "need" else 10
    r.update(kw)
    return r


def _mock_feed(monkeypatch, listings):
    monkeypatch.setattr(
        "apps.federation.polling.client_mod.get_discovery", lambda base_url, headers: {"listings": listings}
    )


def test_poll_upserts_shadows(fed_settings, active_link, monkeypatch):
    rows = [_row(), _row(kind="offer")]
    _mock_feed(monkeypatch, rows)
    assert polling.poll_link(active_link) == 2
    s = ShadowListing.objects.get(remote_uuid=rows[0]["remote_uuid"])
    assert s.kind == "need" and s.category == "Food" and s.urgency == "high"
    assert s.expires_at > timezone.now()
    o = ShadowListing.objects.get(remote_uuid=rows[1]["remote_uuid"])
    assert o.kind == "offer" and o.radius_km == 10


def test_poll_tombstones_rows_that_left_the_feed(fed_settings, active_link, monkeypatch):
    r1 = _row()
    _mock_feed(monkeypatch, [r1])
    polling.poll_link(active_link)
    r2 = _row()
    _mock_feed(monkeypatch, [r2])
    polling.poll_link(active_link)
    assert {str(x.remote_uuid) for x in ShadowListing.objects.all()} == {r2["remote_uuid"]}


def test_poll_updates_existing_in_place(fed_settings, active_link, monkeypatch):
    r = _row(urgency="low")
    _mock_feed(monkeypatch, [r])
    polling.poll_link(active_link)
    r["urgency"] = "critical"
    _mock_feed(monkeypatch, [r])
    polling.poll_link(active_link)
    assert ShadowListing.objects.count() == 1
    assert ShadowListing.objects.get().urgency == "critical"


def test_poll_unreachable_peer_is_audited_not_fatal(fed_settings, active_link, monkeypatch):
    def boom(base_url, headers):
        raise FederationClientError("timeout")

    monkeypatch.setattr("apps.federation.polling.client_mod.get_discovery", boom)
    assert polling.poll_link(active_link) == 0
    assert not ShadowListing.objects.exists()
    assert AuditLog.objects.filter(action="fed.peer_unreachable", resource_type="federationlink").exists()


def test_poll_ignores_malformed_rows(fed_settings, active_link, monkeypatch):
    _mock_feed(
        monkeypatch,
        [
            {"kind": "bogus", "remote_uuid": str(uuid.uuid4())},
            {"kind": "need", "remote_uuid": "not-a-uuid"},
            "not a dict",
            _row(),
        ],
    )
    assert polling.poll_link(active_link) == 1
    assert ShadowListing.objects.count() == 1


def test_sweep_deletes_expired_shadows(fed_settings, active_link, monkeypatch):
    _mock_feed(monkeypatch, [_row()])
    polling.poll_link(active_link)
    ShadowListing.objects.update(expires_at=timezone.now() - timezone.timedelta(days=1))
    assert tasks.sweep_expired_shadows() == 1
    assert not ShadowListing.objects.exists()


def test_poll_all_is_noop_when_disabled(settings, active_link):
    settings.FEDERATION_ENABLED = False
    assert tasks.poll_all_active_links() == 0


def test_poll_all_polls_active_links(fed_settings, active_link, monkeypatch):
    _mock_feed(monkeypatch, [_row()])
    assert tasks.poll_all_active_links() == 1
    assert ShadowListing.objects.filter(link=active_link).count() == 1
