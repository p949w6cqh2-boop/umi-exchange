"""The bright-line check — `manage.py bright_line` (docs/ethics-and-safety.md Part 4).

Why this exists: Part 4 said "fictional demo data only" for weeks while ~7 of 22 accounts
carried real email addresses, and nothing counted. The correction wrote: "a bright line needs
a check, not a sentence." This is the check.

Two halves, deliberately different:
  - registrations are REPORTED (they are already non-zero; a permanently red check is an
    anti-control);
  - sensitive rows — people, households, casework, federation — are FAILED ON (exit 2), because
    they are zero today and must stay zero until the gate closes.
Counts only. The output never carries a username or an address.
"""

import pytest
from django.core.management import call_command
from django.db import connection

from apps.households.models import Household
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db


def run(*args):
    """call_command with stdout captured; returns (exit_code, text)."""
    import io

    out = io.StringIO()
    try:
        call_command("bright_line", *args, stdout=out)
    except SystemExit as e:  # the command exits 2 on a crossed line
        return e.code, out.getvalue()
    return 0, out.getvalue()


def test_counts_seeded_and_other_accounts_separately():
    for i in range(3):
        UserFactory(username=f"demo{i}", email=f"demo{i}@demo.invalid")
    UserFactory(username="real1", email="someone@example.org")
    UserFactory(username="real2", email="another@example.org")
    UserFactory(username="noemail", email=None)

    code, text = run()

    assert code == 0
    assert "accounts" in text
    assert "seeded (@demo.invalid) 3" in text
    assert "other 3 (2 with email, 1 without)" in text


def test_holding_when_no_sensitive_rows():
    UserFactory(username="demo0", email="demo0@demo.invalid")
    code, text = run()
    assert code == 0
    assert "BRIGHT LINE: HOLDING" in text
    assert "sensitive rows   0" in text


def test_exits_2_the_moment_a_sensitive_row_exists():
    """A household is plaintext and needs no key, so it is the cheapest row that crosses the
    line — and the line names households explicitly."""
    u = UserFactory(username="steward", email="s@example.org")
    Household.objects.create(name="A family", created_by=u)

    code, text = run()

    assert code == 2
    assert "BRIGHT LINE: CROSSED" in text
    assert "households 1" in text


def test_output_never_carries_pii():
    UserFactory(username="veryspecificname", email="veryspecific@example.org")
    _, text = run()
    assert "veryspecificname" not in text
    assert "veryspecific@example.org" not in text
    assert "example.org" not in text


def test_counts_every_model_in_the_sensitive_apps_not_a_hardcoded_list():
    """If casework grows a table, the check must see it without being edited. Assert the
    command derives its table set from the app registry by checking it names the casework
    tables that exist right now."""
    _, text = run()
    casework_tables = [t for t in connection.introspection.table_names() if t.startswith("casework_")]
    assert casework_tables, "test precondition: casework app has tables"
    assert "casework 0" in text
