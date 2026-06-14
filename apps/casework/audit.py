"""
Thin shim (kept for import stability): the canonical emitter now lives in
apps.audit.services (§10.1). Existing imports — `from . import audit` /
`audit.emit(...)` — keep working unchanged, including in the test suite.
"""
from apps.audit.services import emit, ip_hash  # noqa: F401

__all__ = ["emit", "ip_hash"]
