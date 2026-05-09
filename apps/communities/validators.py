"""
Shared input sanitization for all user-generated text fields.

Django's template auto-escaping prevents XSS on OUTPUT. This module provides
defense-in-depth by stripping HTML tags on INPUT, so we never store raw HTML
in the database. This is a belt-and-suspenders approach.
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


def sanitize_text_field(value):
    """Strip HTML tags and check for injection patterns. Returns cleaned value."""
    if not value:
        return value
    cleaned = strip_html_tags(value)
    validate_no_script_injection(cleaned)
    return cleaned.strip()
