"""
Shared input checks for user-generated text fields.

Django's template auto-escaping prevents XSS on OUTPUT, and that is what keeps free text safe.
Since the 2026-10 bug hunt sanitize_text_field only trims; the tag and script-pattern helpers
below are no longer applied to free text. The word list never refuses a post: a listed word
sends the saved post to the coordinators' review queue (apps.moderation.services
.flag_listed_words, founder's decision 2026-10-12).
"""

import re

from django.core.exceptions import ValidationError

# Regex to match HTML tags (including self-closing)
HTML_TAG_RE = re.compile(r"<[^>]+>")

# Regex for common script injection patterns
SCRIPT_PATTERNS = re.compile(
    r"(?:javascript|vbscript|data):|on\w+\s*=",
    re.IGNORECASE,
)

# The review list. A post using one of these words still goes up, flagged for a coordinator:
# help requests need them ("prescription drugs", "abuse survivors"). Which words belong here
# is the founder's call; the list itself is unchanged from the old blocklist.
REVIEW_WORDS = {
    "abuse",
    "harass",
    "kill",
    "murder",
    "suicide",
    "terrorism",
    "weapon",
    "drugs",
    "narcotics",
    "prostitution",
    "escort",
    "porn",
    "pornography",
}


def strip_html_tags(value):
    """Remove all HTML tags from a string. Returns plain text."""
    if not value:
        return value
    return HTML_TAG_RE.sub("", value)


def validate_no_html(value):
    """Raise ValidationError if value contains HTML tags."""
    if value and HTML_TAG_RE.search(value):
        raise ValidationError(
            "HTML tags are not allowed. Please use plain text.",
            code="no_html",
        )


def validate_no_script_injection(value):
    """Raise ValidationError if value contains script injection patterns."""
    if value and SCRIPT_PATTERNS.search(value):
        raise ValidationError(
            "This content contains disallowed patterns.",
            code="no_script",
        )


def find_listed_word(*values):
    """The first review-list word used in any of `values` (whole words, any case), or None."""
    for value in values:
        if not value:
            continue
        text = value.lower()
        for word in sorted(REVIEW_WORDS):
            if re.search(r"\b" + re.escape(word) + r"\b", text):
                return word
    return None


def sanitize_text_field(value):
    """Free text, trimmed and otherwise unchanged. It refuses nothing.

    Until 2026-10 this also deleted anything between '<' and '>', refused text matching
    SCRIPT_PATTERNS, and refused any word on the list. The first two broke ordinary posts
    ("I need <5 lbs of rice>", "Phone ran out of data: need a top-up", "Donations = welcome")
    and protected nothing: every surface that shows this text autoescapes it, and none of it
    reaches |safe. The third turned away help requests; a listed word now flags the saved
    post instead (find_listed_word, apps.moderation.services.flag_listed_words).
    """
    if not value:
        return value
    return value.strip()
