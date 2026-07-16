"""Layer P — the platform floor (pipeline §B): /protocol/ on every instance, the raw spec
beside it, ONE true security.txt, no dead domains anywhere, and no instance facts leaking
through the public floor. These tests are written before the views exist (TDD)."""

import hashlib
import re
from datetime import datetime, timedelta, timezone

import pytest
from django.test import Client
from django.urls import reverse

from config.settings.base import BASE_DIR
from tests.conftest import CommunityFactory, MemberFactory

REPO_ROOT = BASE_DIR

# ---------------------------------------------------------------------------
# B5 — link-rot guard: the two fabricated domains must not appear anywhere.
# ---------------------------------------------------------------------------

DEAD_DOMAINS = re.compile(rb"umi-protocol\.org|umi-exchange\.org")
SCAN_ROOTS = ["templates", "static", "docs", "apps", "config", "docker"]
SCAN_FILES = ["README.md"]
# The pipeline doc records the history of these domains on purpose — the sole exception.
ALLOWLIST = {"docs/community-identity-pipeline.md"}
SKIP_SUFFIXES = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pyc"}


def _scan_targets():
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix not in SKIP_SUFFIXES:
                yield path
    for name in SCAN_FILES:
        path = REPO_ROOT / name
        if path.exists():
            yield path


class TestLinkRot:
    def test_no_fabricated_domain_anywhere(self):
        hits = []
        for path in _scan_targets():
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in ALLOWLIST:
                continue
            for lineno, line in enumerate(path.read_bytes().splitlines(), start=1):
                if DEAD_DOMAINS.search(line):
                    hits.append(f"{rel}:{lineno}")
        assert not hits, (
            "Fabricated domains (umi-protocol.org / umi-exchange.org) found — every link "
            "must be a promise we keep:\n" + "\n".join(hits)
        )


# ---------------------------------------------------------------------------
# B1 — /protocol/: the footer line made true, offline.
# ---------------------------------------------------------------------------


class TestProtocolPage:
    def test_renders_for_anonymous(self, client):
        resp = client.get(reverse("protocol"))
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "The UMI Protocol" in body
        assert "CC-BY-4.0" in body

    def test_intro_mirrors_security_policy(self, client):
        # B4: the security policy is mirrored in the /protocol/ intro.
        body = client.get(reverse("protocol")).content.decode()
        assert "SECURITY.md" in body

    def test_toc_anchors_resolve(self, client):
        body = client.get(reverse("protocol")).content.decode()
        toc_targets = re.findall(r'href="#([^"]+)"', body)
        assert len(toc_targets) >= 14, "TOC should list the spec's sections (§0–§13 at least)"
        ids = set(re.findall(r'id="([^"]+)"', body))
        missing = [t for t in toc_targets if t not in ids]
        assert not missing, f"TOC links point at anchors that don't exist: {missing}"

    def test_fragment_is_current_with_spec(self):
        # Staleness guard: the committed pre-rendered fragment must be rebuilt whenever
        # docs/protocol/spec.md changes (scripts/render_protocol.py).
        spec = (REPO_ROOT / "docs" / "protocol" / "spec.md").read_bytes()
        fragment = (REPO_ROOT / "templates" / "pages" / "_protocol_spec.html").read_text()
        m = re.search(r"spec-sha256:([0-9a-f]{64})", fragment)
        assert m, "fragment must carry its source hash (spec-sha256:<hex>)"
        assert m.group(1) == hashlib.sha256(spec).hexdigest(), (
            "templates/pages/_protocol_spec.html is stale — rerun scripts/render_protocol.py"
        )


# ---------------------------------------------------------------------------
# B2 — the raw spec, streamed as markdown.
# ---------------------------------------------------------------------------


class TestRawSpec:
    def test_served_as_markdown(self, client):
        resp = client.get("/protocol/spec.md")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/markdown; charset=utf-8"
        assert resp.content.startswith(b"# The UMI Protocol")

    def test_missing_file_gets_the_human_500(self, monkeypatch, tmp_path):
        from apps.communities import views

        monkeypatch.setattr(views, "SPEC_PATH", tmp_path / "gone.md")
        client = Client(raise_request_exception=False)
        resp = client.get("/protocol/spec.md")
        assert resp.status_code == 500
        assert b"Something went wrong" in resp.content  # the warm template, never a traceback


# ---------------------------------------------------------------------------
# B4 — security.txt: one source of truth, served by Django, RFC 9116 basics.
# ---------------------------------------------------------------------------


class TestSecurityTxt:
    def _fields(self, client):
        resp = client.get("/.well-known/security.txt")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/plain")
        fields = {}
        for line in resp.content.decode().splitlines():
            if ":" in line and not line.startswith("#"):
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        return fields

    def test_rfc9116_required_fields(self, client):
        fields = self._fields(client)
        assert fields["Contact"].startswith("mailto:")
        assert "@" in fields["Contact"]
        expires = datetime.fromisoformat(fields["Expires"].replace("Z", "+00:00"))
        assert expires > datetime.now(timezone.utc) + timedelta(days=300), (
            "Expires must stay comfortably in the future (served dynamically, ~+1y)"
        )

    def test_policy_and_canonical(self, client):
        fields = self._fields(client)
        assert fields["Policy"].endswith("SECURITY.md")
        assert fields["Canonical"].endswith("/.well-known/security.txt")

    def test_single_source_of_truth(self):
        assert not (REPO_ROOT / "static" / "well-known" / "security.txt").exists(), (
            "the unserved static copy must be gone — the Django view is the only source"
        )
        caddy = (REPO_ROOT / "docker" / "Caddyfile.prod").read_text()
        assert "security.txt" not in caddy, "the Caddy respond block must be gone — the path proxies through to Django"

    def test_security_policy_document_exists(self):
        policy = (REPO_ROOT / "SECURITY.md").read_text()
        assert "mailto:" in policy or "@" in policy, "SECURITY.md must say how to reach us"


# ---------------------------------------------------------------------------
# B3 — every reference repointed at the page we actually serve.
# ---------------------------------------------------------------------------


class TestReferenceRepoints:
    @pytest.mark.django_db
    def test_footer_links_the_local_protocol_page(self, client):
        body = client.get(reverse("landing")).content.decode()
        assert 'href="/protocol/"' in body

    def test_badge_uses_the_url_tag(self):
        badge = (REPO_ROOT / "templates" / "components" / "_protocol_badge.html").read_text()
        assert "{% url 'protocol' %}" in badge

    def test_email_footer_builds_from_site_url(self):
        email = (REPO_ROOT / "templates" / "emails" / "notification.html").read_text()
        assert "{{ site_url }}/protocol/" in email

    def test_readme_points_at_the_repo_spec(self):
        readme = (REPO_ROOT / "README.md").read_text()
        assert readme.count("docs/protocol/spec.md") >= 2


# ---------------------------------------------------------------------------
# B6 — the floor never leaks instance facts.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProtocolLeak:
    def test_no_community_facts_on_the_floor(self, client):
        community = CommunityFactory(name="Sacred Heart Leak Probe")
        MemberFactory(community=community)
        page = client.get(reverse("protocol")).content.decode()
        raw = client.get("/protocol/spec.md").content.decode()
        for surface in (page, raw):
            assert "Sacred Heart Leak Probe" not in surface
            assert community.join_code not in surface
