"""A small dark stylesheet that sits comfortably inside 3ds Max.

Deliberately minimal - V0.1 spends its effort on comparison correctness,
not on a design system.
"""

from __future__ import annotations

ACCENT = "#4c9be8"
TEXT = "#d6d6d6"
MUTED = "#8a8a8a"
BACKGROUND = "#2b2b2b"
SURFACE = "#333333"
BORDER = "#454545"

CHANGE_COLORS = {
    "ADDED": "#6fbf73",
    "REMOVED": "#e06c6c",
    "GEOMETRY_CHANGED": "#e0a94c",
    "TRANSFORM_CHANGED": "#4c9be8",
    "GEOMETRY_AND_TRANSFORM_CHANGED": "#c07ce0",
    "UNCHANGED": MUTED,
}

STYLESHEET = f"""
QWidget#RevisionGuardPanel {{
    background: {BACKGROUND};
    color: {TEXT};
    font-size: 11px;
}}
QLabel {{ color: {TEXT}; }}
QLabel#Title {{
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 1px;
    color: {TEXT};
    padding: 2px 0 6px 0;
}}
QLabel#Muted, QLabel#Status {{ color: {MUTED}; }}
QLabel#SectionHeader {{
    color: {MUTED};
    font-weight: bold;
    letter-spacing: 1px;
    padding-top: 4px;
}}
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 6px 10px;
    color: {TEXT};
}}
QPushButton:hover:enabled {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; border-color: #3a3a3a; }}
QPushButton#Primary {{
    background: #3b6ea5;
    border: 1px solid #4c9be8;
    font-weight: bold;
}}
QPushButton#Primary:hover:enabled {{ background: #437cba; }}
QPushButton#Primary:disabled {{ background: {SURFACE}; }}
QListWidget {{
    background: #262626;
    border: 1px solid {BORDER};
    border-radius: 3px;
}}
QListWidget::item {{ padding: 3px 4px; }}
QListWidget::item:selected {{ background: #3b6ea5; color: #ffffff; }}
QFrame#Separator {{ background: {BORDER}; max-height: 1px; border: none; }}
"""
