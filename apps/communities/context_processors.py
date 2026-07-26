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

    # Slug for the mobile bottom nav: the URL's when the visitor is actually an
    # active member there, else the last community they visited so the bar
    # survives slug-less pages like the notifications list. The membership check
    # mirrors HubView (which stamps the session only after its own): this runs on
    # every RequestContext render including 404.html, so without it one GET of a
    # foreign, left or typo'd /c/<slug>/ repointed the bar at four URLs that all
    # 404 for that member, and it stuck. Theming stays URL-driven by design.
    has_session = hasattr(request, "session")
    user = getattr(request, "user", None)
    is_member = False
    if community is not None and user is not None and user.is_authenticated:
        from .models import Member

        is_member = Member.objects.filter(user=user, community=community, is_active=True).exists()
    if is_member and has_session:
        request.session["hub:last_slug"] = slug
    nav_slug = slug if is_member else (request.session.get("hub:last_slug") if has_session else None)

    theme = resolve_theme(community)
    return {
        "umi_theme": theme,
        "umi_primary": theme["primary"],
        "umi_accent": theme["accent"],
        "umi_conformance": getattr(settings, "UMI_CONFORMANCE_LEVEL", "core"),
        "site_url": getattr(settings, "SITE_URL", ""),
        "nav_slug": nav_slug,
    }
