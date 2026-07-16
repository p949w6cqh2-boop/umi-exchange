from django import forms

from .models import RESERVED_SLUGS, CommunityPage


class CommunityPageForm(forms.ModelForm):
    class Meta:
        model = CommunityPage
        fields = ["title", "slug", "content_md", "show_on_landing", "sort_order"]

    def __init__(self, *args, community=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.community = community or (self.instance.community_id and self.instance.community)
        if self.instance.pk and self.instance.first_published_at:
            # Links are promises — the slug froze at first publish (§C).
            self.fields["slug"].disabled = True

    def clean_content_md(self):
        value = self.cleaned_data.get("content_md", "")
        if len(value) > 20000:
            raise forms.ValidationError(
                "That's past the 20,000-character limit. Pages carry the parish's words, not its archives."
            )
        return value

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        if slug in RESERVED_SLUGS:
            # /p/manage/ belongs to the manager (§E) — a page there would be unreachable.
            raise forms.ValidationError("That address is reserved. Pick a different slug.")
        if self.community:
            clash = CommunityPage.objects.filter(community=self.community, slug=slug).exclude(status="archived")
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise forms.ValidationError("Another page already lives at this address. Pick a different slug.")
        return slug
