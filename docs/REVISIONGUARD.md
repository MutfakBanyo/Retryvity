# RevisionGuard V0.1

RevisionGuard answers one question: **what changed in the live 3ds Max
scene since the last snapshot?**

V0.1 is the comparison-engine proof of concept. It is not the future
revision-merge product, and deliberately does not contain any of it.

## Workflow

1. Open the RevisionGuard panel.
2. **Create Snapshot** — scans eligible geometry and fingerprints it.
3. Modify the scene (move / rotate / scale / edit mesh / add / delete).
4. **Compare Scene** — re-scans and classifies every object.
5. **Select Changed** / **Isolate Changed** to act on the result.

## Categories

| Category | Meaning |
|---|---|
| `ADDED` | Eligible node exists now, was not in the snapshot |
| `REMOVED` | Node handle from the snapshot no longer resolves |
| `GEOMETRY_CHANGED` | Local-space mesh fingerprint differs |
| `TRANSFORM_CHANGED` | World transform differs beyond tolerance |
| `GEOMETRY_AND_TRANSFORM_CHANGED` | Both |
| `UNCHANGED` | Neither |

## Object identity

The **3ds Max node handle** is the identity key. That is the right scope
for V0.1: this milestone compares a scene against its own earlier state
within one session, not against an imported revision file. Cross-import
identity (source GUIDs, fuzzy/rename matching) is explicitly out of scope.

A renamed node keeps its handle, so it is *not* reported as
added+removed — it stays matched, and the result shows its current name.

## Eligibility

A node is scanned when `superClassOf node == GeometryClass` and its class
is not in `EXCLUDED_CLASS_NAMES` (`scene_access.py`). That excludes
cameras, lights, helpers, shapes and space warps by superclass, plus a
short deny-list of geometry-superclass classes that are not model
geometry (camera/light targets, bones, legacy particle systems).

Anything else that fails to evaluate is recorded as *skipped* with a
reason and the scan continues — one broken object never aborts a scan.

## Fingerprints

**Transform** — `node.transform` is decomposed into position, rotation
quaternion and scale. The quaternion is canonicalised into the `w >= 0`
hemisphere, because `q` and `-q` describe the same rotation and 3ds Max
may return either for an object that never moved.

**Geometry** — the node is evaluated with `snapshotAsMesh` (a temporary
copy; the user's object is never collapsed or modified, and the temporary
is freed in a `finally`). Vertices are converted to **local space** so a
moved object does not read as a mesh edit, then quantised and hashed with
`hashlib.sha256`. Python's built-in `hash()` is never used — it is salted
per process and is not a stable fingerprint.

Vertices arrive from `snapshotAsMesh` in world space on current 3ds Max.
Rather than trust that across versions, `_looks_world_space()` compares
the evaluated mesh's AABB against the node's world AABB (`node.min` /
`node.max`) and only applies the inverse transform when they coincide. At
an identity transform both readings agree and the conversion is a no-op.

The digest is only a fast-path equality check. When digests differ, a
**tolerant component-wise comparison** decides — raw floats are never
compared with `==`. Tolerances live in `core/constants.py`.

Counts alone are not sufficient and are not relied on: moving one vertex
of a cube leaves 8 verts / 12 faces and is still detected, because every
vertex position feeds the digest.

## Performance

Meshes up to `MAX_HASHED_VERTICES` (20,000) hash every vertex. Denser
meshes fall back to a deterministic strided sample of that many vertices —
same indices on both sides of a comparison, so the result stays
consistent.

pymxs is main-thread-only, so the scan runs on the UI thread and yields to
Qt every `UI_YIELD_INTERVAL` objects. The panel keeps repainting and shows
`Scanning n/total` during a scan.

## Snapshot storage

In memory only, owned by the panel. Closing the panel drops the snapshot —
acceptable for V0.1. `Snapshot.to_dict()` already emits JSON-safe
primitives, so persisting it later is a serialisation call rather than a
rewrite.

## Testing

Host-independent suite (no 3ds Max, no Qt needed for the core tests):

```bash
python3 -m pytest revision_guard/tests
```

`tests/fake_pymxs.py` models Matrix3 decomposition, matrix inversion and
`snapshotAsMesh` faithfully enough to exercise the world→local conversion,
which is the piece most likely to produce a false `GEOMETRY_CHANGED`.

Inside real 3ds Max:

```python
from revision_guard.devtools.smoke_test import run_smoke_test
run_smoke_test()
```

or from the "RevisionGuard" menu → *RevisionGuard Smoke Test*.

It builds its own `RG_Smoke_*` objects, scans **only** those, mutates
them, re-compares, and deletes everything in a `finally` — including when
a case fails. It refuses to run if `RG_Smoke_*` objects already exist, so
it can never delete something you made, and it runs with undo suppressed
so it does not flood your undo stack.

Eight cases: unchanged, moved, rotated, scaled, geometry edited, added,
removed, geometry+transform. Move/rotate/scale must all report
`TRANSFORM_CHANGED` — that is the case a naive world-space fingerprint
gets wrong.

## Known limitations

- Snapshots do not survive closing the panel.
- Identity is the node handle, so it does not survive a scene reload or a
  re-import. That is the V0.1 scope.
- Meshes above 20,000 vertices are sampled; a single-vertex edit on such a
  mesh can be missed if it falls between sampled indices. Counts and
  bounding box still catch larger edits.
- Materials, modifiers and UVs are not compared.
- Isolate Changed depends on 3ds Max's Isolate Selection; if unavailable
  on a build, the panel selects and says so instead of working around it.
