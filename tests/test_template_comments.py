"""Guard against the multi-line ``{# ... #}`` gotcha.

Django's ``{# #}`` comment only spans to end-of-line — the lexer's ``tag_re`` has
no ``DOTALL`` flag — so a ``{# ... #}`` that crosses a newline is NOT a comment.
The opening ``{#`` renders as literal visible text on the page. This has shipped
to production twice (once as a RecursionError from a live ``{% include %}`` inside
such a block, once as stray comment text at the bottom of every page). Multi-line
comments must use ``{% comment %}...{% endcomment %}``.
"""

import pathlib

from config.settings.base import BASE_DIR

TEMPLATE_ROOT = pathlib.Path(BASE_DIR) / "templates"


def test_no_multiline_hash_comments():
    offenders = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            # A line that opens {# but does not close #} after it spans a newline,
            # so Django renders it (and everything until a later #}) as visible text.
            head, sep, tail = line.partition("{#")
            if sep and "#}" not in tail:
                offenders.append(f"{path.relative_to(BASE_DIR)}:{lineno}: {line.strip()[:80]}")
    assert not offenders, (
        "Multi-line {# #} renders as visible text (Django {# #} is single-line only). "
        "Use {% comment %}...{% endcomment %} instead:\n" + "\n".join(offenders)
    )
