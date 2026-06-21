"""
Backwards-compatible shim: the real implementation now lives in
apps.common.state so both casework and tags can share it.
"""

from apps.common.state import StateMachineMixin, TransitionConflict  # noqa: F401

__all__ = ["StateMachineMixin", "TransitionConflict"]
