"""Unit tests for devtools/smart_relink_probe.py — a fake scanner (real
TextureDoctorResult data) and real tmp_path files, no pymxs required."""

from __future__ import annotations

from corona_doctor.core.texture_models import ExternalTextureReference, PathInfo, PathType, SceneInventory, TextureDoctorResult
from corona_doctor.devtools.smart_relink_probe import run_smart_relink_probe
from corona_doctor.devtools.torture_assets import write_stub_png


class _FakeScanner:
    def __init__(self, result: TextureDoctorResult) -> None:
        self.result = result


def _ref(filename: str, path: str, *, exists=False) -> ExternalTextureReference:
    info = PathInfo(raw_path=path, normalized_path=path, comparison_key=path.lower(), path_type=PathType.LOCAL, exists=exists)
    return ExternalTextureReference(
        ref_id=f"ref-{filename}",
        map_class="CoronaBitmap",
        map_name=filename,
        material_name="Mtl",
        object_names=("Box01",),
        path_info=info,
        filename=filename,
        extension="jpg",
    )


def _result(refs) -> TextureDoctorResult:
    return TextureDoctorResult(inventory=SceneInventory(), texture_references=tuple(refs), findings=(), compatibility_warnings=(), unknown_map_classes=(), errors=())


def test_probe_finds_and_ranks_a_candidate(tmp_path, capsys):
    recovery_root = tmp_path / "recovery"
    write_stub_png(recovery_root / "sub" / "wood.jpg", 64, 64)

    scanner = _FakeScanner(_result([_ref("wood.jpg", r"C:\proj\wood.jpg", exists=False)]))
    report = run_smart_relink_probe(roots=[str(recovery_root)], scanner=scanner)

    assert report["missing_assets"] == 1
    assert len(report["results"]) == 1
    assert report["results"][0]["candidates"][0].path.endswith("wood.jpg")

    output = capsys.readouterr().out
    assert "wood.jpg" in output
    assert "EXACT" in output


def test_probe_no_mutation_never_touches_the_scene():
    """No scene-adapter/repair-adapter import at all in this module - the
    probe is search+scoring only, structurally incapable of mutating."""

    import inspect

    import corona_doctor.devtools.smart_relink_probe as probe_module

    source = inspect.getsource(probe_module)
    assert "repair_adapter" not in source
    assert "relink_map_property" not in source


def test_probe_reports_zero_missing_assets_cleanly(capsys):
    scanner = _FakeScanner(_result([_ref("ok.jpg", r"C:\proj\ok.jpg", exists=True)]))
    report = run_smart_relink_probe(roots=["C:/anywhere"], scanner=scanner)

    assert report == {"missing_assets": 0, "results": []}


def test_probe_reports_unresolved_when_no_candidate_found(capsys):
    scanner = _FakeScanner(_result([_ref("nowhere_to_be_found.jpg", r"C:\proj\nowhere_to_be_found.jpg", exists=False)]))
    report = run_smart_relink_probe(roots=["C:/empty_but_valid"], scanner=scanner)

    assert report["results"][0]["candidates"] == []
    assert "unresolved" in capsys.readouterr().out


def test_probe_without_manifest_or_explicit_roots_reports_error(monkeypatch, capsys):
    import corona_doctor.devtools.smart_relink_probe as probe_module

    monkeypatch.setattr(probe_module, "load_torture_manifest", lambda: None)
    scanner = _FakeScanner(_result([_ref("wood.jpg", r"C:\proj\wood.jpg", exists=False)]))

    report = run_smart_relink_probe(scanner=scanner)
    assert "error" in report
