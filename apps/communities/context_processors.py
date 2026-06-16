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

    theme = resolve_theme(community)
    return {
        "umi_theme": theme,
        "umi_primary": theme["primary"],
        "umi_accent": theme["accent"],
        "umi_conformance": getattr(settings, "UMI_CONFORMANCE_LEVEL", "core"),
        "site_url": getattr(settings, "SITE_URL", ""),
    }
