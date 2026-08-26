# Retryvity — 3ds Max plugins

This repository hosts 3ds Max Python plugins. Each one lives in its own
top-level package at the repo root.

| Plugin | What it does | Stage |
|---|---|---|
| [`corona_doctor/`](#corona-doctor) | Diagnostic / optimization / repair assistant for Chaos Corona | Bootstrap |
| [`revision_guard/`](#revisionguard) | Scene revision comparison engine | V0.1 |

---

## RevisionGuard

RevisionGuard snapshots a 3ds Max scene, then tells you exactly what
changed: which objects were added, removed, moved, or had their mesh
edited.

**Install:** drag `install_revision_guard.ms` onto the 3ds Max viewport
(keep it next to the `revision_guard` folder). The panel opens right away
and a "RevisionGuard" menu is added to the menu bar.

**Use:** *Create Snapshot* → modify the scene → *Compare Scene* →
*Select Changed* / *Isolate Changed*.

**Validate inside 3ds Max:**

```python
from revision_guard.devtools.smoke_test import run_smoke_test
run_smoke_test()
```

See [`docs/REVISIONGUARD.md`](docs/REVISIONGUARD.md) for the fingerprint
strategy, identity model, scope boundary and known limitations.

---

## Corona Doctor

Corona Doctor is a diagnostic, optimization and repair assistant for
**Autodesk 3ds Max 2026.3+** running **Chaos Corona 15+**.

## Development stage

This repository currently contains the **architectural bootstrap
phase**: a working plugin shell with a dockable PySide6 panel,
environment/capability detection, a design system, and the
scanner/repair/rule boundaries that future diagnostic milestones will
build on. It intentionally does **not** yet include production diagnostic
rules (texture, material, geometry, lighting checks, etc.) — see
`docs/ARCHITECTURE.md` for what exists and why, and
`docs/DEVELOPMENT.md` for the roadmap.

## Supported environment

| Component | Requirement |
|---|---|
| OS | Windows 10/11 x64 |
| 3ds Max | 2026.3+ |
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
python3 -m pytest corona_doctor/tests revision_guard/tests
```

**Inside 3ds Max 2026.3+, without the installer** (e.g. from the
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

## Documentation

- `docs/REVISIONGUARD.md` — RevisionGuard V0.1 engine, identity model and limits
- `docs/ARCHITECTURE.md` — layer boundaries, threading rules, capability system
- `docs/DEVELOPMENT.md` — hard compatibility rules and coding conventions
- `docs/HOST_VALIDATION.md` — what to verify inside a real 3ds Max + Corona install
