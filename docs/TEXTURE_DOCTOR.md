# Texture Doctor v1

Scene Inventory + Texture Doctor is Corona Doctor's first production
diagnostic milestone. This document describes exactly what it detects,
what it deliberately does not (yet), how it stays read-only, and how to
validate it on a real host.

## Read-only guarantee

`TextureDoctorScanner` and everything it calls
(`adapters/scene_adapter.py`, `adapters/path_utils.py`,
`adapters/image_metadata.py`) never assigns a scene/material/map
property, never changes selection, never creates or deletes anything,
and never writes to a texture file. It reads: `rt.objects`, node/material/
map properties, `os.stat`, and the first few KB of an image file's
header. That's the entire write surface — none.

## What v1 detects

- **Scene Inventory**: node counts by category (geometry / light /
  camera / helper / shape / group), hidden/frozen counts,
  `nodes_with_material_count` (how many nodes have *a* material assigned
  — not a material count) vs. `unique_material_count` (deduplicated
  distinct materials actually discovered by traversal), map counts,
  Corona light/camera counts, texture extension breakdown.
- **TXT-001 Missing Texture** (critical) — an external texture reference
  points to a file that doesn't exist.
- **TXT-002 Duplicate Texture Reference** (optimization) — the same file
  is referenced by more than one map node. Not automatically bad —
  shared textures are normal — just surfaced for review.
- **TXT-003 Potential Duplicate Asset Paths** (optimization, confidence
  0.6) — same filename *and* file size at *different* paths. Explicitly
  a "potential" match: matching filename+size does not prove identical
  content. Never claims certainty without a hash.
- **TXT-004 Oversized Texture** (optimization at 8192px+, warning at
  16384px+ on either dimension) — dimension-based only, see "Known
  limitations".
- **TXT-005 Very Large Texture File** (optimization, 100MB+ on disk by
  default) — disk size, explicitly not decoded RAM usage.
- **TXT-006 Local Texture Path** (info, confidence 0.8) — a texture path
  looks workstation-specific (under a user profile, Desktop, Downloads,
  Temp) and may not be portable to another workstation or render node.

## What v1 does not detect / does not do

- No automatic fix of any kind — every Finding's `repairability` is
  `MANUAL` or `NONE`. No relink, resize, convert, collect-assets, or
  delete-duplicate action exists yet.
- No selection-changing UI. "Affected objects" is a count (and object
  names where traceable), never a "Select in scene" button — even that
  would mutate Max selection state, which this milestone does not do.
- No screen-space analysis (projected pixel footprint, camera distance,
  UV density). TXT-004 is purely dimension-based and says so in its own
  wording.
- No material/renderer diagnostics (CoronaPhysicalMtl parameter
  analysis, IOR/roughness checks, the 308 discovered Corona renderer
  properties, Chaos Scatter/Corona Proxy diagnostics beyond counting).
  These are later milestones.
- No default hashing. Every file's identity signal is normalized path,
  filename, size, and (if readable) resolution — never a content hash by
  default, since hashing every texture in a large scene is expensive.
  Hash-based duplicate *confirmation* is a possible future on-demand,
  worker-thread-only feature (see "Threading").
- No automatic memory/RAM estimate. Disk size (TXT-005) is explicitly
  documented as *not* the same as decoded RAM usage.

## How paths are found

Sub-material/sub-map discovery is generic, not Corona-specific: it uses
the standard MAXScript `getNumSubMtls`/`getSubMtl` and
`getNumSubTexmaps`/`getSubTexmap` interface implemented by virtually
every material/map plugin (Multi/Sub, Blend, CoronaLayeredMtl,
CoronaPhysicalMtl, legacy StandardMtl, ...) — this is what lets Texture
Doctor work in mixed/legacy scenes, not just Corona-only ones.

Once a `TextureMap`-superclass object is found, its file path is read via
a short, ordered candidate-property probe (`rt.isProperty` checked before
every access, so an unsupported map degrades to "unsupported" instead of
raising):

1. `.filename` — confirmed standard on `Bitmaptexture`; expected on
   `CoronaBitmap` per Chaos's own documented Bitmaptexture-compatibility
   layer, **pending real-host confirmation** (see "Host validation"
   below — do not trust this until the probe confirms it).
2. `.HDRIMapName` — used by some environment/dome map classes.

A map class with neither property resolves to `unsupported`/`unknown`
and is recorded in `unknown_map_classes` rather than silently dropped.

