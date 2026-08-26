"""Scene-authoring helpers used by the in-Max smoke test.

Kept beside scene_access (rather than inside devtools) so that pymxs stays
confined to the revision_guard.max package. Nothing in the shipping
snapshot/compare path calls into this module - it only exists so the smoke
test can build and mutate its own throwaway objects.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from revision_guard.max.scene_access import _runtime

try:  # pragma: no cover - only importable inside 3ds Max
    import pymxs  # type: ignore
except ImportError:
    pymxs = None


@contextmanager
def undo_disabled() -> Iterator[None]:
    """Keep smoke-test scene churn out of the user's undo stack."""

    if pymxs is None or not hasattr(pymxs, "undo"):
        yield
        return
    with pymxs.undo(False):
        yield


def create_box(name: str, position: tuple[float, float, float], size: float = 20.0) -> Any:
    rt = _runtime()
    return rt.Box(
        width=size,
        length=size,
        height=size,
        name=name,
        pos=rt.Point3(*position),
    )


def convert_to_editable_poly(node: Any) -> Any:
    """Collapse a primitive to Editable Poly, keeping the same node handle."""

    rt = _runtime()
    rt.convertToPoly(node)
    return node


def offset_poly_vertex(node: Any, index: int, delta: tuple[float, float, float]) -> None:
    """Nudge one vertex without changing vertex or face counts."""

    rt = _runtime()
    current = rt.polyop.getVert(node, index)
    rt.polyop.setVert(node, index, rt.Point3(current.x + delta[0], current.y + delta[1], current.z + delta[2]))
    rt.update(node)


def move_node(node: Any, delta: tuple[float, float, float]) -> None:
    rt = _runtime()
    node.pos = rt.Point3(node.pos.x + delta[0], node.pos.y + delta[1], node.pos.z + delta[2])


def rotate_node(node: Any, degrees_z: float) -> None:
    rt = _runtime()
    rt.rotate(node, rt.eulerAngles(0, 0, degrees_z))


def scale_node(node: Any, factor: float) -> None:
    rt = _runtime()
    rt.scale(node, rt.Point3(factor, factor, factor))


def delete_node(node: Any) -> None:
    _runtime().delete(node)


def nodes_with_prefix(prefix: str) -> list[Any]:
    rt = _runtime()
    return [node for node in rt.objects if str(node.name).startswith(prefix)]


def delete_nodes_with_prefix(prefix: str) -> int:
    rt = _runtime()
    doomed = nodes_with_prefix(prefix)
    for node in doomed:
        try:
            rt.delete(node)
        except Exception:  # noqa: BLE001 - cleanup is best effort
            pass
    return len(doomed)
