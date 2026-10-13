"""Parsing ids that arrive in a request.

A malformed string makes a UUIDField lookup raise ValidationError, which get_object_or_404 does
not catch (only DoesNotExist), so a junk id escaped as a 500. A junk id is a miss, not a server
error (moderation first, then the 2026-10 bug hunt found the same hole across the app).
"""

import uuid

from django.http import Http404


def parse_uuid(raw):
    """The UUID in `raw`, or None when it isn't one."""
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return None


def uuid_or_404(raw):
    """The UUID in `raw`, or Http404 when it isn't one."""
    parsed = parse_uuid(raw)
    if parsed is None:
        raise Http404("malformed id")
    return parsed
