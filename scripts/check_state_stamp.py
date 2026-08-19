#!/usr/bin/env python3
"""Keep STATE.md's header stamp honest.

STATE.md opens with a line of the form::

    > Reflects `main` @ `abc1234` (merged 2026-08-18 UTC).

That stamp exists so a reader pasting the file into a fresh chat knows which
``main`` it describes. It has gone stale three times (see the header's own note),
most recently by 13 commits and 18 days.

**What this check does NOT do, said plainly:** it cannot keep the stamp current
after a merge. Every PR stamps the sha it branched from, and that sha is stale the
moment anything else merges. Only rewriting ``main`` at merge time could fix that,
and branch protection deliberately forbids it.

**What it does instead** is enforce the part that IS knowable when someone edits
the file: if a change touches STATE.md, the stamp must name a real commit that is
an ancestor of this branch's merge-base with ``main``, and must not trail that
merge-base by more than ``MAX_DRIFT`` commits. That turns "18 days and 13 commits
behind" into a failing check, while leaving normal post-merge drift alone.

The check is skipped entirely when STATE.md is untouched, so it can never block an
unrelated pull request.

Usage::

    python scripts/check_state_stamp.py                 # check against origin/main
    python scripts/check_state_stamp.py --base upstream/main
    python scripts/check_state_stamp.py --write         # restamp to the merge-base
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / "STATE.md"

# Matches: > Reflects `main` @ `abc1234` (merged 2026-08-18 UTC).
# The trailing period is part of the match on purpose. Without it, re.sub replaces
# up to the closing paren and leaves the old "." behind, producing "UTC)..".
STAMP_RE = re.compile(
    r"^>\s*Reflects\s+`main`\s+@\s+`(?P<sha>[0-9a-f]{7,40})`\s*\((?P<rest>[^)]*)\)\.?",
    re.MULTILINE,
)

# How far the stamp may trail the merge-base before this fails. Small enough that
# an 18-day drift is caught, large enough that a branch left open over a busy
# couple of days is not punished for someone else's merges.
MAX_DRIFT = 10

# Only the top of the file is scanned; the stamp belongs in the header block.
HEADER_LINES = 40


class StampError(Exception):
    """A problem with the stamp that the author has to fix."""


def git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command and return stripped stdout, raising on failure."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise StampError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_stamp(text: str) -> tuple[str, str]:
    """Return (sha, parenthetical) from the header stamp.

    Raises StampError when the header has no stamp line at all, which is itself
    a failure: the file is supposed to say which main it reflects.
    """
    header = "\n".join(text.splitlines()[:HEADER_LINES])
    match = STAMP_RE.search(header)
    if match is None:
        raise StampError(
            f"no stamp line found in the first {HEADER_LINES} lines of STATE.md.\n"
            "Expected a line like:  > Reflects `main` @ `abc1234` (merged 2026-08-18 UTC)."
        )
    return match.group("sha"), match.group("rest")


def touches_state_file(merge_base: str) -> bool:
    """True when STATE.md differs between the merge-base and the WORKING TREE.

    Deliberately two-dot against the working tree rather than ``merge_base...HEAD``.
    In CI the tree equals HEAD so the two agree, but locally a `make lint` run must
    also see an edit that has not been committed yet. The three-dot form silently
    passed an uncommitted 13-commit-stale stamp during this script's own testing.
    """
    changed = git("diff", "--name-only", merge_base)
    return "STATE.md" in changed.split()


def commit_exists(sha: str) -> bool:
    try:
        git("cat-file", "-e", f"{sha}^{{commit}}")
    except StampError:
        return False
    return True


def is_ancestor(maybe_ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", maybe_ancestor, descendant],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def build_stamp_line(sha: str, date: str) -> str:
    return f"> Reflects `main` @ `{sha}` (merged {date} UTC)."


def restamp(text: str, sha: str, date: str) -> str:
    """Replace the existing stamp line with a fresh one."""
    parse_stamp(text)  # raises if there is nothing to replace
    return STAMP_RE.sub(build_stamp_line(sha, date), text, count=1)


def check(base: str) -> list[str]:
    """Return a list of problems. Empty list means the stamp is acceptable."""
    if not STATE_FILE.exists():
        return [f"{STATE_FILE} does not exist"]

    try:
        merge_base = git("merge-base", base, "HEAD")
    except StampError as exc:
        # A shallow clone cannot answer this. Say so rather than passing quietly:
        # a check that silently degrades to a no-op is worse than no check.
        return [
            f"could not compute the merge-base against {base} ({exc}). "
            "In CI this usually means the checkout was shallow; set fetch-depth: 0."
        ]

    if not touches_state_file(merge_base):
        return []

    text = STATE_FILE.read_text(encoding="utf-8")
    try:
        sha, _rest = parse_stamp(text)
    except StampError as exc:
        return [str(exc)]

    if not commit_exists(sha):
        return [f"the stamp names `{sha}`, which is not a commit in this repository."]

    if not is_ancestor(sha, merge_base):
        return [
            f"the stamp names `{sha}`, which is not an ancestor of the merge-base "
            f"`{merge_base[:7]}`. A stamp must name a commit this branch actually descends from."
        ]

    behind = int(git("rev-list", "--count", f"{sha}..{merge_base}"))
    if behind > MAX_DRIFT:
        return [
            f"the stamp names `{sha}`, which is {behind} commits behind the merge-base "
            f"`{merge_base[:7]}` (limit {MAX_DRIFT}).\n"
            "This change edits STATE.md, so the stamp should name where this branch started.\n"
            "Fix it with:  make state-stamp"
        ]

    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base",
        default="origin/main",
        help="ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the stamp to name the merge-base, then exit",
    )
    args = parser.parse_args(argv)

    if args.write:
        merge_base = git("merge-base", args.base, "HEAD")
        short = git("rev-parse", "--short", merge_base)
        date = git("show", "-s", "--format=%cs", merge_base)
        text = STATE_FILE.read_text(encoding="utf-8")
        STATE_FILE.write_text(restamp(text, short, date), encoding="utf-8")
        print(f"STATE.md stamped: {build_stamp_line(short, date)}")
        return 0

    problems = check(args.base)
    if problems:
        print("STATE.md header stamp check FAILED:\n", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nWhy this exists: the stamp tells a reader which main the file describes, "
            "and it has silently gone stale three times.",
            file=sys.stderr,
        )
        return 1

    print("STATE.md header stamp: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
