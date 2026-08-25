"""Development-only, real-host Torture Scene generator.

Builds a small, controlled 3ds Max scene containing KNOWN texture
problems (CDT-TEX-001..009) so Texture Doctor and the Repair Engine can
be validated against ground truth instead of "eyeballing" a real
production scene — see docs/REPAIR_ENGINE.md, "Torture scene" and
``torture_validator.py``, which scores an actual scan against the
manifest this module writes.

NEVER runs automatically — must be explicitly invoked. NEVER resets or
deletes an existing scene: :func:`create_torture_scene` refuses to run
against a non-empty scene unless the caller explicitly passes
``confirm_destructive=True`` (and even then, it only ADDS fixture
objects — it never deletes anything). Capability-probes every
Corona-specific class before constructing it (``getattr(rt,
"CoronaBitmap", None)`` etc., matching ``adapters/corona_adapter.py``'s
existing probing discipline) and falls back to generic 3ds Max
bitmap/material classes, or skips that one fixture (recorded in the
manifest as ``skipped``) rather than aborting the whole generator.

Bitmap/material attachment uses only the generic, stable MAXScript
Material/Texmap interface (``getNumSubTexmaps``/``setSubTexmap``,
``node.material = ...``) — the exact same interface
``adapters/scene_adapter.py`` already relies on for read-only traversal
— never a guessed Corona-specific property name (see
docs/TEXTURE_DOCTOR.md, "How paths are found" for why guessing property
names is the one thing this codebase refuses to do).

Run from the 3ds Max Python Listener (one line, matching every other dev
entry point in this codebase — see docs/REPAIR_ENGINE.md, "Real-host dev
commands")::

    from corona_doctor.devtools.torture_scene import create_torture_scene; create_torture_scene()
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from corona_doctor.devtools.torture_assets import default_torture_asset_dir, write_stub_png
from corona_doctor.devtools.torture_manifest import FixtureRecord, TortureManifest, save_torture_manifest
from corona_doctor.logging.logger import get_logger

try:
    import pymxs  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    pymxs = None

_logger = get_logger("torture_scene")


class TortureSceneAbortedError(RuntimeError):
    """Raised (never swallowed) when create_torture_scene() refuses to run."""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def scene_appears_empty() -> bool:
    """Best-effort "is this scene safe to add fixtures to" check. Never
    raises — a probe failure is treated as "not empty" (the conservative,
    safe answer) rather than silently proceeding."""

    if pymxs is None:
        return False
    try:
        return int(pymxs.runtime.objects.count) == 0
    except Exception:  # noqa: BLE001
        return False


def _try_construct(rt, class_name: str) -> Any | None:
    """Capability-probed constructor: returns ``None`` (never raises) if
    ``class_name`` doesn't exist on this host or fails to construct."""

    cls = getattr(rt, class_name, None)
    if cls is None:
        return None
    try:
        return cls()
    except Exception:  # noqa: BLE001
        return None


def _make_bitmap(rt, path: str):
    """CoronaBitmap if constructible, else the generic Bitmaptexture -
    see module docstring for why this never guesses a property name."""

    bitmap = _try_construct(rt, "CoronaBitmap")
    if bitmap is None:
        bitmap = _try_construct(rt, "Bitmaptexture")
    if bitmap is not None:
        try:
            if rt.isProperty(bitmap, "filename"):
                bitmap.filename = path
        except Exception:  # noqa: BLE001
            return None
    return bitmap


def _make_material(rt):
    mtl = _try_construct(rt, "CoronaPhysicalMtl")
    if mtl is None:
        mtl = _try_construct(rt, "Standardmaterial")
    return mtl


def _attach_bitmap(rt, mtl, bitmap) -> bool:
    """Attach ``bitmap`` into ``mtl``'s first available sub-texmap slot
    via the generic Material/Texmap interface — never a guessed
    Corona-specific property name."""

    if mtl is None or bitmap is None:
        return False
    try:
        count = int(rt.getNumSubTexmaps(mtl))
        if count < 1:
            return False
        rt.setSubTexmap(mtl, 1, bitmap)
        return True
    except Exception:  # noqa: BLE001
        return False


def _make_box(rt, name: str):
    try:
        box = rt.Box(name=name)
        return box
    except Exception:  # noqa: BLE001
        return None


