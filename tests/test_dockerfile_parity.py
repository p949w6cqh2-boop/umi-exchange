"""The root Dockerfile is a convenience alias for docker/Dockerfile — keep them identical.

docker/Dockerfile is canonical: CI's Docker Build Test and the GHCR push both build it
(.github/workflows/ci.yml, deploy.yml). The root copy exists so a bare `docker build .`
works. They drifted once — the root copy carried an extra libffi-dev — and the droplet's
hand-run deploy built from the root file, so production ran an image CI had never proved.
Prose in a header comment did not hold the line; this test does.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _body(path):
    """The build instructions, minus the leading comment block each file carries."""
    lines = path.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() and not line.startswith("#"))
    return [line for line in lines[start:] if line.strip()]


def test_root_dockerfile_matches_the_canonical_one():
    root = _body(REPO / "Dockerfile")
    canonical = _body(REPO / "docker" / "Dockerfile")
    assert root == canonical, (
        "Dockerfile and docker/Dockerfile have diverged. docker/Dockerfile is the one CI "
        "builds; a droplet built from the root copy would ship an unproven image."
    )
