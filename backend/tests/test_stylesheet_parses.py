"""The stylesheet must actually parse, all of it.

CSS has no failure mode worth the name. A browser meeting something it cannot
understand does not raise, does not warn in the build, and does not stop — it
discards declarations until it finds something that looks like a rule again,
and carries on silently. Whatever was in the discarded stretch simply never
existed.

That happened here. A comment was closed, six lines of prose were left sitting
in the stylesheet, and a second `*/` followed. The parser threw away the prose
AND the `.code-root` rule after it, along with half the declarations of the
next one. The build succeeded. The deploy succeeded. The Code app stayed broken
on phones, and the fix had been "verified" by injecting the rules into a live
page — which of course worked, because injected rules parse fine.

So the stylesheet is checked as text, from the backend suite, because that is
the suite that always runs. Cheap, and it catches the whole class: unbalanced
braces, unterminated comments, and content stranded outside any rule.
"""
import re
from pathlib import Path

import pytest

CSS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "styles"


def stylesheets() -> list[Path]:
    return sorted(CSS_DIR.glob("*.css")) if CSS_DIR.is_dir() else []


def test_there_are_stylesheets_to_check():
    """If this fails the others are vacuous — the path moved."""
    assert stylesheets(), f"no stylesheets found under {CSS_DIR}"


@pytest.mark.parametrize("path", stylesheets(), ids=lambda p: p.name)
def test_comments_are_terminated_and_not_reopened(path: Path):
    src = path.read_text(encoding="utf-8")
    without_comments = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    assert "*/" not in without_comments, (
        f"{path.name}: a stray '*/' remains after removing every complete "
        "comment — text is sitting outside a comment and the browser will "
        "silently discard the rules around it."
    )
    assert "/*" not in without_comments, (
        f"{path.name}: an unterminated comment swallows everything after it."
    )


@pytest.mark.parametrize("path", stylesheets(), ids=lambda p: p.name)
def test_braces_balance(path: Path):
    src = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    depth = 0
    for ch in src:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            assert depth >= 0, f"{path.name}: a '}}' closes a block that was never opened"
    assert depth == 0, f"{path.name}: {depth} block(s) left unclosed"


@pytest.mark.parametrize("path", stylesheets(), ids=lambda p: p.name)
def test_no_prose_stranded_between_rules(path: Path):
    """Catch the exact shape of the bug: words where a selector should be.

    Between one rule's `}` and the next rule's `{` there should only ever be a
    selector, an at-rule, or whitespace. English sentences there mean a comment
    ended early.
    """
    src = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    for chunk in re.findall(r"\}([^{}]*)\{", src):
        selector = chunk.strip()
        if not selector:
            continue
        # A selector never contains a full stop followed by a space, and never
        # runs past a couple of lines.
        assert ". " not in selector, (
            f"{path.name}: prose found where a selector belongs — "
            f"{selector[:70]!r}"
        )
        assert selector.count("\n") <= 4, (
            f"{path.name}: suspiciously long text before a '{{' — "
            f"{selector[:70]!r}"
        )
