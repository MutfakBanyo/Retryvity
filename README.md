# Corona Doctor

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

## Launching the development build

Corona Doctor's core (`corona_doctor.core`, `.compatibility`,
`.adapters`, `.scanners`, `.repair`, `.rules`, `.persistence`,
`.logging`, `.performance`) is importable in a plain Python 3.11
interpreter with no 3ds Max or Qt installed — this is what lets the unit
tests run outside 3ds Max.

**Outside 3ds Max** (unit tests only, no UI):

```bash
python3 -m pytest corona_doctor/tests
```

**Inside 3ds Max 2026.3+:**

1. Make this repository's root directory importable, e.g. by adding it to
   `sys.path` from a 3ds Max startup script, or by placing/symlinking the
   `corona_doctor` package where 3ds Max's bundled Python can find it.
2. Run the MAXScript bridge (`corona_doctor/maxscript/helpers.ms`) once
   to register the `CoronaDoctor_Launch` macroScript, or call directly
   from the Python listener:

   ```python
   from corona_doctor.bootstrap import show_corona_doctor
   show_corona_doctor()
   ```

3. To validate a build inside a real 3ds Max install, run:

   ```python
   from corona_doctor.host_validation import run_host_validation
   run_host_validation()
   ```

   See `docs/HOST_VALIDATION.md` for what this checks and what still
   requires manual verification.

## Documentation

- `docs/ARCHITECTURE.md` — layer boundaries, threading rules, capability system
- `docs/DEVELOPMENT.md` — hard compatibility rules and coding conventions
- `docs/HOST_VALIDATION.md` — what to verify inside a real 3ds Max + Corona install
