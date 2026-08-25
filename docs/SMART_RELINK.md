# Smart Asset Recovery (Smart Relink) — v0.3

Upgrades Missing Texture Relink from "browse to the exact file yourself"
into: select one or more library roots once, recursively search, get
ranked candidates for every missing texture, review, approve, relink
through the existing Repair Engine, verify. Extends
docs/REPAIR_ENGINE.md — read that first for the Repair Engine's own
states/safety guarantees, which this milestone reuses unchanged.

## Architecture

```
smart_relink/                  (pure — no Qt, no pymxs, no filesystem side effects beyond injected calls)
    models.py                  - ConfidenceBand, KnownAssetMetadata, CandidateMetadata,
                                  ScoreEvidence, Candidate, MissingAsset, IndexedFile, SearchIndex
    index.py                   - build_search_index() - recursive walk, injected walk_fn/size_fn
    metadata.py                - read_candidate_metadata() - lazy width/height/size/mtime
    scoring.py                 - score_candidate() / rank_candidates() / is_bulk_acceptable()
    session.py                 - SearchSession, missing_assets_from_references()
    providers.py                - OnlineAssetSearchProvider, build_privacy_safe_query()

ui/
    smart_relink_worker.py     - SmartRelinkSearchWorker(QThread) - index+score off the main thread
    smart_relink_dialog.py     - SmartRelinkDialog - batch review UI
    repair_controller.py       - + plan_batch_relink()/apply_batch_relink() (Repair Engine hookup)

devtools/
    torture_scene.py           - + create_smart_relink_fixtures() (CDT-SMART-001..005)
    torture_validator.py       - + validate_smart_relink() (search-quality, separate from detection)
    smart_relink_probe.py      - one-line real-host dev command
```

`smart_relink/` depends on `core/` (for `ExternalTextureReference`) and
is depended on by `repair/planner.py::build_batch_relink_plan` only in
the sense that the UI passes plain `ExternalTextureReference` iterables
to it — `repair/` itself has no import of `smart_relink/` (see
`build_batch_relink_plan`'s docstring: the dependency runs one
direction only).

## Search index

`smart_relink/index.py::build_search_index(roots, walk_fn=..., size_fn=...)`
walks every root recursively. **One bad root never aborts the whole
search** — a `walk_fn` exception for one root is caught and recorded in
`SearchIndex.root_errors`; a `size_fn` exception for one file leaves
just that file's `size_bytes` as `None`. Real callers pass `os.walk`;
tests pass a fake tree (see `tests/test_smart_relink_index.py`) covering
permission-denied directories, unavailable roots, UNC paths, Unicode/
space/long paths — none of these need special-casing, they're all just
strings to `ntpath.join`.

Built once per session (`ui/smart_relink_worker.py`'s background
thread), reused for every missing asset in that session — never
re-walked per asset. Not persisted across sessions this milestone (see
"Later: persistent indexing" below).

### Two lookup tiers

- `SearchIndex.candidates_for_filename(name)` — exact (case-insensitive)
  filename matches only.
- `SearchIndex.candidates_for_asset(name)` — exact matches, **plus**
  every same-extension file whose stem is at least 50% similar
  (`difflib.SequenceMatcher`, string-only, no metadata read) — this is
  what makes a genuinely **renamed** file findable at all (`.
  candidates_for_filename` alone would never surface it, no matter how
  strong its other evidence). `scoring.py`/the worker/the probe all use
  `candidates_for_asset`; `candidates_for_filename` remains available for
  callers that specifically want exact-only (e.g. the older
  single-file `repair/planner.py::find_relink_candidates` path).

Width/height/size/mtime are read **lazily**, only for candidates that
passed this cheap string pre-filter — never for the whole library (see
`smart_relink/metadata.py`).

## Scoring model

`smart_relink/scoring.py::score_candidate()` — deterministic, no
randomness, no ML, same inputs always produce the same output. Weight
table:

| Criterion | Weight | Counted toward score/max_score? |
|---|---|---|
| Exact filename match | 100 | **No** — see below |
| Filename (stem) similarity | 30 | Always |
| Extension match | 10 | Always |
| Resolution match | 20 | Only if the *original's* width/height is known |
| Aspect ratio match | 10 | Only if the *original's* width/height is known |
| File size similarity | 15 | Only if the *original's* file size is known |
| Folder name similarity | 10 | Always |
| Creation/modification date | 0 | **Never** — see "Metadata evidence" |

**Exact filename match is deliberately excluded from the points total.**
It instead forces `ConfidenceBand.EXACT` directly
(`_classify_band`), overriding every other criterion. Counting it as
ordinary points too would make the 95-point ceiling (everything else
combined) mathematically include 100 unreachable points for any
non-exact candidate, capping every renamed-file match at roughly 49% no
matter how strong its other evidence — which would make HIGH/MEDIUM
bands unreachable for exactly the "smart match when file was renamed"
case this milestone exists to solve. (This was caught by
`tests/test_smart_relink_scoring.py::test_confidence_bands_are_ordered_high_medium_low`
during development — a real regression, not a hypothetical.)

