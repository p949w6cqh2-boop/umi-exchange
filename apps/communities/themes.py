"""Per-community visual themes (UMI "hella options") — design system v2.

v2 discipline: the SURFACES are brand-fixed (stone paper, true-white cards,
espresso ink, warm hairlines) so the product always reads as one product; a
community's theme changes only its ACCENT pair (primary + accent). All accents
are desaturated to sit with the neutrals, and every pairing keeps white-on-
primary ≥ WCAG AA at button sizes.

Stored on Community.settings:
    settings["theme"]        -> a key in THEMES (default "parish")
    settings["theme_custom"] -> optional {var: "#hex"} overrides (win over the preset)

Resolved into CSS custom properties consumed by base.html / input.css.
"""

THEME_DEFAULT = "parish"

# One surface system for every theme — the product's constant ground.
_SURFACES = {
    "bg": "#F6F4EE",
    "bg_soft": "#EDEAE2",
    "card": "#FFFFFF",
    "border": "#E5E1D6",
    "ink": "#1F1C18",
}


def _theme(label, primary, primary_hover, accent):
    theme = {"label": label, "primary": primary, "primary_hover": primary_hover, "accent": accent}
    theme.update(_SURFACES)
    return theme


# Each theme supplies the full var set; surfaces are shared by design.
THEMES = {
    "parish": _theme("Parish — evergreen", "#275D4C", "#1C4739", "#9C7A3C"),
    "kinfolk": _theme("Kinfolk — hearth amber", "#8F5A2B", "#734720", "#4E6E58"),
    "sankofa": _theme("Sankofa — green & gold", "#2F5D33", "#244A28", "#A88434"),
    "forest": _theme("Forest — deep pine", "#1F4D3A", "#173B2D", "#8A7248"),
    "ocean": _theme("Ocean — harbour teal", "#20606C", "#184C56", "#9C7A3C"),
    "royal": _theme("Royal — vestment purple", "#54407C", "#423263", "#A88434"),
    "rose": _theme("Rose — dried rose", "#8C4157", "#703345", "#9C7A3C"),
    "clay": _theme("Clay — terracotta", "#94512E", "#784124", "#4E6E58"),
    "slate": _theme("Slate — quiet blue-grey", "#44546A", "#364457", "#9C7A3C"),
    "midnight": _theme("Midnight — ink & bronze", "#2A3A54", "#212E43", "#A88434"),
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