# -- individual fixtures ------------------------------------------------------


def _build_missing_texture(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-001"
    node_name = "CDT_TEX_001_Box"
    mtl_name = "CDT_TEX_001_Mtl"
    missing_path = str(asset_dir / "cdt_tex_001_MISSING_intentionally.png")  # deliberately never written

    box = _make_box(rt, node_name)
    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, missing_path)
    if mtl is not None and hasattr(mtl, "name"):
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)
    if box is not None and mtl is not None:
        box.material = mtl

    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="A supported file-backed map pointing to a deliberately nonexistent image.",
        expected_rule_id="TXT-001",
        expected_detection="Texture Doctor reports 1 missing texture for this reference.",
        expected_fixability="manual",
        expected_repair_behavior="Find & Relink (Missing Texture Relink workflow).",
        created_object_names=(node_name,) if box else (),
        created_material_names=(mtl_name,) if mtl else (),
        created_map_names=("CDT_TEX_001_Map",) if bitmap else (),
        created_asset_paths=(missing_path,),
        skipped=not (box and mtl and attached),
        skip_reason=None if (box and mtl and attached) else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_local_absolute_path(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-002"
    node_name = "CDT_TEX_002_Box"
    mtl_name = "CDT_TEX_002_Mtl"
    image_path = asset_dir / "cdt_tex_002_local.png"
    write_stub_png(image_path, 512, 512)

    box = _make_box(rt, node_name)
    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, str(image_path))
    if mtl is not None:
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)
    if box is not None and mtl is not None:
        box.material = mtl

    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="An existing texture under a workstation-specific local path (this machine's temp directory).",
        expected_rule_id="TXT-006",
        expected_detection="Texture Doctor flags this as a local/portability-risk path.",
        expected_fixability="manual",
        expected_repair_behavior="Make Project Portable.",
        created_object_names=(node_name,) if box else (),
        created_material_names=(mtl_name,) if mtl else (),
        created_map_names=("CDT_TEX_002_Map",) if bitmap else (),
        created_asset_paths=(str(image_path),),
        skipped=not (box and mtl and attached),
        skip_reason=None if (box and mtl and attached) else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_reused_texture(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-003"
    image_path = asset_dir / "cdt_tex_003_shared.png"
    write_stub_png(image_path, 512, 512)

    node_names = []
    mtl_names = []
    map_names = []
    ok = True
    for i in range(1, 4):
        box = _make_box(rt, f"CDT_TEX_003_Box{i}")
        mtl = _make_material(rt)
        bitmap = _make_bitmap(rt, str(image_path))
        if mtl is not None:
            mtl.name = f"CDT_TEX_003_Mtl{i}"
        attached = _attach_bitmap(rt, mtl, bitmap)
        if box is not None and mtl is not None:
            box.material = mtl
        ok = ok and bool(box and mtl and attached)
        if box:
            node_names.append(box.name)
        if mtl:
            mtl_names.append(mtl.name)
        if bitmap:
            map_names.append(f"CDT_TEX_003_Map{i}")

    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="Three separate map nodes referencing the same image file.",
        expected_rule_id="TXT-002",
        expected_detection='Texture Doctor reports a "Texture Reused By Multiple Map Nodes" group of 3 (never framed as an error).',
        expected_fixability="manual",
        expected_repair_behavior="Review only — not auto-consolidated in this milestone.",
        created_object_names=tuple(node_names),
        created_material_names=tuple(mtl_names),
        created_map_names=tuple(map_names),
        created_asset_paths=(str(image_path),),
        skipped=not ok,
        skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_oversized(rt, asset_dir: Path, fixture_id: str, dimension: int, filename: str, expected_rule_note: str) -> FixtureRecord:
    node_name = f"{fixture_id.replace('-', '_')}_Box"
    mtl_name = f"{fixture_id.replace('-', '_')}_Mtl"
    image_path = asset_dir / filename
    write_stub_png(image_path, dimension, dimension)

    box = _make_box(rt, node_name)
    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, str(image_path))
    if mtl is not None:
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)
    if box is not None and mtl is not None:
        box.material = mtl

    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description=f"A lightweight (solid-color, compressed) test image whose header declares {dimension}x{dimension}.",
        expected_rule_id="TXT-004",
        expected_detection=expected_rule_note,
        expected_fixability="manual",
        expected_repair_behavior="Review — resolution may be legitimate; no automatic downscale.",
        created_object_names=(node_name,) if box else (),
        created_material_names=(mtl_name,) if mtl else (),
        created_map_names=(f"{fixture_id.replace('-', '_')}_Map",) if bitmap else (),
        created_asset_paths=(str(image_path),),
        skipped=not (box and mtl and attached),
        skip_reason=None if (box and mtl and attached) else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_non_ascii_path(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-006"
    node_name = "CDT_TEX_006_Box"
    mtl_name = "CDT_TEX_006_Mtl"
    subdir = asset_dir / "çalışma" / "İstanbul_şömine"
    image_path = subdir / "doku.png"
    write_stub_png(image_path, 256, 256)

    box = _make_box(rt, node_name)
    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, str(image_path))
    if mtl is not None:
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)
    if box is not None and mtl is not None:
        box.material = mtl

    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="A texture path containing non-ASCII (Turkish) characters in both folder and file name.",
        expected_rule_id=None,
        expected_detection="Texture is discovered and its filename/path decoded correctly (no mojibake, no crash).",
        expected_fixability="n/a",
        expected_repair_behavior="n/a — this fixture validates discovery correctness, not a Finding.",
        created_object_names=(node_name,) if box else (),
        created_material_names=(mtl_name,) if mtl else (),
        created_map_names=("CDT_TEX_006_Map",) if bitmap else (),
        created_asset_paths=(str(image_path),),
        skipped=not (box and mtl and attached),
        skip_reason=None if (box and mtl and attached) else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_path_with_spaces(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-007"
    node_name = "CDT_TEX_007_Box"
    mtl_name = "CDT_TEX_007_Mtl"
    image_path = asset_dir / "my textures" / "wood plank 01.png"
    write_stub_png(image_path, 256, 256)

    box = _make_box(rt, node_name)
    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, str(image_path))
    if mtl is not None:
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)
    if box is not None and mtl is not None:
        box.material = mtl

    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="A texture path containing spaces in both folder and file name.",
        expected_rule_id=None,
        expected_detection="Texture is discovered normally — no truncation at the space, no crash.",
        expected_fixability="n/a",
        expected_repair_behavior="n/a — this fixture validates discovery correctness, not a Finding.",
        created_object_names=(node_name,) if box else (),
        created_material_names=(mtl_name,) if mtl else (),
        created_map_names=("CDT_TEX_007_Map",) if bitmap else (),
        created_asset_paths=(str(image_path),),
        skipped=not (box and mtl and attached),
        skip_reason=None if (box and mtl and attached) else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_nested_material_graph(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-008"
    node_name = "CDT_TEX_008_Box"
    root_mtl_name = "CDT_TEX_008_RootMulti"
    nested_mtl_name = "CDT_TEX_008_Nested"
    image_path = asset_dir / "cdt_tex_008_nested.png"
    write_stub_png(image_path, 256, 256)

    box = _make_box(rt, node_name)
    nested_mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, str(image_path))
    if nested_mtl is not None:
        nested_mtl.name = nested_mtl_name
    attached = _attach_bitmap(rt, nested_mtl, bitmap)

    root_mtl = _try_construct(rt, "Multimaterial")
    root_ok = False
    if root_mtl is not None and nested_mtl is not None:
        try:
            root_mtl.name = root_mtl_name
            root_mtl.materialList[0] = nested_mtl
            root_ok = True
        except Exception:  # noqa: BLE001
            root_ok = False
    if box is not None and root_mtl is not None and root_ok:
        box.material = root_mtl
    elif box is not None and nested_mtl is not None:
        # Fall back to a flat (non-nested) assignment rather than skip the
        # whole fixture if Multimaterial specifically is unavailable.
        box.material = nested_mtl

    ok = bool(box and nested_mtl and attached)
    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="root material -> nested material -> file-backed texture (Multi/Sub Object over a physical/standard material).",
        expected_rule_id=None,
        expected_detection="Traversal reaches the texture through the nested material graph (see adapters/scene_adapter.py's recursive _walk).",
        expected_fixability="n/a",
        expected_repair_behavior="n/a — this fixture validates traversal correctness, not a Finding.",
        created_object_names=(node_name,) if box else (),
        created_material_names=tuple(n for n in (root_mtl_name if root_ok else None, nested_mtl_name) if n),
        created_map_names=("CDT_TEX_008_Map",) if bitmap else (),
        created_asset_paths=(str(image_path),),
        skipped=not ok,
        skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
    )


