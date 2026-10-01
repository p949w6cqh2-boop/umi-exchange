"""Scoped legal hold (docs/specs/legal-hold.md; ethics gate box 4).

Routine retention runs on a timer; a legal hold overrides it. Before this existed the only way to
preserve evidence was to stop the whole scheduler, which also suspended erasure for everyone NOT
involved. A hold names a scope, and every automated deletion path skips only what it covers.

A hold is never deleted: releasing it stamps released_at (archive, not delete). The `reference` is
the steward's matter reference ("subpoena served 2026-10-03"). It lives on this redactable row and
is NEVER copied into the append-only audit log.
"""

import uuid

from django.conf import settings
from django.db import models


class LegalHold(models.Model):
    SCOPE_ALL = "all"
    SCOPE_COMMUNITY = "community"
    SCOPE_PERSON = "person"
    SCOPE_CASE = "case"
    SCOPE_NEED = "need"
    SCOPE_CHOICES = [
        (SCOPE_ALL, "Everything (every automated deletion stops)"),
        (SCOPE_COMMUNITY, "One community: its cases and needs"),
        (SCOPE_PERSON, "One person: every case about them"),
        (SCOPE_CASE, "One case"),
        (SCOPE_NEED, "One need"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=12, choices=SCOPE_CHOICES)
    community = models.ForeignKey("communities.Community", null=True, blank=True, on_delete=models.PROTECT)
    person = models.ForeignKey("people.Person", null=True, blank=True, on_delete=models.PROTECT)
    case = models.ForeignKey("casework.CaseFile", null=True, blank=True, on_delete=models.PROTECT)
    need = models.ForeignKey("needs.Need", null=True, blank=True, on_delete=models.PROTECT)
    reference = models.CharField(max_length=200)
    placed_at = models.DateTimeField(auto_now_add=True)
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "holds_legal_hold"
        ordering = ["-placed_at"]

    @property
    def is_active(self):
        return self.released_at is None

    def __str__(self):
        state = "active" if self.is_active else "released"
        return f"Legal hold ({self.scope}, {state}) {self.reference[:40]}"
