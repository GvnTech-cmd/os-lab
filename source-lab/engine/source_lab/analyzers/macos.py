"""macOS desktop static analyzer.

Audits:
- Mach-O headers & load commands:
  - LC_LOAD_DYLIB, LC_RPATH, LC_LOAD_WEAK_DYLIB
  - Sections: __DATA,__interpose and __DATA_CONST,__interpose (dyld interposition)
- Objective-C runtime swizzling:
  - method_exchangeImplementations, class_replaceMethod, class_addMethod
- WKWebView script registration:
  - WKUserScript, addUserScript:, addScriptMessageHandler:name:
  - WKContentWorld configuration
"""

from __future__ import annotations

import plistlib
import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import inapp, macos_rules
from ._common import scan_text
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

MAX_BINARY_BYTES = 256 * 1024 * 1024

MACHO_MAGICS = {
    0xFEEDFACE: ("Mach-O 32-bit LE", "<"),
    0xCEFAEDFE: ("Mach-O 32-bit BE", ">"),
    0xFEEDFACF: ("Mach-O 64-bit LE", "<"),
    0xCFFFAEDFE: ("Mach-O 64-bit BE", ">"),
    0xCAFEBABE: ("Mach-O Universal Fat", ">"),
}

SWIZZLE_PATTERNS = [
    (
        "macos.objc.method-swizzle",
        r"method_exchangeImplementations\s*\(",
        SeverityLevel.HIGH,
        0.8,
        "method_exchangeImplementations",
        "Swizzles Objective-C method implementations at runtime to intercept selector calls.",
    ),
    (
        "macos.objc.class-replace-method",
        r"class_replaceMethod\s*\(",
        SeverityLevel.HIGH,
        0.75,
        "class_replaceMethod",
        "Dynamically replaces class method implementation with a custom hook handler.",
    ),
    (
        "macos.wkwebview.user-script",
        r"WKUserScript\s*alloc\s*\]\s*initWithSource:|addUserScript:",
        SeverityLevel.HIGH,
        0.8,
        "WKUserScript injection",
        "Registers a WKUserScript for injection into all frames or top frame in WKWebView.",
    ),
    (
        "macos.wkwebview.script-bridge",
        r"addScriptMessageHandler\s*:\s*(\w+)\s*name\s*:\s*@?[\"'](\w+)[\"']",
        SeverityLevel.MEDIUM,
        0.7,
        "WKScriptMessageHandler bridge",
        "Exposes a native script message handler bridge to web content in WKWebView.",
    ),
]


