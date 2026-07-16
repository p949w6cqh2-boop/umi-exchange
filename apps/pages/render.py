"""The write-path renderer (§G): content_md → cached content_html on save.

nh3 is the ONLY writer of content_html, and nothing renders at request time.
The wall's grammar is exact and small: words, lists, quotes, links. Images
become links (the words carry the page); headings fold into the page's band
(the platform chrome owns the h1); no class, id, or style ever survives, so
content cannot wear the platform's clothes."""

import markdown
import nh3
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

# Exact allowlist (§G) — extending this is a spec change, not a tweak.
ALLOWED_TAGS = {
    "h2",
    "h3",
    "h4",
    "p",
    "br",
    "em",
    "strong",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
    "code",
    "pre",
    "hr",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
ALLOWED_SCHEMES = {"https", "http", "mailto", "tel"}
LINK_REL = "nofollow noopener noreferrer"


class _FoldTreeprocessor(Treeprocessor):
    """Runs before sanitizing: <img> → <a href=src>alt</a>, h1 → h2, h5/h6 → h4."""

    def run(self, root):
        for el in root.iter():
            if el.tag == "img":
                src = el.get("src", "")
                alt = (el.get("alt") or "").strip() or src
                tail = el.tail
                el.clear()
                el.tag = "a"
                el.set("href", src)
                el.text = alt
                el.tail = tail
            elif el.tag == "h1":
                el.tag = "h2"
            elif el.tag in ("h5", "h6"):
                el.tag = "h4"


class _PageExtension(Extension):
    def extendMarkdown(self, md):  # noqa: N802 (markdown API)
        md.treeprocessors.register(_FoldTreeprocessor(md), "umi_page_fold", 5)


def render_page_html(content_md: str) -> str:
    md = markdown.Markdown(extensions=["sane_lists", _PageExtension()])
    raw = md.convert(content_md or "")
    return nh3.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_SCHEMES,
        link_rel=LINK_REL,
    )
