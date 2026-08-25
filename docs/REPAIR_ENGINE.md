# Repair Engine + Torture Scene (v0.3)

Corona Doctor's first production Repair Engine, and the development-only
Torture Scene fixture generator used to validate it against ground truth
instead of a real (and usually too-clean) production scene.

## The pipeline

Every repair-capable Finding follows the same shape:

```
DETECT -> EXPLAIN -> LOCATE -> PREVIEW FIX -> FIX -> VERIFY
```

A Finding alone (DETECT + EXPLAIN) is not "mature" by this milestone's
standard — see `core/models.py::Finding` for the detect/explain fields
that already existed. This milestone adds LOCATE (`repair_controller.py`
"Show Objects"), PREVIEW (`repair/planner.py` building a `RepairPlan`,
shown before any mutation), FIX (`repair/transaction.py::apply_plan`),
and VERIFY (`repair/verification.py`).

## Architecture

```
repair/
    models.py        - RepairOperation/RepairPlan/RepairManifest/RepairState (pure dataclasses)
    planner.py        - build_make_portable_plan / find_relink_candidates / build_relink_plan (pure, no I/O)
    transaction.py    - apply_plan (the only place that mutates - via injected callables)
    verification.py   - verify_repair (re-reads scene/filesystem after apply)
    revert.py         - build_revert_plan (reads current state, detects conflicts)
    manifest.py       - JSON persistence for RepairManifest (%APPDATA%\CoronaDoctor\corona_doctor_repairs\)

adapters/repair_adapter.py  - the ONLY place that actually calls pymxs to mutate a
                               map property (undo-grouped) or read one back
ui/repair_controller.py     - wires the pure repair/ engine to real os/shutil I/O
                               and repair_adapter.py; the UI layer's only touchpoint
ui/views/textures_view.py   - builds the preview/confirm dialogs and result reports
```

`repair/*` has zero pymxs and zero filesystem import — every scene/disk
query and mutation is a callable the caller injects (`copy_file`,
`create_directory`, `relink`, `read_current_value`, `exists_checker`).
This is what makes copy-once/relink-many, partial-failure handling,
collision handling, and verification fully unit-testable without 3ds Max
or a real filesystem — see `tests/test_repair_planner.py`,
`test_repair_transaction.py`, `test_repair_verification.py`,
`test_repair_revert.py`. `ui/repair_controller.py` is the one place that
wires real `os`/`shutil` calls in; it has no Qt import itself, so it is
also unit-tested directly (real tmp_path files, a fake adapter — see
`test_repair_controller.py`) without needing PySide6.

