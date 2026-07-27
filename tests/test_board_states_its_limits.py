"""
The board says what it is, and safety controls are reachable from it
(ethics gate box 5, second half — docs/ethics-and-safety.md:217-223).

The gate asks for two things beyond the consent work:

  "the terms and the connect screen say plainly that UMI brokers introductions
   and does not vet people, run background checks, supervise meetings, or
   guarantee safety, and ... reporting or blocking a member is possible from the
   board itself."

Before this, the sentence existed only in docs/ethics-and-safety.md:173-176 and had
never been transcribed into a single user-facing surface — there was no terms page
at all, and the connect screen carried only warm copy about reaching out. Reporting
or blocking a *member* was reachable from exactly one place: the accepted-match
screen. From the board proper you could flag a post but not a person, the block
list had no link from anywhere, and the moderation queue had none either.

Promising safety you do not provide is worse than promising nothing, because people
act on it. This is the board saying plainly what it is.
"""

import pytest
from django.test import Client
from django.urls import reverse

from tests.conftest import (
    CategoryFactory,
    CommunityFactory,
    MemberFactory,
    NeedFactory,
    OfferFactory,
)

pytestmark = pytest.mark.django_db

# The load-bearing sentence, per docs/ethics-and-safety.md:173-176.
BROKERS = "brokers introductions"
DOES_NOT = ["does not vet", "background check", "supervise", "guarantee"]


def _client(member):
    c = Client()
    c.force_login(member.user)
    return c


@pytest.fixture
def board():
    community = CommunityFactory()
    category = CategoryFactory(community=community)
    ada = MemberFactory(community=community, display_name="Ada")
    ben = MemberFactory(community=community, display_name="Ben")
    return community, category, ada, ben


# ------------------------------------------------------------- the terms page
def test_a_terms_page_exists_and_states_the_limits():
    body = Client().get(reverse("terms")).content.decode()

    assert BROKERS in body
    for clause in DOES_NOT:
        assert clause in body, f"the terms must say plainly that UMI does not {clause}"


def test_the_terms_are_reachable_without_signing_in():
    """Someone deciding whether to join must be able to read them first."""
    assert Client().get(reverse("terms")).status_code == 200


def test_the_footer_links_the_terms(board):
    community, category, ada, ben = board

    body = _client(ada).get(reverse("hub:community", args=[community.slug])).content.decode()

    assert reverse("terms") in body


# ---------------------------------------------------------- the connect screen
def test_the_connect_screen_states_the_limits_before_accepting(board):
    """Before, not after. A limit disclosed once contact is already exchanged is
    not a limit, it is an apology."""
    community, category, ada, ben = board
    from tests.conftest import MatchFactory

    need = NeedFactory(community=community, category=category, requester=ada, status="open")
    offer = OfferFactory(community=community, category=category, offerer=ben)
    match = MatchFactory(need=need, offer=offer, proposed_by=ben, status="proposed")

    body = _client(ada).get(reverse("match-detail", args=[community.slug, match.pk])).content.decode()

    assert BROKERS in body
    assert "does not vet" in body


# --------------------------------------------- report/block from the board
def test_a_neighbour_can_report_the_person_who_posted_a_need(board):
    community, category, ada, ben = board
    need = NeedFactory(community=community, category=category, requester=ben, status="open")

    body = _client(ada).get(reverse("need-detail", args=[community.slug, need.pk])).content.decode()

    assert reverse("moderation:flag", args=[community.slug]) in body
    assert "target_type" in body and "member" in body


def test_a_neighbour_can_block_the_person_who_posted_an_offer(board):
    community, category, ada, ben = board
    offer = OfferFactory(community=community, category=category, offerer=ben)

    body = _client(ada).get(reverse("offer-detail", args=[community.slug, offer.pk])).content.decode()

    assert reverse("moderation:block", args=[community.slug]) in body


def test_no_safety_controls_against_yourself(board):
    """Reporting yourself is noise, and blocking yourself is a footgun."""
    community, category, ada, ben = board
    own = NeedFactory(community=community, category=category, requester=ada, status="open")

    body = _client(ada).get(reverse("need-detail", args=[community.slug, own.pk])).content.decode()

    assert reverse("moderation:block", args=[community.slug]) not in body


def test_the_block_list_is_reachable_from_settings(board):
    """Blocking is only half a promise if you can never see or undo it."""
    community, category, ada, ben = board

    body = _client(ada).get(reverse("account-settings")).content.decode()

    assert reverse("moderation:blocks", args=[community.slug]) in body


def test_the_moderation_queue_is_reachable_by_a_coordinator(board):
    """Reports go nowhere if the only route to the queue is a notification link."""
    community, category, ada, ben = board
    coordinator = MemberFactory(community=community, role="coordinator", display_name="Cara")

    body = _client(coordinator).get(reverse("community-dashboard", args=[community.slug])).content.decode()

    assert reverse("moderation:queue", args=[community.slug]) in body


def test_the_need_form_cannot_write_a_third_partys_name(board):
    """There used to be an on-behalf field here that no template rendered and no
    screen displayed — reachable only by a hand-crafted POST, and unremovable by
    the person it named. Lake 1 does not collect that until it can do it honestly."""
    from apps.needs.forms import NeedForm

    community, category, ada, ben = board
    form = NeedForm(community=community, member=ada)

    assert "on_behalf_of_text" not in form.fields
