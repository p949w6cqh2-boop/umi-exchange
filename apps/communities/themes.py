"""Per-community visual themes (UMI "hella options").

A community picks a preset theme (or overrides individual colors) and the whole
look re-skins: page background + gradient, cards, buttons, borders, accents.
All themes are LIGHT (dark warm ink on a light tint) so contrast/legibility is
safe across the board — only the hues change.

Stored on Community.settings:
    settings["theme"]        -> a key in THEMES (default "parish")
    settings["theme_custom"] -> optional {var: "#hex"} overrides (win over the preset)

Resolved into CSS custom properties consumed by base.html / input.css.
"""

THEME_DEFAULT = "parish"

# Each theme supplies the full var set. ink stays dark everywhere for legibility.
THEMES = {
    "parish": {
        # Community Hub (Direction D): warm "town well" — water-teal gathering color,
        # gold kept as the warm accent, cream paper with a barely-cool surface tint.
        "label": "Parish — warm teal",
        "primary": "#0F6B73",
        "primary_hover": "#0B585F",
        "accent": "#C49A3C",
        "bg": "#FDFBF7",
        "bg_soft": "#EFF1EE",
        "card": "#F6F8F5",
        "border": "#DDE6E2",
        "ink": "#2C2A29",
    },
    "kinfolk": {
        "label": "Kinfolk — amber & earth",
        "primary": "#B5651D",
        "primary_hover": "#8F4E13",
        "accent": "#C49A3C",
        "bg": "#FBF6EF",
        "bg_soft": "#F3E9DA",
        "card": "#FBF4E9",
        "border": "#E7DAC6",
        "ink": "#2B2622",
    },
    "sankofa": {
        "label": "Sankofa — green & gold",
        "primary": "#1B5E20",
        "primary_hover": "#154A19",
        "accent": "#E0A100",
        "bg": "#FBF7F0",
        "bg_soft": "#F1ECDE",
        "card": "#FAF6EC",
        "border": "#E4Dcc8",
        "ink": "#241F1A",
    },
    "forest": {
        "label": "Forest — deep green",
        "primary": "#1F4D3A",
        "primary_hover": "#173B2D",
        "accent": "#C49A3C",
        "bg": "#F5F8F4",
        "bg_soft": "#E8F0E9",
        "card": "#F6FAF6",
        "border": "#DCE7DD",
        "ink": "#222826",
    },
    "ocean": {
        "label": "Ocean — teal & sand",
        "primary": "#146C7E",
        "primary_hover": "#0F5462",
        "accent": "#C9A24B",
        "bg": "#F4FAFB",
        "bg_soft": "#E3F1F3",
        "card": "#F4FBFC",
        "border": "#D3E6E9",
        "ink": "#1E2A2C",
    },
    "royal": {
        "label": "Royal — purple & gold",
        "primary": "#5B3A8C",
        "primary_hover": "#472D6E",
        "accent": "#C49A3C",
        "bg": "#FAF7FC",
        "bg_soft": "#EFE8F5",
        "card": "#FAF6FD",
        "border": "#E2D8EC",
        "ink": "#262130",
    },
    "rose": {
        "label": "Rose — warm pink",
        "primary": "#9D3B5E",
        "primary_hover": "#7E2F4B",
        "accent": "#C49A3C",
        "bg": "#FDF6F8",
        "bg_soft": "#F6E6EC",
        "card": "#FDF5F8",
        "border": "#EED6DE",
        "ink": "#2C2226",
    },
    "clay": {
        "label": "Clay — terracotta",
        "primary": "#A4471F",
        "primary_hover": "#833818",
        "accent": "#5E8C61",
        "bg": "#FBF5F0",
        "bg_soft": "#F2E4DA",
        "card": "#FBF4EE",
        "border": "#E8D6C8",
        "ink": "#2B2320",
    },
    "slate": {
        "label": "Slate — calm blue-grey",
        "primary": "#3F5168",
        "primary_hover": "#314052",
        "accent": "#C49A3C",
        "bg": "#F6F8FA",
        "bg_soft": "#E8EDF2",
        "card": "#F7F9FB",
        "border": "#DCE3EA",
        "ink": "#222730",
    },
    "midnight": {
        "label": "Midnight — ink & gold",
        "primary": "#22304A",
        "primary_hover": "#1A2638",
        "accent": "#C9A24B",
        "bg": "#F5F6F8",
        "bg_soft": "#E7EAEF",
        "card": "#F6F7F9",
        "border": "#D8DDE5",
        "ink": "#1E232B",
    },
}

# Which keys a community may override individually.
CUSTOMIZABLE = ("primary", "primary_hover", "accent", "bg", "bg_soft", "card", "border", "ink")


def resolve_theme(community):
    """Return the full var dict for a community (or the default if None)."""
    theme = dict(THEMES[THEME_DEFAULT])
    if community is None:
        return theme
    settings = getattr(community, "settings", None) or {}
    key = settings.get("theme") or THEME_DEFAULT
    theme = dict(THEMES.get(key, THEMES[THEME_DEFAULT]))
    for var, value in (settings.get("theme_custom") or {}).items():
        if var in CUSTOMIZABLE and value:
            theme[var] = value
    return theme
