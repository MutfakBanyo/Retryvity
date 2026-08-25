"""Ground-truth manifest for the Torture Scene fixture generator.

Pure dataclasses + JSON persistence, no pymxs — kept separate from
``torture_scene.py`` (which does the actual, pymxs-dependent scene
construction) so the manifest shape is unit-testable without 3ds Max.
See ``torture_scene.py``'s module docstring for the full workflow this
supports and ``torture_validator.py`` for how this manifest is used as
the objective pass/fail ground truth — never "eyeballing output".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from corona_doctor.core.constants import ORG_NAME, SETTINGS_NAMESPACE


@dataclass(frozen=True)
class FixtureRecord:
    fixture_id: str  # e.g. "CDT-TEX-001"
    category: str
    description: str
    expected_rule_id: str | None
    expected_detection: str  # human-readable statement of what a correct scan should find
    expected_fixability: str  # Repairability value, or "n/a"
    expected_repair_behavior: str
    created_object_names: tuple[str, ...] = field(default_factory=tuple)
    created_material_names: tuple[str, ...] = field(default_factory=tuple)
    created_map_names: tuple[str, ...] = field(default_factory=tuple)
    created_asset_paths: tuple[str, ...] = field(default_factory=tuple)
    skipped: bool = False
    skip_reason: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(d: dict) -> "FixtureRecord":
        d = dict(d)
        for tuple_field in ("created_object_names", "created_material_names", "created_map_names", "created_asset_paths"):
            if tuple_field in d:
                d[tuple_field] = tuple(d[tuple_field])
        return FixtureRecord(**d)


@dataclass(frozen=True)
class TortureManifest:
    created_at: str
    asset_directory: str
    fixtures: tuple[FixtureRecord, ...] = ()

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "asset_directory": self.asset_directory,
            "fixtures": [f.to_dict() for f in self.fixtures],
        }

    @staticmethod
    def from_dict(d: dict) -> "TortureManifest":
        return TortureManifest(
            created_at=d["created_at"],
            asset_directory=d["asset_directory"],
            fixtures=tuple(FixtureRecord.from_dict(f) for f in d.get("fixtures", [])),
        )


def default_torture_manifest_path() -> Path:
    import os

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / ORG_NAME / f"{SETTINGS_NAMESPACE}_torture" / "manifest.json"


def save_torture_manifest(manifest: TortureManifest, *, path: Path | None = None) -> Path:
    path = path or default_torture_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_torture_manifest(*, path: Path | None = None) -> TortureManifest | None:
    path = path or default_torture_manifest_path()
    if not path.is_file():
        return None
    return TortureManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
