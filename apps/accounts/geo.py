"""Geolocking: gate who can SIGN UP by country, never who can READ (docs/specs/geolocking.md).

Two switches, both OFF in the code so no self-hosted copy inherits this deployment's lock:

  * GEO_COUNT = True              Phase 0: count sign-up attempts per country (integers only).
  * GEO_ALLOWED_COUNTRIES = [..]  Phase 1: refuse sign-up from anywhere else, with a plain page
                                  that points to self-hosting. Empty = the gate is off.

Both need GEO_DB_PATH (a DB-IP "IP to Country Lite" .mmdb, CC BY 4.0). Rules the spec makes
load-bearing:

  * The only IP source is client_ip() (the reverse-proxy-set X-Real-IP), so a client-supplied
    X-Forwarded-For changes nothing.
  * FAIL OPEN: a missing or unreadable database, or an unknown country, lets the request through,
    and the first failure is logged. A speed bump that breaks closed is an outage.
  * The country is looked up in memory, used for one decision and dropped. No IP is ever stored or
    logged beside it; Phase 0 keeps per-country integers and nothing else.
  * A VPN defeats this in one click. It is a speed bump against casual out-of-region sign-ups, not
    a wall.
"""

import gzip
import logging
import os
import tempfile
import urllib.request

import maxminddb
from django.conf import settings
from django.db.models import F
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .ratelimit import client_ip

log = logging.getLogger(__name__)

UNKNOWN = "--"
DBIP_URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz"

_reader = None
_reader_key = None
_warned = False


def reset_cache():
    global _reader, _reader_key, _warned
    _reader, _reader_key, _warned = None, None, False


def _warn_once(message):
    global _warned
    if not _warned:
        log.warning("geo: %s (geolocking fails OPEN: requests are allowed)", message)
        _warned = True


def _get_reader(path):
    """One reader per database file, reopened when the file is swapped (monthly refresh)."""
    global _reader, _reader_key
    key = (path, os.stat(path).st_mtime_ns)
    if _reader is None or _reader_key != key:
        _reader = maxminddb.open_database(path)
        _reader_key = key
    return _reader


def country_for(ip):
    """ISO country code for `ip`, or None. Never raises: any failure means 'unknown'."""
    path = getattr(settings, "GEO_DB_PATH", "")
    if not path or not ip:
        return None
    try:
        record = _get_reader(path).get(ip)
    except Exception as exc:  # noqa: BLE001 - FAIL OPEN: any lookup failure means "unknown", never a 500
        _warn_once(f"lookup failed ({type(exc).__name__})")
        return None
    code = ((record or {}).get("country") or {}).get("iso_code")
    return code.upper() if code else None


def gated_paths():
    paths = tuple(getattr(settings, "GEO_GATED_PATHS", ()))
    if getattr(settings, "GEO_GATE_ADMIN", False):
        paths += ("/admin/login/",)
    return paths


def count_attempt(country):
    from .models import GeoSignupCount

    code = country or UNKNOWN
    GeoSignupCount.objects.get_or_create(country=code)
    GeoSignupCount.objects.filter(country=code).update(count=F("count") + 1, last_seen=timezone.now())


class GeoGateMiddleware:
    """Placed after AuthRateLimitMiddleware, so a refused region still counts against the
    per-IP throttle. Does nothing at all unless a switch is on."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        paths = gated_paths()
        if not paths or not request.path.startswith(paths):
            return self.get_response(request)
        allowed = [c.upper() for c in getattr(settings, "GEO_ALLOWED_COUNTRIES", [])]
        counting = getattr(settings, "GEO_COUNT", False) and request.method == "POST"
        if not allowed and not counting:
            return self.get_response(request)

        country = country_for(client_ip(request))
        if counting:
            try:
                count_attempt(country)
            except Exception as exc:  # noqa: BLE001 - counting must never cost anyone their sign-up
                log.warning("geo: could not count a sign-up attempt (%s); allowed", type(exc).__name__)
        if allowed and country and country not in allowed:
            return render(
                request,
                "accounts/geo_closed.html",
                {
                    "region": getattr(settings, "GEO_REGION_LABEL", "") or "our pilot area",
                    "self_host_url": reverse("technology"),
                },
                status=403,
            )
        return self.get_response(request)


def download_database(month, dest):
    """Fetch DB-IP's monthly country file and swap it in atomically. The old file stays in place
    unless the new one decompresses AND opens as a database."""
    url = DBIP_URL.format(month=month)
    resp = urllib.request.urlopen(url, timeout=60)  # noqa: S310 (fixed https URL)
    try:
        payload = gzip.decompress(resp.read())
    finally:
        resp.close()
    directory = os.path.dirname(os.path.abspath(dest)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".geo-", suffix=".mmdb")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        maxminddb.open_database(tmp).close()
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return len(payload)
