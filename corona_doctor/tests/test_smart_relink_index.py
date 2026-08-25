"""Unit tests for smart_relink/index.py — pure, fake walk_fn/size_fn, no
real filesystem."""

from __future__ import annotations

import ntpath

from corona_doctor.smart_relink.index import build_search_index


def _walk_fn_from_tree(tree: dict[str, tuple[list[str], list[str]]]):
    """``tree`` maps a directory path to ``(subdir_names, filenames)``.
    Recursively walks it the way ``os.walk`` would."""

    def walk_fn(root: str):
        if root not in tree:
            raise OSError(f"cannot access '{root}'")
        stack = [root]
        while stack:
            current = stack.pop(0)
            subdirs, files = tree.get(current, ([], []))
            yield current, subdirs, files
            for sub in subdirs:
                stack.append(ntpath.join(current, sub))

    return walk_fn


def _size_fn(sizes: dict[str, int]):
    return lambda path: sizes.get(path)


def test_recursive_search_finds_files_in_nested_subfolders():
    tree = {
        r"D:\Library": (["Wood"], ["readme.txt"]),
        r"D:\Library\Wood": (["Oak"], []),
        r"D:\Library\Wood\Oak": ([], ["wood_floor_07.jpg"]),
    }
    index = build_search_index([r"D:\Library"], walk_fn=_walk_fn_from_tree(tree))

    names = {f.filename for f in index.files}
    assert "wood_floor_07.jpg" in names
    assert "readme.txt" in names
    assert index.root_errors == []


def test_multiple_roots_are_all_searched():
    tree = {
        r"D:\A": ([], ["a.jpg"]),
        r"E:\B": ([], ["b.jpg"]),
    }
    index = build_search_index([r"D:\A", r"E:\B"], walk_fn=_walk_fn_from_tree(tree))

    names = {f.filename for f in index.files}
    assert names == {"a.jpg", "b.jpg"}


def test_unc_path_root_is_searched_like_any_other():
    tree = {r"\\SERVER\Assets": ([], ["texture.jpg"])}
    index = build_search_index([r"\\SERVER\Assets"], walk_fn=_walk_fn_from_tree(tree))

    assert index.files[0].filename == "texture.jpg"


def test_permission_denied_root_does_not_abort_other_roots():
    def walk_fn(root):
        if root == r"D:\Locked":
            raise PermissionError("access denied")
        yield root, [], ["ok.jpg"]

    index = build_search_index([r"D:\Locked", r"D:\Open"], walk_fn=walk_fn)

    assert index.root_errors and "D:\\Locked" in index.root_errors[0]
    assert index.files[0].filename == "ok.jpg"


def test_unavailable_root_does_not_abort_the_search():
    tree = {r"D:\Real": ([], ["exists.jpg"])}
    index = build_search_index([r"Z:\Nonexistent", r"D:\Real"], walk_fn=_walk_fn_from_tree(tree))

    assert len(index.root_errors) == 1
    assert index.files[0].filename == "exists.jpg"


def test_unicode_path_is_indexed_correctly():
    tree = {r"D:\çalışma\İstanbul_şömine": ([], ["doku.png"])}
    index = build_search_index([r"D:\çalışma\İstanbul_şömine"], walk_fn=_walk_fn_from_tree(tree))

    assert index.files[0].path == r"D:\çalışma\İstanbul_şömine\doku.png"


def test_path_with_spaces_is_indexed_correctly():
    tree = {r"D:\My Asset Library": ([], ["wood plank 01.jpg"])}
    index = build_search_index([r"D:\My Asset Library"], walk_fn=_walk_fn_from_tree(tree))

    assert index.files[0].filename == "wood plank 01.jpg"


def test_very_long_path_is_indexed_correctly():
    long_dir = "\\".join(["deeply_nested"] * 25)
    root = f"D:\\{long_dir}"
    tree = {root: ([], ["texture.jpg"])}
    index = build_search_index([root], walk_fn=_walk_fn_from_tree(tree))

    assert index.files[0].filename == "texture.jpg"


def test_search_index_records_stem_and_extension():
    tree = {r"D:\Lib": ([], ["wood_floor_07.JPG"])}
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    f = index.files[0]
    assert f.stem == "wood_floor_07"
    assert f.extension == "jpg"


def test_search_index_size_lookup_failure_leaves_size_none_not_fatal():
    """A size_fn that raises for one file must not lose the rest of that
    root's files - the failure is isolated to just that one file's
    size_bytes field."""

    tree = {r"D:\Lib": ([], ["a.jpg", "b.jpg"])}

    def flaky_size_fn(path: str) -> int | None:
        if path.endswith("a.jpg"):
            raise OSError("simulated stat failure")
        return 1234

    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree), size_fn=flaky_size_fn)

    by_name = {f.filename: f for f in index.files}
    assert by_name["a.jpg"].size_bytes is None
    assert by_name["b.jpg"].size_bytes == 1234
    assert index.root_errors == []


def test_cancellation_stops_indexing_early():
    tree = {
        r"D:\Lib": (["A"], ["a.jpg"]),
        r"D:\Lib\A": ([], ["b.jpg"]),
    }
    calls = {"n": 0}

    def cancel_check():
        calls["n"] += 1
        return calls["n"] > 1  # cancel after the first directory is yielded

    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree), cancel_check=cancel_check)

    assert index.cancelled is True


def test_multiple_exact_filenames_in_different_folders_are_all_indexed():
    tree = {
        r"D:\Lib": (["A", "B"], []),
        r"D:\Lib\A": ([], ["wood.jpg"]),
        r"D:\Lib\B": ([], ["wood.jpg"]),
    }
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    matches = index.candidates_for_filename("wood.jpg")
    assert len(matches) == 2
    assert {m.path for m in matches} == {r"D:\Lib\A\wood.jpg", r"D:\Lib\B\wood.jpg"}


def test_candidates_for_filename_is_case_insensitive():
    tree = {r"D:\Lib": ([], ["Wood.JPG"])}
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    assert len(index.candidates_for_filename("wood.jpg")) == 1


def test_candidates_for_asset_includes_exact_matches():
    tree = {r"D:\Lib": ([], ["wood_floor_07.jpg"])}
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    candidates = index.candidates_for_asset("wood_floor_07.jpg")
    assert len(candidates) == 1


def test_candidates_for_asset_also_finds_similarly_named_renamed_files():
    tree = {r"D:\Lib": ([], ["wood_floor_07_final_v2.jpg"])}
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    candidates = index.candidates_for_asset("wood_floor_07.jpg")
    assert len(candidates) == 1
    assert candidates[0].filename == "wood_floor_07_final_v2.jpg"


def test_candidates_for_asset_excludes_wrong_extension_even_if_stem_matches():
    tree = {r"D:\Lib": ([], ["wood_floor_07.txt"])}
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    candidates = index.candidates_for_asset("wood_floor_07.jpg")
    assert candidates == []


def test_candidates_for_asset_excludes_completely_unrelated_filenames():
    tree = {r"D:\Lib": ([], ["completely_different_thing.jpg"])}
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    candidates = index.candidates_for_asset("wood_floor_07.jpg")
    assert candidates == []


def test_candidates_for_asset_respects_custom_similarity_threshold():
    tree = {r"D:\Lib": ([], ["wood_floor_08.jpg"])}  # one-character stem difference
    index = build_search_index([r"D:\Lib"], walk_fn=_walk_fn_from_tree(tree))

    assert index.candidates_for_asset("wood_floor_07.jpg", min_stem_similarity=0.9)
    assert not index.candidates_for_asset("wood_floor_07.jpg", min_stem_similarity=0.999)
