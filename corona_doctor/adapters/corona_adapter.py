"""Adapter around Chaos Corona.

Corona is detected through multiple independent runtime signals rather
than a single fragile string comparison — see :meth:`CoronaAdapter.detect`.
Every method returns ``None``/``False``/an empty collection rather than
raising when Corona is missing or a property cannot be read, so the rest
of Corona Doctor never has to special-case "Corona not installed".

Confirmed real-host behavior (3ds Max 2026.2 / Corona, probed
2026-08-25) — do not "normalize" this away, the two class names are
genuinely different facts:

* ``rt.renderers.classes`` lists the *installed/registered* renderer
  class as ``CoronaRenderer``.
* ``str(rt.classOf(rt.renderers.current))`` for the *active* Corona
  renderer instance returns ``Corona``, not ``CoronaRenderer``.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import pymxs  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    pymxs = None

# Renderer class name(s) as they appear in rt.renderers.classes (the
# registered-renderers list) — installation signal only.
INSTALLED_RENDERER_CLASS_NAMES = ("CoronaRenderer",)

# Renderer class name(s) as classOf() reports them for the *active*
# renderer instance — confirmed to differ from the installed-class name
# above on real hosts.
ACTIVE_RENDERER_CLASS_NAMES = ("Corona", "CoronaRenderer")

# Kept for backwards compatibility with existing callers/tests that only
# care about "is Corona registered at all".
KNOWN_CORONA_RENDERER_CLASS_NAMES = INSTALLED_RENDERER_CLASS_NAMES

# Runtime globals whose mere existence is a strong, independent
# installation signal even when Corona is not the active renderer.
INSTALLATION_SIGNAL_SYMBOLS = (
    "CoronaRenderer",
    "CoronaPhysicalMtl",
    "CoronaLight",
    "CoronaBitmap",
    "CoronaMtl",
)

# Best-effort classification of discovered "*corona*" runtime symbols.
# This is a convenience layer only — discover_symbols() always returns
# the raw, unfiltered names regardless of whether they appear here.
_KNOWN_CORONA_CATEGORIES: dict[str, str] = {
    "corona": "renderer",
    "coronarenderer": "renderer",
    "coronacam": "cameras",
    "coronacameramod": "cameras",
    "coronaao": "maps",
    "coronabitmap": "maps",
    "coronabumpconverter": "maps",
    "coronacolor": "maps",
    "coronacolorcorrect": "maps",
    "coronacurvature": "maps",
    "coronadistance": "maps",
    "coronaedgemap": "maps",
    "coronafrontback": "maps",
    "coronamappingrandomizer": "maps",
    "coronamix": "maps",
    "coronamultimap": "maps",
    "coronanormal": "maps",
    "coronaroundedges": "maps",
    "coronatilemap": "maps",
    "coronatriplanar": "maps",
    "coronawire": "maps",
    "coronaraycswitch": "maps",
    "coronarayswitch": "maps",
    "coronaexr": "maps",
    "coronajpg": "maps",
    "coronapng": "maps",
    "coronafabricmtl": "materials",
    "coronahairmtl": "materials",
    "coronalayeredmtl": "materials",
    "coronalegacymtl": "materials",
    "coronalightmtl": "materials",
    "coronamtl": "materials",
    "coronaoutlinemtl": "materials",
    "coronaphysicalmtl": "materials",
    "coronaportalmtl": "materials",
    "coronarayswitchmtl": "materials",
    "coronascannedmtl": "materials",
    "coronaselectmtl": "materials",
    "coronashadowcatchermtl": "materials",
    "coronaskinmtl": "materials",
    "coronatoonmtl": "materials",
    "coronavolumemtl": "materials",
    "_coronaphysicalmtl": "materials",
    "coronalight": "lights",
    "coronasun": "lights",
    "coronasky": "lights",
    "coronamoon": "lights",
    "corona_light": "lights",
    "coronadisplacementmod": "geometry_modifiers",
    "coronahairmod": "geometry_modifiers",
    "coronafumefxmod": "geometry_modifiers",
    "coronapatternmod": "geometry_modifiers",
    "coronaslicermtl": "geometry_modifiers",
    "corona_ao": "render_elements",
    "corona_beauty": "render_elements",
    "corona_diffuse": "render_elements",
    "corona_diffusecolor": "render_elements",
    "corona_normalmap": "render_elements",
    "corona_reflectcolor": "render_elements",
    "corona_refractcolor": "render_elements",
    "corona_translucencycolor": "render_elements",
    "coronadata": "utilities",
    "coronamateriallibrary": "utilities",
    "coronapowertools": "utilities",
    "coronaselect": "utilities",
    "coronashadows": "utilities",
    "coronatonemapcontrol": "utilities",
    "coronauserproperty": "utilities",
    "corona_improved_picker": "utilities",
    "checkforpreviouscoronaversion": "utilities",
    "vraycoronascattermod": "scatter",
    "vraycoronascatterwrapper": "scatter",
    # Corona Doctor's own MAXScript/Python entry points happen to match
    # "*corona*" substring discovery — they are not Chaos Corona API.
    "launchcoronadoctor": "internal_tooling",
    "show_corona_doctor": "internal_tooling",
}

_KNOWN_CHAOS_CATEGORIES: dict[str, str] = {
    "chaosscatter": "scatter",
    "chaosscatteredgetrimming": "scatter",
    "chaosscattersurfacecolor": "scatter",
    "chaoscosmosassetimportbyid": "utilities",
}

_CATEGORY_KEYWORD_FALLBACK: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("scatter", ("scatter",)),
    ("renderer", ("renderer",)),
    ("lights", ("light", "sun", "sky", "moon", "portal")),
    ("cameras", ("cam",)),
    ("render_elements", ("beauty", "renderelement")),
    ("materials", ("mtl", "material")),
    ("maps", ("map", "bitmap", "color", "mix", "wire", "normal", "tile", "triplanar")),
    ("geometry_modifiers", ("mod", "displacement", "slicer")),
    ("utilities", ("data", "select", "picker", "tool", "property")),
)


@dataclass(frozen=True)
class CoronaDetectionResult:
    """Structured outcome of :meth:`CoronaAdapter.detect`.

    ``installed`` and ``active`` are separate facts: a scene can have
    Corona installed/registered without it being the active renderer,
    and (per the real-host confirmation above) the active-renderer class
    name is not the same string as the installed-renderer class name.
    """

    installed: bool | None
    active: bool | None
    renderer_class: str | None
    renderer_string: str | None
    version: str | None
    confidence: str  # "confirmed" | "probable" | "unknown"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - probes must never crash
        return default


def _hasattr_rt(rt, name: str) -> bool:
    try:
        return getattr(rt, name) is not None
    except Exception:  # noqa: BLE001 - undefined MAXScript globals raise
        return False


def classify_corona_symbol(name: str) -> str:
    """Best-effort category for a discovered "*corona*" runtime symbol.

    Falls back to keyword heuristics for names not in the known-mapping
    table (e.g. symbols added by a future Corona release); callers must
    still retain the raw name regardless of the returned category.
    """

    lowered = name.lower()
    known = _KNOWN_CORONA_CATEGORIES.get(lowered)
    if known is not None:
        return known
    for category, keywords in _CATEGORY_KEYWORD_FALLBACK:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "unknown"


def classify_chaos_symbol(name: str) -> str:
    """Best-effort category for a discovered "*chaos*" runtime symbol."""

    lowered = name.lower()
    known = _KNOWN_CHAOS_CATEGORIES.get(lowered)
    if known is not None:
        return known
    for category, keywords in _CATEGORY_KEYWORD_FALLBACK:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "unknown"


class CoronaAdapter:
    """Minimal, safe surface over Corona detection and introspection."""

    def detect(self) -> CoronaDetectionResult:
        """Multi-signal Corona detection. Never requires every signal at once.

        Signals used (each independently True/False/unknown):
          1. ``CoronaRenderer`` present in ``rt.renderers.classes``
             (installed/registered).
          2. Any of :data:`INSTALLATION_SIGNAL_SYMBOLS` resolves as a
             runtime global (installed).
          3. The active renderer's ``classOf()`` name is in
             :data:`ACTIVE_RENDERER_CLASS_NAMES` (active — and, by
             implication, installed).

        ``confidence`` is "confirmed" when the active-renderer signal
        agrees with at least one installation signal, or when two or
        more installation signals agree; "probable" when exactly one
        signal fired; "unknown" when nothing could be determined (e.g.
        outside 3ds Max, or every probe raised).
        """

        if pymxs is None:
            return CoronaDetectionResult(None, None, None, None, None, "unknown")

        rt = pymxs.runtime

        registered_names = _safe(lambda: [str(c) for c in rt.renderers.classes], None)
        class_registered = (
            any(name in INSTALLED_RENDERER_CLASS_NAMES for name in registered_names)
            if registered_names is not None
            else None
        )

        symbol_present = any(_hasattr_rt(rt, name) for name in INSTALLATION_SIGNAL_SYMBOLS)

        renderer_class: str | None = None
        renderer_string: str | None = None
        active: bool | None = None
        current = _safe(lambda: rt.renderers.current)
        if current is not None:
            renderer_class = _safe(lambda: str(rt.classOf(current)))
            renderer_string = _safe(lambda: str(current))
            active = renderer_class in ACTIVE_RENDERER_CLASS_NAMES if renderer_class else False
        else:
            active = False if registered_names is not None else None

        installed_signals = [s for s in (class_registered, symbol_present, active) if s is not None]
        installed = any(installed_signals) if installed_signals else None

        # A live, running Corona renderer instance (active=True) is proof
        # on its own — it cannot be a false positive the way a bare
        # symbol/class-registration check could. Otherwise fall back to
        # requiring agreement between independent installation signals.
        true_count = sum(1 for s in (class_registered, symbol_present, active) if s is True)
        if active is True or true_count >= 2:
            confidence = "confirmed"
        elif true_count == 1:
            confidence = "probable"
        else:
            confidence = "unknown"

        version = _safe(self._detect_version)

        return CoronaDetectionResult(
            installed=installed,
            active=active,
            renderer_class=renderer_class,
            renderer_string=renderer_string,
            version=version,
            confidence=confidence,
        )

    def _detect_version(self) -> str | None:
        """No documented pymxs-safe Corona version source is known.

        Do not guess a version from the project's minimum-supported
        Corona constant. If Chaos ever exposes a reliable runtime
        property for this, wire it in here — until then "unknown" is
        the honest answer.
        """

        return None

    # -- Backwards-compatible single-purpose accessors -------------------

    def is_installed(self) -> bool | None:
        return self.detect().installed

    def is_active_renderer(self) -> bool | None:
        return self.detect().active

    def get_renderer_class(self) -> str | None:
        """Registered (not necessarily active) Corona renderer class name."""

        if pymxs is None:
            return None
        try:
            rt = pymxs.runtime
            for renderer_class in rt.renderers.classes:
                name = str(renderer_class)
                if name in INSTALLED_RENDERER_CLASS_NAMES:
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
            if current is None or str(rt.classOf(current)) not in ACTIVE_RENDERER_CLASS_NAMES:
                return ()
            names = rt.getPropNames(current)
            return tuple(str(n) for n in names)
        except Exception:  # noqa: BLE001
            return ()

    # -- Development-only runtime symbol discovery ------------------------

    def discover_symbols(self, substring: str) -> tuple[str, ...]:
        """Read-only: every pymxs runtime global whose name contains ``substring``.

        Uses ``dir(rt)`` — this only lists names, it never instantiates,
        constructs, or otherwise touches the scene.
        """

        if pymxs is None:
            return ()
        try:
            names = dir(pymxs.runtime)
        except Exception:  # noqa: BLE001
            return ()
        lowered = substring.lower()
        return tuple(sorted({n for n in names if lowered in n.lower()}))
