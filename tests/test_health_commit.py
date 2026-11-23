"""/health/ names the commit it is running.

Until this, /health/ said only {"status","db","cache"}: nothing outside the host could tell which
commit was live, so verifying a deploy meant an SSH read into the container (STATE.md), and the
2026-07-27 deploy served the OLD tree while every probe read green. The image now carries the
commit it was built from (ARG GIT_SHA → ENV GIT_SHA), and /health/ reports it.

It reports a real commit or the word "unknown", never anything else: an image built without the
build argument, or one handed a value that is not a commit hash, says "unknown" rather than
inventing an answer. And the plumbing is pinned, because it was already broken once without
anyone noticing: CI's image push passed GIT_SHA while neither Dockerfile declared it, and Docker
drops an undeclared build argument without a word.
"""

from pathlib import Path

import pytest
from django.test import Client

REPO = Path(__file__).resolve().parent.parent
SHA = "4b086ed74e0d37e2764c6a21e8a2fe2cb516499d"

pytestmark = pytest.mark.django_db


def _health():
    return Client().get("/health/", HTTP_X_FORWARDED_PROTO="https", secure=True)


def test_health_reports_the_commit_the_image_was_built_from(settings):
    settings.GIT_SHA = SHA
    resp = _health()
    assert resp.status_code == 200
    assert resp.json()["commit"] == SHA


def test_an_image_built_without_the_argument_says_unknown(settings):
    settings.GIT_SHA = ""
    assert _health().json()["commit"] == "unknown"


@pytest.mark.parametrize("junk", ["main", "v1.2", "<script>", SHA + "ff", "abc", "unknown;rm -rf"])
def test_a_value_that_is_not_a_commit_hash_says_unknown(settings, junk):
    settings.GIT_SHA = junk
    assert _health().json()["commit"] == "unknown"


def test_a_short_hash_is_reported_as_given(settings):
    settings.GIT_SHA = SHA[:12].upper()
    assert _health().json()["commit"] == SHA[:12]


def test_the_commit_is_reported_even_when_the_site_is_degraded(settings, monkeypatch):
    from django.core import cache as cache_mod

    settings.GIT_SHA = SHA

    def broken(*a, **k):
        raise ConnectionError("cache down")

    monkeypatch.setattr(cache_mod.cache, "set", broken)
    resp = _health()
    assert resp.status_code == 503
    assert resp.json()["commit"] == SHA  # a broken deploy is exactly when you need to know which one


def test_the_token_gate_still_hides_everything(settings):
    settings.GIT_SHA = SHA
    settings.HEALTH_CHECK_TOKEN = "s3cret"
    resp = _health()
    assert resp.status_code == 403
    assert SHA not in resp.content.decode()


@pytest.mark.parametrize("dockerfile", ["Dockerfile", "docker/Dockerfile"])
def test_both_dockerfiles_declare_the_build_argument(dockerfile):
    text = (REPO / dockerfile).read_text()
    assert "ARG GIT_SHA" in text
    assert "ENV GIT_SHA=${GIT_SHA}" in text


def test_ci_image_push_passes_the_commit():
    assert "GIT_SHA=${{ github.sha }}" in (REPO / ".github/workflows/deploy.yml").read_text()


def test_every_hand_build_of_the_production_image_passes_the_commit():
    builds = [
        (path.relative_to(REPO), line)
        for path in sorted((REPO / "docs").rglob("*.md"))
        for line in path.read_text().splitlines()
        if "docker build" in line and "umi-exchange:local" in line and not line.lstrip().startswith("#")
    ]
    assert any(str(p) == "docs/deploy-runbook.md" for p, _ in builds), "deploy runbook lost its build line"
    for path, line in builds:
        assert '--build-arg GIT_SHA="$(git rev-parse HEAD)"' in line, f"{path}: {line}"
