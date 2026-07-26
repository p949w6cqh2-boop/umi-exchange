"""Sentry options, kept out of production.py so the privacy posture is importable
and testable rather than a comment nobody can assert on.

`send_default_pii=False` is NOT enough on its own, and reading it as "never send
PII" is how this bug happened. It gates cookies and user identity only. Two other
options decide whether casework plaintext leaves the box, and both of the SDK's
defaults are the leaky ones:

  * ``max_request_body_size`` defaults to ``"medium"`` — a POSTed case note body,
    handoff summary or follow-up detail is sent verbatim.
  * ``include_local_variables`` defaults to ``True`` — frame locals at the moment
    of a 500 are exactly where a just-decrypted narrative sits.

The casework field names (body, summary, detail) are on no scrubber denylist, so
nothing downstream would catch it. Both keys are therefore stated explicitly here,
never inherited from the SDK.

Sentry is OFF in this deployment by decision (docs/monitoring-decision.md,
2026-07-18) — this module is what makes it safe for the next operator who turns it
on, since this is a reference implementation others adopt.
"""


def sentry_options(dsn, *, environment, release, traces_sample_rate=0.1):
    """The full option set for sentry_sdk.init, minus integrations."""
    return {
        "dsn": dsn,
        "traces_sample_rate": traces_sample_rate,
        "environment": environment,
        "release": release,
        # Cookies + user identity.
        "send_default_pii": False,
        # Frame locals — a decrypted narrative lives here at exception time.
        "include_local_variables": False,
        # Request bodies — the note the member just typed.
        "max_request_body_size": "never",
    }
