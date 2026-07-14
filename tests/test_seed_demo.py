"""The demo seed must be idempotent, believable, and impossible in production."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.communities.models import Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.tags.models import MemberTag


@pytest.mark.django_db
class TestSeedDemoParish:
    def test_refuses_when_debug_is_off(self, settings):
        settings.DEBUG = False
        with pytest.raises(CommandError):
            call_command("seed_demo_parish")
        assert not Community.objects.filter(slug="st-brigids").exists()

    def test_seeds_a_living_parish(self, settings):
        settings.DEBUG = True
        call_command("seed_demo_parish")
        community = Community.objects.get(slug="st-brigids")
        assert Member.objects.filter(community=community).count() == 12
        assert Member.objects.filter(community=community, role="coordinator").exists()
        assert Need.objects.filter(community=community, status="open").count() >= 4
        assert Offer.objects.filter(community=community, status="active").count() >= 3
        statuses = set(Match.objects.filter(need__community=community).values_list("status", flat=True))
        assert {"proposed", "accepted", "fulfilled"} <= statuses
        assert MemberTag.objects.filter(member__community=community, tag__label="Deacon", status="verified").exists()

    def test_running_twice_changes_nothing(self, settings):
        settings.DEBUG = True
        call_command("seed_demo_parish")
        counts = (
            Member.objects.count(),
            Need.objects.count(),
            Offer.objects.count(),
            Match.objects.count(),
            MemberTag.objects.count(),
        )
        call_command("seed_demo_parish")
        assert counts == (
            Member.objects.count(),
            Need.objects.count(),
            Offer.objects.count(),
            Match.objects.count(),
            MemberTag.objects.count(),
        )
