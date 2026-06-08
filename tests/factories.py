"""
Shared test fixtures: users, communities, members, categories.
"""
import factory
from django.contrib.auth import get_user_model

from apps.communities.models import Category, Community, Member

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):  # noqa: N805 (factory_boy hook signature)
        """Hash the password and persist it ourselves (factory_boy no longer
        auto-saves after postgeneration)."""
        obj.set_password(extracted or "testpass123")
        if create:
            obj.save()


class CommunityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Community

    name = factory.Sequence(lambda n: f"Community {n}")
    created_by = factory.SubFactory(UserFactory)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    community = factory.SubFactory(CommunityFactory)
    name = factory.Sequence(lambda n: f"Category {n}")
    icon = "🔧"


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Member

    user = factory.SubFactory(UserFactory)
    community = factory.SubFactory(CommunityFactory)
    display_name = factory.LazyAttribute(lambda obj: obj.user.username)
    role = "member"