def _build_multiple_object_usage(rt, asset_dir: Path) -> FixtureRecord:
    fixture_id = "CDT-TEX-009"
    mtl_name = "CDT_TEX_009_Mtl"
    image_path = asset_dir / "cdt_tex_009_multi_object.png"
    write_stub_png(image_path, 256, 256)

    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, str(image_path))
    if mtl is not None:
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)

    node_names = []
    for i in range(1, 4):
        box = _make_box(rt, f"CDT_TEX_009_Box{i}")
        if box is not None and mtl is not None:
            box.material = mtl
            node_names.append(box.name)

    ok = bool(len(node_names) == 3 and mtl and attached)
    return FixtureRecord(
        fixture_id=fixture_id,
        category="texture",
        description="One material/texture graph shared by three separate objects.",
        expected_rule_id=None,
        expected_detection="Traceability reports all 3 object names for this texture where the current architecture supports it (see docs/TEXTURE_DOCTOR.md, 'Known limitations' for the single-root-material caveat).",
        expected_fixability="n/a",
        expected_repair_behavior="n/a — this fixture validates traceability, not a Finding.",
        created_object_names=tuple(node_names),
        created_material_names=(mtl_name,) if mtl else (),
        created_map_names=("CDT_TEX_009_Map",) if bitmap else (),
        created_asset_paths=(str(image_path),),
        skipped=not ok,
        skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
    )