**Repair adapter boundary**: a scanner/rule must never import
`repair_adapter.py` — only `ui/repair_controller.py`'s injected `relink`
callable ever calls it, exactly mirroring `adapters/scene_adapter.py`'s
read-only discipline in reverse (see that module's docstring).

**No `RepairRegistry` wiring**: `repair/base.py`'s existing
`RepairAction`/`RepairRegistry` skeleton models "one repair action per
`rule_id`". Make Project Portable and Missing Texture Relink are bulk,
cross-cutting workflows operating on many references/Finding at once,
not a single rule's one-shot fix — forcing them into that per-rule shape
would be a worse fit than just calling `ui/repair_controller.py`
directly from the view. `RepairRegistry` stays unused/empty for this
milestone; a future milestone can revisit if a genuinely single-Finding
repair shows up.

## States

`RepairState`: `PLANNED` (a `RepairPlan` exists, nothing applied yet) ->
`APPLIED` (every ready operation succeeded) / `PARTIAL` (some succeeded,
some failed) / `FAILED` (nothing succeeded) -> `VERIFIED` (re-read
confirms every applied entry actually stuck) -> `REVERTED`.
`ValidationState` is per-operation: `READY` or `BLOCKED` (missing
source, inaccessible file, or — for a revert — the scene no longer
matches the manifest).

## No mutation during proposal/preview

Building a `RepairPlan` (`repair/planner.py`) never calls `copy_file`,
`create_directory`, or `relink` — it only reads (`exists_checker`) to
classify sources as present/missing/inaccessible. Nothing mutates until
`repair/transaction.py::apply_plan` runs, and that only ever runs after
an explicit `QMessageBox.question(...) == Yes` in
`ui/views/textures_view.py` — every preview dialog says "No changes have
been made yet." verbatim.

## Make Project Portable

`repair/planner.py::build_make_portable_plan`:

- Groups references by unique source path — **copy once, relink many**
  (a file referenced by 7 map nodes gets exactly one `COPY_FILE`
  operation and 7 `RELINK_TEXTURE` operations).
- **Never touches a missing source** — `path_info.exists is False`
  sources are recorded in `plan.missing_sources` and produce no
  operation at all (no fabricated file, no relink to nothing).
- **Collision handling**: two *different* source files that would land
  on the same destination filename are never silently overwritten — the
  second one gets a deterministic (same input -> same output, so
  re-planning is stable) collision-safe rename:
  `name__<8-hex-char-sha1-of-source-path>.ext`, recorded in
  `plan.conflicts`.
- **Already-portable assets** are skipped (no copy, no relink) if the
  source is already under the destination directory.
- **Inaccessible sources** (`exists_checker` returns `None` — e.g. a
  permission error) are `BLOCKED` for review, not silently dropped and
  not treated as missing.

## Missing Texture Relink

`repair/planner.py::find_relink_candidates` — deterministic scoring only
(exact filename match required to even be a candidate, then extension
match, then file-size match if both known) — **never fuzzy/AI matching**.
`classify_candidates` maps the ranked list to the exact policy this
milestone specifies:

- **zero candidates** -> stays unresolved, nothing offered.
- **one candidate with the top score** -> offered for user-reviewed
  relink (still requires an explicit Yes — "single" does not mean
  "automatic").
- **multiple candidates tied at the top score** -> shown as a choice
  list (`QInputDialog.getItem` in the UI); never auto-picked.

## Verify after fix

`repair/verification.py::verify_repair` re-reads (never trusts the
apply-time return value alone): for every manifest entry, the scene
property must read back the new path AND the copied file must actually
exist at its destination. Both must hold for every entry for the state
to become `VERIFIED`; otherwise `PARTIAL`/`FAILED`. `ui/main_window.py`
also reconnects `TexturesView.repair_completed` to a real Texture Doctor
rescan — a repair's own verification checks the specific paths it
touched, but only a fresh scan re-evaluates whether e.g. TXT-006's count
actually dropped.

## Revert never deletes copied files

`repair/revert.py::build_revert_plan` only ever emits `UPDATE_PATH`
operations restoring the old scene path — it never emits a delete, and a
copied file in the project asset directory is left in place even after
revert (Corona Doctor cannot prove nothing else now depends on it — see
Part K's absolute safety list). If the scene no longer matches the
manifest (something else changed that property since the repair), that
specific entry is marked `BLOCKED` for manual review instead of being
force-reverted.

## Undo grouping (3ds Max 2026.2)

`adapters/repair_adapter.py` groups each mutation in
`with pymxs.undo(True):` — the current, documented Python-side undo API
(confirmed live against Autodesk's pymxs documentation for this
milestone, not assumed from memory — same "don't guess a removed API"
discipline as the 3ds Max 2025+ menu system repair). The legacy
MAXScript `theHold.Begin()`/`theHold.Accept()` idiom is not used.

## Identity: `getAnimByHandle`

`ExternalTextureReference.map_handle` (new field this milestone) carries
the map's AnimHandle from the scan — but only when it is a genuine,
positive handle; a per-scan fallback identity (see
`adapters/scene_adapter.py::SceneAdapter._identity`, negative) is never
carried into `map_handle`, since that fallback is only meaningful within
the scan that produced it and would be unsafe to hand to
`rt.getAnimByHandle()` later. `RepairAdapter.relink_map_property`/
`read_map_property` re-resolve the live object via
`rt.getAnimByHandle(map_handle)` — the documented inverse of
`rt.getHandleByAnim` this codebase already relies on for read-only
traversal.

## Locate/traceability

`ui/repair_controller.py::select_objects` -> `MaxAdapter.select_nodes_by_name`
— "Show Objects" selects by name (the only identity `ExternalTextureReference.object_names`
currently carries; not a stronger node-handle-based selection, since
object identity was never tracked by handle in this architecture). Only
ever runs on an explicit button click — never a side effect of opening a
finding or hovering a row.

## Torture Scene

`devtools/torture_scene.py::create_torture_scene()` — development-only,
never auto-runs. Refuses to run against a non-empty scene unless
`confirm_destructive=True` is passed explicitly, and even then only ever
*adds* fixture objects — nothing existing is ever deleted or reset.
Capability-probes every Corona-specific class
(`getattr(rt, "CoronaBitmap", None)` etc., matching
`adapters/corona_adapter.py`'s existing probing style) before
constructing it, falling back to the generic 3ds Max
Bitmaptexture/Standardmaterial classes, or skipping that one fixture
(recorded `skipped=True` in the manifest with a reason) rather than
aborting the whole generator. Bitmap-to-material attachment uses only the
generic `getNumSubTexmaps`/`setSubTexmap` interface — never a guessed
Corona-specific property name (`adapters/scene_adapter.py`'s own
discipline, reused here).

### Torture scene assets

`devtools/torture_assets.py::write_stub_png` writes a genuinely valid,
decodable single-color PNG at whatever declared width/height is asked
for. A solid color compresses to a few hundred KB even at 16384x16384
(DEFLATE crushes uniform data), so the 8K/16K oversized fixtures never
require allocating real multi-megabyte pixel data or shipping a large
binary in git — every asset is generated fresh into a dedicated,
clearly-labeled temp directory (`%TEMP%\CoronaDoctor\torture_assets`),
never an arbitrary user folder.

### Fixtures (CDT-TEX-001..009)

| ID | What | Expected rule |
|---|---|---|
| CDT-TEX-001 | Missing texture | TXT-001 |
| CDT-TEX-002 | Local absolute path | TXT-006 |
| CDT-TEX-003 | Reused texture (3 map nodes, 1 file) | TXT-002 |
| CDT-TEX-004 | 8192px stub image | TXT-004 |
| CDT-TEX-005 | 16384px stub image | TXT-004 (strong tier) |
| CDT-TEX-006 | Non-ASCII (Turkish) path | discovery only, no rule |
| CDT-TEX-007 | Path with spaces | discovery only, no rule |
| CDT-TEX-008 | Nested Multi/Sub -> material -> texture | traversal only, no rule |
| CDT-TEX-009 | One texture, 3 objects | traceability only, no rule |

`devtools/torture_manifest.py` persists the ground truth (fixture id,
category, expected rule/detection/fixability/repair behavior, every
created object/material/map name and asset path) to
`%APPDATA%\CoronaDoctor\corona_doctor_torture\manifest.json`.

## Torture Validator

`devtools/torture_validator.py::validate_torture_scene()` runs the REAL
`TextureDoctorScanner` (or an injected fake scanner, for the pure unit
tests in `tests/test_torture_validator.py`) and checks each fixture
against the *actual* scan result — never infers a PASS from a fixture's
name or its manifest status alone. Prints the exact
`CORONA DOCTOR TORTURE VALIDATION` report format this milestone
specifies.

## Real-host dev commands

Every dev entry point is one line — pasting a multi-line command into
the 3ds Max Python Listener has proven less reliable than a single line
(see docs/TEXTURE_DOCTOR.md):

```python
from corona_doctor.devtools.torture_scene import create_torture_scene; create_torture_scene()
```
```python
from corona_doctor.devtools.torture_validator import validate_torture_scene; validate_torture_scene()
```
```python
from corona_doctor.devtools.texture_probe import run_texture_probe; run_texture_probe()
```
```python
from corona_doctor.repair.manifest import load_last_manifest; print(load_last_manifest())
```

## Safety guarantees (Part K)

Every item in Part K's absolute-requirements list maps to a concrete
mechanism in this codebase, not just a promise:

- **Never reset/delete a production scene automatically** —
  `torture_scene.py::scene_appears_empty()` + the `confirm_destructive`
  guard; the generator only ever adds objects, never deletes.
- **Never overwrite different destination files silently** — the
  collision-safe rename in `build_make_portable_plan` (see above).
- **Never guess ambiguous missing-texture replacements** —
  `classify_candidates` forces "multiple" into a user choice, never an
  auto-pick.
- **Never mutate during scan/preview** — `repair/planner.py` has no
  mutation callable at all; `repair/transaction.py::apply_plan` is the
  only mutating entry point, called only after an explicit Yes.
- **Never claim a partial repair is complete** — `RepairState.PARTIAL`/
  `FAILED` are distinct from `APPLIED`/`VERIFIED`, and
  `_report_repair_result` always shows the actual state.
- **Never hide repair failures** — `RepairResult.errors` and
  `RepairManifest.failed_op_ids` are always surfaced in the result
  dialog.
- **Never rewrite an unsupported map property** —
  `RepairAdapter.relink_map_property` checks `rt.isProperty` before
  writing and returns `False` (recorded as a failed operation) if the
  property doesn't exist.
- **Never batch-repair without explicit approval** — every apply path
  requires a `QMessageBox.question(...) == Yes` first.
