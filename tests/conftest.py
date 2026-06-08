"""Shared pytest fixtures and factories for UMI Exchange tests."""
from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.models import User
from apps.communities.models import Category, Community, Member
from apps.matches.models import Match
from apps.needs.models import Need
from apps.offers.models import Offer


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
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