# -- Smart Asset Recovery fixtures (CDT-SMART-001..005) ----------------------
#
# Each of these creates exactly one missing-texture scene reference (same
# shape as CDT-TEX-001) whose ORIGINAL file is never written, plus zero or
# more real files under a shared "recovery library" directory tree that
# smart_relink's search index/scoring is validated against — see
# docs/SMART_RELINK.md, "Torture scene extension".


def _build_missing_reference(rt, asset_dir: Path, fixture_id: str, missing_filename: str) -> tuple:
    """Shared shape for every CDT-SMART fixture: one node+material+bitmap
    pointing at a path under ``asset_dir/missing_originals`` that is
    deliberately never written. Returns ``(box, mtl, bitmap, missing_path)``."""

    node_name = f"{fixture_id.replace('-', '_')}_Box"
    mtl_name = f"{fixture_id.replace('-', '_')}_Mtl"
    missing_path = str(asset_dir / "missing_originals" / missing_filename)

    box = _make_box(rt, node_name)
    mtl = _make_material(rt)
    bitmap = _make_bitmap(rt, missing_path)
    if mtl is not None:
        mtl.name = mtl_name
    attached = _attach_bitmap(rt, mtl, bitmap)
    if box is not None and mtl is not None:
        box.material = mtl

    return box, mtl, bitmap, attached, missing_path, node_name, mtl_name


