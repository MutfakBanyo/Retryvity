# Host Validation

Everything in this document requires a real **3ds Max 2026.2+** install,
ideally with **Chaos Corona 15+** licensed/active. None of it can be
verified in a plain Python environment — that is why it is not part of
the automated test suite.

Real host observed on 2026-08-25 (dev workstation): 3ds Max 2026.2
(`maxversion()` -> `#(28000, 68, 0, 28, 2, 0, 20659, 2026, ".2")`),
Python 3.11.12, Qt 6.5.3, Corona active (`classOf(rt.renderers.current)`
-> `Corona`, while `rt.renderers.classes` registers it as
`CoronaRenderer` — these are two separate, confirmed-different facts,
see `adapters/corona_adapter.py`).

## 1. Run the automated host validation script

From the 3ds Max Python listener (or `python.Execute` from MAXScript):

```python
from corona_doctor.host_validation import run_host_validation
run_host_validation()
```

Expected output shape:

```
Corona Doctor Host Validation
Version: 0.2.0

3ds Max:  2026.2  (raw: [28000, 68, 0, 28, 2, 0, 20659, 2026, '.2'])
Python:   3.11.x
Qt:       6.5.x
Corona:   Detected

Dock creation:      PASS
Environment scan:   PASS
Capability probe:      PASS
Corona installation:   PASS
Corona active:         PASS
Corona version:        UNKNOWN (unknown)
Corona confidence:     confirmed
Demo scan:          PASS
```

`Capability probe: PASS` means the probe *ran* successfully — it is not
a verdict on whether Corona itself was found. `Corona version: UNKNOWN`
is expected and correct (no safe runtime source for it exists yet) and
must not be read as a failure; only `Corona installation`/`Corona
active` reading `FAIL` (a hard `False`, not `UNKNOWN`) indicates a real
problem.

If any line reads `FAIL (...)`, the parenthetical contains the
exception; check `corona_doctor`'s log file (see
`logging/logger.py::default_log_path()`, typically
`%LOCALAPPDATA%\CoronaDoctor\corona_doctor.log` on Windows) for the full
traceback.

### 1b. Comprehensive runtime capability probe (developer tooling)

For a full, read-only dump — every discoverable `*corona*`/`*chaos*`
runtime symbol (classified best-effort), the active renderer's property
names, and both normalized/raw version strings — run:

```python
from corona_doctor.devtools.runtime_probe import run_runtime_probe
run_runtime_probe()
```

This never creates, deletes, or modifies scene state, materials,
selection, or renderer settings — it only uses `dir()`, `getPropNames()`,
`str()`, and `classOf()`. It prints a short human-readable summary to the
Listener and writes the full structured report to
`<default_log_path().parent>/runtime_probe.json` (same folder as
`corona_doctor.log`) for anything too long to read comfortably in the
Listener (the full symbol lists, property names, per-step timings, and
any errors encountered).

## 1c. Scene Inventory + Texture Doctor probe (production scanner)

```python
from corona_doctor.devtools.texture_probe import run_texture_probe
run_texture_probe()
```

Read-only — see docs/TEXTURE_DOCTOR.md for the full guarantee, what it
detects, and a real-host validation checklist. Writes
`%LOCALAPPDATA%\CoronaDoctor\texture_probe.json`.

## 2. Launch and inspect the panel manually

```python
from corona_doctor.bootstrap import show_corona_doctor
show_corona_doctor()
```

Check:

- [ ] The panel appears docked inside the 3ds Max main window (not as a
      detached window), and appears quickly (no visible delay/spinner).
- [ ] **Overview** shows "No scan has been performed yet." and a
      disabled-until-clicked `Scan Scene` button — no scene scan runs
      automatically on open.
- [ ] Clicking **Scan Scene** runs the real Scene Inventory + Texture
      Doctor scan (not the demo scanner), updates the health score arc,
      the Critical/Warnings/Optimization tiles, the Scene stat row
      (Objects/Materials/Textures/Missing/8K+), and populates
      **Diagnostics** with real TXT-00x findings (or none, on a clean
      scene).
- [ ] **Textures** shows the scanned reference count, populates the
      table, and search/filter/sort all work without re-scanning the
      scene (see docs/TEXTURE_DOCTOR.md).
- [ ] **Environment** shows the real detected 3ds Max version, Python
      version, Qt version, and Corona detection state (not "unknown"
      for any of these on a properly configured machine).
- [ ] Calling `show_corona_doctor()` again focuses the existing panel
      instead of creating a second dock widget.
- [ ] Closing the panel and calling `show_corona_doctor()` again creates
      a fresh panel cleanly (no error, no stale reference).

## 3. Docking / resizing behavior

- [ ] Drag the panel to float, then re-dock it to the left and right
      sides of the main window.
- [ ] Resize the 3ds Max viewport / workspace layout; the panel must not
      crash, freeze, or leave the layout in a broken state.
- [ ] Narrow the dock to roughly its minimum width (~280px) and confirm
      the Overview stat tiles stack into a single column (COMPACT layout
      state) and the nav sidebar collapses.
- [ ] Widen the dock past ~720 logical px and confirm the layout does
      not visually break (EXPANDED state — content may simply have more
      breathing room in this phase).

## 4. High-DPI

- [ ] Test at 100% and at least one scaled setting (125% or 150%) if
      your workstation supports switching without a reboot. Text and
      icons should remain crisp and layouts should not clip or overlap.

## 5. Corona-absent fallback

If feasible, test on a machine (or a temporarily renderer-switched
scene) without Corona set active:

- [ ] Environment view shows "Not detected" or "unknown" rather than
      crashing or showing a stale/incorrect value.
- [ ] The rest of the panel (Overview, Diagnostics, demo scan) still
      functions normally.

## What this does NOT cover

Production diagnostic accuracy (real texture/geometry/material
findings), repair execution, and MAXScript bridge coverage beyond the
single `launchCoronaDoctor` helper are out of scope until those
milestones ship — see `docs/DEVELOPMENT.md`, "Not yet implemented."
