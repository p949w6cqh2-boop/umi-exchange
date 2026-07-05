"""H-4: the coordinator CSV export writes member-controlled strings straight into
csv.writer.writerow. A member posts a Need titled `=HYPERLINK(...)` (or sets a
formula as their display name / neighborhood); a coordinator opens the export in
Excel/Sheets and the formula executes in their spreadsheet. The export must
neutralize any cell that starts with a formula-trigger char by prefixing an
apostrophe — reversibly (a real title starting with '-' stays readable)."""

import csv as csvmod

import pytest
from django.test import Client
from django.urls import reverse

from .conftest import (
    CategoryFactory,
    CommunityFactory,
    MatchFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

FORMULA_TITLE = "=cmd|' /c calc'!A0"
FORMULA_NAME = "@SUM(1+1)"
FORMULA_HOOD = "+1-1"
FORMULA_CAT = "-2+3+cmd"


def _coord_client(community):
    coord = MemberFactory(community=community, role="coordinator")
    client = Client()
    client.force_login(coord.user)
    return client


def _data_row(resp):
    rows = list(csvmod.reader(resp.content.decode().splitlines()))
    return rows[1]  # row 0 is the header


@pytest.mark.django_db
def test_needs_export_neutralizes_formula_cells():
    community = CommunityFactory()
    category = CategoryFactory(community=community, name=FORMULA_CAT)
    requester = MemberFactory(community=community, display_name=FORMULA_NAME)
    NeedFactory(
        community=community,
        requester=requester,
        category=category,
        title=FORMULA_TITLE,
        neighborhood=FORMULA_HOOD,
        status="open",
    )

    resp = _coord_client(community).get(reverse("dashboard-export", kwargs={"slug": community.slug}) + "?type=needs")
    assert resp.status_code == 200
    row = _data_row(resp)

    assert "'" + FORMULA_TITLE in row  # title (member-set)
    assert "'" + FORMULA_NAME in row  # requester display_name (member-set)
    assert "'" + FORMULA_HOOD in row  # neighborhood (member-set)
    assert "'" + FORMULA_CAT in row  # category.name (coordinator-set, defense-in-depth)
    assert FORMULA_TITLE not in row  # the bare formula is never emitted


@pytest.mark.django_db
def test_matches_export_neutralizes_formula_cells():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    requester = MemberFactory(community=community)
    offerer = MemberFactory(community=community, display_name=FORMULA_NAME)
    need = NeedFactory(community=community, requester=requester, category=category, title=FORMULA_TITLE, status="open")
    offer = OfferFactory(community=community, offerer=offerer, category=category)
    MatchFactory(need=need, offer=offer, proposed_by=offerer, status="proposed")

    resp = _coord_client(community).get(reverse("dashboard-export", kwargs={"slug": community.slug}) + "?type=matches")
    assert resp.status_code == 200
    row = _data_row(resp)

    assert "'" + FORMULA_TITLE in row  # need.title (member-set)
    assert "'" + FORMULA_NAME in row  # proposed_by display_name (member-set)
    assert FORMULA_TITLE not in row


@pytest.mark.django_db
def test_legit_data_is_not_corrupted():
    """The guard only prefixes cells that START with a trigger char, so ordinary
    values round-trip untouched (no false apostrophes)."""
    community = CommunityFactory()
    category = CategoryFactory(community=community, name="Home Repair")
    requester = MemberFactory(community=community, display_name="Maria G.")
    NeedFactory(
        community=community,
        requester=requester,
        category=category,
        title="Leaky faucet",
        neighborhood="West End",
        status="open",
    )

    resp = _coord_client(community).get(reverse("dashboard-export", kwargs={"slug": community.slug}) + "?type=needs")
    row = _data_row(resp)

    assert "Leaky faucet" in row
    assert "Maria G." in row
    assert "West End" in row
    assert "Home Repair" in row
