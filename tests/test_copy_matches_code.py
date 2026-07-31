"""
Public copy may not promise more privacy than the code delivers.

This exists because the failure has now happened twice, the same way both times.

1. `/about/` said the software "can actually forget them" while
   `docs/ethics-and-safety.md` already named that exact unscoped claim a
   self-deception: display names, account contact details and free-text need
   titles are stored in plain columns. Fixed in #133 — on that one page. The
   identical claim stayed live on the landing page, because nobody swept.

2. Five surfaces told a neighbour their contact details go to the other party
   ALONE. `Match.get_contact_info_for()` reveals them to any coordinator of the
   community, party or not, for oversight. `STATE.md` recorded this correctly
   the whole time; only the copy was wrong.

The pattern is the point: a doc that records the truth does not stop copy from
outrunning it, and a fix applied to one page does not reach its siblings. A test
does both. It fails on the sentence, wherever the sentence is.

These are static assertions over the templates on purpose. They need no database
and no client, so they cannot be skipped for being slow, and they read as prose a
reviewer can check against the code themselves.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"


def _visible_text(html: str) -> str:
    """What a neighbour actually reads. Comments and template logic are not promises."""
    for pattern in (
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
        r"\{#.*?#\}",
        r"<!--.*?-->",
    ):
        html = re.sub(pattern, " ", html, flags=re.S)
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"\{%.*?%\}", " ", html, flags=re.S)
    html = re.sub(r"\{\{.*?\}\}", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html, flags=re.S))


def _all_visible_copy():
    return {p: _visible_text(p.read_text(encoding="utf-8", errors="replace")) for p in TEMPLATES.rglob("*.html")}


def _offenders(*phrases):
    hits = []
    for path, text in _all_visible_copy().items():
        low = text.lower()
        for phrase in phrases:
            if phrase.lower() in low:
                hits.append(f"{path.relative_to(REPO)}: {phrase!r}")
    return hits


def test_no_page_claims_contact_goes_only_to_the_other_party():
    """A coordinator sees both parties' contact details. Saying otherwise is a
    privacy promise the code does not keep, and people act on those."""
    hits = _offenders(
        "two of you alone",
        "only between the two of you",
        "only with the neighbour you accepted",
        "revealed only to the person you agreed",
    )

    assert not hits, (
        "Public copy says contact is shared with the other party alone, but "
        "Match.get_contact_info_for() reveals it to any coordinator of the "
        "community for oversight. Name the coordinator, or change the code:\n  " + "\n  ".join(hits)
    )


def test_the_coordinator_is_named_wherever_contact_sharing_is_explained():
    """Not enough to delete the false claim. The surfaces that explain contact
    sharing have to say who actually sees it."""
    surfaces = [
        TEMPLATES / "pages" / "privacy.html",
        TEMPLATES / "pages" / "terms.html",
        TEMPLATES / "matches" / "detail.html",
    ]
    missing = [
        str(p.relative_to(REPO))
        for p in surfaces
        if "coordinator" not in _visible_text(p.read_text(encoding="utf-8")).lower()
    ]

    assert not missing, (
        f"These surfaces explain contact sharing without naming the coordinator who can see it: {missing}"
    )


def test_the_code_still_reveals_contact_to_coordinators():
    """The coupling that makes the tests above honest rather than superstitious.

    If someone later restricts contact revelation to participants only, this fails
    and tells them the copy may go back to the stronger promise. A copy assertion
    that never re-checks its premise is how the first false claim survived."""
    source = (REPO / "apps" / "matches" / "models.py").read_text(encoding="utf-8")

    assert "is_coordinator = requesting_member.is_coordinator" in source, (
        "Match.get_contact_info_for() no longer grants coordinators contact "
        "access. If that is deliberate, the public copy in privacy.html, "
        "terms.html, matches/detail.html, hub/_first_steps.html and "
        "pages/landing.html can go back to promising the two parties alone."
    )


def test_no_page_claims_the_software_can_simply_forget_someone():
    """#133 scoped this on /about/ and it stayed live on the landing page.
    Crypto-shred covers case notes, the identity behind a request and on-behalf-of
    names. It does not cover display names, emails, or the title of an ask."""
    hits = _offenders(
        "software itself can forget",
        "can actually forget them",
        "encrypted so thoroughly",
    )

    assert not hits, (
        "Copy claims unscoped erasure. docs/ethics-and-safety.md names that exact "
        "claim a self-deception: display names, account contact details and "
        "free-text need titles are plain columns.\n  " + "\n  ".join(hits)
    )
