"""
A bare `ssh` line is a paste of its own.

Pasted as one block, `ssh root@host` followed by the droplet's commands never reaches the droplet.
The laptop's shell (bash, with bracketed paste) runs the ssh line, holds every line after it, and
runs them on the laptop once the ssh session ends. On 2026-10-18 the droplet checks printed laptop
errors after `exit`, and a block's closing `exit` closed the laptop's terminal. The runbooks said
to paste a block whole.

So a bare ssh line (a host, no remote command) stands alone in its code block, and the droplet's
commands follow in the next block, pasted at the droplet's prompt. An ssh that carries its own
command (`ssh host 'docker exec ...'`) finishes and returns, so it is fine anywhere.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BARE_SSH = re.compile(r"^ssh(\s+-\S+)*\s+[\w.@-]+\s*(#.*)?$")


def _code_blocks(text):
    for match in re.finditer(r"^[ \t]*```[^\n]*\n(.*?)^[ \t]*```", text, re.S | re.M):
        yield text[: match.start()].count("\n") + 1, match.group(1)


def test_a_bare_ssh_line_is_pasted_on_its_own():
    offenders = []
    for path in sorted(REPO.glob("docs/**/*.md")) + sorted(REPO.glob("*.md")):
        for line_no, block in _code_blocks(path.read_text(encoding="utf-8")):
            commands = [line.strip() for line in block.splitlines()]
            commands = [c for c in commands if c and not c.startswith("#")]
            if len(commands) > 1 and any(BARE_SSH.match(c) for c in commands):
                offenders.append(f"{path.relative_to(REPO)}:{line_no}")

    assert not offenders, (
        "A bare ssh line shares a code block with other commands. Pasted whole, the lines after it "
        "run on the laptop once ssh exits, not on the droplet. Give the ssh line its own block and "
        "start the droplet's block at its prompt:\n  " + "\n  ".join(offenders)
    )


def test_an_ssh_that_carries_its_own_command_is_not_flagged():
    """The rotate_demo_password line runs one command on the droplet and returns; it is safe."""
    assert not BARE_SSH.match("ssh root@157.230.185.124 'docker exec -i docker-app-1 python manage.py x' \\")
    assert BARE_SSH.match("ssh root@157.230.185.124")
    assert BARE_SSH.match("ssh -t root@157.230.185.124   # the droplet")
