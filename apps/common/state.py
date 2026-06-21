"""
Shared state-machine mixin (design §3.5; seed of lakes-common §12.1).

transition_to():
  * locks the row with SELECT FOR UPDATE,
  * 409s the loser of a race (caller's snapshot went stale),
  * 409s illegal transitions per VALID_TRANSITIONS,
  * applies timestamp side-effects atomically.

TransitionConflict subclasses ValidationError (as requested) and carries
status_code=409 so views can map it directly.
"""

from django.core.exceptions import ValidationError
from django.db import transaction


class TransitionConflict(ValidationError):  # noqa: N818 (mirrors Django's ValidationError)
    status_code = 409

    def __init__(self, message, current=None, target=None):
        super().__init__(message)
        self.current = current
        self.target = target


class StateMachineMixin:
    VALID_TRANSITIONS: dict[str, set[str]] = {}
    STATUS_FIELD = "status"
    # {target_status: timestamp_field_to_set}
    TRANSITION_TIMESTAMPS: dict[str, str] = {}

    def transition_to(self, new_status: str, extra_update_fields=()):
        """Atomically move STATUS_FIELD to new_status. Raises
        TransitionConflict (409) on illegal transition or lost race."""
        snapshot = getattr(self, self.STATUS_FIELD)
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            current = getattr(locked, self.STATUS_FIELD)

            if current != snapshot:
                raise TransitionConflict(
                    f"This record changed while you were viewing it (now '{current}'). Reload and try again.",
                    current=current,
                    target=new_status,
                )
            allowed = self.VALID_TRANSITIONS.get(current, set())
            if new_status not in allowed:
                raise TransitionConflict(
                    f"Cannot move from '{current}' to '{new_status}'.",
                    current=current,
                    target=new_status,
                )

            setattr(locked, self.STATUS_FIELD, new_status)
            update_fields = [self.STATUS_FIELD, *extra_update_fields]
            ts_field = self.TRANSITION_TIMESTAMPS.get(new_status)
            if ts_field:
                from django.utils import timezone

                setattr(locked, ts_field, timezone.now())
                update_fields.append(ts_field)
            # copy any extra fields the caller staged on self
            for f in extra_update_fields:
                setattr(locked, f, getattr(self, f))
            locked.save(update_fields=update_fields)

            # reflect the committed state back onto the caller's instance
            for f in update_fields:
                setattr(self, f, getattr(locked, f))
        return self
