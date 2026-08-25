"""Unit tests for TXT-00x texture rules. No 3ds Max required."""

from __future__ import annotations

from corona_doctor.core.models import Severity
from corona_doctor.core.rules import RuleEngine
from corona_doctor.core.texture_models import (
    ExternalTextureReference,
    PathInfo,
    PathType,
    SceneInventory,
    TextureScanFacts,
    TextureThresholds,
)
from corona_doctor.rules.definitions.texture_rules import build_texture_rules


def _path_info(raw: str, exists: bool | None = True, path_type: PathType = PathType.LOCAL) -> PathInfo:
    normalized = raw
    return PathInfo(raw_path=raw, normalized_path=normalized, comparison_key=normalized.lower(), path_type=path_type, exists=exists)


def _ref(
    filename: str,
    path: str,
    exists: bool | None = True,
    width: int | None = None,
    height: int | None = None,
    size_bytes: int | None = None,
    path_type: PathType = PathType.LOCAL,
    reference_count: int = 1,
) -> ExternalTextureReference:
    return ExternalTextureReference(
        ref_id=f"ref-{filename}",
        map_class="CoronaBitmap",
        map_name=filename,
        material_name="Mat_A",
        object_names=("Box01",),
        path_info=_path_info(path, exists=exists, path_type=path_type),
        filename=filename,
        extension=filename.rsplit(".", 1)[-1].lower(),
        file_size_bytes=size_bytes,
        file_size_human="unknown",
        width=width,
        height=height,
        reference_count=reference_count,
    )


def _facts(*refs: ExternalTextureReference) -> TextureScanFacts:
    return TextureScanFacts(inventory=SceneInventory(), texture_references=refs)


def _run(facts: TextureScanFacts, thresholds: TextureThresholds | None = None):
    engine = RuleEngine(build_texture_rules(thresholds))
    return {f.rule_id: f for f in engine.run({"texture_facts": facts})}


def test_no_findings_for_empty_facts():
    findings = _run(_facts())
    assert findings == {}


def test_txt001_missing_texture():
    ref = _ref("wood.jpg", r"C:\proj\wood.jpg", exists=False)
    findings = _run(_facts(ref))
    assert "TXT-001" in findings
    assert findings["TXT-001"].severity == Severity.CRITICAL
    assert "wood.jpg" in findings["TXT-001"].affected_items


def test_txt001_not_triggered_when_exists_unknown():
    ref = _ref("wood.jpg", "textures/wood.jpg", exists=None, path_type=PathType.RELATIVE)
    findings = _run(_facts(ref))
    assert "TXT-001" not in findings


def test_txt002_duplicate_reference_same_path():
    a = _ref("wood.jpg", r"C:\proj\wood.jpg", exists=True, reference_count=2)
    b = _ref("wood.jpg", r"C:\proj\wood.jpg", exists=True, reference_count=2)
    findings = _run(_facts(a, b))
    assert "TXT-002" in findings
    assert findings["TXT-002"].severity == Severity.OPTIMIZATION


def test_txt002_not_triggered_for_single_reference():
    ref = _ref("wood.jpg", r"C:\proj\wood.jpg")
    findings = _run(_facts(ref))
    assert "TXT-002" not in findings


def test_txt003_potential_duplicate_different_paths_same_filename_size():
    a = _ref("wood.jpg", r"C:\proj\wood.jpg", size_bytes=1000)
    b = _ref("wood.jpg", r"Z:\assets\wood.jpg", size_bytes=1000)
    findings = _run(_facts(a, b))
    assert "TXT-003" in findings
    assert findings["TXT-003"].confidence < 1.0


def test_txt003_not_triggered_for_different_sizes():
    a = _ref("wood.jpg", r"C:\proj\wood.jpg", size_bytes=1000)
    b = _ref("wood.jpg", r"Z:\assets\wood.jpg", size_bytes=2000)
    findings = _run(_facts(a, b))
    assert "TXT-003" not in findings


def test_txt003_not_triggered_for_same_path():
    # Same comparison_key is TXT-002's domain, not TXT-003's.
    a = _ref("wood.jpg", r"C:\proj\wood.jpg", size_bytes=1000)
    b = _ref("wood.jpg", r"C:\proj\wood.jpg", size_bytes=1000)
    findings = _run(_facts(a, b))
    assert "TXT-003" not in findings


def test_txt004_oversized_warning_tier():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", width=10000, height=8500)
    findings = _run(_facts(ref))
    assert "TXT-004" in findings
    assert findings["TXT-004"].severity == Severity.OPTIMIZATION


def test_txt004_oversized_strong_tier_escalates_severity():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", width=20000, height=16500)
    findings = _run(_facts(ref))
    assert "TXT-004" in findings
    assert findings["TXT-004"].severity == Severity.WARNING


def test_txt004_not_triggered_below_threshold():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", width=4096, height=4096)
    findings = _run(_facts(ref))
    assert "TXT-004" not in findings


def test_txt004_not_triggered_when_dimensions_unknown():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", width=None, height=None)
    findings = _run(_facts(ref))
    assert "TXT-004" not in findings


def test_txt005_large_file():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", size_bytes=150 * 1024 * 1024)
    findings = _run(_facts(ref))
    assert "TXT-005" in findings


def test_txt005_not_triggered_below_threshold():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", size_bytes=10 * 1024 * 1024)
    findings = _run(_facts(ref))
    assert "TXT-005" not in findings


def test_txt006_local_workstation_path():
    ref = _ref("wood.jpg", r"C:\Users\alice\Desktop\wood.jpg", path_type=PathType.LOCAL)
    findings = _run(_facts(ref))
    assert "TXT-006" in findings
    assert findings["TXT-006"].severity == Severity.INFO


def test_txt006_not_triggered_for_project_path():
    ref = _ref("wood.jpg", r"C:\Project\Textures\wood.jpg", path_type=PathType.LOCAL)
    findings = _run(_facts(ref))
    assert "TXT-006" not in findings


def test_txt006_not_triggered_for_network_path():
    ref = _ref("wood.jpg", r"\\server\assets\wood.jpg", path_type=PathType.NETWORK_UNC)
    findings = _run(_facts(ref))
    assert "TXT-006" not in findings


def test_thresholds_are_configurable():
    ref = _ref("rock.jpg", r"C:\proj\rock.jpg", width=5000, height=4096)
    default_findings = _run(_facts(ref))
    assert "TXT-004" not in default_findings

    strict = TextureThresholds(oversized_warning_px=4096, oversized_strong_warning_px=8192)
    strict_findings = _run(_facts(ref), thresholds=strict)
    assert "TXT-004" in strict_findings
