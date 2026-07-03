"""Revoking a consent must leave an append-only audit trail."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.consent.models import Consent

pytestmark = pytest.mark.django_db


def _user(handle):
    return get_user_model().objects.create_user(
        username=handle, email=f"{handle}@example.test", password="pw-Str0ng!pass"
    )


def _active_consent(user):
    return Consent.objects.create(
        participant=user,
        granted_to="St. Patrick Conference",
        scope=["case_records", "case_export"],
        purpose="test",
        method="digital",
    )


def test_revoke_emits_audit_and_flips_status():
    user = _user("revoker")
    consent = _active_consent(user)
    client = Client()
    client.force_login(user)

    resp = client.post(reverse("consent-revoke", kwargs={"pk": consent.pk}))
    assert resp.status_code == 302

    consent.refresh_from_db()
    assert consent.status == "revoked"
    assert consent.revoked_at is not None

    row = AuditLog.objects.filter(action="consent.revoked", resource_id=consent.pk).first()
    assert row is not None
    assert row.user_id == user.pk
    assert row.resource_type == "consent"
    # PII-free details only.
    assert set(row.details or {}) <= {"grantee_type", "scope"}


def test_cannot_revoke_another_users_consent():
    owner = _user("owner")
    other = _user("other")
    consent = _active_consent(owner)
    client = Client()
    client.force_login(other)

    resp = client.post(reverse("consent-revoke", kwargs={"pk": consent.pk}))
    assert resp.status_code == 404
    consent.refresh_from_db()
    assert consent.status == "active"
    assert not AuditLog.objects.filter(action="consent.revoked").exists()
