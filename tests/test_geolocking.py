"""Geolocking (docs/specs/geolocking.md): gate who can SIGN UP by country, never who can READ.

Phase 0 counts sign-up attempts per country (integers only). Phase 1 refuses sign-up from outside
GEO_ALLOWED_COUNTRIES with a plain page that points to self-hosting. Empty allow list = OFF, and the
codebase default is empty, so no self-hoster inherits this deployment's lock. Fails OPEN.
"""

import gzip
import io
import logging
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts import geo
from apps.accounts.models import GeoSignupCount, User
from tests.conftest import register_payload

pytestmark = pytest.mark.django_db

ON = {"GEO_DB_PATH": "/tmp/test-geo.mmdb"}


@pytest.fixture(autouse=True)
def _clean(settings):
    from django.core.cache import cache

    settings.RATELIMIT_ENABLED = False
    cache.clear()
    geo.reset_cache()


def _register(client, username="farhere", **extra):
    data = register_payload(
        username=username, email="", password="Str0ng-pass-word!", password_confirm="Str0ng-pass-word!"
    )
    return client.post(reverse("register"), data, **extra)


def _country(code):
    return mock.patch.object(geo, "country_for", return_value=code)


# ── Off by default ─────────────────────────────────────────────


def test_defaults_are_off(settings):
    assert settings.GEO_DB_PATH == ""
    assert settings.GEO_ALLOWED_COUNTRIES == []
    assert settings.GEO_COUNT is False


def test_with_nothing_configured_sign_up_is_untouched_and_no_lookup_happens():
    with mock.patch.object(geo, "country_for") as lookup:
        resp = Client().get(reverse("register"))
        assert resp.status_code == 200
        _register(Client())
    lookup.assert_not_called()
    assert User.objects.filter(username="farhere").exists()


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=[])
def test_empty_allow_list_means_the_gate_is_off_even_for_a_far_country():
    with _country("FR"):
        assert Client().get(reverse("register")).status_code == 200


# ── Phase 1: the gate ──────────────────────────────────────────


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"])
def test_allowed_country_signs_up():
    with _country("US"):
        _register(Client())
    assert User.objects.filter(username="farhere").exists()


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"], GEO_REGION_LABEL="the United States")
def test_blocked_country_gets_the_plain_page_with_the_self_host_link_and_no_account():
    with _country("FR"):
        page = Client().get(reverse("register"))
        post = _register(Client())
    for resp in (page, post):
        assert resp.status_code == 403
        body = resp.content.decode()
        assert "the United States" in body
        assert reverse("technology") in body
    assert not User.objects.filter(username="farhere").exists()


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"])
def test_unknown_country_is_allowed():
    with _country(None):
        assert Client().get(reverse("register")).status_code == 200


@override_settings(GEO_DB_PATH="/nonexistent/geo.mmdb", GEO_ALLOWED_COUNTRIES=["US"])
def test_missing_database_fails_open_and_says_so(caplog):
    with caplog.at_level(logging.WARNING):
        assert Client().get(reverse("register")).status_code == 200
    assert "geo" in caplog.text.lower()


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"])
def test_any_lookup_error_fails_open_not_a_500(tmp_path, settings):
    """The review's MAJOR finding: an exception type the lookup did not anticipate must still
    allow the request rather than 500 the sign-up page."""
    settings.GEO_DB_PATH = str(tmp_path / "geo.mmdb")
    (tmp_path / "geo.mmdb").write_bytes(b"x")
    reader = mock.Mock()
    reader.get.side_effect = RuntimeError("unexpected inside the reader")
    with mock.patch.object(geo.maxminddb, "open_database", return_value=reader):
        assert Client().get(reverse("register")).status_code == 200


@override_settings(**ON, GEO_COUNT=True)
def test_a_counting_failure_never_blocks_the_sign_up(caplog):
    with _country("FR"), mock.patch.object(geo, "count_attempt", side_effect=RuntimeError("db down")):
        with caplog.at_level(logging.WARNING):
            _register(Client(), username="stillin")
    assert User.objects.filter(username="stillin").exists()
    assert "could not count" in caplog.text


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"])
def test_reading_pages_are_never_gated():
    with _country("FR"):
        for name in ("landing", "about", "technology", "login"):
            assert Client().get(reverse(name)).status_code == 200, name


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"])
def test_admin_login_is_not_gated_unless_opted_in():
    with _country("FR"):
        assert Client().get("/admin/login/").status_code != 403


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"], GEO_GATE_ADMIN=True)
def test_admin_login_gated_when_opted_in():
    with _country("FR"):
        assert Client().get("/admin/login/").status_code == 403


