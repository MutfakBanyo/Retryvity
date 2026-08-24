"""Adapter around Chaos Corona.

Corona is detected purely through introspection of the running 3ds Max
process (available renderer classes) — no assumptions about undocumented
properties are made. Every method returns ``None``/``False``/an empty
collection rather than raising when Corona is missing or a property
cannot be read, so the rest of Corona Doctor never has to special-case
"Corona not installed".
"""

from __future__ import annotations

try:
    import pymxs  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    pymxs = None

KNOWN_CORONA_RENDERER_CLASS_NAMES = (
    "CoronaRenderer",
)


class CoronaAdapter:
    """Minimal, safe surface over Corona detection and introspection."""

    def is_installed(self) -> bool | None:
        """Return True/False, or None if this cannot be determined.

        Detection is attempted via ``renderers.classes`` (a pymxs array of
        every registered renderer class), which does not require Corona to
        be the active renderer.
        """

        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            for renderer_class in rt.renderers.classes:
                if str(renderer_class) in KNOWN_CORONA_RENDERER_CLASS_NAMES:
                    return True
            return False
        except Exception:  # noqa: BLE001
            return None

    def is_active_renderer(self) -> bool | None:
        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            current = rt.renderers.current
            if current is None:
                return False
            return str(rt.classOf(current)) in KNOWN_CORONA_RENDERER_CLASS_NAMES
        except Exception:  # noqa: BLE001
            return None

    def get_renderer_class(self) -> str | None:
        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            for renderer_class in rt.renderers.classes:
                name = str(renderer_class)
                if name in KNOWN_CORONA_RENDERER_CLASS_NAMES:
                    return name
            return None
        except Exception:  # noqa: BLE001
            return None

    def get_available_properties(self) -> tuple[str, ...]:
        """List property names exposed on the active Corona renderer.

        Used only for introspection/diagnostics — never assume a specific
        property exists elsewhere in the codebase without checking this
        (or the CapabilityRegistry, which is built from probes like this
        one) first.
        """

        if pymxs is None:
            return ()
        try:
            rt = pymxs.runtime
            current = rt.renderers.current
            if current is None or str(rt.classOf(current)) not in KNOWN_CORONA_RENDERER_CLASS_NAMES:
                return ()
            names = rt.getPropNames(current)
            return tuple(str(n) for n in names)
        except Exception:  # noqa: BLE001
            return ()