### Confidence bands and bulk accept

`ConfidenceBand`: `EXACT` (forced by filename) / `HIGH` (>=75% of
*applicable* max score) / `MEDIUM` (>=45%) / `LOW` (below) / `NONE`
(zero candidates). **Only `EXACT` is eligible for "Accept All Exact
Matches"** (`scoring.py::is_bulk_acceptable`) — there is deliberately no
"Accept All HIGH" action; every HIGH/MEDIUM/LOW candidate always
requires individual review, per the milestone brief's explicit
instruction not to auto-relink anything short of unambiguous identity.

### Metadata evidence — what's actually implemented

**No EXIF/XMP byte-level parser is implemented this milestone.**
`CandidateMetadata.modified_at` is the candidate file's own filesystem
modification time (`os.path.getmtime`) — a cheap, always-available,
non-destructive piece of evidence, but explicitly **not** scored: the
*original* missing file's own timestamp was lost the moment it went
missing, so there is nothing to compare a candidate's mtime against.
This is recorded as its own evidence line
("creation/modification date — original timestamp not available")
rather than silently omitted, so the user sees why. Width/height/size
work the same way in the other direction: they're only ever compared
when `KnownAssetMetadata` actually holds a value, and `KnownAssetMetadata`
is only ever populated from a source that legitimately knew the
original (see below) — never guessed from the filename or invented.

### Known vs. candidate metadata — the honesty boundary

`smart_relink/models.py::KnownAssetMetadata` — what Corona Doctor can
*legitimately* claim to know about the ORIGINAL missing file. Every
field defaults to `None`. For a real missing texture, this is almost
always fully empty: the file is gone, and this codebase does not
maintain a persistent width/height/size history across scans (a real
future enhancement — see "Later: known-metadata history" below). The
**one** legitimate source in this milestone is the Torture Scene: since
`torture_scene.py::create_smart_relink_fixtures()` wrote the recovery
file itself, it genuinely knows its dimensions, and records them in
`FixtureRecord.known_width`/`known_height` — `torture_validator.py`
feeds that into `KnownAssetMetadata` for its CDT-SMART-002 (renamed
recovery) check. A production scan never has this - `missing_assets_from_references()`'s `known_metadata_lookup` parameter
defaults every asset to fully-unknown metadata unless a caller
explicitly supplies otherwise, and nothing in this codebase does yet.

## One missing file, many map nodes

`smart_relink/session.py::missing_assets_from_references()` groups every
`ExternalTextureReference` whose file is missing by its raw path — one
physical missing file referenced by several map nodes becomes ONE
`MissingAsset` with every `map_ref_ids` entry. One approved candidate
then repairs every one of those references through a single
`repair/planner.py::build_batch_relink_plan()` call (see
`tests/test_repair_planner.py::test_batch_relink_plan_repairs_every_ref_sharing_one_missing_file`).

## Search performance

`ui/smart_relink_worker.py::SmartRelinkSearchWorker` is a `QThread`:
index build + candidate pre-filter + lazy metadata read + scoring all
happen off the main/Qt thread. `progress(done, total)` fires per
completed asset; `cancel()` sets a flag `build_search_index` checks
between directories/roots, so cancellation is prompt without needing to
kill the thread. **The worker never touches pymxs or a Qt widget** — it
imports nothing from `adapters/` or `ui/views/`, so "no scene mutation
from worker threads" and "pymxs stays on the main thread" hold by
construction, not just convention.

## Batch recovery / review UI

`ui/smart_relink_dialog.py::SmartRelinkDialog` — one root selection
covers every missing asset. Table: Missing Asset / Best Candidate /
Confidence. Selecting a row shows every ranked candidate with its full
evidence breakdown and a best-effort thumbnail (`QPixmap`, session-local
cache keyed by path — see "Preview" below). Per-asset actions: Accept /
Reject / Skip; bulk: "Accept All Exact Matches" only (see above).
"Build Repair Plan…" gathers every accepted `(asset, path)` pair,
converts each `MissingAsset` back to its underlying
`ExternalTextureReference`s, calls
`repair_controller.plan_batch_relink()` (side-effect free — see
docs/REPAIR_ENGINE.md), shows a "no changes have been made yet" preview,
and only calls `apply_batch_relink()` after an explicit Yes — then
`verify()`s the result and reports PLANNED/APPLIED/VERIFIED/PARTIAL/
FAILED plainly, exactly like every other Repair Engine action.
`repair_completed` is wired to `TexturesView.repair_completed` (already
connected to a real rescan in `ui/main_window.py`), matching Make
Project Portable's existing pattern.

### Preview

