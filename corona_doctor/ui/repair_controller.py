"""Wires the pure ``repair/`` engine to real filesystem operations and
``adapters/repair_adapter.py``, driven by the UI — mirrors
``ui/scan_controller.py``'s separation: the UI never calls
``repair/transaction.py`` directly, only through here, and this module
never builds a Qt widget/dialog itself (that stays in the view layer —
see ``ui/views/textures_view.py``). Real filesystem I/O (``shutil.copy2``,
``os.makedirs``, ``os.path.isfile``) lives here, not in ``repair/``, so
the pure planning/transaction/verification modules stay filesystem-free
and unit-testable without touching disk.
"""

from __future__ import annotations

import os
import shutil
from typing import Iterable

from corona_doctor.adapters.max_adapter import MaxAdapter
from corona_doctor.adapters.repair_adapter import RepairAdapter
from corona_doctor.core.texture_models import ExternalTextureReference
from corona_doctor.repair import manifest as repair_manifest
from corona_doctor.repair.models import RepairManifest, RepairPlan, RepairResult, RepairState
from corona_doctor.repair.planner import (
    RelinkCandidate,
    build_batch_relink_plan,
    build_make_portable_plan,
    build_relink_plan,
    classify_candidates,
    find_relink_candidates,
)
from corona_doctor.repair.revert import build_revert_plan
from corona_doctor.repair.transaction import apply_plan
from corona_doctor.repair.verification import verify_repair


def _exists_checker(path: str) -> bool | None:
    try:
        return os.path.isfile(path)
    except OSError:
        return None


def _copy_file(source: str, destination: str) -> None:
    shutil.copy2(source, destination)


def _create_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class RepairController:
    """One instance per panel session — see ``ui/main_window.py``."""

    def __init__(self, adapter: RepairAdapter | None = None, max_adapter: MaxAdapter | None = None) -> None:
        self._adapter = adapter or RepairAdapter()
        self._max_adapter = max_adapter or MaxAdapter()

    # -- Locate / traceability ---------------------------------------------

    def select_objects(self, object_names: Iterable[str]) -> int:
        """"Show Objects" — see docs/REPAIR_ENGINE.md, "Locate/traceability".
        Returns how many were actually found and selected."""

        return self._max_adapter.select_nodes_by_name(tuple(object_names))

    # -- Make Project Portable ------------------------------------------

    def plan_make_portable(self, references: Iterable[ExternalTextureReference], destination_dir: str) -> RepairPlan:
        """Side-effect free — see ``repair/planner.py``."""

        return build_make_portable_plan(references, destination_dir, exists_checker=_exists_checker)

    def apply_make_portable(self, plan: RepairPlan) -> RepairResult:
        return self._apply_and_save(plan)

    # -- Missing Texture Relink ------------------------------------------

    def find_candidates(self, missing_filename: str, search_roots: Iterable[str]) -> tuple[list[RelinkCandidate], str]:
        """Walks ``search_roots`` for files, ranks them deterministically
        (see ``repair/planner.py::find_relink_candidates`` — never fuzzy/AI
        matching), and classifies the result as "none"/"single"/"multiple"."""

        target_name = os.path.basename(missing_filename).lower()
        candidate_paths: list[str] = []
        for root in search_roots:
            for dirpath, _dirs, filenames in os.walk(root):
                for name in filenames:
                    if name.lower() == target_name:
                        candidate_paths.append(os.path.join(dirpath, name))
        candidates = find_relink_candidates(missing_filename, candidate_paths, size_lookup=self._size_lookup)
        return candidates, classify_candidates(candidates)

    @staticmethod
    def _size_lookup(path: str) -> int | None:
        try:
            return os.path.getsize(path)
        except OSError:
            return None

    def plan_relink(self, ref: ExternalTextureReference, chosen_path: str) -> RepairPlan:
        return build_relink_plan(ref, chosen_path)

    def apply_relink(self, plan: RepairPlan) -> RepairResult:
        return self._apply_and_save(plan)

    # -- Smart Asset Recovery (batch) ------------------------------------

    def plan_batch_relink(self, accepted: Iterable[tuple[Iterable[ExternalTextureReference], str]]) -> RepairPlan:
        """Combine every accepted Smart Relink candidate into ONE plan
        — see ``repair/planner.py::build_batch_relink_plan`` and
        docs/SMART_RELINK.md, "Relink must use the Repair Engine"."""

        return build_batch_relink_plan(accepted)

    def apply_batch_relink(self, plan: RepairPlan) -> RepairResult:
        return self._apply_and_save(plan)

    # -- Revert -------------------------------------------------------------

    def load_last_manifest(self) -> RepairManifest | None:
        return repair_manifest.load_last_manifest()

    def plan_revert(self, manifest: RepairManifest) -> RepairPlan:
        return build_revert_plan(manifest, read_current_value=self._read_current_value)

    def apply_revert(self, plan: RepairPlan) -> RepairResult:
        result = apply_plan(plan, copy_file=_copy_file, create_directory=_create_directory, relink=self._relink)
        reverted_manifest = _mark_reverted(result.manifest)
        repair_manifest.save_manifest(reverted_manifest)
        return RepairResult(manifest=reverted_manifest, summary=result.summary, errors=result.errors)

    # -- Verify -------------------------------------------------------------

    def verify(self, manifest: RepairManifest) -> tuple[RepairState, tuple[str, ...]]:
        return verify_repair(manifest, read_current_value=self._read_current_value, exists_checker=_exists_checker)

    # -- internals ----------------------------------------------------------

    def _apply_and_save(self, plan: RepairPlan) -> RepairResult:
        result = apply_plan(plan, copy_file=_copy_file, create_directory=_create_directory, relink=self._relink)
        repair_manifest.save_manifest(result.manifest)
        return result

    def _relink(self, map_handle: int | None, source_property: str | None, _ref_id: str, new_path: str) -> bool:
        return self._adapter.relink_map_property(map_handle, source_property, new_path)

    def _read_current_value(self, map_handle: int | None, source_property: str | None, _ref_id: str) -> str | None:
        return self._adapter.read_map_property(map_handle, source_property)


def _mark_reverted(manifest: RepairManifest) -> RepairManifest:
    from dataclasses import replace

    return replace(manifest, state=RepairState.REVERTED)
