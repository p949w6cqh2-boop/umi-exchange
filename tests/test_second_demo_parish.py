"""A second fictional demo parish, built for fresh B-roll and shaped for TikTok.

The founder's ask (2026-11-21): new footage of "a brand new community", optimized for TikTok,
because the St. Brigid's screens have carried every cut since August. The second parish rides
the same seed command behind --parish, so every guard the first one earned (DEBUG-only, never
adopting a real account, phones so no reveal is a bare name, both yeses on a match) applies to it
unchanged. Running the command with no arguments must still mean St. Brigid's: three runbooks and
the tutorial rig call it that way.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.communities.management.commands.seed_demo_parish import MEMBERS, PARISHES
from apps.communities.models import Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer

SECOND = "st-kateris"


@pytest.mark.django_db
class TestSecondDemoParish:
    def test_no_arguments_still_means_st_brigids_alone(self, settings):
        settings.DEBUG = True
        call_command("seed_demo_parish")
        assert Community.objects.filter(slug="st-brigids").exists()
        assert not Community.objects.filter(slug=SECOND).exists()

    def test_refuses_when_debug_is_off(self, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError):
            call_command("seed_demo_parish", parish=SECOND)
        assert not Community.objects.filter(slug=SECOND).exists()

    def test_refuses_an_unknown_parish(self, settings):
        settings.DEBUG = True
        with pytest.raises(CommandError):
            call_command("seed_demo_parish", parish="no-such-parish")

    def test_seeds_a_living_second_parish(self, settings):
        settings.DEBUG = True
        call_command("seed_demo_parish", parish=SECOND)
        community = Community.objects.get(slug=SECOND)
        assert community.name == PARISHES[SECOND].name
        assert Member.objects.filter(community=community).count() == len(PARISHES[SECOND].members)
        assert Member.objects.filter(community=community, role="coordinator").exists()
        assert Need.objects.filter(community=community, status="open").count() >= 4
        assert Offer.objects.filter(community=community, status="active").count() >= 3
        statuses = set(Match.objects.filter(need__community=community).values_list("status", flat=True))
        assert {"proposed", "accepted", "fulfilled"} <= statuses

    def test_both_parishes_live_in_one_database(self, settings):
        """The B-roll rig seeds a scratch DB that may already hold St. Brigid's."""
        settings.DEBUG = True
        call_command("seed_demo_parish")
        call_command("seed_demo_parish", parish=SECOND)
        assert Community.objects.filter(slug__in=["st-brigids", SECOND]).count() == 2
        assert Member.objects.filter(community__slug="st-brigids").count() == len(MEMBERS)

    def test_reseeding_is_idempotent(self, settings):
        settings.DEBUG = True
        call_command("seed_demo_parish", parish=SECOND)
        call_command("seed_demo_parish", parish=SECOND)
        community = Community.objects.get(slug=SECOND)
        assert Need.objects.filter(community=community).count() == len(PARISHES[SECOND].needs)
        assert Match.objects.filter(need__community=community).count() == len(PARISHES[SECOND].matches)

    def test_the_accepted_match_shows_both_yeses(self, settings):
        """'Two people say yes' is one of his best TikToks (C7). The screen has to show it."""
        settings.DEBUG = True
        call_command("seed_demo_parish", parish=SECOND)
        accepted = Match.objects.filter(need__community__slug=SECOND, status="accepted")
        assert accepted.exists()
        assert all(m.asker_yes_at and m.helper_yes_at for m in accepted)


class TestSecondParishData:
    """Contracts on the data itself, no database needed."""

    def test_usernames_never_collide_with_st_brigids(self):
        first = {username for username, _, _ in MEMBERS}
        second = {username for username, _, _ in PARISHES[SECOND].members}
        assert not first & second

    def test_every_member_has_a_phone_so_no_reveal_is_a_bare_name(self):
        spec = PARISHES[SECOND]
        assert {username for username, _, _ in spec.members} == set(spec.phones)

    def test_phones_are_in_the_range_set_aside_for_fiction(self):
        for phone in PARISHES[SECOND].phones.values():
            assert phone.startswith("555-01")

    def test_titles_read_at_phone_size(self):
        """TikTok: a title longer than five words does not read on a phone at a glance."""
        spec = PARISHES[SECOND]
        titles = [n[2] for n in spec.needs] + [o[2] for o in spec.offers]
        assert all(len(t.split()) <= 5 for t in titles), [t for t in titles if len(t.split()) > 5]

    def test_matches_point_at_real_asks_and_offers(self):
        spec = PARISHES[SECOND]
        need_titles = {n[2] for n in spec.needs}
        offer_titles = {o[2] for o in spec.offers}
        for need_title, offer_title, _through, _helper_yes in spec.matches:
            assert need_title in need_titles
            assert offer_title in offer_titles
