"""The questions every deletion path asks before it destroys anything (docs/specs/legal-hold.md).

Each returns a filter the caller EXCLUDES, so a sweep stays one query and a held record is simply
never selected. With no active hold, all of these are empty and nothing changes.
"""

from django.db.models import Q

from .models import LegalHold


def active():
    return LegalHold.objects.filter(released_at__isnull=True)


def everything_held():
    """A hold of scope ALL is in force: every automated deletion must stop."""
    return active().filter(scope=LegalHold.SCOPE_ALL).exists()


def held_cases_q():
    """Q matching CaseFile rows covered by an active hold (by case, person or community)."""
    holds = active()
    return (
        Q(pk__in=holds.filter(scope=LegalHold.SCOPE_CASE).values("case"))
        | Q(subject_person__in=holds.filter(scope=LegalHold.SCOPE_PERSON).values("person"))
        | Q(community__in=holds.filter(scope=LegalHold.SCOPE_COMMUNITY).values("community"))
    )


def held_needs_q():
    """Q matching Need rows covered by an active hold (by need or community)."""
    holds = active()
    return Q(pk__in=holds.filter(scope=LegalHold.SCOPE_NEED).values("need")) | Q(
        community__in=holds.filter(scope=LegalHold.SCOPE_COMMUNITY).values("community")
    )


def need_is_held(need):
    from apps.needs.models import Need

    return everything_held() or Need.objects.filter(held_needs_q(), pk=need.pk).exists()
