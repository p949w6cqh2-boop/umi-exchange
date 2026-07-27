"""Move the on-behalf breadcrumb onto a real field.

Casework intake used to record a no-account subject's consent by putting the
COORDINATOR in as `participant` and leaving a note in `custom`:

    custom = {"on_behalf_person_id": "<uuid>"}

That note was written at apps/casework/views.py and read nowhere in the repo, and
the participant it named was the wrong human — the thing docs/protocol/spec.md
§4.1 forbids. Now that `subject_person` exists, those rows can say what they
always meant: this consent is ABOUT that person, and the coordinator only wrote it
down.

Reversible: the backward pass puts the breadcrumb back and restores the case's
opener as participant, so this can be rolled back without losing information.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    Consent = apps.get_model("consent", "Consent")
    Person = apps.get_model("people", "Person")

    for consent in Consent.objects.exclude(custom={}).iterator():
        person_id = (consent.custom or {}).get("on_behalf_person_id")
        if not person_id or consent.subject_person_id:
            continue
        if not Person.objects.filter(pk=person_id).exists():
            continue  # person was hard-deleted; leave the row alone rather than guess

        consent.subject_person_id = person_id
        # Who wrote it down: the coordinator who opened the case this consent gates.
        case = consent.case_files.order_by("created_at").first()
        consent.recorded_by_id = case.opened_by_id if case else None
        consent.participant = None
        remaining = dict(consent.custom or {})
        remaining.pop("on_behalf_person_id", None)
        consent.custom = remaining
        consent.save(update_fields=["subject_person", "recorded_by", "participant", "custom"])


def backwards(apps, schema_editor):
    Consent = apps.get_model("consent", "Consent")

    for consent in Consent.objects.filter(subject_person__isnull=False).iterator():
        case = consent.case_files.order_by("created_at").first()
        opener = case.opened_by if case else None
        if opener is None or opener.user_id is None:
            continue  # cannot reconstruct a participant; leave it for a human
        custom = dict(consent.custom or {})
        custom["on_behalf_person_id"] = str(consent.subject_person_id)
        consent.custom = custom
        consent.participant_id = opener.user_id
        consent.subject_person = None
        consent.recorded_by = None
        consent.save(update_fields=["subject_person", "recorded_by", "participant", "custom"])


class Migration(migrations.Migration):
    dependencies = [
        ("consent", "0003_onbehalf_subject_person"),
        ("casework", "0001_initial"),
        ("people", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