def create_smart_relink_fixtures(rt, asset_dir: Path) -> list:
    """Builds CDT-SMART-001..005 and their shared recovery library. See
    module docstring above."""

    recovery_root = asset_dir / "recovery_library"
    fixtures = []

    # CDT-SMART-001: exact filename, deeply nested in the recovery root.
    filename = "cdt_smart_001_wood_floor.png"
    box, mtl, bitmap, attached, missing_path, node_name, mtl_name = _build_missing_reference(rt, asset_dir, "CDT-SMART-001", filename)
    exact_path = recovery_root / "a" / "b" / "c" / filename
    write_stub_png(exact_path, 256, 256)
    ok = bool(box and mtl and attached)
    fixtures.append(
        FixtureRecord(
            fixture_id="CDT-SMART-001",
            category="smart_relink",
            description="Exact filename exists several subfolders deep inside the recovery library.",
            expected_rule_id="TXT-001",
            expected_detection="Recursive search finds an EXACT-band candidate at the nested path.",
            expected_fixability="manual",
            expected_repair_behavior="Search Library -> exact match -> user-reviewed relink.",
            created_object_names=(node_name,) if box else (),
            created_material_names=(mtl_name,) if mtl else (),
            created_asset_paths=(missing_path, str(exact_path)),
            recovery_root=str(recovery_root),
            skipped=not ok,
            skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
        )
    )

    # CDT-SMART-002: renamed file, but dimensions strongly match the
    # (torture-fixture-only) known original metadata.
    filename = "cdt_smart_002_original_name.png"
    box, mtl, bitmap, attached, missing_path, node_name, mtl_name = _build_missing_reference(rt, asset_dir, "CDT-SMART-002", filename)
    renamed_path = recovery_root / "renamed" / "cdt_smart_002_renamed_asset.png"
    write_stub_png(renamed_path, 512, 512)
    ok = bool(box and mtl and attached)
    fixtures.append(
        FixtureRecord(
            fixture_id="CDT-SMART-002",
            category="smart_relink",
            description="Original filename was changed, but resolution matches the (fixture-known) original metadata strongly.",
            expected_rule_id="TXT-001",
            expected_detection="No exact-filename candidate; the renamed file scores HIGH/MEDIUM via dimension + aspect-ratio evidence.",
            expected_fixability="manual",
            expected_repair_behavior="Search Library -> renamed match -> user-reviewed relink (never auto-applied).",
            created_object_names=(node_name,) if box else (),
            created_material_names=(mtl_name,) if mtl else (),
            created_asset_paths=(missing_path, str(renamed_path)),
            known_width=512,
            known_height=512,
            recovery_root=str(recovery_root),
            skipped=not ok,
            skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
        )
    )

    # CDT-SMART-003: multiple plausible (ambiguous) candidates.
    filename = "cdt_smart_003_marble.png"
    box, mtl, bitmap, attached, missing_path, node_name, mtl_name = _build_missing_reference(rt, asset_dir, "CDT-SMART-003", filename)
    candidate_a = recovery_root / "marble_v1" / "cdt_smart_003_marble_v1.png"
    candidate_b = recovery_root / "marble_v2" / "cdt_smart_003_marble_v2.png"
    write_stub_png(candidate_a, 256, 256)
    write_stub_png(candidate_b, 256, 256)
    ok = bool(box and mtl and attached)
    fixtures.append(
        FixtureRecord(
            fixture_id="CDT-SMART-003",
            category="smart_relink",
            description="Two similarly-named candidates in different folders — neither an exact filename match.",
            expected_rule_id="TXT-001",
            expected_detection="Search returns multiple plausible candidates; none is auto-selected.",
            expected_fixability="manual",
            expected_repair_behavior="Search Library -> ambiguous -> explicit user choice required.",
            created_object_names=(node_name,) if box else (),
            created_material_names=(mtl_name,) if mtl else (),
            created_asset_paths=(missing_path, str(candidate_a), str(candidate_b)),
            recovery_root=str(recovery_root),
            skipped=not ok,
            skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
        )
    )

    # CDT-SMART-004: no candidate anywhere in the recovery library.
    # Deliberately NOT prefixed "cdt_smart_004_..." like its siblings -
    # every other fixture's recovery file shares that boilerplate prefix,
    # which would otherwise make candidates_for_asset()'s cheap stem-
    # similarity pre-filter (see smart_relink/models.py) pick them up as
    # false "similar name" candidates purely from the shared naming
    # convention, not from anything a real asset library would produce.
    filename = "zzz_no_match_anywhere_in_library.png"
    box, mtl, bitmap, attached, missing_path, node_name, mtl_name = _build_missing_reference(rt, asset_dir, "CDT-SMART-004", filename)
    ok = bool(box and mtl and attached)
    fixtures.append(
        FixtureRecord(
            fixture_id="CDT-SMART-004",
            category="smart_relink",
            description="No matching or similarly-named file exists anywhere in the recovery library.",
            expected_rule_id="TXT-001",
            expected_detection="Search returns zero candidates; the asset stays unresolved.",
            expected_fixability="manual",
            expected_repair_behavior="Remains unresolved — nothing to relink.",
            created_object_names=(node_name,) if box else (),
            created_material_names=(mtl_name,) if mtl else (),
            created_asset_paths=(missing_path,),
            recovery_root=str(recovery_root),
            skipped=not ok,
            skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
        )
    )

    # CDT-SMART-005: exact match under a Unicode (Turkish) candidate path.
    filename = "cdt_smart_005_doku.png"
    box, mtl, bitmap, attached, missing_path, node_name, mtl_name = _build_missing_reference(rt, asset_dir, "CDT-SMART-005", filename)
    unicode_path = recovery_root / "çalışma" / "İstanbul" / filename
    write_stub_png(unicode_path, 128, 128)
    ok = bool(box and mtl and attached)
    fixtures.append(
        FixtureRecord(
            fixture_id="CDT-SMART-005",
            category="smart_relink",
            description="Exact filename match under a non-ASCII (Turkish) candidate folder path.",
            expected_rule_id="TXT-001",
            expected_detection="Recursive search correctly discovers and scores the Unicode-path candidate as EXACT.",
            expected_fixability="manual",
            expected_repair_behavior="Search Library -> exact match -> user-reviewed relink.",
            created_object_names=(node_name,) if box else (),
            created_material_names=(mtl_name,) if mtl else (),
            created_asset_paths=(missing_path, str(unicode_path)),
            recovery_root=str(recovery_root),
            skipped=not ok,
            skip_reason=None if ok else "material/bitmap construction or attachment unavailable on this host",
        )
    )

    return fixtures


