"""The demo seed must be idempotent, believable, and impossible in production."""

import re

import pytest
from django.contrib.auth import get_user_model
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

    def test_seeded_members_are_human_verified(self, settings):
        """Every seeded member can actually use the board.

        #148 soft-gated the four write doors behind human verification. The seed
        was never updated, so every demo account came out with verified_at=None:
        a twelve-member parish where nobody could join a community, post a need,
        post an offer or propose a match. Found 2026-08-24 when the tutorial rig
        — the only thing that drives this fixture end to end as a real user —
        died at the join screen on "One more step before you can post".
        """
        settings.DEBUG = True
        call_command("seed_demo_parish")
        community = Community.objects.get(slug="st-brigids")
        members = Member.objects.filter(community=community).select_related("user")
        assert members.count() == 12
        unverified = [m.user.username for m in members if not m.user.is_human_verified]
        assert unverified == [], f"seeded members cannot use the board: {unverified}"
        # "coordinator" is the honest provenance: these people are known to the
        # parish in person. "backfill" means predating the gate, which a freshly
        # seeded account does not, and "email" would claim a link nobody clicked.
        assert {m.user.verified_via for m in members} == {"coordinator"}

    def test_verification_survives_a_reseed(self, settings):
        """Idempotence has to cover the users the first run already created.

        get_or_create returns created=False on the second pass, so anything set
        only under `if created` silently stops happening — which is how a field
        added later gets missed for every pre-existing row.
        """
        settings.DEBUG = True
        call_command("seed_demo_parish")
        user_model = get_user_model()
        user_model.objects.filter(username="nuala").update(verified_at=None, verified_via="")
        call_command("seed_demo_parish")
        nuala = user_model.objects.get(username="nuala")
        assert nuala.is_human_verified, "reseeding left an existing account unverified"

    def test_the_demo_ride_needs_only_nualas_yes(self, settings):
        """Contact opens after both people say yes (the founder's call, 2026-10-06). The
        seed's ride is Marta's introduction, so Dan's yes is recorded and Nuala's one tap
        completes it, which is the moment the tutorial films."""
        settings.DEBUG = True
        call_command("seed_demo_parish")
        ride = Match.objects.get(need__title="A ride to the 9:30 Mass on Sunday")
        assert ride.helper_said_yes and not ride.asker_said_yes
        nuala = Member.objects.get(user__username="nuala", community__slug="st-brigids")
        assert ride.record_yes(nuala) is True

    def test_the_demo_connect_opens_onto_a_phone_number(self, settings):
        """The connect is the payoff, so the demo has to show one.

        Every seeded ask and offer used to keep the form's default contact choice, "in the
        app", and no seeded account had a number, so every reveal in the demo read "They
        prefer to arrange things through the community." Found 2026-10-06 by the tutorial v2
        recording, on the clip the whole video builds to.
        """
        settings.DEBUG = True
        call_command("seed_demo_parish")
        ride = Match.objects.get(need__title="A ride to the 9:30 Mass on Sunday")
        ride.transition_to("accepted")
        nuala = Member.objects.get(user__username="nuala", community__slug="st-brigids")
        assert ride.get_contact_info_for(nuala).get("phone") == "555-0131"  # Dan, the driver

        faucet = Match.objects.get(need__title="Someone to look at a leaky kitchen faucet")
        assert faucet.status == "accepted"
        asker = faucet.need.requester
        helper = faucet.offer.offerer
        assert faucet.get_contact_info_for(asker).get("phone") == helper.user.phone
        assert faucet.get_contact_info_for(helper).get("phone") == asker.user.phone

    def test_every_seeded_number_is_a_fictional_one(self, settings):
        """555-0100 to 555-0199 are set aside for fiction; nothing else may appear."""
        settings.DEBUG = True
        call_command("seed_demo_parish")
        phones = list(Member.objects.filter(community__slug="st-brigids").values_list("user__phone", flat=True))
        assert len(phones) == 12
        assert all(re.fullmatch(r"555-01\d\d", p or "") for p in phones), phones
        assert len(set(phones)) == 12

    def test_contact_choices_are_repaired_on_reseed(self, settings):
        """Same rule as verification: set outside `if created`, so a parish seeded before this
        change gets its numbers and choices on the next reseed (the live demo's path,
        docs/demo-reseed-runbook.md §3)."""
        settings.DEBUG = True
        call_command("seed_demo_parish")
        get_user_model().objects.filter(username="dan").update(phone="")
        Offer.objects.filter(title="I can drive Sunday mornings").update(contact_pref="in_app")
        Need.objects.filter(title="A ride to the 9:30 Mass on Sunday").update(contact_pref="in_app")
        call_command("seed_demo_parish")
        assert get_user_model().objects.get(username="dan").phone == "555-0131"
        assert Offer.objects.get(title="I can drive Sunday mornings").contact_pref == "phone"
        assert Need.objects.get(title="A ride to the 9:30 Mass on Sunday").contact_pref == "phone"

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
