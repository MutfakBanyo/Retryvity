"""The ONLY place allowed to actually mutate a scene for a repair.

Mirrors ``adapters/scene_adapter.py``'s read-only discipline in reverse:
every write goes through here, nowhere else. A scanner/rule must never
import this module (see ``core/rules.py``'s "rules must never reach into
pymxs" and docs/REPAIR_ENGINE.md, "Repair adapter boundary") — only
``repair/transaction.py``'s injected ``relink`` callable, wired up by the
UI layer, ever calls it.

Undo grouping uses ``pymxs.undo(True)`` — the documented, current
(3ds Max 2017+, still current in 2026.2) Python-side undo API — not the
legacy MAXScript ``theHold.Begin()``/``theHold.Accept()`` idiom, which
this module does not use or assume still works (see
docs/REPAIR_ENGINE.md, "Undo grouping" for the source this was verified
against — the same class of "don't guess a removed API" lesson as the
3ds Max 2025+ menu system repair).

Identity: relinking targets a live scene object by AnimHandle (via
``rt.getAnimByHandle`` — the documented inverse of
``rt.getHandleByAnim``, see ``adapters/max_adapter.py``), never by
recomputing/guessing an object from a name or path, since a Finding's
``map_handle`` is exactly what the read-only scan already resolved that
object to.
"""

from __future__ import annotations

from corona_doctor.logging.logger import get_logger

try:
    import pymxs  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    pymxs = None

_logger = get_logger("repair_adapter")


class RepairAdapter:
    """Safe, minimal surface for applying a repair's scene mutations."""

    def is_available(self) -> bool:
        return pymxs is not None

    def relink_map_property(self, map_handle: int | None, source_property: str | None, new_path: str) -> bool:
        """Set ``source_property`` (e.g. ``"filename"``) on the map
        object identified by ``map_handle`` to ``new_path``.

        Returns ``False`` (never raises) on any failure — a missing
        handle, an unresolved object, an unsupported property, or a
        pymxs-level error — so ``repair/transaction.py``'s per-operation
        failure handling can record it without special-casing exceptions
        from this specific call.
        """

        if pymxs is None or map_handle is None or not source_property:
            return False
        try:
            rt = pymxs.runtime
            obj = rt.getAnimByHandle(map_handle)
            if obj is None:
                _logger.warning("repair: no live object for handle %s", map_handle)
                return False
            if not rt.isProperty(obj, source_property):
                _logger.warning("repair: %s has no property %r", rt.classOf(obj), source_property)
                return False
            with pymxs.undo(True):
                setattr(obj, source_property, new_path)
            return bool(rt.isProperty(obj, source_property)) and str(getattr(obj, source_property)) == new_path
        except Exception:  # noqa: BLE001 - a repair mutation must never crash the host
            _logger.exception("repair: relink failed for handle %s", map_handle)
            return False

    def read_map_property(self, map_handle: int | None, source_property: str | None) -> str | None:
        """Read ``source_property``'s current value — used by
        ``repair/verification.py`` and ``repair/revert.py`` to check the
        scene still matches a repair manifest before trusting it."""

        if pymxs is None or map_handle is None or not source_property:
            return None
        try:
            rt = pymxs.runtime
            obj = rt.getAnimByHandle(map_handle)
            if obj is None or not rt.isProperty(obj, source_property):
                return None
            value = getattr(obj, source_property)
            return str(value) if value is not None else None
        except Exception:  # noqa: BLE001
            _logger.exception("repair: read failed for handle %s", map_handle)
            return None
