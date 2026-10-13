"""Erasing one person (privacy page: "If you ask us to erase you"; 2026-10 bug hunt, L16).

Before this, nothing erased a Person. The seven-year sweep shredded what a case said and left whom
it was about, and the runbook's advice (delete the record's `*_enc_dek` by hand) left ciphertext
with no key, which fails loud on every read, and kept the name's blind index, so the erased name
stayed equality-testable.

Erasure here nulls ciphertext and key together through the model setters (which clear the blind
index too), shreds every case about the person with the same helper the sweep uses, and writes
audit rows that hold ids, counts and a fixed reason, never the person's details.

It refuses, changing nothing, when a legal hold covers the person or any case about them, or
while one of their cases is still open: closing a case is a coordinator's decision, made in the
app, not a side effect of an erasure.
"""

from django.db import transaction
from django.db.models import Q

from apps.audit.services import emit

# A fixed vocabulary: the audit log is append-only, so free text never goes in it.
REASONS = ("erasure_request", "steward_decision")


class ErasureRefusedError(Exception):
    """Nothing was erased; the message says why."""


def identity_present_q():
    """Person rows that still hold something to erase."""
    return (
        Q(display_name_enc__isnull=False)
        | Q(contact_enc__isnull=False)
        | Q(dob_enc__isnull=False)
        | Q(name_bidx__isnull=False)
    )


def shred_identity(person):
    """Null the name, contact and date of birth. The setters null ciphertext and key together (a
    read then returns None) and the name setter clears the blind index."""
    person.display_name = None
    person.contact = None
    person.dob = None
    person.save(
        update_fields=[
            "display_name_enc",
            "display_name_enc_dek",
            "name_bidx",
            "contact_enc",
            "contact_enc_dek",
            "dob_enc",
            "dob_enc_dek",
        ]
    )


def _same_person(person):
    """The person and every record merged into them, which are the same human by definition."""
    from .models import Person

    records, frontier = [person], [person.pk]
    while frontier:
        found = list(
            Person.objects.select_for_update().filter(merged_into__in=frontier).exclude(pk__in=[r.pk for r in records])
        )
        records.extend(found)
        frontier = [p.pk for p in found]
    return records


def shred_person(person, *, reason="erasure_request"):
    """Erase a person and every case about them. Returns how many cases were shredded."""
    from apps.casework.models import CaseFile
    from apps.casework.tasks import shred_case_content
    from apps.holds.services import person_is_held

    from .models import Person

    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")
    with transaction.atomic():
        person = Person.objects.select_for_update().get(pk=person.pk)
        records = _same_person(person)
        if any(person_is_held(r) for r in records):
            raise ErasureRefusedError(f"Person {person.short_code} is under a legal hold; nothing was erased.")
        cases = list(
            CaseFile.objects.select_for_update()
            .filter(subject_person__in=[r.pk for r in records])
            .order_by("created_at")
        )
        still_open = [c.short_code for c in cases if c.status != CaseFile.STATUS_CLOSED]
        if still_open:
            raise ErasureRefusedError(
                f"Person {person.short_code} still has open cases ({', '.join(still_open)}). "
                "Close them in the app first; nothing was erased."
            )
        for case in cases:
            emit("case.erasure_shredded", case, details={"reason": reason, **shred_case_content(case)})
        for record in records:
            shred_identity(record)
            emit("person.shredded", record, details={"reason": reason, "cases": len(cases)})
    return len(cases)
