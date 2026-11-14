"""Compatibility checks for exported schemas and generated frontend contracts."""
import json
from pathlib import Path
import pytest
from source_lab.cli.run_detection import main as detect
from source_lab.contracts import schema_document, typescript, validate
from source_lab.paths import LAB_ROOT
from source_lab.sourcemap import RepoMap


# @lat: [[source-tests#Contracts#Evidence artifact compatibility]]
def test_evidence_artifact_compatibility(tmp_path):
    target = Path(__file__).parent / "fixtures/injection/browser_positive"
    assert detect([str(target), "-o", str(tmp_path)]) == 0
    analysis = json.loads((tmp_path / "analysis-v2.json").read_text())
    assert not validate(analysis, "AnalysisV2")
    for finding in analysis["findings"]:
        assert not validate(finding, "Finding")
    assert not validate(analysis["coverage"], "Coverage")
    analysis["schema_version"] = 9
    assert any("unsupported version" in error for error in validate(analysis, "AnalysisV2"))


# @lat: [[source-tests#Contracts#Malformed findings rejected]]
@pytest.mark.parametrize("changes", [{"confidence": 2}, {"confidence": float("nan")},
    {"state": "confirmed"}, {"evidence": []}, {"target": {"identifier": ""}}])
def test_malformed_findings_rejected(tmp_path, changes):
    target = Path(__file__).parent / "fixtures/injection/browser_positive"
    assert detect([str(target), "-o", str(tmp_path)]) == 0
    finding = json.loads((tmp_path / "findings.json").read_text())[0]
    finding.update(changes)
    assert validate(finding, "Finding")


# @lat: [[source-tests#Contracts#Structural map compatibility]]
def test_structural_map_compatibility(tmp_path):
    (tmp_path / "sample.py").write_text("def greet(name: str) -> str:\n    return name\n")
    document = RepoMap().generate(tmp_path)
    assert not validate(document, "RepoMapV1")
    document["schema_version"] = 2
    assert validate(document, "RepoMapV1")


# @lat: [[source-tests#Contracts#Generated contracts stay current]]
def test_generated_contracts_stay_current():
    assert json.loads((LAB_ROOT / "contracts/schema.json").read_text()) == schema_document()
    assert (LAB_ROOT.parent / "dashboard/src/lib/source-contracts.ts").read_text() == typescript()
