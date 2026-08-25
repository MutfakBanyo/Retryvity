"""Read-only 3ds Max scene/material/map traversal for Scene Inventory + Texture Doctor.

This is the only module (besides ``max_adapter``/``corona_adapter``) that
touches pymxs for this milestone. Every method here is READ-ONLY — it
never assigns a property, never changes selection, never creates or
deletes anything. Main-thread-only, like every pymxs access in this
codebase (see docs/ARCHITECTURE.md, "Threading").

Identity: cycle detection and dedup during material/map traversal use
``MaxAdapter.get_animatable_handle`` (MAXScript's stable Animatable
handle), not Python ``id()`` — see that method's docstring for why.

Generic traversal, not Corona-specific: sub-material/sub-texmap discovery
uses ``rt.getNumSubMtls``/``rt.getSubMtl`` and
``rt.getNumSubTexmaps``/``rt.getSubTexmap`` — the standard, generic
MAXScript Material/Texmap interface implemented by virtually every
material and map plugin (Multi/Sub, Blend, CoronaLayeredMtl,
CoronaPhysicalMtl, legacy StandardMtl, ...). This is what lets Texture
Doctor work in mixed/legacy scenes instead of only understanding one
Corona material class.

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

_KNOWN_SUPERCLASSES = {
    "GeometryClass": "geometry",
    "Light": "light",
    "Camera": "camera",
    "Helper": "helper",
    "Shape": "shape",
}


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

    def is_available(self) -> bool:
        return pymxs is not None

    def get_node_count(self) -> int:
        """Cheap upfront node count, used only to size scan progress totals."""

        return self._max.get_scene_object_count() or 0

    # -- Stage 1: scene nodes ------------------------------------------------

    def iter_node_facts(self, batch_size: int = 2000) -> Iterator[list[NodeFacts]]:
        """Yield batches of :class:`NodeFacts` for every node in the scene."""

        if pymxs is None:
            return
        rt = pymxs.runtime
        batch: list[NodeFacts] = []
        for node in rt.objects:
            facts = self._node_facts(node)
            if facts is not None:
                batch.append(facts)
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _node_facts(self, node) -> NodeFacts | None:
        rt = pymxs.runtime
        try:
            name = str(node.name)
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"node facts: {exc}")
            return None

        handle = self._max.get_animatable_handle(node)
        superclass_key = "unknown"
        try:
            superclass_key = _KNOWN_SUPERCLASSES.get(str(rt.superClassOf(node)), "unknown")
        except Exception:  # noqa: BLE001
            pass

        class_name = "unknown"
        try:
            class_name = str(rt.classOf(node))
        except Exception:  # noqa: BLE001
            pass

        is_hidden = bool(_safe_bool(lambda: node.isHidden))
        is_frozen = bool(_safe_bool(lambda: node.isFrozen))
        is_group_head = bool(_safe_bool(lambda: node.isGroupHead))

        material_handle = None
        material = _safe(lambda: node.material)
        if material is not None:
            material_handle = self._max.get_animatable_handle(material)

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
        Animatable handle so a shared/instanced sub-material or map is
        only visited — and only appears in the results, and only counted
        once toward ``unique_material_count``/``map_reference_count`` —
        regardless of how many nodes/materials reference it. ponytail:
        when the same map instance is nested under more than one root
        material, only the first-visited root's node association is
        recorded — full multi-parent traceability is a later milestone if
        usage shows it matters (see docs/TEXTURE_DOCTOR.md, "Known
        limitations").
        """

        if pymxs is None:
            return
        rt = pymxs.runtime

        material_to_nodes: dict[int, list[str]] = {}
        root_materials: dict[int, object] = {}
        for node in rt.objects:
            material = _safe(lambda node=node: node.material)
            if material is None:
                continue
            handle = self._max.get_animatable_handle(material)
            if handle is None:
                continue
            node_name = _safe(lambda node=node: str(node.name)) or "?"
            material_to_nodes.setdefault(handle, []).append(node_name)
            root_materials.setdefault(handle, material)

        visited: set[int] = set()
        batch: list[MapDiscovery] = []

        for handle, material in root_materials.items():
            owning_nodes = tuple(material_to_nodes.get(handle, ()))
            for item in self._walk(rt, material, owning_nodes, root_material_name=_safe_name(material), visited=visited):
                batch.append(item)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []

        if batch:
            yield batch

    def _walk(self, rt, obj, owning_nodes: tuple[str, ...], root_material_name: str | None, visited: set[int]) -> Iterator[MapDiscovery]:
        handle = self._max.get_animatable_handle(obj)
        if handle is not None:
            if handle in visited:
                return
            visited.add(handle)

        superclass = _safe(lambda: str(rt.superClassOf(obj))) or "unknown"

        if superclass == "TextureMap":
            self.map_reference_count += 1
            yield self._describe_map(rt, obj, root_material_name, owning_nodes)
        elif superclass == "Material":
            self.unique_material_count += 1

        for sub_mtl in _safe_iter_sub_mtls(rt, obj):
            yield from self._walk(rt, sub_mtl, owning_nodes, root_material_name, visited)

        for sub_map in _safe_iter_sub_texmaps(rt, obj):
            yield from self._walk(rt, sub_map, owning_nodes, root_material_name, visited)

    def _describe_map(self, rt, map_obj, material_name: str | None, owning_nodes: tuple[str, ...]) -> MapDiscovery:
        map_class = _safe(lambda: str(rt.classOf(map_obj))) or "unknown"
        map_name = _safe_name(map_obj)
        handle = self._max.get_animatable_handle(map_obj)

        raw_path, source_property = _probe_filename(rt, map_obj)
        if raw_path is None and map_class not in self.unknown_map_classes:
            self.unknown_map_classes.append(map_class)

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
