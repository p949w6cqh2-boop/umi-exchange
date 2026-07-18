"""P3 audit fixes — search finds the relevant thing:
area keywords hit (neighborhood was invisible to the tsvector), and results
rank by relevance instead of pure recency when a query is present."""

import pytest
from django.db import connection
from django.test import Client
from django.urls import reverse

from tests.conftest import CategoryFactory, CommunityFactory, MemberFactory, NeedFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def board():
    community = CommunityFactory()
    member = MemberFactory(community=community, role="member")
    category = CategoryFactory(community=community)
    return community, member, category


def _login(member):
    c = Client()
    c.force_login(member.user)
    return c


def test_area_keyword_finds_the_need(board):
    community, member, category = board
    NeedFactory(
        community=community,
        requester=member,
        category=category,
        title="Groceries once a week",
        description="Standing order, nothing heavy.",
        neighborhood="Riverside",
    )
    resp = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug}), {"q": "riverside"})
    assert b"Groceries once a week" in resp.content


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="relevance ranking needs Postgres FTS (ts_rank); SQLite has no ranking, so ordering falls back to recency",
)
def test_relevance_beats_recency_when_searching(board):
    community, member, category = board
    strong = NeedFactory(
        community=community,
        requester=member,
        category=category,
        title="Borrow a ladder for gutter cleaning",
        description="A ladder, ladder work all afternoon.",
    )
    newer_but_less_relevant = NeedFactory(
        community=community,
        requester=member,
        category=category,
        title="Garden tidy-up",
        description="ladder",
    )
    resp = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug}), {"q": "ladder"})
    body = resp.content.decode()
    assert body.index("Borrow a ladder") < body.index("Garden tidy-up")
    assert newer_but_less_relevant.created_at > strong.created_at  # recency alone would flip them


def test_no_query_keeps_newest_first(board):
    community, member, category = board
    NeedFactory(community=community, requester=member, category=category, title="Oldest ask")
    NeedFactory(community=community, requester=member, category=category, title="Newest ask")
    resp = _login(member).get(reverse("community-feed", kwargs={"slug": community.slug}))
    body = resp.content.decode()
    assert body.index("Newest ask") < body.index("Oldest ask")
