"""Windows desktop static analyzer.

Audits:
- PE headers and imports:
  - Process memory & injection: VirtualAllocEx, WriteProcessMemory, CreateRemoteThread, QueueUserAPC, SetThreadContext
  - Hooking & interception: SetWindowsHookExW, DetourAttach, MinHook
  - DLL search order & proxying
- WebView2 registration:
  - AddScriptToExecuteOnDocumentCreated
  - AddHostObjectToScript
- Electron application review:
  - package.json main script & preload script registration
  - nodeIntegration, contextIsolation settings
"""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import windows_rules
from ._common import scan_text
from .binfmt import parse_asar
from .binfmt.asar import iter_text_entries
from source_lab.evidence.schema import (
    Coverage,
    EvidenceSpan,
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
)

WINDOWS_BINARY_EXTS = {".exe", ".dll", ".sys", ".node"}
MAX_BINARY_BYTES = 512 * 1024 * 1024
WEBVIEW2_PATTERNS = [
    (
        "windows.webview2.document-created-script",
        r"AddScriptToExecuteOnDocumentCreated",
        SeverityLevel.HIGH,
        0.75,
        "WebView2 script injection at document creation",
        "Registers a JavaScript snippet injected into every document and iframe created in WebView2.",
    ),
    (
        "windows.webview2.host-object-bridge",
        r"AddHostObjectToScript",
        SeverityLevel.MEDIUM,
        0.7,
        "WebView2 native COM host object exposure",
        "Exposes a native Win32/COM host object directly to untrusted web content in WebView2.",
    ),
]

