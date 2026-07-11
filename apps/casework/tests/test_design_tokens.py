"""Overhaul phase 5 — casework is a work tool: restrained token sweep only
(palette + umi-card + serif), zero layout/flow changes. These guards pin the
palette: no legacy gray-*/blue-* utilities on rendered casework pages."""

import pytest

pytestmark = pytest.mark.django_db

LEGACY = ("text-gray-", "bg-gray-", "text-blue-6", "border-blue-")


def _assert_tokened(body):
    for cls in LEGACY:
        assert cls not in body, f"legacy utility {cls!r} still rendered"


@pytest.mark.parametrize("name", ["list", "create", "visit", "followups-mine"])
def test_casework_pages_tokened(world, auth, u, name):
    client = auth(world.coord_u)
    resp = client.get(u(name))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


def test_case_detail_tokened(world, auth, u, make_note):
    make_note(status="final")
    client = auth(world.coord_u)
    resp = client.get(u("detail", pk=world.case.pk))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())


def test_reauth_page_tokened(world, auth, u):
    client = auth(world.coord_u, stamp=False)  # unstamped → reauth challenge
    resp = client.get(u("reauth"))
    assert resp.status_code == 200
    _assert_tokened(resp.content.decode())
