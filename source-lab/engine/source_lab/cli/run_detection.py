#!/usr/bin/env python3
"""Unified CLI runner for multi-platform injection detection and forensic correlation.

Usage:
  python3 -m source_lab.cli.run_detection /path/to/target -o ./out
  python3 -m source_lab.cli.run_detection target.apk -o ./out
  python3 -m source_lab.cli.run_detection target.ipa -o ./out
  python3 -m source_lab.cli.run_detection /path/to/ext --session runtime-sessions/ses_123 -o ./out
  python3 -m source_lab.cli.run_detection /path/to/ext --run-canary https://example.test -o ./out
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

from source_lab.analyzers import (
    AndroidAppAnalyzer,
    BrowserExtensionAnalyzer,
    IOSAppAnalyzer,
    MacOSAppAnalyzer,
    WindowsAppAnalyzer,
)
from source_lab.evidence.correlate import Correlator
from source_lab.evidence.heuristics import enrich_findings
from source_lab.evidence.report import ReportExporter
from source_lab.evidence.schema import (
    Coverage,
    Finding,
    PlatformType,
    TargetIdentity,
    utcnow_iso,
)
from source_lab.evidence.session import SessionBundleReader, SessionKeyError, load_hmac_key
from source_lab.paths import Paths


def _is_electron_project(p: Path) -> bool:
    """Returns True when package.json marks the folder as an Electron app."""
    package_json = p / "package.json"
    if not package_json.is_file():
        return False
    try:
        data = json.loads(package_json.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False
    return (
        "electron" in data.get("devDependencies", {})
        or "electron" in data.get("dependencies", {})
        or "main" in data
    )


# @lat: [[source-lab#Detection]]
def detect_platform(target_path: Path) -> PlatformType:
    """Auto-detects the platform type of the target path."""
    p = Path(target_path)

    # File based detection
    if p.is_file():
        ext = p.suffix.lower()
        if ext in {".apk", ".xapk", ".apks", ".aab"}:
            return PlatformType.ANDROID_APP
        if ext == ".ipa":
            return PlatformType.IOS_APP
        if ext in {".exe", ".dll", ".sys", ".node"}:
            return PlatformType.WINDOWS_APP

    # Directory based detection
    if p.is_dir():
        if (p / "manifest.json").is_file() or (p / "src/manifest.json").is_file():
            return PlatformType.BROWSER_EXTENSION
        if (p / "AndroidManifest.xml").is_file() or (p / "app/src/main/AndroidManifest.xml").is_file():
            return PlatformType.ANDROID_APP
        if any(p.glob("*.xcodeproj")) or (p / "embedded.mobileprovision").is_file():
            return PlatformType.IOS_APP
        if p.suffix.lower() == ".app":
            return PlatformType.MACOS_APP
        plist_path = p / "Info.plist"
        if plist_path.is_file():
            try:
                plist_data = plistlib.loads(plist_path.read_bytes())
            except Exception:
                plist_data = {}
            if plist_data.get("LSRequiresIPhoneOS") is True or plist_data.get("UIDeviceFamily"):
                return PlatformType.IOS_APP
            return PlatformType.MACOS_APP
        if any(p.glob("*.sln")) or any(p.glob("*.vcxproj")):
            return PlatformType.WINDOWS_APP
        if _is_electron_project(p):
            return PlatformType.WINDOWS_APP

    # Default to browser extension
    return PlatformType.BROWSER_EXTENSION


# @lat: [[source-lab#Detection]]
def _session_integrity_problems(reader: SessionBundleReader) -> List[str]:
    """Returns the reasons a session bundle cannot be trusted, if any."""
    result = reader.verify_integrity()
    problems = list(result.get("mismatches", []))
    if result.get("error"):
        problems.append(result["error"])
    if not result.get("signature_verified"):
        problems.append("manifest signature not verified")
    if not result.get("valid") and not problems:
        problems.append("manifest hashes not verified")
    return problems


def _verified_events(reader: SessionBundleReader, coverage: Coverage) -> list:
    metadata = reader.get_metadata()
    if metadata.collector.profile_mode == "synthetic":
        coverage.limitations.append("Synthetic session: simulated events are excluded from runtime correlation.")
        return []
    if metadata.collector.profile_mode == "collection_failed":
        coverage.limitations.append("Browser collection failed; events are excluded from runtime correlation.")
        return []
    if metadata.platform != coverage.platform or metadata.target.identifier != coverage.target.identifier:
        coverage.limitations.append("Runtime session does not match the analyzed target and platform; events ignored.")
        return []
    coverage.limitations.extend(metadata.limitations)
    return reader.read_events()


# @lat: [[source-lab#Detection]]
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-platform injection detection and forensic correlation workbench.")
    parser.add_argument("target", help="Path to target directory, package, or repository.")
    parser.add_argument("-o", "--output", help="Output directory (default: private per-target analysis storage).")
    parser.add_argument("--platform", choices=["browser-extension", "windows-app", "macos-app", "android-app", "ios-app"], help="Force specific platform analyzer.")
    parser.add_argument("--session", help="Path to a runtime session directory (runtime-sessions/<id>) for correlation.")
    parser.add_argument("--run-canary", help="Run dynamic browser canary against the specified test URL.")
    parser.add_argument("--format", choices=["all", "json", "sarif", "markdown", "stix"], default="all", help="Output report format.")

    args = parser.parse_args(argv)
    target_path = Path(args.target).resolve()
    if not target_path.exists():
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        return 1

    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", target_path.name)[:80] or "target"
    identity = hashlib.sha256(str(target_path).encode()).hexdigest()[:12]
    out_dir = Path(args.output).resolve() if args.output else Paths.from_env().analysis / f"{slug}__{identity}"
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Resolve platform
    if args.platform:
        platform_type = PlatformType(args.platform)
    else:
        platform_type = detect_platform(target_path)

    print(f"[*] Target: {target_path.name}")
    print(f"[*] Detected platform: {platform_type.value}")

    target_id = TargetIdentity(
        identifier=target_path.name,
        package_name=target_path.stem,
    )

    # 1. Static Analysis
    print(f"[*] Running static analysis with {platform_type.value} analyzer...")
    analyzer_map = {
        PlatformType.BROWSER_EXTENSION: BrowserExtensionAnalyzer,
        PlatformType.WINDOWS_APP: WindowsAppAnalyzer,
        PlatformType.MACOS_APP: MacOSAppAnalyzer,
        PlatformType.ANDROID_APP: AndroidAppAnalyzer,
        PlatformType.IOS_APP: IOSAppAnalyzer,
    }

    analyzer = analyzer_map[platform_type](target_identity=target_id)
    findings, coverage = analyzer.analyze(target_path)
    print(f"[+] Static analysis complete: {len(findings)} finding(s), {coverage.scanned_files} scanned file(s).")

    # 2. Dynamic Collection (Optional Live Canary)
    runtime_events = []
    session_key_error: Optional[str] = None
    try:
        load_hmac_key()
    except SessionKeyError as exc:
        session_key_error = str(exc)

    def skip_runtime_evidence(detail: str) -> None:
        limitation = "runtime evidence skipped: no session key configured"
        if limitation not in coverage.limitations:
            coverage.limitations.append(limitation)
        print(f"[!] Runtime evidence skipped: {detail}", file=sys.stderr)

    if args.run_canary and platform_type == PlatformType.BROWSER_EXTENSION:
        if session_key_error:
            skip_runtime_evidence(session_key_error)
        else:
            print(f"[*] Running dynamic canary against URL: {args.run_canary}...")
            try:
                from source_lab.collectors.browser.runner import BrowserCanaryRunner
                runner = BrowserCanaryRunner(output_root=out_dir, target_id=target_id)
                session_dir = runner.run_session(test_url=args.run_canary, extension_dir=target_path if target_path.is_dir() else None)
                reader = SessionBundleReader(session_dir)
                problems = _session_integrity_problems(reader)
                if problems:
                    coverage.limitations.append(
                        "Runtime session integrity verification failed: " + "; ".join(problems)
                    )
                    print("[!] Canary session failed integrity verification; events ignored.", file=sys.stderr)
                else:
                    runtime_events = _verified_events(reader, coverage)
                    print(f"[+] Dynamic canary run recorded session: {session_dir.name} with {len(runtime_events)} event(s).")
            except SessionKeyError as e:
                skip_runtime_evidence(str(e))
            except Exception as e:
                coverage.limitations.append(f"Dynamic canary execution failed: {e}")
                print(f"[!] Dynamic canary execution failed: {e}", file=sys.stderr)

    # 3. Dynamic Telemetry Import (Optional Existing Session)
    if args.session:
        session_path = Path(args.session).resolve()
        if session_path.is_dir():
            if session_key_error:
                skip_runtime_evidence(session_key_error)
            else:
                print(f"[*] Importing runtime session: {session_path}...")
                try:
                    reader = SessionBundleReader(session_path)
                    problems = _session_integrity_problems(reader)
                except SessionKeyError as e:
                    skip_runtime_evidence(str(e))
                except Exception as e:
                    coverage.limitations.append(f"Runtime session could not be read: {e}")
                    print(f"[!] Session could not be read: {e}", file=sys.stderr)
                else:
                    if problems:
                        coverage.limitations.append(
                            "Runtime session integrity verification failed: " + "; ".join(problems)
                        )
                        print("[!] Session failed integrity verification; events ignored.", file=sys.stderr)
                    else:
                        runtime_events = _verified_events(reader, coverage)
                        print(f"[+] Read {len(runtime_events)} runtime event(s) from session.")
        else:
            coverage.limitations.append("Runtime session directory not found; static analysis only.")
            print(f"[!] Session directory not found: {session_path}", file=sys.stderr)

    # 4. Correlation
    if runtime_events:
        print(f"[*] Correlating {len(findings)} static finding(s) with {len(runtime_events)} runtime event(s)...")
        correlator = Correlator()
        findings = correlator.correlate(findings, runtime_events, target_override=target_id)
        correlated_count = sum(1 for f in findings if f.state.value == "correlated_behavior")
        print(f"[+] Correlation finished: {correlated_count} confirmed correlated finding(s).")

    # 5. Stamp H1-H5 dimensions and decision-matrix guidance, then export
    enrich_findings(findings)
    exporter = ReportExporter(findings=findings, coverage=coverage, target=target_id)

    if args.format in ("all", "json"):
        exporter.export_analysis_v2(out_dir / "analysis-v2.json")
        exporter.export_findings_json(out_dir / "findings.json")
        (out_dir / "coverage.json").write_text(json.dumps(coverage.to_dict(), indent=2))
        print(f"[+] Written V2 JSON artifacts to {out_dir}")

    if args.format in ("all", "sarif"):
        sarif_path = out_dir / "report.sarif"
        exporter.export_sarif(sarif_path)
        print(f"[+] Written SARIF 2.1 report to {sarif_path}")

    if args.format in ("all", "markdown"):
        md_path = out_dir / "summary.md"
        exporter.export_markdown(md_path)
        print(f"[+] Written Markdown summary to {md_path}")

    if args.format in ("all", "stix"):
        stix_path = out_dir / "report.stix.json"
        exporter.export_stix(stix_path)
        print(f"[+] Written STIX 2.1 bundle to {stix_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
