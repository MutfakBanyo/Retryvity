# Architecture

Corona Doctor is built as a set of layers with one-directional
dependencies. Higher layers depend on lower ones; lower layers never
import from higher ones.

```
ui/            (PySide6, qtmax)
   |
app/           (composition: wires services + UI together)
   |
scanners/      (produce Finding objects; no widgets)
repair/        (interfaces only in this phase; no scene mutation)
rules/         (rule definitions — TXT-00x Texture Doctor rules; see docs/TEXTURE_DOCTOR.md)
   |
compatibility/ (capability registry, version parsing, feature flags)
adapters/      (the ONLY place allowed to import pymxs/qtmax/Corona)
   |
core/          (domain models, event bus, rule engine, diagnostic engine)
```

`core/`, `compatibility/`, `persistence/`, `logging/` and `performance/`
have **no Qt or pymxs dependency** and must remain importable in a plain
Python 3.11 interpreter — this is what lets `corona_doctor/tests/` run
outside 3ds Max.

## UI boundary

The UI layer (`ui/`) never contains scene-analysis logic. Views
(`ui/views/*`) are dumb: they render whatever domain object
(`Finding`, `ScanSummary`, `EnvironmentReport`) they are handed and emit
Qt signals for user actions (e.g. `OverviewView.scan_requested`). They do
not call scanners or adapters directly — that happens in
`ui/main_window.py` via `ui/scan_controller.py`, which drives
`DiagnosticEngine.iter_run()`.

Findings are rendered with Qt Model/View
(`ui/models/findings_model.py` + `ui/delegates/finding_delegate.py`) —
never one `QWidget` per finding — per the UI performance rules in the
project brief. Rule IDs are deliberately not shown in the primary list;
they belong in a future technical-details pane.

## Scanner boundary

A scanner (`scanners/base.py::BaseScanner`) returns `Finding` objects
(`core/models.py`) from a generator, never widgets, and never touches
`self` state a widget could read directly. `DemoScanner`
(`scanners/demo_scanner.py`) is a deterministic, clearly-labeled stand-in
for real scene analysis — every demo `Finding.details` string says so
explicitly, so it can never be mistaken for real Corona/scene diagnostic
output. It remains in the codebase for dev/testing but the UI's "Scan
Scene" button no longer wires to it (see below).

`TextureDoctorScanner` (`scanners/texture_doctor_scanner.py`) is the
first **production** scanner — Scene Inventory + Texture Doctor v1, read
only. It follows a strict "scanner collects facts, rules interpret them"
split: `adapters/scene_adapter.py` walks the real scene into detached
`SceneInventory`/`ExternalTextureReference` facts
(`core/texture_models.py`), then `rules/definitions/texture_rules.py`
(loaded via `rules/loader.py::load_rules()`) turns those facts into
`Finding`s through the existing `core/rules.py::RuleEngine` — no
diagnostic logic is hardcoded inside the scanner itself. See
docs/TEXTURE_DOCTOR.md for what it detects, what it deliberately does
not, and its read-only guarantee. Future production scanners (geometry,
lighting, renderer tuning, ...) will implement the same `BaseScanner`
contract and the same facts/rules split.

## Adapter layer

`adapters/max_adapter.py` and `adapters/corona_adapter.py` are the only
modules allowed to `import pymxs` / `import qtmax`. Both follow:

```python
try:
    import pymxs
except ImportError:
    pymxs = None
```

and every public method returns a safe default (`None`, `False`, `()`)
rather than raising when the host API is unavailable or a probe fails.
`adapters/environment_adapter.py` aggregates both into a structured
`EnvironmentReport` — the single source environment data flows through.

## Capability system

Nothing above the adapter layer should assume a Corona property exists.
`compatibility/capabilities.py::CapabilityRegistry` is built once from an
`EnvironmentReport` and exposes `supports(key) -> bool | None`. `None`
means "could not be determined" and callers must treat it as "do not
assume this exists," not as `False`. Future rules will call
`capabilities.supports(...)` instead of hardcoding Corona property
assumptions, and degrade with a "rule skipped: capability unavailable"
finding rather than crashing.

## Repair boundary

`repair/base.py::RepairAction` defines the interface every future repair
action implements: `can_apply`, `apply`, `undo`. **No repair action
executes in this bootstrap phase** — `repair/registry.py::RepairRegistry`
exists but starts empty. This is a deliberate design invariant: a
scanner must never be able to reach a repair action directly (there is no
import path from `scanners/` to `repair/`), and no repair action may ship
without undo support.

## Event system

`core/events.py::EventBus` is a minimal synchronous pub/sub bus with no
Qt dependency, so `core/diagnostics.py::DiagnosticEngine` can publish
`ScanStarted` / `ScanProgress` / `FindingAdded` / `ScanFinished` /
`ScanFailed` / `EnvironmentUpdated` events without importing PySide6. The
UI subscribes to this bus (`MainPanel._on_event`) rather than the
diagnostic engine calling into widgets directly.