@override_settings(**ON, GEO_ALLOWED_COUNTRIES=["US"])
def test_a_spoofed_forwarded_for_header_changes_nothing():
    with mock.patch.object(geo, "country_for", return_value="US") as lookup:
        Client().get(reverse("register"), REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="8.8.8.8")
    lookup.assert_called_once_with("203.0.113.9")


# ── Phase 0: count, store nothing else ─────────────────────────


@override_settings(**ON, GEO_COUNT=True)
def test_count_mode_counts_sign_up_attempts_per_country_and_blocks_nothing():
    with _country("FR"):
        Client().get(reverse("register"))  # a page view is not an attempt
        _register(Client(), username="one")
        _register(Client(), username="two")
    with _country(None):
        _register(Client(), username="three")
    assert GeoSignupCount.objects.get(country="FR").count == 2
    assert GeoSignupCount.objects.get(country="--").count == 1
    assert User.objects.filter(username__in=["one", "two", "three"]).count() == 3


@override_settings(**ON, GEO_COUNT=True)
def test_no_ip_is_stored_or_logged(caplog):
    with caplog.at_level(logging.DEBUG), _country("FR"):
        _register(Client(), REMOTE_ADDR="198.51.100.77")
    stored = " ".join(str(v) for row in GeoSignupCount.objects.values() for v in row.values())
    assert "198.51.100.77" not in stored
    assert "198.51.100.77" not in caplog.text
    assert {f.name for f in GeoSignupCount._meta.get_fields()} == {"country", "count", "first_seen", "last_seen"}


@override_settings(**ON, GEO_COUNT=True)
def test_geo_counts_command_prints_the_table():
    with _country("US"):
        _register(Client())
    out = io.StringIO()
    call_command("geo_counts", stdout=out)
    assert "US" in out.getvalue() and "1" in out.getvalue()


# ── The real lookup and the monthly refresh ────────────────────


def test_country_for_reads_the_iso_code_from_the_database(settings, tmp_path):
    settings.GEO_DB_PATH = str(tmp_path / "geo.mmdb")
    (tmp_path / "geo.mmdb").write_bytes(b"placeholder")
    reader = mock.Mock()
    reader.get.return_value = {"country": {"iso_code": "us"}}
    with mock.patch.object(geo.maxminddb, "open_database", return_value=reader):
        assert geo.country_for("203.0.113.9") == "US"
        reader.get.return_value = None
        assert geo.country_for("10.0.0.1") is None


def test_refresh_swaps_in_a_valid_download_and_keeps_the_old_file_on_failure(settings, tmp_path):
    dest = tmp_path / "geo.mmdb"
    dest.write_bytes(b"OLD")
    settings.GEO_DB_PATH = str(dest)
    good = mock.Mock()
    good.read.return_value = gzip.compress(b"NEWDB")
    with (
        mock.patch.object(geo.urllib.request, "urlopen", return_value=good),
        mock.patch.object(geo.maxminddb, "open_database", return_value=mock.Mock()),
    ):
        call_command("refresh_geoip", "--month", "2026-10")
    assert dest.read_bytes() == b"NEWDB"

    bad = mock.Mock()
    bad.read.return_value = b"not gzip"
    with mock.patch.object(geo.urllib.request, "urlopen", return_value=bad), pytest.raises(Exception):
        call_command("refresh_geoip", "--month", "2026-11")
    assert dest.read_bytes() == b"NEWDB"


def test_the_download_identifies_itself_because_db_ip_refuses_pythons_default(tmp_path):
    """Measured 2026-10-01 from the droplet and a laptop: DB-IP answers 403 to Python's default
    user agent and 200 to curl's or an identifying one. Without this, the first refresh failed
    (safely: the old file was kept) and counting could only be switched on by hand. The agent
    names the software, not a deployment, because self-hosted copies run it too."""
    good = mock.Mock()
    good.read.return_value = gzip.compress(b"NEWDB")
    with (
        mock.patch.object(geo.urllib.request, "urlopen", return_value=good) as opened,
        mock.patch.object(geo.maxminddb, "open_database", return_value=mock.Mock()),
    ):
        geo.download_database("2026-10", str(tmp_path / "geo.mmdb"))
    request = opened.call_args.args[0]
    agent = request.get_header("User-agent") or ""
    assert "umi-exchange" in agent
    assert "Python-urllib" not in agent
    assert "reciprocalaid" not in agent
