# Corona Doctor

Corona Doctor is a diagnostic, optimization and repair assistant for
**Autodesk 3ds Max 2026.2+** running **Chaos Corona 15+**.

## Development stage

This repository contains the architectural bootstrap (a dockable PySide6
panel, environment/capability detection, a design system) plus its first
production diagnostic milestone: **Scene Inventory + Texture Doctor v1**
— read-only scene/material/texture analysis with 6 diagnostic rules
(TXT-001..006). See `docs/TEXTURE_DOCTOR.md` for exactly what it detects
and its read-only guarantee, `docs/ARCHITECTURE.md` for what exists and
why, and `docs/DEVELOPMENT.md` for the roadmap. Material/renderer
diagnostics, repair actions, and other scan categories are still future
milestones.

## Supported environment

| Component | Requirement |
|---|---|
| OS | Windows 10/11 x64 |
| 3ds Max | 2026.2+ |
| Python | 3.11.x (the runtime bundled with 3ds Max) |
| Qt | 6.5.x (as bundled with 3ds Max) |
| UI toolkit | PySide6 |
| 3ds Max API | pymxs, qtmax |
| Renderer | Chaos Corona 15+ |

3ds Max 2025 and older, MaxPlus, WinForms/WPF, PySide2/Qt5, and MAXScript
rollout UIs are explicitly out of scope.

## Installing inside 3ds Max (drag & drop)

1. Get this repository onto the Windows machine that has 3ds Max
   installed (clone it, or download it as a folder) — do not move
   `install_corona_doctor.ms` out of the repo root; it must stay next to
   the `corona_doctor` folder.
2. Open 3ds Max, then drag `install_corona_doctor.ms` from Explorer and
   drop it onto the viewport.
3. The panel opens immediately. A "Corona Doctor" menu is also added to
   the main menu bar, and a small startup script is written to your user
   startup scripts folder so Corona Doctor loads automatically on every
   future 3ds Max launch — you don't need to drag the installer again.

Safe to re-run: dropping the installer again just re-confirms the setup,
it doesn't duplicate menus or path entries.

To uninstall the auto-load, delete
`CoronaDoctor_Startup.ms` from your 3ds Max user startup scripts folder
(3ds Max menu: Scripting → Show MAXScript Listener, run
`getDir #userStartupScripts` to find it).

## Launching the development build (manual / advanced)

Corona Doctor's core (`corona_doctor.core`, `.compatibility`,
`.adapters`, `.scanners`, `.repair`, `.rules`, `.persistence`,
`.logging`, `.performance`) is importable in a plain Python 3.11
interpreter with no 3ds Max or Qt installed — this is what lets the unit
tests run outside 3ds Max.

**Outside 3ds Max** (unit tests only, no UI):

```bash
python3 -m pytest corona_doctor/tests
```

**Inside 3ds Max 2026.2+, without the installer** (e.g. from the
MAXScript Listener or Python console), useful for quick one-off testing:

```python
import sys
sys.path.append(r"C:\path\to\this\repo")
from corona_doctor.bootstrap import show_corona_doctor
show_corona_doctor()
```

To validate a build inside a real 3ds Max install, run:

```python
from corona_doctor.host_validation import run_host_validation
run_host_validation()
```

See `docs/HOST_VALIDATION.md` for what this checks and what still
requires manual verification.

For a deeper, developer-only dump of everything Corona Doctor can
introspect about the running host (raw + normalized versions, every
discoverable Corona/Chaos runtime symbol, active-renderer properties),
run:

```python
from corona_doctor.devtools.runtime_probe import run_runtime_probe
run_runtime_probe()
```

This is strictly read-only — see `docs/HOST_VALIDATION.md` for details
and where the JSON report is written.

## Documentation

- `docs/ARCHITECTURE.md` — layer boundaries, threading rules, capability system
- `docs/DEVELOPMENT.md` — hard compatibility rules and coding conventions
- `docs/HOST_VALIDATION.md` — what to verify inside a real 3ds Max + Corona install
- `docs/TEXTURE_DOCTOR.md` — Scene Inventory + Texture Doctor v1: what it
  detects, its read-only guarantee, threshold logic, and known limitations
