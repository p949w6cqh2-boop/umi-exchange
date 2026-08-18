"""
View smoke tests: verify all URLs return expected status codes.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from .conftest import register_payload
from .factories import CategoryFactory, CommunityFactory, MemberFactory, UserFactory


@pytest.mark.django_db
class TestPublicViews:
    """Views accessible without authentication."""

    def test_landing_page(self):
        client = Client()
        response = client.get(reverse("landing"))
        assert response.status_code == 200

    def test_health_check(self):
        client = Client()
        response = client.get("/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"

    def test_technology_page(self):
        client = Client()
        response = client.get(reverse("technology"))
        assert response.status_code == 200

    def test_login_page(self):
        client = Client()
        response = client.get(reverse("login"))
        assert response.status_code == 200

    def test_register_page(self):
        client = Client()
        response = client.get(reverse("register"))
        assert response.status_code == 200


@pytest.mark.django_db
class TestAuthRequired:
    """Views that redirect to login when unauthenticated."""

    def test_join_requires_auth(self):
        client = Client()
        response = client.get(reverse("community-join"))
        assert response.status_code == 302
        assert "/auth/login/" in response.url

    def test_settings_requires_auth(self):
        client = Client()
        response = client.get(reverse("account-settings"))
        assert response.status_code == 302

    def test_notifications_requires_auth(self):
        client = Client()
        response = client.get(reverse("notification-list"))
        assert response.status_code == 302


@pytest.mark.django_db
class TestAuthenticatedViews:
    """Views accessible with authentication."""

    def setup_method(self):
        self.user = UserFactory()
        self.client = Client()
        self.client.force_login(self.user)

    def test_join_community_page(self):
        response = self.client.get(reverse("community-join"))
        assert response.status_code == 200

    def test_create_community_page(self):
        response = self.client.get(reverse("community-create"))
        assert response.status_code == 200

    def test_account_settings_page(self):
        response = self.client.get(reverse("account-settings"))
        assert response.status_code == 200

    def test_notification_list_page(self):
        response = self.client.get(reverse("notification-list"))
        assert response.status_code == 200

    def test_community_feed(self):
        community = CommunityFactory(created_by=self.user)
        MemberFactory(user=self.user, community=community)
        response = self.client.get(reverse("community-feed", kwargs={"slug": community.slug}))
        assert response.status_code == 200

    def test_need_create_page(self):
        community = CommunityFactory(created_by=self.user)
        MemberFactory(user=self.user, community=community)
        CategoryFactory(community=community)
        response = self.client.get(reverse("need-create", kwargs={"slug": community.slug}))
        assert response.status_code == 200

    def test_offer_create_page(self):
        community = CommunityFactory(created_by=self.user)
        MemberFactory(user=self.user, community=community)
        CategoryFactory(community=community)
        response = self.client.get(reverse("offer-create", kwargs={"slug": community.slug}))
        assert response.status_code == 200


@pytest.mark.django_db
class TestRegistration:
    def test_register_new_user(self):
        client = Client()
        response = client.post(
            reverse("register"),
            register_payload(
                username="newuser",
                password="SecurePass123!",
                password_confirm="SecurePass123!",
            ),
        )
        assert response.status_code == 302  # Redirect on success

    def test_register_password_mismatch(self):
        client = Client()
        response = client.post(
            reverse("register"),
            register_payload(
                username="newuser",
                password="SecurePass123!",
                password_confirm="WrongPass123!",
            ),
        )
        assert response.status_code == 200  # Re-renders form with errors

    def test_register_two_users_without_email(self):
        """Regression: blank email must store as NULL, so a second email-less
        signup never collides with the first on the unique constraint.

        Each POST uses its own REMOTE_ADDR: registration is IP-throttled
        (3/m, django_ratelimit) and the test client's default 127.0.0.1
        shares one bucket across the whole suite run.
        """
        client = Client()
        for i, username in enumerate(("nomail-one", "nomail-two")):
            response = client.post(
                reverse("register"),
                register_payload(
                    username=username,
                    password="SecurePass123!",
                    password_confirm="SecurePass123!",
                ),
                REMOTE_ADDR=f"10.99.1.{i + 1}",
            )
            form = response.context["form"] if response.status_code == 200 else None
            assert response.status_code == 302, (
                f"{username} signup failed: {response.status_code} "
                f"{form.errors.as_data() if form else response.content[:200]}"
            )
        users = get_user_model().objects.filter(username__startswith="nomail-")
        assert users.count() == 2
        assert all(user.email is None for user in users)

    def test_register_duplicate_email_rejected(self):
        client = Client()
        payload = register_payload(
            username="first-owner",
            email="taken@example.com",
            password="SecurePass123!",
            password_confirm="SecurePass123!",
        )
        first = client.post(reverse("register"), payload, REMOTE_ADDR="10.99.2.1")
        assert first.status_code == 302
        response = client.post(
            reverse("register"),
            {**payload, "username": "second-claimant"},
            REMOTE_ADDR="10.99.2.2",
        )
        assert response.status_code == 200  # Re-renders form with errors
        assert "This email is already in use." in response.content.decode()
        assert not get_user_model().objects.filter(username="second-claimant").exists()


@pytest.mark.django_db
class TestDashboardAccess:
    def test_dashboard_requires_coordinator(self):
        user = UserFactory()
        community = CommunityFactory(created_by=user)
        MemberFactory(user=user, community=community, role="member")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("community-dashboard", kwargs={"slug": community.slug}))
        assert response.status_code == 403

    def test_dashboard_accessible_to_coordinator(self):
        user = UserFactory()
        community = CommunityFactory(created_by=user)
        MemberFactory(user=user, community=community, role="coordinator")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("community-dashboard", kwargs={"slug": community.slug}))
        assert response.status_code == 200


@pytest.mark.django_db
class TestCommunitySettings:
    def test_settings_requires_admin_or_coordinator(self):
        user = UserFactory()
        community = CommunityFactory(created_by=user)
        MemberFactory(user=user, community=community, role="member")
        client = Client()
        client.force_login(user)
        response = client.get(reverse("community-settings", kwargs={"slug": community.slug}))
        assert response.status_code == 302

    def test_settings_update_details(self):
        user = UserFactory()
        community = CommunityFactory(created_by=user)
        MemberFactory(user=user, community=community, role="admin")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("community-settings", kwargs={"slug": community.slug}),
            {"name": "New Community Name", "description": "New description", "visibility": "public"},
        )
        assert response.status_code == 302
        community.refresh_from_db()
        assert community.name == "New Community Name"
        assert community.description == "New description"
        assert community.visibility == "public"

    def test_settings_regenerate_join_code(self):
        user = UserFactory()
        community = CommunityFactory(created_by=user)
        old_code = community.join_code
        MemberFactory(user=user, community=community, role="admin")
        client = Client()
        client.force_login(user)
        response = client.post(
            reverse("community-settings", kwargs={"slug": community.slug}),
            {"action": "regenerate_join_code"},
        )
        assert response.status_code == 302
        community.refresh_from_db()
        assert community.join_code != old_code
