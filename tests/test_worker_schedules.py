"""The worker's scheduler: an overdue schedule runs once, not once per missed interval.

Until 2026-10-18 nothing ran the schedules in production (no django-q cluster existed),
so every next_run sat at the 10-13 deploy. django-q's default `catch_up` replays one run
per missed interval when a cluster finally starts: about 140 back-to-back runs of each
hourly expiry sweep, one every scheduler pass. The sweeps act on everything stale in one
run, so the replays add only load, and the casework digest would repeat its email.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from django_q.models import Schedule
from django_q.scheduler import scheduler

pytestmark = pytest.mark.django_db


def test_an_overdue_schedule_runs_once_not_once_per_missed_interval(monkeypatch):
    # The scheduler closes "old" connections first, which inside a test's transaction
    # would close the test's own connection. Nothing else about it is stubbed.
    monkeypatch.setattr("django_q.scheduler.close_old_django_connections", lambda: None)
    sweep = Schedule.objects.create(
        name="overdue-hourly-sweep",
        func="apps.needs.tasks.expire_stale_needs",
        schedule_type=Schedule.HOURLY,
        repeats=-1,
        next_run=timezone.now() - timedelta(days=5),
    )

    scheduler()

    sweep.refresh_from_db()
    assert sweep.task, "the overdue schedule did not run at all"
    assert sweep.next_run > timezone.now(), (
        "after one run the next one is still in the past, so the next pass replays it: "
        "catch_up is on, and a schedule five days overdue would run about 120 more times"
    )
