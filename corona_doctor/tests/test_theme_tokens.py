"""Regression tests for the dark.qss <-> theme-token contract.

A real 3ds Max 2026.2 host crashed on launch with::

    KeyError: 'DISPLAY_SIZE'

from ``ui.themes.load_dark_theme()`` — a placeholder referenced by
dark.qss had no matching entry in the substitution map at the time. These
tests make that class of bug fail here, in a plain Python 3.11+
interpreter with no PySide6/3ds Max required (``ui/themes/__init__.py``
only imports the pure-dataclass ``ui/design/*`` modules), instead of only
surfacing as a real-host crash. See ui/themes/__init__.py's module
docstring.
"""

from __future__ import annotations

import re

from corona_doctor.ui.themes import _QSS_PATH, _TOKEN_PATTERN, _substitute_token, build_theme_tokens, load_dark_theme

_UNRESOLVED_PLACEHOLDER = re.compile(r"\{[A-Za-z_]+\}")


def _placeholders_in_qss() -> set[str]:
    source = _QSS_PATH.read_text(encoding="utf-8")
    return set(_TOKEN_PATTERN.findall(source))


def test_every_qss_placeholder_has_a_token():
    """No placeholder in dark.qss is missing from the substitution map.

    This is exactly the KeyError: 'DISPLAY_SIZE' real-host failure —
    reproduced here as a set-difference assertion instead of a runtime
    crash.
    """

    placeholders = _placeholders_in_qss()
    tokens = build_theme_tokens()
    missing = placeholders - tokens.keys()
    assert not missing, f"dark.qss references undefined theme token(s): {sorted(missing)}"


def test_every_token_is_referenced_by_qss():
    """No dead token in the substitution map (drift in the other direction).

    Not a crash risk by itself, but a token nobody references is a sign
    the two sides have drifted and is worth catching too.
    """

    placeholders = _placeholders_in_qss()
    tokens = build_theme_tokens()
    unused = tokens.keys() - placeholders
    assert not unused, f"theme token(s) defined but never referenced by dark.qss: {sorted(unused)}"


def test_load_dark_theme_leaves_no_unresolved_placeholders():
    css = load_dark_theme()
    unresolved = _UNRESOLVED_PLACEHOLDER.findall(css)
    assert unresolved == [], f"unresolved placeholder(s) survived substitution: {unresolved}"


def test_load_dark_theme_smoke():
    """Direct smoke test: the theme loads as a non-empty string with no
    leftover ``{TOKEN}`` markers — see docs/ARCHITECTURE.md, "Typography"."""

    css = load_dark_theme()
    assert isinstance(css, str)
    assert len(css) > 0
    assert not _UNRESOLVED_PLACEHOLDER.search(css)
    print("THEME LOAD PASS")


def test_missing_token_raises_clear_error_not_bare_keyerror():
    """If a future edit does drop a token, the failure must be diagnosable
    (name the missing token + where to fix it) — not a bare
    ``KeyError: 'DISPLAY_SIZE'`` with no context, which is what actually
    reached the real host."""

    match = _TOKEN_PATTERN.match("{SOME_MISSING_TOKEN}")
    assert match is not None
    try:
        _substitute_token(match, tokens={})
    except KeyError as exc:
        message = str(exc)
        assert "SOME_MISSING_TOKEN" in message
        assert "build_theme_tokens" in message
    else:
        raise AssertionError("expected a KeyError when a referenced token is missing")
