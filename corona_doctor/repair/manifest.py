"""Repair manifest persistence — JSON on disk, same discipline as
``persistence/settings.py`` (dependency-free, human-readable, no
credentials/scene data). Stores one file per repair plus a "last repair"
pointer so ``Revert Last Repair`` and devtools inspection have a stable
place to read from.
"""

from __future__ import annotations

import json
from pathlib import Path

from corona_doctor.core.constants import ORG_NAME, SETTINGS_NAMESPACE
from corona_doctor.repair.models import RepairManifest


def default_repairs_dir() -> Path:
    import os

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / ORG_NAME / f"{SETTINGS_NAMESPACE}_repairs"


def save_manifest(manifest: RepairManifest, *, directory: Path | None = None) -> Path:
    directory = directory or default_repairs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{manifest.repair_id}.json"
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    (directory / "last_repair.txt").write_text(manifest.repair_id, encoding="utf-8")
    return path


def load_manifest(repair_id: str, *, directory: Path | None = None) -> RepairManifest | None:
    directory = directory or default_repairs_dir()
    path = directory / f"{repair_id}.json"
    if not path.is_file():
        return None
    return RepairManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_last_manifest(*, directory: Path | None = None) -> RepairManifest | None:
    directory = directory or default_repairs_dir()
    pointer = directory / "last_repair.txt"
    if not pointer.is_file():
        return None
    repair_id = pointer.read_text(encoding="utf-8").strip()
    if not repair_id:
        return None
    return load_manifest(repair_id, directory=directory)
