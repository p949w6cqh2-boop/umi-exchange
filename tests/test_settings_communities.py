"""Account settings: the communities you are in outrank the invitations to join more.

His observation, 2026-10-26: "the join community section is more prominent of a section
then joined communities, I dont think thats best." Nothing on that page is visually
bigger than anything else — every card is `umi-card` + `h2 text-lg` — so position was
the only hierarchy, and Household (which advertises "Join household" to anyone not in
one) sat above the list of communities the person actually belongs to.

The household defect fell out of reading that template: `memberships.0.household` reads
one slot, but household is a ForeignKey on Member, so it is per-community. Someone in two
communities saw only the first one's household, and if that slot was empty the page said
"Not in a household" while they were in one somewhere else.
"""

import pytest
from django.urls import reverse

from apps.households.models import Household
from tests.conftest import CommunityFactory, MemberFactory, UserFactory


@pytest.mark.django_db
class TestCommunitiesOutrankJoining:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.user = UserFactory()
        client.force_login(self.user)
        self.client = client

    def test_communities_card_comes_before_household_card(self):
        """Position is the whole hierarchy on this page, so order is the fix."""
        MemberFactory(user=self.user, community=CommunityFactory(created_by=self.user))

        body = self.client.get(reverse("account-settings")).content.decode()

        assert body.index("My Communities") < body.index(">Household<"), (
            "Household (which offers 'Join household') must not sit above the list of "
            "communities the person is already in."
        )

    def test_communities_heading_outweighs_the_other_cards(self):
        """It is the only card that links somewhere you go, not a setting you change."""
        MemberFactory(user=self.user, community=CommunityFactory(created_by=self.user))

        body = self.client.get(reverse("account-settings")).content.decode()
        heading = body[body.index("My Communities") - 120 : body.index("My Communities")]

        assert "text-lg" not in heading, "My Communities should not share the weight of every other card"
        assert "text-xl" in heading or "text-2xl" in heading


@pytest.mark.django_db
class TestHouseholdIsPerCommunity:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.user = UserFactory()
        client.force_login(self.user)
        self.client = client

    def test_household_in_a_second_community_is_shown(self):
        """`memberships.0.household` missed this entirely."""
        first = CommunityFactory(created_by=self.user)
        second = CommunityFactory(created_by=self.user)
        household = Household.objects.create(name="The Rodriguez Family", created_by=self.user)

        MemberFactory(user=self.user, community=first, household=None)
        MemberFactory(user=self.user, community=second, household=household)

        body = self.client.get(reverse("account-settings")).content.decode()

        assert "The Rodriguez Family" in body
        assert "Not in a household." not in body, (
            "The page told someone they were in no household while they were in one in their second community."
        )

    def test_not_in_a_household_still_shown_when_truly_in_none(self):
        """The guard must not swing the other way and hide the create/join links."""
        MemberFactory(user=self.user, community=CommunityFactory(created_by=self.user), household=None)

        body = self.client.get(reverse("account-settings")).content.decode()

        assert "Not in a household." in body
        assert reverse("household-join") in body
