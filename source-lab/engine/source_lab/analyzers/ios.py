"""iOS static analyzer for IPAs, app bundles, and source projects.

Audits:
- Info.plist:
  - NSAppTransportSecurity / NSAllowsArbitraryLoads (CORS / HTTP protection bypass)
  - CFBundleURLSchemes (custom URL schemes for external process invocation)
  - UIBackgroundModes (silent background execution)
- embedded.mobileprovision:
  - TeamIdentifier verification
  - get-task-allow (debuggable entitlement allowing task_for_pid attachment)
- WKWebView injection and bridge security:
  - WKUserScript alloc / addUserScript: (script injection at document start)
  - WKContentWorld configuration (page vs isolated world)
  - addScriptMessageHandler:name: (bi-directional native bridge)
  - evaluateJavaScript:completionHandler: (dynamic execution)
- Objective-C / Swift runtime hooking:
  - method_exchangeImplementations, class_replaceMethod, class_addMethod
- Mach-O binary & framework inspection:
  - LC_LOAD_DYLIB, LC_RPATH references to Substrate, ElleKit, FridaGadget
- Tweak filter plists:
  - MobileSubstrate / Substitute filter bundles targeting app processes
"""

from __future__ import annotations

import plistlib
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import inapp, ios_rules
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

IOS_SOURCE_EXTS = {".m", ".h", ".mm", ".swift", ".plist"}

MACHO_MAGICS = {
    0xFEEDFACE: ("Mach-O 32-bit LE", "<"),
    0xCEFAEDFE: ("Mach-O 32-bit BE", ">"),
    0xFEEDFACF: ("Mach-O 64-bit LE", "<"),
    0xCFFFAEDFE: ("Mach-O 64-bit BE", ">"),
    0xCAFEBABE: ("Mach-O Universal Fat", ">"),
}

WKWEBVIEW_PATTERNS = [
    (
        "ios.wkwebview.user-script-injection",
        r"(?:WKUserScript\s*alloc\s*\]\s*initWithSource:|addUserScript:)",
        SeverityLevel.HIGH,
        0.85,
        "WKUserScript injection",
        "Registers a user script injected into WKWebView at document start or end.",
    ),
    (
        "ios.wkwebview.message-handler-bridge",
        r"(?:addScriptMessageHandler:|addScriptMessageHandlerWithReply:.*?name:)",
        SeverityLevel.MEDIUM,
        0.75,
        "addScriptMessageHandler bridge",
        "Registers a native message handler bridge exposed to window.webkit.messageHandlers.",
    ),
    (
        "ios.wkwebview.evaluate-javascript",
        r"evaluateJavaScript:\s*.*?completionHandler:",
        SeverityLevel.MEDIUM,
        0.65,
        "evaluateJavaScript call",
        "Dynamically evaluates JavaScript strings inside the WKWebView instance.",
    ),
]

SWIZZLE_PATTERNS = [
    (
        "ios.objc.method-swizzle",
        r"method_exchangeImplementations\s*\(",
        SeverityLevel.HIGH,
        0.85,
        "method_exchangeImplementations",
        "Swizzles Objective-C method implementations at runtime to intercept selector calls.",
    ),
    (
        "ios.objc.class-replace-method",
        r"class_replaceMethod\s*\(",
        SeverityLevel.HIGH,
        0.8,
        "class_replaceMethod",
        "Dynamically replaces class method implementation with a custom hook handler.",
    ),
    (
        "ios.objc.class-add-method",
        r"class_addMethod\s*\(",
        SeverityLevel.MEDIUM,
        0.6,
        "class_addMethod",
        "Dynamically injects new method selectors into Objective-C class dispatch tables.",
    ),
]

HOOK_FRAMEWORKS = [
    (b"CydiaSubstrate", "Substrate jailbreak hooking framework"),
    (b"ElleKit", "ElleKit rootless tweak injection engine"),
    (b"FridaGadget", "Frida dynamic instrumentation gadget"),
    (b"libhooker", "libhooker runtime hook engine"),
    (b"Substitute", "Substitute dynamic hooking engine"),
]


