"""Adapter around 3ds Max (pymxs / qtmax).

This module is the only place in Corona Doctor allowed to import pymxs or
qtmax. Every public method degrades gracefully — it returns ``None`` or a
safe default rather than raising — because Corona Doctor must be able to
report a useful environment probe even when running outside 3ds Max
(e.g. during development or unit tests).

Threading note: pymxs scene access is main-thread-only. Do not call any
method on this adapter from a worker thread — see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

try:
    import pymxs  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    pymxs = None

try:
    import qtmax  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    qtmax = None


def _parse_maxversion_array(version_info) -> str | None:
    """Normalize ``maxversion()``'s array into "<year>.<service pack>".

    Confirmed on a real 3ds Max 2026.2 host:
    ``#(28000, 68, 0, 28, 2, 0, 20659, 2026, ".2")`` -> index 7 is the
    marketing year (2026), index 8 is the service-pack suffix (".2") ->
    "2026.2". This is empirical, not documented Autodesk behavior, so it
    degrades to ``None`` (caller falls back to other sources) rather than
    guessing when the shape does not match.
    """

    try:
        items = list(version_info)
    except Exception:  # noqa: BLE001
        return None
    if len(items) < 9:
        return None
    try:
        year = int(items[7])
    except (TypeError, ValueError):
        return None
    suffix = str(items[8])
    if suffix.startswith("."):
        return f"{year}{suffix}"
    return f"{year}.{suffix}" if suffix else str(year)


class MaxAdapter:
    """Safe, minimal surface over the 3ds Max host APIs."""

    def is_available(self) -> bool:
        return pymxs is not None

    def get_max_version_string(self) -> str | None:
        """Return the normalized, human-readable 3ds Max version, e.g. "2026.2".

        Uses ``maxversion()`` via MAXScript through pymxs because pymxs
        itself does not expose a friendly product-year string directly.
        Falls back to ``getFileVersion``'s product string, and finally to
        the raw array's ``str()`` if neither can be parsed — callers that
        need the untouched raw value should use
        :meth:`get_max_version_raw` instead.
        """

        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            version_info = rt.maxversion()

            parsed = _parse_maxversion_array(version_info)
            if parsed:
                return parsed

            product_string = getattr(rt, "getFileVersion", None)
            if callable(product_string):
                try:
                    return str(rt.getFileVersion("$max/../3dsmax.exe", "productversion"))
                except Exception:  # noqa: BLE001 - best-effort only
                    pass
            return str(version_info)
        except Exception:  # noqa: BLE001 - never let a probe crash the host
            return None

    def get_max_version_raw(self) -> str | None:
        """Return the untouched ``str(maxversion())`` array, for diagnostics."""

        if pymxs is None:
            return None
        try:
            return str(pymxs.runtime.maxversion())
        except Exception:  # noqa: BLE001
            return None

    def get_max_main_window(self):
        """Return the 3ds Max main window as a QWidget, or ``None``."""

        if qtmax is None:
            return None
        try:
            return qtmax.GetQMaxMainWindow()
        except AttributeError:
            try:
                return qtmax.GetQMaxWindow()
            except Exception:  # noqa: BLE001
                return None
        except Exception:  # noqa: BLE001
            return None

    def get_current_renderer_class_name(self) -> str | None:
        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            renderer = rt.renderers.current
            if renderer is None:
                return None
            return rt.classOf(renderer).__str__() if hasattr(rt.classOf(renderer), "__str__") else str(rt.classOf(renderer))
        except Exception:  # noqa: BLE001
            return None

    def get_scene_object_count(self) -> int | None:
        """Cheap scene stat used only for environment context, not a scan."""

        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            return int(rt.objects.count)
        except Exception:  # noqa: BLE001
            return None