## Identity: why Animatable handles, not `id()`

Materials and maps can be shared/instanced (the same sub-material used
under two different top-level materials, the same bitmap in two slots).
Python's `id()` only identifies one specific pymxs wrapper *instance* —
pymxs may hand back a freshly-constructed wrapper each time the same
underlying MAXScript object is fetched through a different path, so
`id()` cannot be trusted as a stable identity key across a scan.
`MaxAdapter.get_animatable_handle()` uses `rt.getHandleByAnim()` instead
— the MAXScript-level Animatable handle, stable for the object's session
lifetime — for both cycle detection and dedup during traversal. See that
method's docstring in `adapters/max_adapter.py`.

**Fallback identity.** A real 3ds Max 2026.2 host was observed returning
`None` from `getHandleByAnim()` for some material objects despite
Autodesk documenting AnimHandles as valid for every Animatable — this
silently dropped every material from traversal (`SceneAdapter` used to
`continue` past a `None` handle when building the root-material set).
`SceneAdapter._identity()` now never drops an object for this reason: if
the AnimHandle is unavailable it assigns a per-scan fallback identity
keyed on Python `id(obj)` (negative, so it can never collide with a real
handle). The fallback is only guaranteed stable for the life of the
current scan — it is never persisted across scans/sessions, and it only
fully dedups an object reachable via the *same* Python wrapper instance
(not two independently-fetched wrappers of the same underlying object).
`devtools/texture_probe.py`'s diagnostics report how many materials/maps
used the fallback, so a real-host run can tell whether this path is being
hit.

## Node/material classification: why not a guessed string compare

`SceneAdapter` used to classify scene nodes and material-graph objects by
comparing `str(rt.superClassOf(obj))` against a hardcoded literal
(`"Light"`, `"Camera"`, `"Material"`, `"TextureMap"`, ...). On a real host
this failed for Corona light/camera nodes specifically — `classOf()`
still matched `"CoronaLight"`/`"CoronaCam"` fine, but the generic
`light_count`/`camera_count` came back 0 even though `corona_light_count`/
`corona_camera_count` were correct — while it happened to still work for
plain geometry. `_classify_by_equality()` (in `scene_adapter.py`) now
layers three signals, most reliable first, and for scene nodes a fourth,
even-more-authoritative one is checked before any of them:

1. **Host collection membership** (`rt.lights`, `rt.cameras`,
   `rt.geometry`, `rt.helpers`, `rt.shapes`) — the categorized collections
   3ds Max itself maintains; checked light/camera first since a render
   plugin's light/camera nodes have been observed sharing
   geometry-class icon plumbing on some hosts.
2. **Live Class-object equality** (`rt.superClassOf(obj) == rt.Light`),
   not a string compare — robust to whatever `str()` happens to produce.
3. **Normalized string compare**, only as a last resort.

A `Target`/`TargetObject` node (the crosshair helper a targeted light or
camera points at) is special-cased to `"helper"` before any of the above
— historical Max behavior places it under `GeometryClass`, which would
otherwise inflate `geometry_count` with non-renderable helper nodes.

The same `_classify_by_equality()` function (with a different attribute
map) also replaces the old `superclass == "Material"` /
`superclass == "TextureMap"` string checks used while walking the
material/map graph.

## Threshold logic

All numeric thresholds live in one place —
`core/texture_models.py::TextureThresholds` — never scattered inline:

