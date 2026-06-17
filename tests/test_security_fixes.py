"""Regression tests for the verified-flaw fixes (see docs/sandbox-report.md §5)."""

import hashlib

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.ratelimit import client_ip
from apps.audit.models import AuditLog
from apps.audit.services import ip_hash

from .conftest import CommunityFactory, MemberFactory, UserFactory


class TestTrustedClientIP:
    """8.1 + 8.2: never trust the spoofable left-most X-Forwarded-For; salt the hash."""

    def _req(self, **meta):
        return RequestFactory().get("/", **meta)

    def test_client_ip_ignores_forwarded_for(self):
        req = self._req(
            HTTP_X_FORWARDED_FOR="1.2.3.4",  # attacker-supplied — must be ignored
            HTTP_X_REAL_IP="10.0.0.9",  # set by the reverse proxy
            REMOTE_ADDR="172.16.0.1",
        )
        assert client_ip(req) == "10.0.0.9"

    def test_client_ip_falls_back_to_remote_addr(self):
        req = self._req(HTTP_X_FORWARDED_FOR="1.2.3.4", REMOTE_ADDR="172.16.0.1")
        assert client_ip(req) == "172.16.0.1"

    def test_ip_hash_is_salted(self, settings):
        settings.SECRET_KEY = "test-secret-key"
        req = self._req(HTTP_X_REAL_IP="10.0.0.9")
        digest = ip_hash(req)
        # A plain (unsalted) SHA-256 would be rainbow-tableable; ours must not match it.
        assert digest != hashlib.sha256(b"10.0.0.9").hexdigest()
        assert digest == hashlib.sha256(b"10.0.0.9:test-secret-key").hexdigest()

    def test_ip_hash_uses_real_ip_not_forwarded_for(self, settings):
        settings.SECRET_KEY = "test-secret-key"
        req = self._req(HTTP_X_FORWARDED_FOR="1.2.3.4", HTTP_X_REAL_IP="10.0.0.9")
        assert ip_hash(req) == hashlib.sha256(b"10.0.0.9:test-secret-key").hexdigest()

    def test_ip_hash_no_request_is_empty(self):
        assert ip_hash(None) == ""


@pytest.mark.django_db
class TestHouseholdJoinAudit:
    """8.6: joining a household is an audited, bounded write — not a silent mass update."""

    def test_join_updates_active_memberships_and_audits(self, client):
        user = UserFactory()
        m1 = MemberFactory(user=user, community=CommunityFactory())
        m2 = MemberFactory(user=user, community=CommunityFactory())
        client.force_login(user)

        # First create a household (as another user) to get a join code.
        owner = UserFactory()
        MemberFactory(user=owner, community=m1.community)
        client.force_login(owner)
        client.post(reverse("household-create"), {"name": "Test Family"})
        from apps.households.models import Household

        household = Household.objects.get(name="Test Family")

        client.force_login(user)
        resp = client.post(reverse("household-join"), {"household_code": household.join_code})
        assert resp.status_code == 302

        m1.refresh_from_db()
        m2.refresh_from_db()
        assert m1.household_id == household.id
        assert m2.household_id == household.id

        row = AuditLog.objects.filter(action="household.joined", resource_id=household.id).first()
        assert row is not None
        assert str(m1.id) in row.details["memberships"]
        assert str(m2.id) in row.details["memberships"]
