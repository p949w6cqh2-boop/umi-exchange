"""The env template must not set GIT_SHA.

#249 bakes the commit into the image (`docker build --build-arg GIT_SHA=...`) and /health/ reports
it. Docker Compose's `env_file` beats the image's ENV, so any `GIT_SHA=` line in a server's .env,
even an empty one copied from this template, erases the stamp and /health/ says "unknown". That is
what happened on the 2026-11-23 deploy, from a template line present since May.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_env_template_does_not_set_git_sha():
    text = (ROOT / ".env.example").read_text()

    assert not re.search(r"^\s*GIT_SHA\s*=", text, re.M)
