"""The board shows times in Eastern time (the founder's call, 2026-10-22).

Until then no TIME_ZONE was set, so Django's default, America/Chicago, applied: pages showed
Central time and the worker's log printed Chicago time, while the community settings already
defaulted to America/New_York (apps/communities/models.py DEFAULT_SETTINGS).
"""

from datetime import UTC, datetime

from django.conf import settings
from django.template import Context, Template

from apps.communities.models import DEFAULT_SETTINGS


def test_the_site_runs_on_eastern_time():
    assert settings.TIME_ZONE == "America/New_York"
    assert settings.USE_TZ is True


def test_the_site_matches_the_community_default():
    assert settings.TIME_ZONE == DEFAULT_SETTINGS["timezone"]


def test_a_page_shows_a_utc_moment_in_eastern_time():
    # 16:00 UTC on 1 July is noon in New York (EDT, UTC-4) and 11:00 in Chicago.
    when = datetime(2026, 7, 1, 16, 0, tzinfo=UTC)
    rendered = Template('{{ when|date:"G:i" }}').render(Context({"when": when}))
    assert rendered == "12:00"


def test_a_winter_moment_is_eastern_standard_time():
    """The other half of the year, which the July case alone cannot see.

    Measured against real settings rather than assumed, rendering noon-in-New-York
    for each date (July 16:00 UTC, January 17:00 UTC):

        America/New_York   july 12:00   january 12:00   <- the only one that passes both
        America/Chicago    july 11:00   january 11:00   <- the old default, either case catches it
        EST                july 11:00   january 12:00   <- July catches it, January does not
        Etc/GMT+4          july 12:00   january 13:00   <- JANUARY catches it, July does not

    So the pair pins both offsets: July rules out a fixed UTC-5, January rules out a
    fixed UTC-4, and only a DST-aware zone satisfies both. A timezone that is right
    for half the year is the failure this guards.
    """
    when = datetime(2026, 1, 1, 17, 0, tzinfo=UTC)
    rendered = Template('{{ when|date:"G:i" }}').render(Context({"when": when}))
    assert rendered == "12:00"
