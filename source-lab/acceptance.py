#!/usr/bin/env python3
"""Portable owned-fixture acceptance; emits no private paths, keys or target data."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import subprocess
import sys
import tempfile


def fingerprint(root: Path):
    files = [root / "labctl", root / "android-lab/lab/web_ui.py", root / "source-lab/run.py", root / "source-lab/list_inputs.py", root / "source-lab/acceptance.py"]
    files += list((root / "console").glob("*.py")) + list((root / "console").glob("*.json"))
    files += list((root / "source-lab/engine/source_lab").rglob("*.py"))
    digest = hashlib.sha256()
    for file in sorted(files):
        digest.update(file.relative_to(root).as_posix().encode() + b"\0" + file.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def check(root: Path, installed_only=False, expected=None):
    root = root.resolve()
    report = {"system": platform.system(), "python": platform.python_version(), "checks": [],
              "packagedRuntime": (root / "STAGED.txt").is_file() and not (root / ".git").exists(),
              "manualAcceptance": "Native fresh install/update, GUI, process cleanup and live collection remain separate checks."}
    step = "runtime files"
    try:
        required = ["source-lab/run.py", "source-lab/list_inputs.py", "source-lab/engine/source_lab/import_legacy.py", "console/source_api.py", "console/source_pipeline.json", "dashboard/dist/source/index.html", "dashboard/dist/source/evidence/index.html", "dashboard/dist/source/brain/index.html", "dashboard/dist/source/docs/runbook/index.html"]
        if any(not (root / path).is_file() for path in required) or (installed_only and not report["packagedRuntime"]):
            raise ValueError("Required runtime files or installed-only marker missing")
        report["sourceFingerprint"] = fingerprint(root)
        if expected and report["sourceFingerprint"] != expected:
            raise ValueError("Source fingerprint mismatch")
        stamp = root / ".app-version"
        version = stamp.read_text().strip() if stamp.is_file() and stamp.stat().st_size <= 64 and not stamp.is_symlink() else ""
        report["appVersion"] = version if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", version) else "staged-or-checkout"
        with tempfile.TemporaryDirectory(prefix="oslab-source-acceptance-") as temporary:
            temp = Path(temporary)
            env = dict(os.environ, SOURCE_LAB_STORAGE=str(temp / "state"), SOURCE_LAB_RESOURCES=str(temp / "resources"), PATH="")
            for name in ("GITHUB_TOKEN", "GH_TOKEN", "IQ_SESSION_HMAC_KEY", "IQ_SESSION_HMAC_KEY_FILE"):
                env.pop(name, None)
            def run(label, args):
                nonlocal step
                step = label
                result = subprocess.run([sys.executable, "-I", "-S", str(root / "source-lab/run.py"), *args], cwd=temp,
                                        env=env, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    raise ValueError("Source command failed")
                return result.stdout
            status = json.loads(run("download-free status", ["status", "--json"]))
            assert not (temp / "state").exists()
            assert not status["optional"]["git"] and not status["optional"]["node"]
            report["checks"].append({"step": "status", "passed": True, "readOnly": True, "gitNodeAbsent": True})
            run("private setup", ["setup"])
            fixture_root = root / "source-lab/engine/tests/fixtures/injection"
            mapping = [("browser-extension", "browser_positive"), ("windows-app", "windows_fixture"), ("android-app", "android_fixture"), ("ios-app", "ios_fixture")]
            mac = temp / "Owned.app"
            mac.mkdir()
            (mac / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "org.oslab.owned", "CFBundleExecutable": "Owned"}))
            (mac / "Owned.m").write_text("void owned() { method_exchangeImplementations(0,0); }", encoding="utf-8")
            targets = [(kind, fixture_root / name) for kind, name in mapping] + [("macos-app", mac)]
            for kind, target in targets:
                output = temp / "state/analysis" / ("owned__" + kind)
                run("static " + kind, ["detect", str(target), "--platform", kind, "--output", str(output)])
                findings = json.loads((output / "findings.json").read_text())
                coverage = json.loads((output / "coverage.json").read_text())
                assert coverage["schema_version"] == 2 and coverage["platform"] == kind
                assert not any(f["state"] in ("runtime_observation", "correlated_behavior") for f in findings)
                report["checks"].append({"step": kind, "passed": True, "findings": len(findings), "limitations": len(coverage["limitations"]), "runtimeClaims": 0})
            report["passed"] = True
    except Exception as error:
        report.update(passed=False, failedStep=step, error=type(error).__name__)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--installed-only", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = check(args.root, args.installed_only, args.expected_fingerprint)
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
