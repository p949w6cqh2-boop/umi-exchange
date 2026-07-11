"""Overhaul phase 5 — federation member surfaces on the token idiom.
Palette guards only; flows untouched."""

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

LEGACY = ("text-gray-", "bg-gray-", "text-blue-6", "border-blue-")


def _assert_tokened(body):
    for cls in LEGACY:
        assert cls not in body, f"legacy utility {cls!r} still rendered"


def test_listings_page_tokened(client, fed_settings, active_link, world):
    client.force_login(world.plain_u)
    resp = client.get(f"/c/{world.community.slug}/federation/listings")
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


def test_matches_page_tokened(client, fed_settings, active_link, world):
    client.force_login(world.plain_u)
    resp = client.get(f"/c/{world.community.slug}/federation/matches")
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())
