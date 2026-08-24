"""A plain composition object bundling the app's core collaborators.

This is intentionally NOT a service locator or DI framework — just one
dataclass built once at startup and passed down explicitly. Anything that
needs the event bus or diagnostic engine takes an ``AppServices`` (or the
specific piece it needs) as a constructor argument.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from corona_doctor.compatibility.feature_flags import FeatureFlags
from corona_doctor.core.diagnostics import DiagnosticEngine
from corona_doctor.core.events import EventBus
from corona_doctor.persistence.settings import SettingsStore
from corona_doctor.repair.registry import RepairRegistry


@dataclass
class AppServices:
    settings: SettingsStore
    bus: EventBus
    engine: DiagnosticEngine
    repair_registry: RepairRegistry = field(default_factory=RepairRegistry)
    feature_flags: FeatureFlags = field(default_factory=FeatureFlags)

    @staticmethod
    def create(settings: SettingsStore | None = None) -> "AppServices":
        store = settings or SettingsStore()
        bus = EventBus()
        engine = DiagnosticEngine(bus)
        flags = FeatureFlags.from_settings(store.as_dict())
        return AppServices(settings=store, bus=bus, engine=engine, feature_flags=flags)
