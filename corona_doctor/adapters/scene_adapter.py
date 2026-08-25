"""Read-only 3ds Max scene/material/map traversal for Scene Inventory + Texture Doctor.

This is the only module (besides ``max_adapter``/``corona_adapter``) that
touches pymxs for this milestone. Every method here is READ-ONLY — it
never assigns a property, never changes selection, never creates or
deletes anything. Main-thread-only, like every pymxs access in this
codebase (see docs/ARCHITECTURE.md, "Threading").

Identity: cycle detection and dedup during material/map traversal use
``MaxAdapter.get_animatable_handle`` (MAXScript's stable Animatable
handle) as the *preferred* identity, but never drop a material/map from
traversal solely because that handle comes back ``None`` on a given host
— see ``SceneAdapter._identity`` for the per-scan fallback identity used
instead, and docs/TEXTURE_DOCTOR.md, "Identity" for why this matters on
real hosts where ``getHandleByAnim`` has been observed to fail for some
Animatable-derived objects despite Autodesk documenting it as universally
valid.

Generic traversal, not Corona-specific: sub-material/sub-texmap discovery
uses ``rt.getNumSubMtls``/``rt.getSubMtl`` and
``rt.getNumSubTexmaps``/``rt.getSubTexmap`` — the standard, generic
MAXScript Material/Texmap interface implemented by virtually every
material and map plugin (Multi/Sub, Blend, CoronaLayeredMtl,
CoronaPhysicalMtl, legacy StandardMtl, ...). This is what lets Texture
Doctor work in mixed/legacy scenes instead of only understanding one
Corona material class.

Classification: node superclass (geometry/light/camera/helper/shape) and
material-graph node kind (material/texturemap) are never decided by
comparing a *guessed* Python string against ``str(rt.superClassOf(obj))``
alone — real-host testing showed that comparison silently fails for some
class/host combinations. ``_classify_by_equality`` layers three signals,
most-reliable first: (1) host collection membership (``rt.lights``,
``rt.cameras``, ``rt.geometry``, ``rt.helpers``, ``rt.shapes`` — the
categorized collections 3ds Max itself maintains), (2) direct equality of
the live Class object (``rt.superClassOf(obj) == rt.Light``, not a string
compare), (3) a normalized string compare as a last resort. See
docs/TEXTURE_DOCTOR.md, "Node/material classification" for detail.

File-path extraction is deliberately conservative: it probes a short,
documented list of candidate property names (currently ``filename`` —
confirmed standard on Bitmaptexture, expected on CoronaBitmap per Chaos's
own Bitmaptexture-compatibility documentation — and ``HDRIMapName`` for
environment/dome maps) via ``rt.isProperty`` before ever touching the
attribute, so an unsupported/custom map class degrades to "unsupported"
rather than raising. See docs/TEXTURE_DOCTOR.md, "How paths are found"
for the exact, host-validated property list once confirmed on a real
scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from corona_doctor.adapters.max_adapter import MaxAdapter

try:
    import pymxs  # type: ignore
except ImportError:  # pragma: no cover - exercised only inside 3ds Max
    pymxs = None

# Best-effort, tunable after real-host validation (see docs/TEXTURE_DOCTOR.md).
_FILENAME_CANDIDATE_PROPERTIES = ("filename", "HDRIMapName")

# Best-effort scene-node classification. Not exhaustive — anything not
# listed here is still recorded, just not counted toward these totals.
_CORONA_LIGHT_CLASSES = ("CoronaLight", "CoronaSun")
_CORONA_CAMERA_CLASSES = ("CoronaCam",)

# rt attribute name for each generic node superclass bucket, used both for
# live Class-object equality and as a last-resort normalized string compare.
_NODE_SUPERCLASS_ATTR_NAMES = {
    "geometry": "GeometryClass",
    "light": "Light",
    "camera": "Camera",
    "helper": "Helper",
    "shape": "Shape",
}

# Same idea for material-graph node kind (used while walking a material's
# sub-material/sub-texmap graph, not the scene node list).
_GRAPH_SUPERCLASS_ATTR_NAMES = {
    "material": "Material",
    "texturemap": "TextureMap",
}

# rt collection attribute name for each node superclass bucket, checked in
# this priority order — Corona lights/cameras have been observed sharing
# icon/geometry plumbing with GeometryClass on some hosts, so light/camera
# membership is checked before geometry.
_HOST_NODE_COLLECTIONS = (
    ("light", "lights"),
    ("camera", "cameras"),
    ("geometry", "geometry"),
    ("helper", "helpers"),
    ("shape", "shapes"),
)

# A Target/TargetObject node (the crosshair a targeted light/camera points
# at) is a distinct scene node but not renderable geometry — historical Max
# superclass behavior places it under GeometryClass, which would otherwise
# inflate geometry_count. Classified as "helper" instead.
_TARGET_CLASS_NAMES = {"Target", "TargetObject"}

_IDENTITY_SAMPLE_SUCCESS_CAP = 8
_IDENTITY_SAMPLE_FAILURE_CAP = 32
_REJECTED_MAP_SAMPLE_CAP = 20


@dataclass(frozen=True)
class NodeFacts:
    """Detached, plain-Python facts about one scene node."""

    name: str
    handle: int | None
    superclass_key: str  # "geometry" | "light" | "camera" | "helper" | "shape" | "unknown"
    class_name: str
    is_hidden: bool
    is_frozen: bool
    is_group_head: bool
    material_handle: int | None


@dataclass(frozen=True)
class MapDiscovery:
    """Detached facts about one discovered Texmap node (file-backed or not)."""

    handle: int | None
    map_class: str
    map_name: str | None
    raw_path: str | None
    source_property: str | None
    material_name: str | None
    object_names: tuple[str, ...]
    is_file_backed_class_guess: bool


class SceneAdapter:
    """Safe, minimal surface over 3ds Max scene/material/map traversal."""

    def __init__(self, max_adapter: MaxAdapter | None = None) -> None:
        self._max = max_adapter or MaxAdapter()
        # Populated by traverse_materials_and_maps(); read after the
        # generator is exhausted. Total (non-deduplicated) material
        # *assignment* count is derived by the scanner from NodeFacts
        # instead — see scanners/texture_doctor_scanner.py.
        self.unique_material_count = 0
        self.map_reference_count = 0
        self.unknown_map_classes: list[str] = []
        self.errors: list[str] = []

        # Per-scan fallback identity for materials/maps whose AnimHandle
        # comes back None — see _identity(). Keyed by python id(obj), which
        # is only safe within a single traversal (the object is guaranteed
        # not to be garbage-collected mid-scan because the caller holds a
        # live reference to it). Never persisted across scans/sessions.
        self._fallback_ids: dict[int, int] = {}
        self._fallback_counter = 0

        # Development-only diagnostic counters/samples — see
        # docs/TEXTURE_DOCTOR.md and devtools/texture_probe.py. Not shown
        # in production UI.
        self.root_materials_encountered = 0
        self.materials_with_valid_handle = 0
        self.materials_using_fallback_identity = 0
        self.sub_material_edges_traversed = 0
        self.map_nodes_encountered = 0
        self.maps_with_valid_handle = 0
        self.maps_using_fallback_identity = 0
        self.external_file_backed_maps_recognized = 0
        self.maps_with_candidate_filename_properties = 0
        self.maps_rejected_as_non_file_backed = 0
        self.identity_samples: list[dict] = []
        self.rejected_map_samples: list[dict] = []

    def is_available(self) -> bool:
        return pymxs is not None

    def get_node_count(self) -> int:
        """Cheap upfront node count, used only to size scan progress totals."""

        return self._max.get_scene_object_count() or 0

    # -- Identity --------------------------------------------------------

    def _identity(self, obj) -> tuple[int, bool]:
        """Stable-for-this-scan identity: AnimHandle if valid, else fallback.

        Returns ``(identity, used_fallback)``. A valid material/map must
        never disappear from traversal solely because
        ``get_animatable_handle`` returned ``None`` — see module docstring
        and docs/TEXTURE_DOCTOR.md, "Identity". The fallback identity is
        keyed on Python ``id(obj)`` and is only guaranteed stable for the
        life of this single scan (never persisted, never compared across
        scans): it does not fully solve dedup when the same underlying Max
        object is reachable through two different freshly-constructed
        pymxs wrappers, but it guarantees the object is still visited and
        reported rather than silently dropped. Fallback identities are
        negative so they can never collide with a real (always positive)
        AnimHandle.
        """

        handle = self._max.get_animatable_handle(obj)
        if handle is not None:
            return handle, False
        key = id(obj)
        fallback = self._fallback_ids.get(key)
        if fallback is None:
            self._fallback_counter -= 1
            fallback = self._fallback_counter
            self._fallback_ids[key] = fallback
        return fallback, True

    def _maybe_record_identity_sample(self, rt, obj, kind: str, used_fallback: bool) -> None:
        successes = sum(1 for s in self.identity_samples if not s["used_fallback"])
        failures = sum(1 for s in self.identity_samples if s["used_fallback"])
        if used_fallback and failures >= _IDENTITY_SAMPLE_FAILURE_CAP:
            return
        if not used_fallback and successes >= _IDENTITY_SAMPLE_SUCCESS_CAP:
            return
        self.identity_samples.append(
            {
                "kind": kind,
                "repr": _safe(lambda: repr(obj), "?"),
                "classOf": _safe(lambda: str(rt.classOf(obj)), "?"),
                "superClassOf": _safe(lambda: str(rt.superClassOf(obj)), "?"),
                "getHandleByAnim_raw": _safe(lambda: rt.getHandleByAnim(obj)),
                "python_wrapper_type": type(obj).__name__,
                "used_fallback": used_fallback,
            }
        )

    def _maybe_record_rejected_map_sample(self, rt, map_obj, map_class: str) -> None:
        if any(s["map_class"] == map_class for s in self.rejected_map_samples):
            return  # one representative sample per unique class is enough
        if len(self.rejected_map_samples) >= _REJECTED_MAP_SAMPLE_CAP:
            return
        prop_names = _safe(lambda: [str(p) for p in rt.getPropNames(map_obj)], [])
        self.rejected_map_samples.append(
            {
                "map_class": map_class,
                "property_names": prop_names,
                "candidate_properties_checked": list(_FILENAME_CANDIDATE_PROPERTIES),
            }
        )

    # -- Stage 1: scene nodes ------------------------------------------------

    def iter_node_facts(self, batch_size: int = 2000) -> Iterator[list[NodeFacts]]:
        """Yield batches of :class:`NodeFacts` for every node in the scene."""

        if pymxs is None:
            return
        rt = pymxs.runtime
        node_class_objects = _resolve_class_objects(rt, _NODE_SUPERCLASS_ATTR_NAMES)
        host_collection_handles = self._build_host_collection_handles(rt)

        batch: list[NodeFacts] = []
        for node in rt.objects:
            facts = self._node_facts(node, rt, node_class_objects, host_collection_handles)
            if facts is not None:
                batch.append(facts)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _build_host_collection_handles(self, rt) -> dict[str, set[int]]:
        """AnimHandle sets for ``rt.lights``/``rt.cameras``/etc.

        These are the categorized collections 3ds Max itself maintains —
        more reliable than inferring every category from a class-string
        comparison (see module docstring). Built once per scan.
        """

        result: dict[str, set[int]] = {}
        for key, attr in _HOST_NODE_COLLECTIONS:
            handles: set[int] = set()
            collection = _safe(lambda attr=attr: getattr(rt, attr))
            if collection is not None:
                for obj in _safe_iter_collection(collection):
                    handle = self._max.get_animatable_handle(obj)
                    if handle is not None:
                        handles.add(handle)
            result[key] = handles
        return result

    def _node_facts(self, node, rt, node_class_objects: dict[str, object], host_collection_handles: dict[str, set[int]]) -> NodeFacts | None:
        try:
            name = str(node.name)
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"node facts: {exc}")
            return None

        handle = self._max.get_animatable_handle(node)

        class_name = "unknown"
        try:
            class_name = str(rt.classOf(node))
        except Exception:  # noqa: BLE001
            pass

        if class_name in _TARGET_CLASS_NAMES:
            superclass_key = "helper"
        else:
            superclass_key = "unknown"
            if handle is not None:
                for key, handles in host_collection_handles.items():
                    if handle in handles:
                        superclass_key = key
                        break
            if superclass_key == "unknown":
                superclass_key = _classify_by_equality(rt, node, node_class_objects, _NODE_SUPERCLASS_ATTR_NAMES)

        is_hidden = bool(_safe_bool(lambda: node.isHidden))
        is_frozen = bool(_safe_bool(lambda: node.isFrozen))
        is_group_head = bool(_safe_bool(lambda: node.isGroupHead))

        material_handle = None
        material = _safe(lambda: node.material)
        if material is not None:
            identity, _used_fallback = self._identity(material)
            material_handle = identity

        return NodeFacts(
            name=name,
            handle=handle,
            superclass_key=superclass_key,
            class_name=class_name,
            is_hidden=is_hidden,
            is_frozen=is_frozen,
            is_group_head=is_group_head,
            material_handle=material_handle,
        )

    # -- Stage 2: material/map graph -----------------------------------------

    def traverse_materials_and_maps(self, batch_size: int = 200) -> Iterator[list[MapDiscovery]]:
        """Recursively walk every node's material graph, yielding discovered maps.

        Re-iterates ``rt.objects`` directly (rather than reusing
        :class:`NodeFacts`) so each node's real ``.material`` object is
        available without an extra by-name lookup. Deduplicates by
        identity (see :meth:`_identity`) so a shared/instanced
        sub-material or map is only visited — and only appears in the
        results, and only counted once toward
        ``unique_material_count``/``map_reference_count`` — regardless of
        how many nodes/materials reference it. A material is *never*
        skipped just because its AnimHandle came back ``None`` — see
        :meth:`_identity`. ponytail: when the same map instance is nested
        under more than one root material, only the first-visited root's
        node association is recorded — full multi-parent traceability is a
        later milestone if usage shows it matters (see
        docs/TEXTURE_DOCTOR.md, "Known limitations").
        """

        if pymxs is None:
            return
        rt = pymxs.runtime
        graph_class_objects = _resolve_class_objects(rt, _GRAPH_SUPERCLASS_ATTR_NAMES)

        material_to_nodes: dict[int, list[str]] = {}
        root_materials: dict[int, object] = {}
        for node in rt.objects:
            material = _safe(lambda node=node: node.material)
            if material is None:
                continue
            handle, _used_fallback = self._identity(material)
            node_name = _safe(lambda node=node: str(node.name)) or "?"
            material_to_nodes.setdefault(handle, []).append(node_name)
            root_materials.setdefault(handle, material)

        self.root_materials_encountered = len(root_materials)

        visited: set[int] = set()
        batch: list[MapDiscovery] = []

        for handle, material in root_materials.items():
            owning_nodes = tuple(material_to_nodes.get(handle, ()))
            for item in self._walk(rt, material, owning_nodes, _safe_name(material), visited, graph_class_objects):
                batch.append(item)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []

        if batch:
            yield batch

    def _walk(self, rt, obj, owning_nodes: tuple[str, ...], root_material_name: str | None, visited: set[int], graph_class_objects: dict[str, object]) -> Iterator[MapDiscovery]:
        handle, used_fallback = self._identity(obj)
        if handle in visited:
            return
        visited.add(handle)

        kind = _classify_by_equality(rt, obj, graph_class_objects, _GRAPH_SUPERCLASS_ATTR_NAMES)

        if kind == "texturemap":
            self.map_reference_count += 1
            self.map_nodes_encountered += 1
            if used_fallback:
                self.maps_using_fallback_identity += 1
            else:
                self.maps_with_valid_handle += 1
            self._maybe_record_identity_sample(rt, obj, "map", used_fallback)
            yield self._describe_map(rt, obj, root_material_name, owning_nodes, handle)
        elif kind == "material":
            self.unique_material_count += 1
            if used_fallback:
                self.materials_using_fallback_identity += 1
            else:
                self.materials_with_valid_handle += 1
            self._maybe_record_identity_sample(rt, obj, "material", used_fallback)

        for sub_mtl in _safe_iter_sub_mtls(rt, obj):
            self.sub_material_edges_traversed += 1
            yield from self._walk(rt, sub_mtl, owning_nodes, root_material_name, visited, graph_class_objects)

        for sub_map in _safe_iter_sub_texmaps(rt, obj):
            self.sub_material_edges_traversed += 1
            yield from self._walk(rt, sub_map, owning_nodes, root_material_name, visited, graph_class_objects)

    def _describe_map(self, rt, map_obj, material_name: str | None, owning_nodes: tuple[str, ...], handle: int | None) -> MapDiscovery:
        map_class = _safe(lambda: str(rt.classOf(map_obj))) or "unknown"
        map_name = _safe_name(map_obj)

        raw_path, source_property = _probe_filename(rt, map_obj)
        if source_property is not None:
            self.maps_with_candidate_filename_properties += 1
        if raw_path is None:
            self.maps_rejected_as_non_file_backed += 1
            self._maybe_record_rejected_map_sample(rt, map_obj, map_class)
            if map_class not in self.unknown_map_classes:
                self.unknown_map_classes.append(map_class)
        else:
            self.external_file_backed_maps_recognized += 1

        return MapDiscovery(
            handle=handle,
            map_class=map_class,
            map_name=map_name,
            raw_path=raw_path,
            source_property=source_property,
            material_name=material_name,
            object_names=owning_nodes,
            is_file_backed_class_guess=raw_path is not None,
        )


def _resolve_class_objects(rt, attr_names: dict[str, str]) -> dict[str, object]:
    """Resolve live Class objects (e.g. ``rt.Light``) for equality compares.

    Comparing ``rt.superClassOf(obj) == rt.Light`` is robust across pymxs
    versions in a way ``str(rt.superClassOf(obj)) == "Light"`` is not — see
    module docstring. Missing on a given host degrades to ``None`` per key,
    which callers must skip.
    """

    return {key: _safe(lambda name=name: getattr(rt, name)) for key, name in attr_names.items()}


def _classify_by_equality(rt, obj, class_objects: dict[str, object], attr_names: dict[str, str]) -> str:
    """Classify ``obj`` by its ``superClassOf``, most-reliable signal first.

    1. Direct equality against a live Class object (``rt.Light``, ...).
    2. Normalized string compare, as a last resort for hosts where even
       Class-object equality is unavailable/unreliable.
    """

    sc = _safe(lambda: rt.superClassOf(obj))
    if sc is None:
        return "unknown"

    for key, class_obj in class_objects.items():
        if class_obj is not None and _safe(lambda class_obj=class_obj: bool(sc == class_obj), False):
            return key

    normalized = (_safe(lambda: str(sc), "") or "").strip().lower()
    for key, name in attr_names.items():
        if normalized == name.lower():
            return key
    return "unknown"


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _safe_bool(fn) -> bool:
    return bool(_safe(fn, False))


def _safe_name(obj) -> str | None:
    try:
        name = getattr(obj, "name", None)
        return str(name) if name is not None else None
    except Exception:  # noqa: BLE001
        return None


def _safe_iter_collection(collection) -> list:
    try:
        return list(collection)
    except Exception:  # noqa: BLE001
        return []


def _safe_iter_sub_mtls(rt, obj) -> list:
    try:
        count = int(rt.getNumSubMtls(obj))
    except Exception:  # noqa: BLE001
        return []
    results = []
    for i in range(1, count + 1):
        sub = _safe(lambda i=i: rt.getSubMtl(obj, i))
        if sub is not None:
            results.append(sub)
    return results


def _safe_iter_sub_texmaps(rt, obj) -> list:
    try:
        count = int(rt.getNumSubTexmaps(obj))
    except Exception:  # noqa: BLE001
        return []
    results = []
    for i in range(1, count + 1):
        sub = _safe(lambda i=i: rt.getSubTexmap(obj, i))
        if sub is not None:
            results.append(sub)
    return results


def _probe_filename(rt, map_obj) -> tuple[str | None, str | None]:
    for prop in _FILENAME_CANDIDATE_PROPERTIES:
        try:
            if not rt.isProperty(map_obj, prop):
                continue
            value = getattr(map_obj, prop)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(value, str) and value.strip():
            return value, prop
    return None, None
