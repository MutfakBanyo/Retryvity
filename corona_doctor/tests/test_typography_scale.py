"""Unit tests asserting the v0.2 readability floor on the type scale.

No PySide6/Qt import needed — Typography is a plain dataclass module, so
this can run in any environment (see docs/ARCHITECTURE.md, "Typography").
Regression guard for the real-host readability complaint that drove the
v0.2 type-scale rework: text must never silently shrink back below these
floors.
"""

from __future__ import annotations

from corona_doctor.ui.design.typography import Typography


def test_body_text_meets_minimum_readable_size():
    assert Typography.BODY.size >= 13
    assert Typography.BODY_EMPHASIS.size >= 13


def test_secondary_text_meets_minimum_size():
    assert Typography.SECONDARY.size >= 12


def test_caption_text_meets_minimum_size():
    assert Typography.CAPTION.size >= 11


def test_section_titles_in_expected_range():
    assert 15 <= Typography.SECTION_TITLE.size <= 17


def test_major_titles_in_expected_range():
    assert 18 <= Typography.TITLE.size <= 22


def test_caption_is_the_smallest_token():
    sizes = [
        Typography.BODY.size,
        Typography.BODY_EMPHASIS.size,
        Typography.SECONDARY.size,
        Typography.SECTION_TITLE.size,
        Typography.TITLE.size,
        Typography.DISPLAY.size,
        Typography.BUTTON.size,
        Typography.TABLE.size,
    ]
    assert Typography.CAPTION.size <= min(sizes)


def test_scale_is_monotonic_caption_to_display():
    assert (
        Typography.CAPTION.size
        <= Typography.SECONDARY.size
        <= Typography.BODY.size
        <= Typography.SECTION_TITLE.size
        <= Typography.TITLE.size
        <= Typography.DISPLAY.size
    )
