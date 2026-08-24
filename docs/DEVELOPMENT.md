# Development

## Hard compatibility rules

- Target **3ds Max 2026.3+** only. Never assume compatibility with 2025
  or older — 3ds Max version APIs, Python version, and Qt version all
  shifted around the 2025→2026 line.
- **Python 3.11** — the interpreter bundled with 3ds Max. Do not use
  syntax or stdlib features newer than 3.11.
- **PySide6 / Qt 6.5.x** only. Never `import PySide2` or assume Qt5
  stylesheet/API behavior.
- **pymxs + qtmax** are the only supported host bridges. `MaxPlus`,
  WinForms, and WPF are not used anywhere in this codebase.
- **MAXScript** is a deliberately small bridge
  (`corona_doctor/maxscript/helpers.ms`), not the application core. Every
  helper in that file documents why pymxs alone was insufficient, which
  Max versions it targets, what it returns, and whether it mutates scene
  state.
- Do not invent undocumented Corona properties. If a Corona API's
  presence or behavior is uncertain, probe for it
  (`adapters/corona_adapter.py::get_available_properties`) and expose the
  result through `compatibility/capabilities.py` rather than assuming it.
- No pip packages beyond the Python standard library + the versions of
  PySide6/pymxs/qtmax bundled with 3ds Max. Do not `pip install` anything
  into the 3ds Max Python environment.

## Import safety

`corona_doctor/core`, `compatibility`, `persistence`, `logging`, and
`performance` must stay importable without 3ds Max or Qt installed. If
you add a new module to one of those packages, do not import PySide6,
pymxs, or qtmax at module scope in it — push host-bound imports into
`adapters/` or `ui/`, and use local imports (inside a function) where a
module needs to *optionally* touch a host API.

Verify with:

```bash
python3 -c "import corona_doctor.core.models, corona_doctor.compatibility.capabilities"
```

## Testing

```bash
python3 -m pytest corona_doctor/tests
```

These are unit tests for Max-independent components only (version
parsing, capability model, diagnostic models, rule engine, settings,
findings domain logic). There are currently no automated 3ds Max
integration tests — that boundary is intentional; see
`docs/HOST_VALIDATION.md` for what must be checked by hand inside a real
3ds Max + Corona install.

## Design tokens

Never hard-code a color, spacing value, radius, or font size directly in
a widget file. Add or reuse a token in `ui/design/colors.py`,
`ui/design/metrics.py`, or `ui/design/typography.py`, and reference it
from there. The dark theme QSS (`ui/themes/dark.qss`) is a *template*,
not a source of truth — values are substituted in from the same token
modules by `ui/themes/__init__.py::load_dark_theme()`.

## UI performance rules

- Never create one `QWidget` per diagnostic finding. Use
  `ui/models/findings_model.py` (`QAbstractListModel`) with
  `ui/delegates/finding_delegate.py` (`QStyledItemDelegate` + `QPainter`).
- No `QGraphicsBlurEffect`, no continuous animated gradients, no
  `QGraphicsDropShadowEffect` on repeated list rows. The "glass" look is
  faked with tonal surfaces, thin borders, and spacing — see
  `ui/design/colors.py`.
- No `setFixedSize()` on the application/panel window. Use layouts and
  size policies so the panel supports 100–200% DPI scaling and arbitrary
  dock widths (`ui/responsive/breakpoint_manager.py`).
- Icons are loaded once and cached (`ui/icons/icon_registry.py`) — never
  re-read from disk in a paint event.

## Not yet implemented (by design)

The following are explicitly out of scope for this bootstrap phase and
must not be faked with placeholder UI:

- Production scanners (geometry, materials, textures, lighting, cameras,
  render settings, Chaos Scatter, Corona Proxy, memory estimation)
- Any rule in `rules/definitions/` (the directory exists; it is empty)
- One-click repair execution (`repair/` is interfaces only)
- Navigation sections beyond Overview / Diagnostics / Environment
  (Scene, Renderer, Materials, Textures, Geometry, Lighting, Performance,
  Report are declared in `core/constants.py` but not wired to a view)

Do not add a button or panel for any of the above that doesn't do
anything — leave the section out of the navigation entirely until it has
real content.
