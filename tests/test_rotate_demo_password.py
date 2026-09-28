"""rotate_demo_password: the seeded demo accounts' shared password is in this public
repository, which is fine on a laptop and not on a live site. There, anyone could sign in
as the demo parish's coordinator, and a coordinator can vouch ANY account on the instance
as a verified human (VouchMemberView resolves its target by username alone)."""

import io
import sys

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditLog

NEW = "a-new-private-demo-password-42"


def _stdin(monkeypatch, text):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


@pytest.fixture()
def seeded(settings):
    settings.DEBUG = True
    call_command("seed_demo_parish", stdout=io.StringIO())
    return get_user_model().objects.filter(email__iendswith="@demo.invalid")


@pytest.mark.django_db
class TestRotateDemoPassword:
    def test_every_seeded_account_moves_off_the_public_password(self, seeded, monkeypatch):
        assert seeded.count() == 12
        assert all(u.check_password("demo-parish") for u in seeded)
        _stdin(monkeypatch, NEW + "\n")
        call_command("rotate_demo_password", stdout=io.StringIO())
        for u in get_user_model().objects.filter(email__iendswith="@demo.invalid"):
            assert not u.check_password("demo-parish"), u.username
            assert u.check_password(NEW), u.username

    def test_real_accounts_are_never_touched(self, seeded, monkeypatch):
        user_model = get_user_model()
        real = user_model.objects.create_user(
            username="realperson", email="real@example.com", password="their-own-pass-123"
        )
        # A real registrant who typed a .invalid address is still not a seeded account.
        stray = user_model.objects.create_user(
            username="stray", email="stray@demo.invalid", password="their-own-pass-456"
        )
        _stdin(monkeypatch, NEW + "\n")
        call_command("rotate_demo_password", stdout=io.StringIO())
        real.refresh_from_db()
        stray.refresh_from_db()
        assert real.check_password("their-own-pass-123")
        assert stray.check_password("their-own-pass-456")

    def test_output_never_carries_the_password(self, seeded, monkeypatch):
        _stdin(monkeypatch, NEW + "\n")
        out = io.StringIO()
        call_command("rotate_demo_password", stdout=out)
        assert NEW not in out.getvalue()
        assert "12" in out.getvalue()

    def test_each_rotation_is_on_the_audit_record(self, seeded, monkeypatch):
        _stdin(monkeypatch, NEW + "\n")
        call_command("rotate_demo_password", stdout=io.StringIO())
        assert AuditLog.objects.filter(action="demo.password_rotated").count() == 12

    @pytest.mark.parametrize("given", ["", "\n", "short\n", "demo-parish\n"])
    def test_refuses_a_missing_short_or_public_password(self, seeded, monkeypatch, given):
        _stdin(monkeypatch, given)
        # Match the REASON: an unknown command raises CommandError too, and would pass.
        with pytest.raises(CommandError, match="refusing"):
            call_command("rotate_demo_password", stdout=io.StringIO())
        assert all(u.check_password("demo-parish") for u in seeded)

    def test_refuses_when_there_is_no_demo_parish(self, monkeypatch):
        _stdin(monkeypatch, NEW + "\n")
        with pytest.raises(CommandError, match="no seeded demo accounts"):
            call_command("rotate_demo_password", stdout=io.StringIO())
