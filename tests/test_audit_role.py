"""The append-only REVOKE must target the runtime app role, not whoever ran
the migration — settings.AUDIT_DB_APP_ROLE is that override (must-fix #1)."""

import importlib
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings

append_only = importlib.import_module("apps.audit.migrations.0002_append_only")


class TestAppRoleResolution:
    @override_settings(AUDIT_DB_APP_ROLE="umi_app")
    def test_explicit_setting_wins(self):
        assert append_only._app_role() == "umi_app"

    def test_falls_back_to_database_user(self, settings):
        settings.AUDIT_DB_APP_ROLE = None
        settings.DATABASES = {"default": {"USER": "fallback_user"}}
        assert append_only._app_role() == "fallback_user"


@pytest.mark.django_db
class TestRestrictCommand:
    @override_settings(AUDIT_DB_APP_ROLE="umi_app")
    def test_command_targets_app_role_setting(self):
        out = StringIO()
        with mock.patch("apps.audit.management.commands.restrict_audit_permissions.connection") as conn:
            conn.cursor.return_value.__enter__ = mock.Mock(return_value=mock.Mock())
            conn.cursor.return_value.__exit__ = mock.Mock(return_value=False)
            call_command("restrict_audit_permissions", stdout=out)
        assert "umi_app" in out.getvalue()
