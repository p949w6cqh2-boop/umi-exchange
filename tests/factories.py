"""
Shared test fixtures: users, communities, members, categories.
"""
import factory
from django.contrib.auth import get_user_model
from apps.communities.models import Community, Member, Category

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


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
