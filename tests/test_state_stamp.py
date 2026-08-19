"""Tests for scripts/check_state_stamp.py.

These cover the pure parsing and rewriting logic, which is where the bugs would
actually live. The git-touching half is exercised by CI running the real thing on
every pull request.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_state_stamp.py"

spec = importlib.util.spec_from_file_location("check_state_stamp", SCRIPT)
assert spec is not None and spec.loader is not None
stamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp)


HEADER = """# UMI Exchange — Current State

> Authoritative project snapshot. Paste this into a fresh chat.
> Reflects `main` @ `a2a7628` (merged 2026-08-18 UTC).
>
> More header prose that should be left alone.

## Body
Nothing here should be touched.
"""


class TestParseStamp:
    def test_reads_sha_and_parenthetical(self):
        sha, rest = stamp.parse_stamp(HEADER)
        assert sha == "a2a7628"
        assert rest == "merged 2026-08-18 UTC"

    def test_accepts_a_full_length_sha(self):
        text = HEADER.replace("a2a7628", "a2a7628426585e99894f4443a2d14af9a863ca01")
        sha, _ = stamp.parse_stamp(text)
        assert sha == "a2a7628426585e99894f4443a2d14af9a863ca01"

    def test_missing_stamp_is_an_error(self):
        with pytest.raises(stamp.StampError, match="no stamp line found"):
            stamp.parse_stamp("# Title\n\n> No stamp at all here.\n")

    def test_stamp_below_the_header_window_does_not_count(self):
        # A stamp buried 40+ lines down is not the header stamp a reader sees.
        buried = "# Title\n" + ("\n" * 60) + "> Reflects `main` @ `abc1234` (merged 2026-01-01 UTC).\n"
        with pytest.raises(stamp.StampError):
            stamp.parse_stamp(buried)

    def test_uppercase_sha_is_not_matched(self):
        # Git prints lowercase; an uppercase value is a hand-typed mistake.
        with pytest.raises(stamp.StampError):
            stamp.parse_stamp(HEADER.replace("a2a7628", "A2A7628"))


class TestRestamp:
    def test_replaces_only_the_stamp_line(self):
        out = stamp.restamp(HEADER, "deadbee", "2026-09-01")
        assert "> Reflects `main` @ `deadbee` (merged 2026-09-01 UTC)." in out
        assert "a2a7628" not in out
        assert "More header prose that should be left alone." in out
        assert "Nothing here should be touched." in out

    def test_leaves_the_rest_of_the_file_byte_identical(self):
        out = stamp.restamp(HEADER, "deadbee", "2026-09-01")
        old_line = "> Reflects `main` @ `a2a7628` (merged 2026-08-18 UTC)."
        new_line = "> Reflects `main` @ `deadbee` (merged 2026-09-01 UTC)."
        assert out.replace(new_line, old_line) == HEADER

    def test_restamping_twice_is_stable(self):
        once = stamp.restamp(HEADER, "deadbee", "2026-09-01")
        twice = stamp.restamp(once, "deadbee", "2026-09-01")
        assert once == twice

    def test_restamp_without_a_stamp_raises(self):
        with pytest.raises(stamp.StampError):
            stamp.restamp("# Title\n\nno stamp\n", "deadbee", "2026-09-01")


class TestBuildStampLine:
    def test_round_trips_through_the_parser(self):
        line = stamp.build_stamp_line("abc1234", "2026-08-19")
        sha, rest = stamp.parse_stamp(f"# T\n\n{line}\n")
        assert sha == "abc1234"
        assert rest == "merged 2026-08-19 UTC"
