"""The public contact page.

The page exists because the videos now ask people to reach out, and the site had
no contact destination at all. It is deliberately a *signpost*, not a form: a
form would put real people's names, addresses and messages in this database, and
the ethics gate in docs/ethics-and-safety.md is not passed (3 of 6). So the page
stores nothing and accepts nothing, and these tests hold it to that.
"""

import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
class TestContactPage:
    def test_reachable_without_login(self):
        """A mission page: logged-out visitors are the whole audience."""
        response = Client().get(reverse("contact"))
        assert response.status_code == 200

    def test_uses_the_mission_page_template(self):
        response = Client().get(reverse("contact"))
        assert "pages/contact.html" in [t.name for t in response.templates]

    def test_names_the_routes_a_visitor_can_actually_use(self):
        body = Client().get(reverse("contact")).content.decode()
        assert "jasiahbuilds.substack.com" in body
        assert "Jasiahbuilds" in body or "jasiahbuilds" in body

    def test_security_address_is_labelled_security_only(self):
        """SECURITY.md promises that mailbox for vulnerability reports.

        General inbound must not be invited into it, or a real report gets buried
        under it. The page may name it, but only as the security route.
        """
        body = Client().get(reverse("contact")).content.decode()
        if "usermegadatainfrastructure@proton.me" in body:
            assert "SECURITY.md" in body
            assert "security" in body.lower()

    def test_accepts_no_submissions(self):
        """The whole point: nothing is collected, so there is nothing to POST to."""
        response = Client().post(reverse("contact"), {"message": "hello"})
        assert response.status_code == 405

    def test_renders_no_form(self):
        body = Client().get(reverse("contact")).content.decode()
        assert "<form" not in body.lower()

    def test_says_plainly_that_nothing_is_collected(self):
        body = Client().get(reverse("contact")).content.decode().lower()
        assert "collect" in body or "store" in body
