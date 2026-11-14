"""Distribution, import isolation and evidence-honesty regressions."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

import pytest

from source_lab.cli.run_detection import main as detect
from source_lab.collectors.browser.runner import BrowserCanaryRunner
from source_lab.evidence.schema import TargetIdentity
from source_lab.evidence.session import SessionBundleReader
from source_lab.paths import LAB_ROOT
from source_lab.pipeline.merge_csvs import merge_extension_csvs

FIXTURES = Path(__file__).parent / "fixtures/injection"


def run_cli(tmp_path, *args):
    return subprocess.run([sys.executable, str(LAB_ROOT / "run.py"), *args], cwd=tmp_path,
                          env={**os.environ, "SOURCE_LAB_STORAGE": str(tmp_path / "state")},
                          capture_output=True, text=True, timeout=30)


# @lat: [[source-tests#Distribution#Read-only readiness]]
def test_readiness_and_setup(tmp_path):
    result = run_cli(tmp_path, "status", "--json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["state"] == "ready" and not report["resources"]["required"]
    assert not (tmp_path / "state").exists()
    assert run_cli(tmp_path, "setup").returncode == 0
    assert (tmp_path / "state/analysis").is_dir()
    assert not (tmp_path / "state/resources").exists()
    if os.name != "nt":
        assert (tmp_path / "state").stat().st_mode & 0o077 == 0


# @lat: [[source-tests#Distribution#Five-platform CLI reports]]
@pytest.mark.parametrize("platform,fixture", [("browser-extension", "browser_positive"),
    ("windows-app", "windows_fixture"), ("android-app", "android_fixture"),
    ("ios-app", "ios_fixture"), ("macos-app", None)])
def test_cli_reports(tmp_path, platform, fixture):
    target = FIXTURES / fixture if fixture else tmp_path / "Sample.app"
    if fixture is None:
        target.mkdir()
        (target / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "test.example.sample"}))
        (target / "Hook.m").write_text("void inspect(void) { method_exchangeImplementations(a, b); }\n")
    output = tmp_path / "reports"
    result = run_cli(tmp_path, "detect", str(target), "--platform", platform, "-o", str(output))
    assert result.returncode == 0, result.stderr
    assert {p.name for p in output.iterdir()} >= {"analysis-v2.json", "findings.json", "coverage.json", "report.sarif", "summary.md", "report.stix.json"}
    analysis = json.loads((output / "analysis-v2.json").read_text())
    assert analysis["coverage"]["platform"] == platform
    assert analysis["coverage"]["scanned_files"] > 0 and analysis["scorecard"]
    assert all(f["state"] in {"capability", "static_lead"} for f in analysis["findings"])


# @lat: [[source-tests#Distribution#Per-target output isolation]]
def test_default_output_isolation(tmp_path):
    for parent in ("first", "second"):
        target = tmp_path / parent / "sample"
        target.mkdir(parents=True)
        (target / "manifest.json").write_text('{"manifest_version": 3, "name": "Local fixture", "version": "1"}')
        result = run_cli(tmp_path, "detect", str(target))
        assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "state/analysis").glob("*/analysis-v2.json"))) == 2
    assert run_cli(tmp_path, "detect", "missing", "-o", str(tmp_path / "absent")).returncode == 1
    assert not (tmp_path / "absent").exists()


# @lat: [[source-tests#Distribution#Module isolation]]
def test_module_isolation():
    code = '''
import sys, types
for name in ("analyzers", "evidence", "collectors", "cli", "pipeline", "sourcemap"):
    sys.modules[name] = types.ModuleType(name)
from source_lab.cli.run_detection import detect_platform
from source_lab.sourcemap import RepoMap
assert detect_platform and RepoMap
assert all(not hasattr(sys.modules[n], "__file__") for n in ("analyzers", "evidence", "cli"))
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=LAB_ROOT / "engine", capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


# @lat: [[source-tests#Distribution#Unsupported VM commands]]
def test_unsupported_vm_commands(tmp_path):
    for command in ("start", "resize", "shell", "reset"):
        result = run_cli(tmp_path, command)
        assert result.returncode == 2 and "Unsupported Source Lab command" in result.stderr
    assert not (tmp_path / "state").exists()


# @lat: [[source-tests#Distribution#Synthetic evidence stays static]]
def test_synthetic_evidence_stays_static(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    target = FIXTURES / "browser_positive"
    session = BrowserCanaryRunner(tmp_path, TargetIdentity(identifier=target.name)).run_session()
    reader = SessionBundleReader(session)
    assert reader.verify_integrity()["signature_verified"]
    assert reader.get_metadata().collector.profile_mode == "synthetic"
    out = tmp_path / "out"
    assert detect([str(target), "--session", str(session), "-o", str(out)]) == 0
    analysis = json.loads((out / "analysis-v2.json").read_text())
    assert analysis["findings"]
    assert all(f["state"] in {"capability", "static_lead"} for f in analysis["findings"])
    assert any("Synthetic session" in text for text in analysis["coverage"]["limitations"])


# @lat: [[source-tests#Distribution#Catalog inputs remain unchanged]]
def test_catalog_inputs_remain_unchanged(tmp_path):
    sources = tmp_path / "resources"
    sources.mkdir()
    catalog = sources / "browser-extensions.csv"
    catalog.write_text("Category,Extension,Repo Link,Description\n")
    before = catalog.read_bytes()
    output = tmp_path / "state/catalogs"
    merge_extension_csvs(sources, tmp_path / "analysis", output)
    assert catalog.read_bytes() == before
    assert {p.name for p in sources.iterdir()} == {"browser-extensions.csv"}
    assert (output / "browser-extensions-merged.csv").is_file()


# @lat: [[source-tests#Distribution#Standalone PE input]]
def test_standalone_pe_is_scanned(tmp_path):
    from builders import build_pe
    target = tmp_path / "sample.exe"
    target.write_bytes(build_pe(imports={"kernel32.dll": ["CreateRemoteThread"]}))
    output = tmp_path / "reports"
    assert detect([str(target), "-o", str(output)]) == 0
    findings = json.loads((output / "findings.json").read_text())
    assert any(f["finding_id"] == "windows.pe.injection-api.createremotethread" for f in findings)
    assert json.loads((output / "coverage.json").read_text())["scanned_files"] == 1