`SmartRelinkDialog._set_thumbnail` loads a `QPixmap` for the selected
candidate and scales it down to a small on-screen size, cached per
session by path so re-selecting the same candidate never reloads it.
If the format can't be decoded (`QPixmap.isNull()`), the panel falls
back to "no preview (metadata only)" — the evidence text panel above it
already shows dimensions/size from `CandidateMetadata` regardless, so
nothing is lost, it just isn't visual. This is a simple on-demand load
(one image at a time, only for whatever the user has selected), not a
prefetch of every candidate's thumbnail — safe for 8K/16K sources since
only the file the user is actively looking at gets decoded.

## Online search — architecture + first implementation

`smart_relink/providers.py::OnlineAssetSearchProvider` — the Protocol
the core application depends on; `UnsplashProvider`/`PexelsProvider` are
credential-gated stubs (`is_available()` checks an env var, e.g.
`CORONA_DOCTOR_UNSPLASH_API_KEY`) that correctly report unavailable
until configured, and raise (never silently return an empty list) if
`search()` is called anyway. **No real HTTP call is implemented this
milestone** — there is no credential available to develop or test
against, and inventing one is explicitly out of scope. The UI's "Search
Online" action lists every known provider and its availability, and
explains that online replacement requires configuration — this is the
deliverable for "architecture + first implementation", not a working
live search.

### Privacy-safe query generation

`build_privacy_safe_query()` builds search terms ONLY from the missing
file's filename stem and its immediate parent folder name (plus,
optionally, material/map name) — never the full local path, drive
letter, username, or other folder segments. See
`tests/test_smart_relink_providers.py` for the regression guard proving
a realistic `C:\Users\alice\Desktop\SecretClientProject\...` path never
leaks a username or project name into the query.

### Local recovery vs. online replacement

Never conflated. An online result (`OnlineCandidate`) carries
`provider`/`source_url`/`license_info` and is never described as
"recovered" — it is a possible **replacement**, explicitly distinct from
local recovery of the actual original file, and it is never
automatically downloaded or substituted (the milestone brief's Part 17
requirement — enforced here simply by the fact that no download code
exists yet; when a provider is implemented, the same "explicit approval
required" flow Make Project Portable/batch relink already use applies).

## Torture scene extension

`devtools/torture_scene.py::create_smart_relink_fixtures()` adds
CDT-SMART-001..005 to the existing CDT-TEX-* fixtures, sharing one
`recovery_library` directory tree (`TortureManifest.smart_relink_recovery_root`):

| ID | Tests | Recovery library content |
|---|---|---|
| CDT-SMART-001 | Exact match, deeply nested | exact filename 3 folders deep |
| CDT-SMART-002 | Renamed file, known metadata | differently-named file, same 512x512 dims (`FixtureRecord.known_width/height`) |
| CDT-SMART-003 | Ambiguous (multiple candidates) | two similarly-named files in different folders, tied score |
| CDT-SMART-004 | No match | recovery library has nothing similar (filename deliberately does NOT share the `cdt_smart_0xx` prefix its siblings use — see the fixture's own comment for why that prefix alone caused a false-positive collision during development) |
| CDT-SMART-005 | Unicode candidate path | exact filename under a Turkish (`çalışma`/`İstanbul`) folder |

`devtools/torture_validator.py::validate_smart_relink()` runs the REAL
`smart_relink` engine (index + scoring) against the real recovery
library and the real scan result — never infers a PASS from a fixture
id. Printed separately from `validate_torture_scene()`'s detection
score, per the milestone brief: search quality and detection quality are
different questions.

```
SMART RELINK VALIDATION

Exact recovery        PASS
Renamed recovery       PASS
Ambiguous recovery     PASS
No-match handling      PASS
Unicode recovery       PASS
```

## Real-host dev commands (one line each)

```python
from corona_doctor.devtools.torture_scene import create_torture_scene; create_torture_scene()
```
```python
from corona_doctor.devtools.smart_relink_probe import run_smart_relink_probe; run_smart_relink_probe()
```
```python
from corona_doctor.devtools.torture_validator import validate_smart_relink; validate_smart_relink()
```

`run_smart_relink_probe()` performs **no scene mutation** — it prints
candidate rankings only (see `tests/test_smart_relink_probe.py::test_probe_no_mutation_never_touches_the_scene`,
which asserts the module has no `repair_adapter`/`relink_map_property`
reference at all).

## Later (not this milestone)

- **Persistent indexing**: `SearchIndex` is rebuilt every session. A
  future milestone could cache it (keyed by root + mtime) for a very
  large, rarely-changing asset library.
- **Known-metadata history**: if a future milestone starts recording
  width/height/size the moment a texture is first scanned (before it
  can go missing), `missing_assets_from_references()`'s
  `known_metadata_lookup` parameter is already the seam to feed that in
  — no signature change needed.
- **Real online providers**: once a user configures credentials,
  `UnsplashProvider`/`PexelsProvider.search()` need a real HTTP
  implementation behind the existing Protocol — the UI/query-builder/
  attribution-display side is already done.
