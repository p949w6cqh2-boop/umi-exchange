"""Global template context: UMI theming and conformance level."""
from django.conf import settings


def umi_context(request):
    return {
        "umi_primary": getattr(settings, "UMI_PRIMARY_COLOR", "#1A1A2E"),
        "umi_accent": getattr(settings, "UMI_ACCENT_COLOR", "#3B82F6"),
        "umi_conformance": getattr(settings, "UMI_CONFORMANCE_LEVEL", "core"),
        "site_url": getattr(settings, "SITE_URL", ""),
    }