class MacOSAppAnalyzer:
    """Static analyzer for macOS app bundles and Mach-O binaries."""

    def __init__(self, target_identity: Optional[TargetIdentity] = None):
        self.target = target_identity or TargetIdentity("macos-app")

    def identify(self, root: Path) -> bool:
        """Checks if directory contains a macOS .app bundle or Mach-O binary."""
        for p in root.rglob("*"):
            if p.suffix.lower() == ".app" or p.name == "Info.plist":
                return True
        return False

    def analyze(self, root: Path) -> Tuple[List[Finding], Coverage]:
        root = Path(root)
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        # 1. Info.plist & App bundle metadata
        for p in root.rglob("Info.plist"):
            if any(x in p.parts for x in (".git", "node_modules")):
                continue
            scanned_files += 1
            rel = str(p.relative_to(root))
            try:
                data = plistlib.loads(p.read_bytes())
                bundle_id = data.get("CFBundleIdentifier")
                version = data.get("CFBundleShortVersionString")
                if bundle_id:
                    span = EvidenceSpan(file=rel, symbol="CFBundleIdentifier", artifact="manifest", snippet=f"{bundle_id} ({version})")
                    findings.append(Finding(
                        finding_id="macos.bundle.identity",
                        platform=PlatformType.MACOS_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.CAPABILITY,
                        severity=SeverityLevel.INFO,
                        confidence=0.9,
                        evidence=[span],
                        scope=FindingScope(process=bundle_id),
                        hypothesis=f"App bundle identifier: {bundle_id} (version {version}).",
                    ))
                findings.extend(macos_rules.analyze_info_plist_environment(rel, data, self.target))
            except Exception as e:
                limitations.append(f"Failed to parse {p.name}: {e}")

        # 1b. Other plists (launchd jobs, helper tools) that set DYLD_* variables
        for p in root.rglob("*.plist"):
            if p.name == "Info.plist" or any(x in p.parts for x in (".git", "node_modules", "Pods", "Carthage")):
                continue
            try:
                parsed = plistlib.loads(p.read_bytes())
                if isinstance(parsed, dict):
                    findings.extend(macos_rules.analyze_info_plist_environment(str(p.relative_to(root)), parsed, self.target))
            except Exception:
                pass

        # 2. Source code review for Objective-C / Swift hooking & WKWebView
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".m", ".mm", ".swift", ".h", ".c", ".cpp"}:
                if any(x in p.parts for x in (".git", "node_modules", "Pods", "Carthage")):
                    skipped_files += 1
                    continue
                scanned_files += 1
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    rel = str(p.relative_to(root))
                    for fid, pattern, sev, conf, sym, hyp in SWIZZLE_PATTERNS:
                        m = re.search(pattern, text)
                        if m:
                            line_no = text[:m.start()].count("\n") + 1
                            span = EvidenceSpan(
                                file=rel,
                                line=line_no,
                                symbol=sym,
                                artifact="source",
                                snippet=text.splitlines()[line_no - 1].strip()[:160],
                            )
                            findings.append(Finding(
                                finding_id=fid,
                                platform=PlatformType.MACOS_APP,
                                target=self.target,
                                phase="static",
                                state=FindingState.STATIC_LEAD,
                                severity=sev,
                                confidence=conf,
                                evidence=[span],
                                scope=FindingScope(process="host", world="MAIN"),
                                hypothesis=hyp,
                                alternative_explanations=["Analytics SDK, UI component swizzling, or legitimate WebView wrapper."],
                            ))
                    findings.extend(scan_text(rel, text, macos_rules.SOURCE_RULES + inapp.RULES, self.target, PlatformType.MACOS_APP, max_per_rule=1))
                except Exception:
                    pass

        # 3. Binary Mach-O inspection: load commands, rpaths, sections, symbols, signature and entitlements
        for p in root.rglob("*"):
            if not p.is_file() or any(x in p.parts for x in (".git", "node_modules")):
                continue
            in_bundle_bin = "MacOS" in p.parts or "Frameworks" in p.parts
            if not (p.suffix.lower() in {".dylib", ".so"} or "." not in p.name or in_bundle_bin):
                continue
            try:
                if p.stat().st_size > MAX_BINARY_BYTES:
                    limitations.append(f"Skipped {p.name}: larger than {MAX_BINARY_BYTES // (1024 * 1024)} MB")
                    continue
                data = p.read_bytes()
                rel = str(p.relative_to(root))
                macho_findings, was_macho = macos_rules.analyze_macho_file(rel, data, p, self.target)
                if was_macho:
                    scanned_files += 1
                    findings.extend(macho_findings)
                elif len(data) >= 4 and (struct.unpack(">I", data[:4])[0] in MACHO_MAGICS or struct.unpack("<I", data[:4])[0] in MACHO_MAGICS):
                    limitations.append(f"{rel} looks like Mach-O but could not be parsed; only a string search was applied")
                    if b"__interpose" in data:
                        findings.append(Finding(
                            finding_id="macos.macho.dyld-interposition",
                            platform=PlatformType.MACOS_APP,
                            target=self.target,
                            phase="static",
                            state=FindingState.CAPABILITY,
                            severity=SeverityLevel.CRITICAL,
                            confidence=0.6,
                            evidence=[EvidenceSpan(file=rel, symbol="__interpose", artifact="binary", offset=hex(data.find(b"__interpose")), snippet="'__interpose' string in an unparsed Mach-O")],
                            scope=FindingScope(process="dyld"),
                            hypothesis="A Mach-O library that could not be parsed contains the __interpose section name.",
                        ))
            except Exception:
                pass

        coverage = Coverage(
            platform=PlatformType.MACOS_APP,
            target=self.target,
            parser_mode="macho_bundle_scanner",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )
        return findings, coverage