## Threading rule (critical)

**pymxs scene access is main-thread-only.** No adapter method, scanner,
or rule may be invoked from a worker thread (`QThread`,
`concurrent.futures`, etc.) if it touches `pymxs.runtime`. Long scans are
instead structured as generators (`BaseScanner.scan()`) that yield
between batches; `ui/scan_controller.py::run_scan_async` drives that
generator one step per `QTimer.singleShot(0, ...)` callback, which keeps
the Qt event loop responsive without ever leaving the main thread.

Worker threads are reserved for work that does **not** touch 3ds Max
scene state: file hashing, image metadata reads, JSON/report processing,
and (in future milestones) network requests. `TextureDoctorScanner`'s
filesystem/image-header stage (`adapters/path_utils.py`,
`adapters/image_metadata.py`) is exactly this kind of work — it operates
on plain Python strings detached from pymxs — but v1 still runs it
synchronously on the main thread between chunked yields, correctness
first. Moving it to a worker thread is a reasonable follow-up once real
production scenes show it's the bottleneck (see docs/TEXTURE_DOCTOR.md,
"Known limitations").

## Chunked / incremental scanning

`DiagnosticEngine.iter_run()` is a generator that publishes a batch's
events and then yields, handing control back to whatever drove it.
`DemoScanner` simulates four stages (environment, geometry, materials,
textures) to exercise this path end to end. `TextureDoctorScanner` is the
first scanner to do this against a real scene: it yields per batch of
~2000 scene nodes, ~200 material/map graph nodes, and ~200
filesystem/metadata lookups, so a 50k-node production scene never blocks
the Qt event loop for one long stretch. It also supports cooperative
cancellation (`TextureDoctorScanner.cancel()`, checked between batches) —
safe at any point since the scan never mutates the scene.

## Error UX

Adapters and rules never raise into the UI layer uncaught — failures are
logged (`logging/logger.py`) and surfaced as a friendly status message
(e.g. `EnvironmentView` shows "Partial" when `EnvironmentReport.errors`
is non-empty) rather than a raw traceback. Full tracebacks only ever go
to the log file, never directly into a widget.

## Typography

`ui/design/typography.py::Typography` is the single source of truth for
every font size/weight in the UI — a semantic token (`BODY`,
`SECONDARY`, `CAPTION`, `SECTION_TITLE`, `TITLE`, `DISPLAY`,
`BODY_EMPHASIS`, `BUTTON`, `TABLE`, `BADGE`), never a raw pixel literal
scattered through QSS or a widget/delegate. `ui/themes/dark.qss` is a
*template* substituted by `ui/themes/__init__.py::load_dark_theme()` —
edit the Python token, never a size in the `.qss` file directly. Painted
delegates (`ui/delegates/finding_delegate.py`) and manually-built
`QFont`s (`ui/components/health_score.py`) read the same tokens via
`.size`/`.weight` rather than hardcoding a `setPixelSize`/`setPointSize`
number.

The v0.2 scale floors — body >= 13px, secondary >= 12px, caption >= 11px,
section titles 15-17px, major titles 18-22px — exist because real-host
testing showed the v0.1 scale (9-12px) was uncomfortably small at normal
3ds Max viewing distance. `corona_doctor/tests/test_typography_scale.py`
guards these floors without needing PySide6 installed (pure dataclass
module, no Qt import) — a regression there should fail loudly, not
silently ship smaller text again.

Spacing/radius (`ui/design/metrics.py`) and breakpoints
(`ui/responsive/breakpoint_manager.py`) are expressed in Qt logical
pixels, which Qt scales automatically for the active DPI — widget code
must never manually multiply a dimension by a DPI factor.

## Glass/depth language

A few major *static* surfaces (`QWidget#SurfaceRaised` in `dark.qss` —
the Scene Health card, the About screen's author card) use a two-stop
`qlineargradient` plus a slightly lighter border to suggest a raised/
glass-like surface. This is a static paint, not a runtime effect — no
blur, no translucency stacking, no per-frame recomputation — so it costs
nothing beyond an ordinary flat fill. Ordinary tiles/cards
(`QWidget#Surface`) stay flat; reserve the raised gradient for surfaces
that are genuinely a level up in the visual hierarchy, not everywhere.

## Startup performance

`app/application.py::launch()` profiles `bootstrap.total` (services +
UI shell construction) via `performance/profiler.py` and logs it on every
launch — watch this number, don't let it regress. A real-host measurement
recorded ~23.7ms for the full shell (five eagerly-constructed views,
nav, and the dark theme QSS load). Additions to the shell (the About
screen, the brand-mark SVG render) follow the same pattern already used
for the four other views and the nav's SVG icon rendering — a handful of
label/layout widgets and one more cached SVG-to-QPixmap render — not a
new class of cost. Anything genuinely expensive (a real scan) never runs
during `launch()`; it only runs after the user clicks "Scan Scene".
