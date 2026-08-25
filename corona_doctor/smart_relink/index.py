"""Builds an in-memory ``SearchIndex`` for one recovery session's
selected roots — see docs/SMART_RELINK.md, "Search index".

Pure: the actual directory walk is injected as ``walk_fn`` (matching
``os.walk``'s ``(dirpath, dirnames, filenames)`` shape) and file size as
``size_fn`` — the same "filesystem access is always a callable the
caller injects" discipline as ``repair/planner.py``. Real callers (UI/
devtools) pass ``os.walk``/``os.path.getsize``; tests pass fakes,
including ones that simulate permission errors, unavailable roots, and
Unicode/space/long paths without touching a real filesystem.

**One bad root/directory must never abort the whole search** — an
exception from ``walk_fn`` for one root, or a size lookup failing for
one file, is recorded in ``SearchIndex.root_errors`` and skipped, never
raised out of ``build_search_index``.
"""

from __future__ import annotations

import ntpath
from typing import Callable, Iterable

from corona_doctor.smart_relink.models import IndexedFile, SearchIndex

WalkFn = Callable[[str], Iterable[tuple[str, list[str], list[str]]]]
SizeFn = Callable[[str], int | None]
CancelCheckFn = Callable[[], bool]


def _default_size_fn(path: str) -> int | None:
    import os

    try:
        return os.path.getsize(path)
    except OSError:
        return None


def build_search_index(
    roots: Iterable[str],
    *,
    walk_fn: WalkFn,
    size_fn: SizeFn = _default_size_fn,
    cancel_check: CancelCheckFn = lambda: False,
) -> SearchIndex:
    """Recursively index every file under every root. Never raises —
    per-root failures are recorded, not fatal (see module docstring)."""

    index = SearchIndex()

    for root in roots:
        if cancel_check():
            index.cancelled = True
            return index
        try:
            for dirpath, _dirnames, filenames in walk_fn(root):
                if cancel_check():
                    index.cancelled = True
                    return index
                for name in filenames:
                    full_path = ntpath.join(dirpath, name)
                    stem, _, ext = name.rpartition(".")
                    if not stem:
                        stem, ext = name, ""
                    try:
                        size_bytes = size_fn(full_path)
                    except Exception:  # noqa: BLE001 - one file's size lookup must not lose the rest of this root
                        size_bytes = None
                    index.files.append(
                        IndexedFile(
                            path=full_path,
                            filename=name,
                            stem=stem,
                            extension=ext.lower(),
                            size_bytes=size_bytes,
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - one bad root must never abort the search
            index.root_errors.append(f"{root}: {exc}")
            continue

    return index
