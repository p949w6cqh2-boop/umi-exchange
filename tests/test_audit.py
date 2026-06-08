"""Append-only audit log enforcement (UMI Protocol Section 8.3)."""
import uuid

import pytest
from django.core.exceptions import PermissionDenied

from apps.audit.models import AuditLog


@pytest.mark.django_db
class TestAuditAppendOnly:
    def _entry(self):
        return AuditLog.objects.create(
            user=None, action="create", resource_type="match", resource_id=uuid.uuid4()
        )

    def test_insert_is_allowed(self):
        entry = self._entry()
        assert AuditLog.objects.filter(pk=entry.pk).exists()

    def test_update_is_blocked(self):
        entry = self._entry()
        entry.action = "tampered"
        with pytest.raises(PermissionDenied):
            entry.save()
        entry.refresh_from_db()
        assert entry.action == "create"

    def test_delete_is_blocked(self):
        entry = self._entry()
        with pytest.raises(PermissionDenied):
            entry.delete()
        assert AuditLog.objects.filter(pk=entry.pk).exists()
