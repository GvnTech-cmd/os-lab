"""Tests for report exports, including STIX 2.1."""

import json
import sys
from pathlib import Path

from source_lab.cli import run_detection
from source_lab.evidence.report import EvidenceReportWriter
from source_lab.evidence.schema import (
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
)

FIXTURES = Path(__file__).parent / "fixtures" / "injection"


def _finding(finding_id: str, platform: PlatformType) -> Finding:
    return Finding(
        finding_id=finding_id,
        platform=platform,
        target=TargetIdentity(identifier="test/target"),
        phase="static",
        state=FindingState.STATIC_LEAD,
        severity=SeverityLevel.HIGH,
        confidence=0.8,
        evidence=[],
        scope=FindingScope(),
        hypothesis="Test finding.",
    )


# @lat: [[source-tests#Reports#STIX platform pattern]]
def test_stix_uses_each_finding_platform(tmp_path):
    findings = [
        _finding("browser.wrapped-fetch", PlatformType.BROWSER_EXTENSION),
        _finding("windows.injected-thread", PlatformType.WINDOWS_APP),
    ]

    bundle = EvidenceReportWriter(tmp_path).export_stix(TargetIdentity(identifier="test/target"), findings)

    indicators = [obj for obj in bundle["objects"] if obj["type"] == "indicator"]
    assert len(indicators) == 2

    patterns = {indicator["name"]: indicator["pattern"] for indicator in indicators}
    assert "browser-extension" in patterns["browser.wrapped-fetch"]
    assert "windows-app" in patterns["windows.injected-thread"]
    assert "windows-app" not in patterns["browser.wrapped-fetch"]
    assert indicators[0]["confidence"] == 80


# @lat: [[source-tests#Reports#STIX CLI format]]
def test_cli_writes_stix_bundle(tmp_path):
    out = tmp_path / "out"
    argv = [
        "run_detection",
        str(FIXTURES / "browser_positive"),
        "-o",
        str(out),
        "--platform",
        "browser-extension",
        "--format",
        "stix",
    ]
    old_argv = sys.argv
    sys.argv = argv
    try:
        assert run_detection.main() == 0
    finally:
        sys.argv = old_argv

    stix_path = out / "report.stix.json"
    assert stix_path.is_file()
    bundle = json.loads(stix_path.read_text(encoding="utf-8"))
    assert bundle["type"] == "bundle"
    assert any(obj["type"] == "indicator" for obj in bundle["objects"])
    assert not (out / "findings.json").exists()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
