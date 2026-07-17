"""§D structured identity — the four small facts on Community.settings.

patron (≤80) · welcome_lines (≤10 lines, each ≤140 — the hub greeting rotates
through them by the day; the founder's call, 2026-07-17) · signin_blurb (≤300,
the anon /p/ index) · scene_choices ({surface: slug} from the committed prints).

The wall has no second door: every fact renders auto-escaped in templates —
never |safe, never concatenated into HTML. Unknown scene slugs are dropped at
the writer AND fall back at the reader (resolve_theme posture)."""

MAX_PATRON = 80
MAX_WELCOME_LINE = 140
MAX_WELCOME_LINES = 10
MAX_BLURB = 300

SCENE_SURFACES = ("hub", "landing")

# Keyed by template stem in templates/illustrations/ — the 10 committed prints.
SCENE_SLUGS = (
    "board",
    "carrying",
    "exchange",
    "hill",
    "lakes",
    "one_place",
    "priest",
    "spring",
    "threshold",
    "well",
)


def parse_identity_post(post):
    """POST → (updates, errors). Only fields PRESENT in the POST are parsed —
    an omitted field is left untouched, so a partial or crafted submit can
    never wipe keys the writer didn't send. A present-but-blank field means
    "clear". Any length violation rejects the whole write (nothing half-lands).
    Scene values are per-surface: blank clears that surface, an unknown slug
    is a silent no-op — resolve_theme posture."""
    errors = []
    updates = {}

    if "patron" in post:
        patron = post["patron"].strip()
        if len(patron) > MAX_PATRON:
            errors.append(f"The patron line stays under {MAX_PATRON} characters.")
        updates["patron"] = patron

    if "welcome_lines" in post:
        lines = [line.strip() for line in post["welcome_lines"].splitlines() if line.strip()]
        if len(lines) > MAX_WELCOME_LINES:
            errors.append(f"Up to {MAX_WELCOME_LINES} welcome lines — the hub rotates through them daily.")
        if any(len(line) > MAX_WELCOME_LINE for line in lines):
            errors.append(f"Each welcome line stays under {MAX_WELCOME_LINE} characters.")
        updates["welcome_lines"] = lines

    if "signin_blurb" in post:
        blurb = post["signin_blurb"].strip()
        if len(blurb) > MAX_BLURB:
            errors.append(f"The sign-in blurb stays under {MAX_BLURB} characters.")
        updates["signin_blurb"] = blurb

    scenes = {s: post[f"scene_{s}"].strip() for s in SCENE_SURFACES if f"scene_{s}" in post}
    if scenes:
        updates["scene_choices"] = scenes

    return updates, errors


def signin_blurb(community):
    """The sign-in door's blurb, or "" — every §D read lives in this module."""
    return (getattr(community, "settings", None) or {}).get("signin_blurb", "")


def welcome_line_for_today(community, today=None):
    """The day's greeting sub-line, rotating through the parish's own words —
    deterministic by date ordinal, so everyone sees the same line all day and
    it turns over at midnight. One line = static; none = None."""
    lines = (getattr(community, "settings", None) or {}).get("welcome_lines") or []
    if not lines:
        return None
    if today is None:
        from django.utils import timezone

        today = timezone.localdate()
    return lines[today.toordinal() % len(lines)]


def scene_template(community, surface, default=None):
    """Template path for a surface's chosen print, falling back silently to
    `default` (resolve_theme posture — an unknown or absent choice never errors)."""
    chosen = ((getattr(community, "settings", None) or {}).get("scene_choices") or {}).get(surface)
    slug = chosen if chosen in SCENE_SLUGS else default
    return f"illustrations/_{slug}.html" if slug else None
