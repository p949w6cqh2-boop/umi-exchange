"""Retention policy (set 2026-07-11): aged terminal records lose their
encrypted PII by crypto-shred — BOTH envelope columns nulled, so reads return
None (no fail-loud ciphertext-without-DEK state) and the envelope censuses
stay clean."""

import datetime

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.needs.models import Need
from apps.needs.tasks import NEED_PII_RETENTION_DAYS, shred_aged_need_pii
from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _encryption_key(settings):
    # Envelope writes need a KEK; CI runs with ENCRYPTION_KEY="" and a fresh
    # dev checkout has none — same hermetic fixture as apps/casework/tests.
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()


def _make_need(status="fulfilled", age_days=NEED_PII_RETENTION_DAYS + 1):
    community = CommunityFactory()
    member = MemberFactory(community=community)
    need = NeedFactory(
        community=community,
        requester=member,
        category=CategoryFactory(community=community),
        status=status,
    )
    need.on_behalf_of_name = "Maria Garcia"
    need.save()
    Need.objects.filter(pk=need.pk).update(updated_at=timezone.now() - datetime.timedelta(days=age_days))
    return need


def test_aged_terminal_need_is_shredded_clean():
    need = _make_need()
    result = shred_aged_need_pii()
    need.refresh_from_db()
    assert need.on_behalf_of is None
    assert need.on_behalf_of_dek is None
    assert need.on_behalf_of_name is None  # reads None, not a hard error
    assert "1 aged needs" in result


def test_young_and_open_needs_are_kept():
    young = _make_need(age_days=30)
    open_aged = _make_need(status="open")
    shred_aged_need_pii()
    young.refresh_from_db()
    open_aged.refresh_from_db()
    assert young.on_behalf_of_dek is not None
    assert open_aged.on_behalf_of_dek is not None


def test_shred_is_idempotent_and_audited_once():
    need = _make_need()
    shred_aged_need_pii()
    assert "0 aged needs" in shred_aged_need_pii()
    assert AuditLog.objects.filter(action="need.pii_shredded", resource_id=need.pk).count() == 1