class WindowsAppAnalyzer:
    """Static analyzer for Windows binaries and packages."""

    def __init__(self, target_identity: Optional[TargetIdentity] = None):
        self.target = target_identity or TargetIdentity("windows-app")

    def identify(self, root: Path) -> bool:
        """Checks if directory contains Windows binaries or Electron package."""
        p_root = Path(root)
        if p_root.is_file() and p_root.suffix.lower() in WINDOWS_BINARY_EXTS:
            return True
        if (p_root / "package.json").is_file():
            try:
                data = json.loads((p_root / "package.json").read_text(encoding="utf-8", errors="ignore"))
                if "electron" in data.get("devDependencies", {}) or "electron" in data.get("dependencies", {}) or "main" in data:
                    return True
            except Exception:
                pass
        for p in p_root.rglob("*"):
            if p.suffix.lower() in WINDOWS_BINARY_EXTS:
                return True
        return False

    def analyze(self, root: Path) -> Tuple[List[Finding], Coverage]:
        root = Path(root)
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        # 1. Electron package review
        pkg_json = root / "package.json"
        if pkg_json.is_file():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                scanned_files += 1
                main_file = data.get("main")
                if main_file:
                    span = EvidenceSpan(file="package.json", symbol="main", artifact="source", snippet=f"main: {main_file}")
                    findings.append(Finding(
                        finding_id="windows.electron.entrypoint",
                        platform=PlatformType.WINDOWS_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.CAPABILITY,
                        severity=SeverityLevel.INFO,
                        confidence=0.5,
                        evidence=[span],
                        scope=FindingScope(process="main"),
                        hypothesis=f"Electron main process entrypoint defined at '{main_file}'.",
                    ))
            except Exception as e:
                limitations.append(f"Failed to parse package.json: {e}")

        # 2. Binary / PE inspection
        pe_files: List[Path] = []
        for p in ([root] if root.is_file() else root.rglob("*")):
            if p.is_file() and p.suffix.lower() in WINDOWS_BINARY_EXTS:
                if any(x in p.parts for x in (".git", "node_modules")):
                    skipped_files += 1
                    continue
                pe_files.append(p)

        for pe_path in pe_files[:100]:
            scanned_files += 1
            rel = pe_path.name if root.is_file() else str(pe_path.relative_to(root))
            try:
                if pe_path.stat().st_size > MAX_BINARY_BYTES:
                    limitations.append(f"Skipped {pe_path.name}: larger than {MAX_BINARY_BYTES // (1024 * 1024)} MB")
                    continue
                raw_bytes = pe_path.read_bytes()
                findings.extend(self._analyze_pe_bytes(rel, raw_bytes))
                findings.extend(windows_rules.analyze_electron_fuses(rel, raw_bytes, self.target))
            except Exception as e:
                limitations.append(f"Error inspecting {pe_path.name}: {e}")

        # 2b. Electron ASAR archives: scan the packed sources, and flag an app that is not packed at all
        for asar_path in root.rglob("*.asar"):
            if any(x in asar_path.parts for x in (".git", "node_modules")):
                continue
            scanned_files += 1
            rel = str(asar_path.relative_to(root))
            try:
                if asar_path.stat().st_size > MAX_BINARY_BYTES:
                    limitations.append(f"Skipped {asar_path.name}: larger than {MAX_BINARY_BYTES // (1024 * 1024)} MB")
                    continue
                blob = asar_path.read_bytes()
                archive = parse_asar(blob)
                if archive is None:
                    limitations.append(f"{asar_path.name} is not a readable ASAR archive")
                    continue
                for inner, text in iter_text_entries(blob, archive):
                    findings.extend(scan_text(f"{rel}!{inner}", text, windows_rules.ELECTRON_RULES, self.target, PlatformType.WINDOWS_APP, max_per_rule=1))
                unpacked = [e.path for e in archive.entries if e.unpacked]
                if unpacked:
                    limitations.append(f"{asar_path.name}: {len(unpacked)} file(s) are stored unpacked and were not scanned")
            except Exception as e:
                limitations.append(f"Error reading {asar_path.name}: {e}")
        for app_pkg in root.rglob("resources/app/package.json"):
            if any(x in app_pkg.parts for x in (".git", "node_modules")):
                continue
            rel = str(app_pkg.relative_to(root))
            findings.append(Finding(
                finding_id="windows.electron.unpacked-app",
                platform=PlatformType.WINDOWS_APP,
                target=self.target,
                phase="static",
                state=FindingState.CAPABILITY,
                severity=SeverityLevel.MEDIUM,
                confidence=0.6,
                evidence=[EvidenceSpan(file=rel, symbol="resources/app", artifact="source", snippet="Electron app shipped as a plain folder instead of app.asar")],
                scope=FindingScope(process="main"),
                hypothesis="The Electron app is not packed into app.asar, so its code can be edited in place without breaking an integrity check.",
                alternative_explanations=["Development build or an installer that unpacks the app on purpose."],
            ))

        # 3. Text search for WebView2 in source files
        source_count = 0
        for src_path in ([root] if root.is_file() else root.rglob("*")):
            if src_path.is_file() and src_path.suffix.lower() in {".cs", ".cpp", ".c", ".h", ".js", ".ts"}:
                if any(x in src_path.parts for x in (".git", "node_modules")):
                    continue
                try:
                    if source_count >= 500 or src_path.stat().st_size > 512 * 1024:
                        skipped_files += 1
                        if "Source scan limited to 500 files of at most 512 KB each" not in limitations:
                            limitations.append("Source scan limited to 500 files of at most 512 KB each")
                        continue
                    text = src_path.read_text(encoding="utf-8", errors="ignore")
                    source_count += 1
                    scanned_files += 1
                    src_rel = src_path.name if root.is_file() else str(src_path.relative_to(root))
                    for fid, pattern, sev, conf, sym, hyp in WEBVIEW2_PATTERNS:
                        m = re.search(pattern, text)
                        if m:
                            line_no = text[:m.start()].count("\n") + 1
                            span = EvidenceSpan(
                                file=src_rel,
                                line=line_no,
                                symbol=sym,
                                artifact="source",
                                snippet=text.splitlines()[line_no - 1].strip()[:160],
                            )
                            findings.append(Finding(
                                finding_id=fid,
                                platform=PlatformType.WINDOWS_APP,
                                target=self.target,
                                phase="static",
                                state=FindingState.STATIC_LEAD,
                                severity=sev,
                                confidence=conf,
                                evidence=[span],
                                scope=FindingScope(process="renderer", world="MAIN"),
                                hypothesis=hyp,
                                alternative_explanations=["Legitimate WebView2 application bridge."],
                            ))
                    findings.extend(scan_text(src_rel, text, windows_rules.ELECTRON_RULES, self.target, PlatformType.WINDOWS_APP, max_per_rule=1))
                except Exception as exc:
                    limitations.append(f"Error reading {src_path.name}: {exc}")

        coverage = Coverage(
            platform=PlatformType.WINDOWS_APP,
            target=self.target,
            parser_mode="pe_binary_scanner",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )
        return findings, coverage

    def _analyze_pe_bytes(self, rel_path: str, data: bytes) -> List[Finding]:
        """Findings for one PE file; the work lives in windows_rules.analyze_pe."""
        return windows_rules.analyze_pe(rel_path, data, self.target)
