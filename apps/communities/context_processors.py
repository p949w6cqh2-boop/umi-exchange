"""Global template context: per-community UMI theming and conformance level."""

from django.conf import settings

from .themes import resolve_theme


def umi_context(request):
    # Resolve the current community from the URL (community pages carry <slug>),
    # so each community renders in its own theme. Non-community pages → default.
    community = None
    rm = getattr(request, "resolver_match", None)
    slug = rm.kwargs.get("slug") if rm else None
    if slug:
        from .models import Community

        community = Community.objects.filter(slug=slug).only("id", "settings").first()

    # Slug for the mobile bottom nav: the URL's when present, else the last
    # community the member visited so the bar survives slug-less pages like
    # the notifications list. Keep the fallback fresh from every slug page.
    has_session = hasattr(request, "session")
    if slug and has_session:
        request.session["hub:last_slug"] = slug
    nav_slug = slug or (request.session.get("hub:last_slug") if has_session else None)

    theme = resolve_theme(community)
    return {
        "umi_theme": theme,
        "umi_primary": theme["primary"],
        "umi_accent": theme["accent"],
        "umi_conformance": getattr(settings, "UMI_CONFORMANCE_LEVEL", "core"),
        "site_url": getattr(settings, "SITE_URL", ""),
        "nav_slug": nav_slug,
    }
