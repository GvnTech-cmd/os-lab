"""The portable acceptance command must use only owned fixtures and sanitized output."""
import json
from pathlib import Path
import subprocess
import sys


def test_portable_acceptance_without_site_packages_or_other_tools(tmp_path):
    root = Path(__file__).resolve().parents[3]
    report = tmp_path / "acceptance.json"
    result = subprocess.run([sys.executable, str(root / "source-lab/acceptance.py"), "--out", str(report)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    value = json.loads(report.read_text())
    assert value["passed"] and len(value["checks"]) == 6
    assert value["checks"][0]["gitNodeAbsent"]
    assert all(check.get("runtimeClaims", 0) == 0 for check in value["checks"])
    assert str(root) not in report.read_text() and str(tmp_path) not in report.read_text()