# -- entry point ---------------------------------------------------------------


def create_torture_scene(*, confirm_destructive: bool = False, asset_dir: Path | None = None) -> TortureManifest:
    """Build the Torture Scene fixtures and write the manifest.

    Refuses to run against a non-empty scene unless
    ``confirm_destructive=True`` — and even then never deletes/resets
    anything, it only adds fixture objects (see module docstring). The
    16K fixture (CDT-TEX-005) alone takes a few seconds to compress; the
    whole generator is expected to run in low single-digit seconds, not
    a scan-critical path.
    """

    if pymxs is None:
        raise TortureSceneAbortedError("pymxs unavailable — run this from inside 3ds Max.")

    if not scene_appears_empty() and not confirm_destructive:
        raise TortureSceneAbortedError(
            "Current scene is not empty. create_torture_scene() refuses to run against a "
            "non-empty scene by default — open a NEW EMPTY scene first. If you understand "
            "the risk and want fixtures added to the current scene anyway (nothing existing "
            "is ever deleted/reset), call create_torture_scene(confirm_destructive=True)."
        )

    rt = pymxs.runtime
    resolved_asset_dir = asset_dir or default_torture_asset_dir()
    _logger.info("Torture scene: writing test assets to %s", resolved_asset_dir)

    fixtures = [
        _build_missing_texture(rt, resolved_asset_dir),
        _build_local_absolute_path(rt, resolved_asset_dir),
        _build_reused_texture(rt, resolved_asset_dir),
        _build_oversized(rt, resolved_asset_dir, "CDT-TEX-004", 8192, "cdt_tex_004_8k.png", ">= 8192px triggers TXT-004 at OPTIMIZATION/WARNING severity."),
        _build_oversized(rt, resolved_asset_dir, "CDT-TEX-005", 16384, "cdt_tex_005_16k.png", ">= 16384px triggers TXT-004's stronger WARNING tier."),
        _build_non_ascii_path(rt, resolved_asset_dir),
        _build_path_with_spaces(rt, resolved_asset_dir),
        _build_nested_material_graph(rt, resolved_asset_dir),
        _build_multiple_object_usage(rt, resolved_asset_dir),
    ]
    fixtures.extend(create_smart_relink_fixtures(rt, resolved_asset_dir))

    skipped = [f for f in fixtures if f.skipped]
    for f in skipped:
        _logger.warning("Torture scene: skipped %s (%s)", f.fixture_id, f.skip_reason)

    manifest = TortureManifest(
        created_at=_now_iso(),
        asset_directory=str(resolved_asset_dir),
        fixtures=tuple(fixtures),
        smart_relink_recovery_root=str(resolved_asset_dir / "recovery_library"),
    )
    path = save_torture_manifest(manifest)
    _logger.info(
        "Torture scene created: %d fixture(s), %d skipped. Manifest written to %s",
        len(fixtures) - len(skipped),
        len(skipped),
        path,
    )
    return manifest


if __name__ == "__main__":  # pragma: no cover - manual/host invocation only
    create_torture_scene()
