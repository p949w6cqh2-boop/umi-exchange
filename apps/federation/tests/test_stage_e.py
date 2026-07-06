"""
Stage E — ops & census (§12 E, §11 "KEK rotation vs shadows"): the federation
envelope columns must ride the SAME rotation + census tooling as every other
envelope field, and operators get a one-command health/retention readout.
"""

import json
import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.utils import timezone

from apps.federation.models import FederatedMatch, FederationEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def ops_world(fed_settings, active_link, world):
    fmatch = FederatedMatch.objects.create(
        link=active_link,
        role="mirror",
        proposal_uuid=uuid.uuid4(),
        remote_match_uuid=uuid.uuid4(),
        mirror_status="accepted",
    )
    fmatch.contact_payload = {"display_name": "Maria", "preference": "email", "email": "maria@peer.test"}
    fmatch.save(update_fields=["contact_payload_enc", "contact_payload_dek"])
    ev = FederationEvent.objects.create(
        link=active_link, direction="out", event_uuid=uuid.uuid4(), kind="accepted", next_attempt_at=timezone.now()
    )
    ev.secret_payload = {"contact": {"email": "maria@peer.test"}}
    ev.save(update_fields=["payload_enc", "payload_dek"])
    return SimpleNamespace(link=active_link, fmatch=fmatch, ev=ev)


# ── §11: rotate_keks must cover federation DEKs ─────────────────


def test_rotate_keks_rewraps_federation_deks(ops_world, settings):
    old_key = settings.ENCRYPTION_KEY
    new_key = Fernet.generate_key().decode()
    settings.ENCRYPTION_KEYS = [new_key, old_key]  # rotation step 2
    call_command("rotate_keks", stdout=StringIO())
    settings.ENCRYPTION_KEYS = [new_key]  # step 4: retire the old KEK

    ops_world.fmatch.refresh_from_db()
    ops_world.ev.refresh_from_db()
    # readable under the NEW KEK alone ⇒ the wraps were rotated
    assert ops_world.fmatch.contact_payload["email"] == "maria@peer.test"
    assert ops_world.ev.secret_payload["contact"]["email"] == "maria@peer.test"


def test_rotate_keks_dry_run_lists_federation_fields(ops_world, settings):
    settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode(), settings.ENCRYPTION_KEY]
    out = StringIO()
    call_command("rotate_keks", "--dry-run", stdout=out)
    text = out.getvalue()
    assert "federation.FederatedMatch.contact_payload_dek" in text
    assert "federation.FederationEvent.payload_dek" in text


# ── census: federation_envelope_status ──────────────────────────


def test_federation_envelope_status_counts(ops_world):
    FederatedMatch.objects.create(  # a shredded/never-exchanged row counts as empty
        link=ops_world.link, role="authority", proposal_uuid=uuid.uuid4()
    )
    out = StringIO()
    call_command("federation_envelope_status", stdout=out)
    text = out.getvalue()
    assert "FederatedMatch.contact_payload_enc: empty=1 envelope=1 unreadable=0" in text
    assert "FederationEvent.payload_enc: empty=0 envelope=1 unreadable=0" in text
    assert "envelope-encrypted" in text  # the all-clear line


def test_federation_envelope_status_flags_unreadable(ops_world):
    # corrupt the wrap: ciphertext with a garbage DEK
    FederatedMatch.objects.filter(pk=ops_world.fmatch.pk).update(contact_payload_dek=b"garbage")
    out, err = StringIO(), StringIO()
    call_command("federation_envelope_status", stdout=out, stderr=err)
    assert "unreadable=1" in out.getvalue()
    assert "do NOT" in err.getvalue() or "investigate" in err.getvalue()


# ── ops readout: federation_status ──────────────────────────────


def test_federation_status_reports_health_and_retention(ops_world, world, fed_settings):
    from apps.federation.models import FederationLink, ShadowListing

    # an unreachable link
    lonely = FederationLink.objects.create(
        peer=ops_world.link.peer,
        community=world.community,
        remote_community_uuid=uuid.uuid4(),
        status="active",
        unreachable_since=timezone.now() - timedelta(days=2),
    )
    # a failed outbox row + an old pending one
    FederationEvent.objects.create(
        link=ops_world.link, direction="out", event_uuid=uuid.uuid4(), kind="cancelled", state="failed"
    )
    FederationEvent.objects.filter(pk=ops_world.ev.pk).update(created_at=timezone.now() - timedelta(hours=3))
    # an overdue contact shred (grace passed, payload still present)
    FederatedMatch.objects.filter(pk=ops_world.fmatch.pk).update(contact_expires_at=timezone.now() - timedelta(hours=1))
    ShadowListing.objects.create(
        link=ops_world.link, kind="need", remote_uuid=uuid.uuid4(), expires_at=timezone.now() + timedelta(days=1)
    )

    out = StringIO()
    call_command("federation_status", "--json", stdout=out)
    data = json.loads(out.getvalue())
    assert data["enabled"] is True
    assert data["links"]["active"] == 2
    assert data["links"]["unreachable"] == 1
    assert data["outbox"]["pending"] == 1
    assert data["outbox"]["failed"] == 1
    assert data["outbox"]["oldest_pending_hours"] >= 2
    assert data["retention"]["contacts_overdue_shred"] == 1
    assert data["shadows"]["live"] == 1
    assert lonely.pk  # silence lint

    # human output names the problems
    out2 = StringIO()
    call_command("federation_status", stdout=out2)
    text = out2.getvalue()
    assert "unreachable" in text and "overdue" in text
