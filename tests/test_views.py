"""
View smoke tests: verify all URLs return expected status codes.
"""
import pytest
from django.test import Client
from django.urls import reverse

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
        response = client.post(reverse("register"), {
            "username": "newuser",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        })
        assert response.status_code == 302  # Redirect on success

    def test_register_password_mismatch(self):
        client = Client()
        response = client.post(reverse("register"), {
            "username": "newuser",
            "password": "SecurePass123!",
            "password_confirm": "WrongPass123!",
        })
        assert response.status_code == 200  # Re-renders form with errors


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