| Field | Default |
|---|---|
| `oversized_warning_px` | 8192 |
| `oversized_strong_warning_px` | 16384 |
| `large_file_warning_bytes` | 100 MB |
| `large_file_strong_bytes` | 250 MB (reserved for a future finer-grained tier) |
| `large_file_extreme_bytes` | 500 MB (reserved) |
| `local_path_markers` | `\users\`, `\desktop\`, `\downloads\`, `\temp\`, `\appdata\` |

`TextureDoctorScanner(thresholds=...)` and `rules.loader.load_rules(...)`
both accept an override.

## How paths are normalized

`adapters/path_utils.py::build_path_info` never rewrites the raw path a
map reports — `PathInfo.raw_path` is always verbatim. It classifies the
path's *shape* (`PathType.LOCAL` / `NETWORK_UNC` / `RELATIVE` / `MISSING`
/ `UNKNOWN`) separately from whether the file *exists*
(`PathInfo.exists`). A drive-letter path is **not** automatically
`LOCAL`: `classify_path` probes `GetDriveTypeW` (stdlib `ctypes`, no new
dependency) and only reports `LOCAL` for a confirmed fixed/removable
drive, `NETWORK_UNC` for a confirmed mapped network drive, and `UNKNOWN`
when the platform API is unavailable — never guesses. Relative paths are
never resolved against the wrong base directory; `exists` stays `None`
(unknown) for them rather than risking a false answer (see "Known
limitations").

## Threading

All pymxs access happens on the main thread, in a chunked generator
(`TextureDoctorScanner.scan()`) driven by
`ui/scan_controller.py::run_scan_async` via `QTimer.singleShot(0, ...)` —
this is what keeps a 50k-node scene from freezing the host UI. The
filesystem/image-header stage operates on plain Python strings (already
detached from pymxs) but v1 still runs it on the main thread between
batches rather than on a worker thread — see docs/ARCHITECTURE.md,
"Threading rule".

## Performance

Two techniques keep this from becoming quadratic on a production scene:

- **Handle-based dedup during traversal** — a shared sub-material/map is
  visited (and its file-path/size/dimension work done) exactly once,
  regardless of how many parent materials/nodes reference it.
- **`FilesystemMetadataCache`** (`adapters/path_utils.py`) and an
  in-scan image-dimension cache, both keyed by normalized path — a
  texture referenced by 50 different map nodes gets `os.stat`'d and
  header-read exactly once, not 50 times.

Per-stage timings are recorded via the existing `performance/profiler.py`
and logged (not printed) at scan completion; the devtools probe
(`devtools/texture_probe.py`) surfaces them in its JSON report's
`timings_ms`.

## Known limitations

- **Multi-parent traceability**: when the same map instance is nested
  under more than one root material, only the first-visited root
  material's owning node(s) are recorded as `object_names`/
  `material_name` — this keeps traversal linear in the number of unique
  graph nodes rather than the number of (root material × shared node)
  pairs. If this proves too coarse in practice, a later milestone can
  build a full multi-parent reverse index.
- **Relative paths**: `exists` is always `None` (unknown) for a relative
  path rather than resolved against a possibly-wrong base directory.
  Wiring in 3ds Max's actual project/scene path for correct resolution is
  a follow-up.
- **Filename-property probe list is short and unverified against a real
  CoronaBitmap instance** until the host probe below runs. If the real
  property name differs, `devtools/texture_probe.py`'s
  `unknown_map_classes` output will show `CoronaBitmap` there, and the
  candidate list in `adapters/scene_adapter.py::_FILENAME_CANDIDATE_PROPERTIES`
  needs a new entry.
- **No screen-space awareness** for TXT-004 (see above) — a 4K texture on
  a background prop and a 4K texture filling the frame are flagged
  identically in v1.

## No silent zeroes

`scanners/texture_doctor_scanner.py::_check_invariants()` runs after every
scan and flags results that contradict each other — logged as a warning
(never raised, never shown as a UI error) and surfaced in
`TextureScanFacts.compatibility_warnings`:

- `nodes_with_material_count > 0` and `unique_material_count == 0`
- `corona_light_count > light_count`
- `corona_camera_count > camera_count`

Each of these was directly observed in the real-host bug this section
documents. A clean scan reports an empty `compatibility_warnings` tuple.

## Host validation procedure

Unit-tested and import-tested (see below) but **not yet run against a
real 3ds Max scene** — that requires the real host. Run this from the
3ds Max Python Listener:

```python
from corona_doctor.devtools.texture_probe import run_texture_probe
run_texture_probe()
```

This scans the current scene, prints a Scene Inventory + Texture Doctor
summary, and writes a full JSON report to
`%LOCALAPPDATA%\CoronaDoctor\texture_probe.json` (developer JSON only —
local paths, never uploaded, no network transfer, no telemetry).

After running it on a real production scene, specifically check:

- [ ] `Corona` under "Corona runtime symbols" resolved a `CoronaBitmap`
      file path via `.filename` (not left in `unknown_map_classes`)
- [ ] Node/material/map counts look plausible for the scene you know
- [ ] At least one known-missing texture (if any) shows up under TXT-001
- [ ] Scan duration is acceptable for your scene's size (see
      `timings_ms` in the JSON report)
- [ ] The panel's Overview/Textures views populate correctly after
      clicking "Scan Scene"
