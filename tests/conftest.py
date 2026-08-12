"""Shared pytest fixtures and factories for UMI Exchange tests."""

from datetime import timedelta

import factory
import pytest
from django.conf import settings
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.models import User
from apps.communities.models import Category, Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer
from apps.pages.models import CommunityPage


@pytest.fixture(scope="session", autouse=True)
def _ensure_static_root():
    """Create STATIC_ROOT before tests run so WhiteNoise does not warn about a
    missing directory (collectstatic creates it in production)."""
    settings.STATIC_ROOT.mkdir(parents=True, exist_ok=True)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    # Factory users predate the human-verification gate by construction (the
    # backfill migration's promise) — tests exercising the UNVERIFIED path set
    # verified_at=None explicitly.
    verified_at = factory.LazyFunction(timezone.now)
    verified_via = "backfill"

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):  # noqa: N805 (factory_boy hook signature)
        """Hash the password and persist it ourselves (factory_boy no longer
        auto-saves after postgeneration)."""
        obj.set_password(extracted or "testpass123")
        if create:
            obj.save()


class CommunityFactory(DjangoModelFactory):
    class Meta:
        model = Community

    name = factory.Sequence(lambda n: f"Community {n}")
    slug = factory.Sequence(lambda n: f"community-{n}")
    created_by = factory.SubFactory(UserFactory)


class MemberFactory(DjangoModelFactory):
    class Meta:
        model = Member

    user = factory.SubFactory(UserFactory)
    community = factory.SubFactory(CommunityFactory)
    display_name = factory.Faker("first_name")
    role = "member"


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    community = factory.SubFactory(CommunityFactory)
    name = "Home Repair"
    icon = "\U0001f527"


class NeedFactory(DjangoModelFactory):
    class Meta:
        model = Need

    community = factory.SubFactory(CommunityFactory)
    requester = factory.SubFactory(MemberFactory)
    category = factory.SubFactory(CategoryFactory)
    title = factory.Faker("sentence", nb_words=5)
    urgency = "medium"
    status = "open"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))


class OfferFactory(DjangoModelFactory):
    class Meta:
        model = Offer

    community = factory.SubFactory(CommunityFactory)
    offerer = factory.SubFactory(MemberFactory)
    category = factory.SubFactory(CategoryFactory)
    title = factory.Faker("sentence", nb_words=5)
    status = "active"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=90))


class MatchFactory(DjangoModelFactory):
    class Meta:
        model = Match

    need = factory.SubFactory(NeedFactory)
    offer = factory.SubFactory(OfferFactory)
    proposed_by = factory.SubFactory(MemberFactory)
    status = "proposed"


@pytest.fixture
def user(db):
    return UserFactory()


class PageFactory(DjangoModelFactory):
    class Meta:
        model = CommunityPage

    community = factory.SubFactory(CommunityFactory)
    title = factory.Sequence(lambda n: f"Page {n}")
    slug = factory.Sequence(lambda n: f"page-{n}")
    content_md = "Words for neighbours."
    created_by = factory.SubFactory(MemberFactory, community=factory.SelfAttribute("..community"))
