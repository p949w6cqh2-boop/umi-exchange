"""App-wide AA guards (the founder's follow-up order, 2026-07-17).

The muted ink family sits at 70%: axe measured 60% compositing to 4.2:1 on
the stone surface — under WCAG AA's 4.5:1 for small text — and 45/55 lower
still. The re-tint closed the last six pre-existing contrast spots; this
guard keeps the sub-AA tiers from creeping back into any template."""

import re
from pathlib import Path

SUB_AA_MUTED_INK = re.compile(r"text-parish-ink/(45|50|55|60)\b")


def test_no_sub_aa_muted_ink_in_templates():
    offenders = []
    for path in Path("templates").rglob("*.html"):
        for match in SUB_AA_MUTED_INK.finditer(path.read_text()):
            offenders.append(f"{path}: {match.group(0)}")
    assert offenders == [], "sub-AA muted ink returned:\n" + "\n".join(offenders)
