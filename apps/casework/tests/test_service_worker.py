"""M-7 regression: the offline visit-capture service worker is registered by
static/casework/visit_offline.js but its template never existed, so the route
500'd and the SW never installed. It must serve 200 with a JavaScript
content type (a SW served as text/html will not register in browsers)."""

import pytest

pytestmark = pytest.mark.django_db


def test_service_worker_served_as_javascript(world, auth, u):
    client = auth(world.coord_u)
    client.raise_request_exception = False  # want the 500 as a response, not a raise

    resp = client.get(u("sw"))

    assert resp.status_code == 200
    assert "javascript" in resp["Content-Type"].lower()


def test_service_worker_caches_the_visit_shell(world, auth, u):
    """The SW body must reference the visit shell it precaches, or offline cold
    loads still fail even though registration succeeds."""
    client = auth(world.coord_u)
    body = client.get(u("sw")).content.decode()

    assert "install" in body  # has an install handler
    assert "/cases/visit/" in body  # precaches the visit route shell