class IOSAppAnalyzer:
    """Static analyzer for iOS IPA packages, App bundles, and source repositories."""

    def __init__(self, target_identity: Optional[TargetIdentity] = None):
        self.target = target_identity or TargetIdentity("ios-app")

    def identify(self, root: Path) -> bool:
        """Determines if the path is an iOS IPA package (.ipa), .app bundle, or Xcode project."""
        p = Path(root)
        if p.is_file() and p.suffix.lower() == ".ipa":
            return True
        if p.is_dir():
            if p.suffix.lower() == ".app":
                return True
            for name in ("Info.plist", "embedded.mobileprovision"):
                if (p / name).is_file():
                    return True
            for child in p.iterdir():
                if child.suffix.lower() in {".xcodeproj", ".xcworkspace", ".app"}:
                    return True
        return False

    def analyze(self, root: Path) -> Tuple[List[Finding], Coverage]:
        """Runs full static analysis on iOS root or IPA package."""
        root = Path(root)
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        if root.is_file() and root.suffix.lower() == ".ipa":
            return self._analyze_ipa(root)

        # 1. Info.plist check
        plist_path = self._locate_plist(root)
        if plist_path:
            scanned_files += 1
            try:
                findings.extend(self._analyze_info_plist(plist_path, root))
            except Exception as e:
                limitations.append(f"Failed to parse Info.plist: {e}")
        else:
            limitations.append("No Info.plist found in standard iOS paths")

        # 2. embedded.mobileprovision check
        provision_path = root / "embedded.mobileprovision"
        if provision_path.is_file():
            scanned_files += 1
            try:
                findings.extend(self._analyze_mobileprovision(provision_path, root))
            except Exception as e:
                limitations.append(f"Failed to parse embedded.mobileprovision: {e}")

        # 3. Scan Objective-C / Swift sources & tweak plists
        source_files: List[Path] = []
        for p in root.rglob("*"):
            if any(x in p.parts for x in (".git", "DerivedData", "Pods", "Carthage")):
                continue
            injected = ios_rules.analyze_framework_name(str(p.relative_to(root)), self.target)
            if injected and (p.suffix.lower() in (".dylib", ".framework")):
                findings.append(injected)
            if p.is_file():
                if p.suffix.lower() in IOS_SOURCE_EXTS:
                    parts = p.parts
                    if any(x in parts for x in (".git", "build", "DerivedData", "Pods", "Carthage")):
                        skipped_files += 1
                        continue
                    source_files.append(p)
                else:
                    # Check for Mach-O binaries
                    if self._is_macho(p):
                        scanned_files += 1
                        findings.extend(self._analyze_macho(p, root))

        for src in source_files[:500]:
            scanned_files += 1
            try:
                text = src.read_text(encoding="utf-8", errors="ignore")
                src_rel = str(src.relative_to(root))
                findings.extend(self._scan_source_code(src_rel, text))
            except Exception as e:
                limitations.append(f"Error reading {src.name}: {e}")

        coverage = Coverage(
            platform=PlatformType.IOS_APP,
            target=self.target,
            parser_mode="regex_ast_hybrid",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )
        return findings, coverage

    def _locate_plist(self, root: Path) -> Optional[Path]:
        for name in ("Info.plist", "App/Info.plist", "Payload/*.app/Info.plist"):
            matches = list(root.glob(name))
            if matches:
                return matches[0]
        return None

    def _analyze_ipa(self, ipa_path: Path) -> Tuple[List[Finding], Coverage]:
        """Inspects an IPA archive directly without external dependencies."""
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        try:
            with zipfile.ZipFile(ipa_path, "r") as zf:
                namelist = zf.namelist()
                scanned_files = len(namelist)

                # Look for Info.plist in Payload/*.app/
                plist_names = [n for n in namelist if re.match(r"^Payload/[^/]+\.app/Info\.plist$", n)]
                if plist_names:
                    try:
                        plist_bytes = zf.read(plist_names[0])
                        findings.extend(self._parse_plist_bytes(plist_bytes, plist_names[0]))
                    except Exception as e:
                        limitations.append(f"Error parsing Info.plist: {e}")

                # Look for embedded.mobileprovision
                prov_names = [n for n in namelist if "embedded.mobileprovision" in n]
                if prov_names:
                    try:
                        prov_bytes = zf.read(prov_names[0])
                        findings.extend(self._parse_mobileprovision_bytes(prov_bytes, prov_names[0]))
                    except Exception as e:
                        limitations.append(f"Error parsing mobileprovision: {e}")

                # Injected hooking libraries by file name, and jailbreak paths in plists
                for name in namelist:
                    injected = ios_rules.analyze_framework_name(name, self.target, container=ipa_path.name)
                    if injected and name.endswith((".dylib", ".framework/")):
                        findings.append(injected)
                    if name.endswith(".plist") and name.count("/") <= 4:
                        try:
                            blob = zf.read(name)
                            if any(path in blob for path in ios_rules.JAILBREAK_PATHS):
                                findings.append(Finding(
                                    finding_id="ios.jailbreak-path",
                                    rule_id="RULE-IOS-JAILBREAK-PATH",
                                    platform=PlatformType.IOS_APP,
                                    target=self.target,
                                    phase="static",
                                    state=FindingState.STATIC_LEAD,
                                    severity=SeverityLevel.HIGH,
                                    confidence=0.7,
                                    evidence=[EvidenceSpan(file=f"{ipa_path.name}!{name}", artifact="manifest", snippet="plist references a jailbreak tweak path")],
                                    scope=FindingScope(),
                                    hypothesis="The bundle references MobileSubstrate or rootless jailbreak tweak directories.",
                                ))
                        except Exception:
                            pass

                # Look for binary executables and frameworks
                for name in namelist:
                    if name.endswith((".dylib", ".framework/")) or re.match(r"^Payload/[^/]+\.app/[^/.]+$", name) or re.match(r"^Payload/[^/]+\.app/Frameworks/[^/]+\.framework/[^/.]+$", name):
                        try:
                            blob = zf.read(name)
                            findings.extend(ios_rules.analyze_macho_bytes(name, blob, self.target))
                            head = blob[:4096]
                            for sig, desc in HOOK_FRAMEWORKS:
                                if sig in head:
                                    findings.append(
                                        Finding(
                                            finding_id="ios.macho.hook-framework-ref",
                                            rule_id="RULE-IOS-HOOK-FW",
                                            platform=PlatformType.IOS_APP,
                                            target=self.target,
                                            phase="static",
                                            state=FindingState.STATIC_LEAD,
                                            severity=SeverityLevel.CRITICAL,
                                            confidence=0.9,
                                            evidence=[EvidenceSpan(file=name, artifact="binary", snippet=f"Mach-O binary references {desc}")],
                                            scope=FindingScope(),
                                            hypothesis=f"Application binary imports tweak or hooking library: {sig.decode()}.",
                                        )
                                    )
                        except Exception:
                            continue

        except Exception as e:
            limitations.append(f"Failed to read IPA archive: {e}")

        coverage = Coverage(
            platform=PlatformType.IOS_APP,
            target=self.target,
            parser_mode="ipa_archive_binary",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )
        return findings, coverage

    def _analyze_info_plist(self, plist_path: Path, root: Path) -> List[Finding]:
        findings = []
        rel_path = str(plist_path.relative_to(root))
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)

        # Check App Transport Security
        ats = data.get("NSAppTransportSecurity", {})
        if ats.get("NSAllowsArbitraryLoads") is True:
            findings.append(
                Finding(
                    finding_id="ios.plist.allows-arbitrary-loads",
                    rule_id="RULE-IOS-ATS-ALLOWS-ALL",
                    platform=PlatformType.IOS_APP,
                    target=self.target,
                    phase="static",
                    state=FindingState.CAPABILITY,
                    severity=SeverityLevel.HIGH,
                    confidence=1.0,
                    evidence=[EvidenceSpan(file=rel_path, artifact="manifest", snippet="NSAllowsArbitraryLoads = true")],
                    scope=FindingScope(),
                    hypothesis="Application disables App Transport Security (ATS), allowing unencrypted HTTP traffic.",
                )
            )

        # Check Custom URL Schemes
        url_types = data.get("CFBundleURLTypes", [])
        for ut in url_types:
            schemes = ut.get("CFBundleURLSchemes", [])
            for s in schemes:
                findings.append(
                    Finding(
                        finding_id="ios.plist.custom-url-scheme",
                        rule_id="RULE-IOS-URL-SCHEME",
                        platform=PlatformType.IOS_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.CAPABILITY,
                        severity=SeverityLevel.INFO,
                        confidence=0.9,
                        evidence=[EvidenceSpan(file=rel_path, symbol=s, artifact="manifest", snippet=f"CFBundleURLSchemes: {s}")],
                        scope=FindingScope(target_url=f"{s}://"),
                        hypothesis=f"Application registers custom URL scheme '{s}://' accessible by external apps.",
                    )
                )

        return findings

    def _parse_plist_bytes(self, plist_bytes: bytes, file_name: str) -> List[Finding]:
        data = plistlib.loads(plist_bytes)
        findings = []
        ats = data.get("NSAppTransportSecurity", {})
        if ats.get("NSAllowsArbitraryLoads") is True:
            findings.append(
                Finding(
                    finding_id="ios.plist.allows-arbitrary-loads",
                    rule_id="RULE-IOS-ATS-ALLOWS-ALL",
                    platform=PlatformType.IOS_APP,
                    target=self.target,
                    phase="static",
                    state=FindingState.CAPABILITY,
                    severity=SeverityLevel.HIGH,
                    confidence=1.0,
                    evidence=[EvidenceSpan(file=file_name, artifact="manifest", snippet="NSAllowsArbitraryLoads = true")],
                    scope=FindingScope(),
                    hypothesis="Application disables App Transport Security (ATS) via NSAllowsArbitraryLoads.",
                )
            )
        return findings

    def _analyze_mobileprovision(self, prov_path: Path, root: Path) -> List[Finding]:
        try:
            data = prov_path.read_bytes()
            return self._parse_mobileprovision_bytes(data, str(prov_path.relative_to(root)))
        except Exception:
            return []

    def _parse_mobileprovision_bytes(self, data: bytes, file_name: str) -> List[Finding]:
        """Extracts and parses embedded XML plist from CMS / PKCS#7 mobileprovision envelope."""
        findings = []
        try:
            start = data.find(b"<?xml")
            end = data.find(b"</plist>")
            if start != -1 and end != -1:
                xml_data = data[start : end + 8]
                plist_obj = plistlib.loads(xml_data)

                # Check get-task-allow (debuggable flag)
                entitlements = plist_obj.get("Entitlements", {})
                if entitlements.get("get-task-allow") is True:
                    findings.append(
                        Finding(
                            finding_id="ios.provision.get-task-allow",
                            rule_id="RULE-IOS-GET-TASK-ALLOW",
                            platform=PlatformType.IOS_APP,
                            target=self.target,
                            phase="static",
                            state=FindingState.CAPABILITY,
                            severity=SeverityLevel.HIGH,
                            confidence=1.0,
                            evidence=[EvidenceSpan(file=file_name, artifact="manifest", snippet="get-task-allow = true")],
                            scope=FindingScope(),
                            hypothesis="Provisioning profile enables get-task-allow, permitting task_for_pid attachment and memory inspection.",
                        )
                    )

                findings.extend(ios_rules.analyze_mobileprovision(plist_obj, file_name, self.target))

                # Record TeamIdentifier
                team_id = plist_obj.get("TeamIdentifier", [])
                if team_id:
                    self.target.signing_identity = team_id[0] if isinstance(team_id, list) else str(team_id)

        except Exception:
            pass
        return findings

    def _scan_source_code(self, rel_path: str, text: str) -> List[Finding]:
        findings = []
        lines = text.splitlines()

        for finding_id, pattern, severity, confidence, symbol, hypothesis in WKWEBVIEW_PATTERNS + SWIZZLE_PATTERNS:
            regex = re.compile(pattern)
            for idx, line in enumerate(lines, start=1):
                m = regex.search(line)
                if m:
                    findings.append(
                        Finding(
                            finding_id=finding_id,
                            rule_id=f"RULE-IOS-{finding_id.upper().replace('.', '-')}",
                            platform=PlatformType.IOS_APP,
                            target=self.target,
                            phase="static",
                            state=FindingState.STATIC_LEAD,
                            severity=severity,
                            confidence=confidence,
                            evidence=[EvidenceSpan(file=rel_path, line=idx, symbol=symbol, artifact="source", snippet=line.strip()[:180])],
                            scope=FindingScope(),
                            hypothesis=hypothesis,
                        )
                    )

        findings.extend(scan_text(rel_path, text, ios_rules.SOURCE_RULES + inapp.RULES, self.target, PlatformType.IOS_APP))

        # Check for Tweak Filter Plist
        if "Filter" in text and "Bundles" in text:
            findings.append(
                Finding(
                    finding_id="ios.tweak.filter-plist",
                    rule_id="RULE-IOS-TWEAK-FILTER",
                    platform=PlatformType.IOS_APP,
                    target=self.target,
                    phase="static",
                    state=FindingState.STATIC_LEAD,
                    severity=SeverityLevel.HIGH,
                    confidence=0.85,
                    evidence=[EvidenceSpan(file=rel_path, artifact="manifest", snippet="Filter = { Bundles = (...) }")],
                    scope=FindingScope(),
                    hypothesis="Property list matches MobileSubstrate/Substitute tweak injection target filter.",
                )
            )

        return findings

    def _is_macho(self, p: Path) -> bool:
        try:
            with open(p, "rb") as f:
                head = f.read(4)
                if len(head) < 4:
                    return False
                magic = struct.unpack(">I", head)[0]
                return magic in MACHO_MAGICS or struct.unpack("<I", head)[0] in MACHO_MAGICS
        except Exception:
            return False

    def _analyze_macho(self, p: Path, root: Path) -> List[Finding]:
        findings = []
        try:
            data = p.read_bytes()
            rel_path = str(p.relative_to(root))
            structured = ios_rules.analyze_macho_bytes(rel_path, data, self.target)
            findings.extend(structured)
            referenced = " ".join(f.evidence[0].snippet or "" for f in structured if f.finding_id == "ios.macho.hook-framework-ref").lower()
            for sig, desc in HOOK_FRAMEWORKS:
                if sig in data and sig.decode().lower() not in referenced:
                    findings.append(
                        Finding(
                            finding_id="ios.macho.hook-framework-ref",
                            rule_id="RULE-IOS-HOOK-FW",
                            platform=PlatformType.IOS_APP,
                            target=self.target,
                            phase="static",
                            state=FindingState.STATIC_LEAD,
                            severity=SeverityLevel.CRITICAL,
                            confidence=0.9,
                            evidence=[EvidenceSpan(file=rel_path, artifact="binary", snippet=f"Mach-O binary imports {desc}")],
                            scope=FindingScope(),
                            hypothesis=f"Application binary imports tweak or hooking library: {sig.decode()}.",
                        )
                    )
        except Exception:
            pass
        return findings
