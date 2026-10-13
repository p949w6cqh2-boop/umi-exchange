"""
A proposal from another community arrives with what it offers (the founder's call, 2026-10-13,
bug hunt L61).

The sending side put the offer's title and category in every proposal, as the federation design
says (§5 table: title up to 200 characters, rendered as text, and the category), but the receiving
side dropped both, so the person here accepted a "<community> (federated)" match without seeing
what was offered. Now the authority keeps them on the FederatedMatch and shows them, as plain
text, on the match page and in the ask's list of matches. Inbound text is capped and stripped of
control and direction-override characters, and a review-list word puts the match in front of the
coordinators, as it would for a local post.
"""

import json
import uuid

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.communities.models import Category
from apps.consent.models import Consent
from apps.federation import sharing
from apps.federation.models import FederatedMatch
from apps.moderation.models import Flag

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.federation.tests.urls_enabled")]

PROPOSALS_PATH = "/federation/v1/proposals"


@pytest.fixture
def shared_need(fed_settings, active_link, world):
    from apps.needs.models import Need

    cat = Category.objects.create(community=world.community, name="Food")
    need = Need.objects.create(
        community=world.community,
        requester=world.plain,
        category=cat,
        title="groceries",
        urgency="high",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    Consent.objects.create(
        participant=world.plain_u,
        granted_to="Peer",
        grantee_type="community",
        grantee_id=active_link.remote_community_uuid,
        scope=["federated_share"],
        purpose="fed",
        method="digital",
    )
    share = sharing.share_record(need, active_link, actor_user=world.admin_u)
    return need, share


def _propose(client, remote, fed_settings, share, offer):
    item = {"need_remote_uuid": str(share.remote_uuid), "proposal_uuid": str(uuid.uuid4())}
    if offer is not None:
        item["offer"] = offer
    body = json.dumps({"proposals": [item]}).encode()
    sig = remote.sign("POST", settings.SITE_URL.rstrip("/") + PROPOSALS_PATH, body, fed_settings.instance_id)
    resp = client.post(PROPOSALS_PATH, data=body, content_type="application/json", HTTP_X_UMI_SIGNATURE=sig)
    assert resp.status_code == 200, resp.content
    result = resp.json()["results"][0]
    assert result["status"] == "created", result
    return FederatedMatch.objects.get(match_id=result["match_uuid"])


def test_the_offer_title_and_category_are_kept(client, fed_settings, remote, shared_need):
    _need, share = shared_need
    fm = _propose(client, remote, fed_settings, share, {"title": "Fresh bread and soup", "category": "Meals"})

    assert fm.offer_title == "Fresh bread and soup"
    assert fm.offer_category == "Meals"


def test_the_asker_sees_what_is_offered_as_plain_text(client, fed_settings, remote, shared_need, world):
    need, share = shared_need
    fm = _propose(client, remote, fed_settings, share, {"title": "<b>Fresh</b> bread & soup", "category": "Meals"})
    asker = Client()
    asker.force_login(world.plain_u)

    page = asker.get(reverse("match-detail", kwargs={"slug": world.community.slug, "pk": fm.match_id}))
    body = page.content.decode()
    assert page.status_code == 200
    assert "&lt;b&gt;Fresh&lt;/b&gt; bread &amp; soup" in body
    assert "<b>Fresh</b>" not in body
    assert "Meals" in body
    assert "Peer Board" in body  # the community it comes from

    listing = asker.get(reverse("need-detail", kwargs={"slug": world.community.slug, "pk": need.pk}))
    assert "&lt;b&gt;Fresh&lt;/b&gt; bread &amp; soup" in listing.content.decode()


@pytest.mark.parametrize(
    ("offer", "title", "category"),
    [
        ({"title": "x" * 500, "category": "y" * 300}, "x" * 200, "y" * 100),
        ({"title": "Rides‮ to clinic\x00\x07", "category": "Trans⁦port"}, "Rides to clinic", "Transport"),
        ({"title": 42, "category": ["Meals"]}, "", ""),
        ({"title": "Tea", "category_slug": "drinks"}, "Tea", "drinks"),
        ("not an object", "", ""),
        (None, "", ""),
    ],
    ids=["capped", "controls-stripped", "non-strings", "slug-key", "not-an-object", "absent"],
)
def test_inbound_text_is_capped_and_cleaned(client, fed_settings, remote, shared_need, offer, title, category):
    _need, share = shared_need
    fm = _propose(client, remote, fed_settings, share, offer)

    assert fm.offer_title == title
    assert fm.offer_category == category


def test_a_review_word_in_a_peer_title_is_flagged_for_coordinators(client, fed_settings, remote, shared_need):
    _need, share = shared_need
    fm = _propose(client, remote, fed_settings, share, {"title": "Help after abuse at home", "category": "Support"})

    flag = Flag.objects.get(target_type="match", target_id=fm.match_id)
    assert flag.reason == "word_list"
    assert flag.reporter is None
