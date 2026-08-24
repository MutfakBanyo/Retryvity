"""Lightweight developer/UI feature flags.

Deliberately not a framework: a small frozen dataclass of booleans loaded
from persisted settings at startup. Add a field here only when a real
future milestone needs to gate behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureFlags:
    developer_mode: bool = False
    ui_performance_mode: bool = False

    @staticmethod
    def from_settings(values: dict[str, bool]) -> "FeatureFlags":
        return FeatureFlags(
            developer_mode=bool(values.get("developer_mode", False)),
            ui_performance_mode=bool(values.get("ui_performance_mode", False)),
        )
