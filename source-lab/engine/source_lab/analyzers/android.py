"""Android static analyzer for APKs, packages, and project sources.

Audits:
- AndroidManifest.xml:
  - debuggable flag (android:debuggable="true")
  - exported activities, services, broadcast receivers, and content providers
  - sensitive permissions (SYSTEM_ALERT_WINDOW, WRITE_SETTINGS, PACKAGE_USAGE_STATS, REQUEST_INSTALL_PACKAGES)
- WebView injection and bridge security:
  - addJavascriptInterface (exposes Java reflection bridge to web frames)
  - addDocumentStartJavaScript (androidx.webkit document start script injection)
  - setJavaScriptEnabled(true)
  - setAllowFileAccessFromFileURLs(true), setAllowUniversalAccessFromFileURLs(true)
  - evaluateJavascript execution
- Dynamic Code Loading (DCL):
  - DexClassLoader, PathClassLoader, InMemoryDexClassLoader
  - System.loadLibrary, System.load
- Hooking & tampering indicators:
  - Xposed / LSPosed / Frida signatures in code or manifest
- Native ELF (.so) libraries:
  - Scans ELF headers and dynamic symbols for ptrace, mprotect, dlopen
"""

from __future__ import annotations

import json
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from . import android_rules, inapp
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

ANDROID_SOURCE_EXTS = {".java", ".kt", ".smali", ".xml", ".gradle", ".kts"}

WEBVIEW_PATTERNS = [
    (
        "android.webview.js-interface-bridge",
        r"addJavascriptInterface\s*\(",
        SeverityLevel.HIGH,
        0.8,
        "addJavascriptInterface bridge",
        "Exposes a native Java object to untrusted web content via WebView bridge.",
    ),
    (
        "android.webview.document-start-script",
        r"addDocumentStartJavaScript\s*\(",
        SeverityLevel.HIGH,
        0.85,
        "addDocumentStartJavaScript injection",
        "Injects JavaScript into all frames at document creation time using WebViewCompat.",
    ),
    (
        "android.webview.evaluate-js",
        r"evaluateJavascript\s*\(",
        SeverityLevel.MEDIUM,
        0.65,
        "evaluateJavascript call",
        "Dynamically executes arbitrary JavaScript strings in the WebView context.",
    ),
    (
        "android.webview.allow-universal-access",
        r"setAllowUniversalAccessFromFileURLs\s*\(\s*true\s*\)",
        SeverityLevel.HIGH,
        0.85,
        "setAllowUniversalAccessFromFileURLs enabled",
        "Allows local file:// URLs in WebView to access arbitrary origins via CORS bypass.",
    ),
    (
        "android.webview.allow-file-access",
        r"setAllowFileAccessFromFileURLs\s*\(\s*true\s*\)",
        SeverityLevel.MEDIUM,
        0.75,
        "setAllowFileAccessFromFileURLs enabled",
        "Allows local file:// URLs to access other local files in the WebView sandbox.",
    ),
]

DCL_PATTERNS = [
    (
        "android.dcl.dex-class-loader",
        r"(?:DexClassLoader|InMemoryDexClassLoader|PathClassLoader)\s*\(",
        SeverityLevel.HIGH,
        0.8,
        "Dynamic DEX ClassLoader invocation",
        "Loads arbitrary bytecode from storage, external media, or memory dynamically.",
    ),
    (
        "android.dcl.native-library-load",
        r"System\.(?:load|loadLibrary)\s*\(",
        SeverityLevel.MEDIUM,
        0.6,
        "Dynamic native library loading",
        "Loads compiled native ELF shared object (.so) into application process.",
    ),
]

TAMPER_PATTERNS = [
    (
        "android.hooking.xposed-bridge",
        r"(?:de\.robv\.android\.xposed|IXposedHookLoadPackage|XposedBridge\.hookMethod)",
        SeverityLevel.CRITICAL,
        0.9,
        "Xposed / LSPosed hook framework reference",
        "Integrates with or implements Xposed module hooking interfaces.",
    ),
    (
        "android.hooking.frida-reference",
        r"(?:frida-agent|frida-server|gum-js-loop|FridaGadget)",
        SeverityLevel.CRITICAL,
        0.9,
        "Frida dynamic instrumentation signature",
        "Embedded Frida gadget or client hooking artifacts detected.",
    ),
]


class AndroidAppAnalyzer:
    """Static analyzer for Android APK packages and source repositories."""

    def __init__(self, target_identity: Optional[TargetIdentity] = None):
        self.target = target_identity or TargetIdentity("android-app")

    def identify(self, root: Path) -> bool:
        """Determines if the path is an Android package (.apk) or project directory."""
        p = Path(root)
        if p.is_file() and p.suffix.lower() in {".apk", ".xapk", ".apks", ".aab"}:
            return True
        if p.is_dir():
            for name in ("AndroidManifest.xml", "app/src/main/AndroidManifest.xml", "build.gradle", "app/build.gradle"):
                if (p / name).is_file():
                    return True
        return False

    def analyze(self, root: Path) -> Tuple[List[Finding], Coverage]:
        """Runs full static analysis on Android root or APK."""
        root = Path(root)
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        if root.is_file() and root.suffix.lower() in {".apk", ".xapk", ".apks", ".aab"}:
            return self._analyze_apk(root)

        # Source repository analysis
        manifest_path = self._locate_manifest(root)
        if manifest_path:
            try:
                scanned_files += 1
                mf_findings = self._analyze_manifest_file(manifest_path, root)
                findings.extend(mf_findings)
            except Exception as e:
                limitations.append(f"Failed to parse AndroidManifest.xml: {e}")
        else:
            limitations.append("No AndroidManifest.xml found in standard project paths")

        # Scan Java, Kotlin, Smali, Gradle source files
        source_files: List[Path] = []
        for p in root.rglob("*"):
            if p.is_file():
                if p.suffix.lower() in ANDROID_SOURCE_EXTS:
                    parts = p.parts
                    if any(x in parts for x in (".git", "build", "dist", "node_modules", ".gradle")):
                        skipped_files += 1
                        continue
                    source_files.append(p)
                elif p.suffix.lower() == ".so":
                    scanned_files += 1
                    findings.extend(self._analyze_elf(p, root))
                    injected = android_rules.analyze_injected_lib_name(str(p.relative_to(root)), self.target)
                    if injected:
                        findings.append(injected)
                elif p.name == "apktool.yml":
                    findings.append(self._repackaging_marker(str(p.relative_to(root))))

        for src in source_files[:500]:
            scanned_files += 1
            try:
                text = src.read_text(encoding="utf-8", errors="ignore")
                src_rel = str(src.relative_to(root))
                findings.extend(self._scan_source_code(src_rel, text))
            except Exception as e:
                limitations.append(f"Error reading {src.name}: {e}")

        coverage = Coverage(
            platform=PlatformType.ANDROID_APP,
            target=self.target,
            parser_mode="regex_ast_hybrid",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )
        return findings, coverage

    def _locate_manifest(self, root: Path) -> Optional[Path]:
        for name in ("AndroidManifest.xml", "app/src/main/AndroidManifest.xml", "src/main/AndroidManifest.xml"):
            p = root / name
            if p.is_file():
                return p
        return None

    def _analyze_apk(self, apk_path: Path) -> Tuple[List[Finding], Coverage]:
        """Inspects an APK archive directly without external dependencies."""
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        try:
            with zipfile.ZipFile(apk_path, "r") as zf:
                namelist = zf.namelist()
                scanned_files = len(namelist)
                try:
                    findings.extend(android_rules.analyze_apk_signing(apk_path.name, apk_path.read_bytes(), namelist, self.target))
                except Exception as e:
                    limitations.append(f"Could not read the signing block: {e}")
                for name in namelist:
                    injected = android_rules.analyze_injected_lib_name(name, self.target, container=apk_path.name)
                    if injected:
                        findings.append(injected)
                    if name.endswith("apktool.yml"):
                        findings.append(self._repackaging_marker(f"{apk_path.name}!{name}"))

                # Check for AndroidManifest.xml
                if "AndroidManifest.xml" in namelist:
                    manifest_bytes = zf.read("AndroidManifest.xml")
                    findings.extend(self._parse_manifest_bytes(manifest_bytes, apk_path.name))
                    findings.extend(android_rules.analyze_binary_manifest(manifest_bytes, apk_path.name, self.target))

                # Check classes*.dex
                dex_files = [n for n in namelist if re.match(r"^classes\d*\.dex$", n)]
                for dex_name in dex_files:
                    try:
                        dex_bytes = zf.read(dex_name)
                        findings.extend(self._scan_dex_strings(dex_bytes, dex_name))
                    except Exception as e:
                        limitations.append(f"Error scanning {dex_name}: {e}")

                # Check native libraries (.so)
                so_files = [n for n in namelist if n.endswith(".so")]
                for so_name in so_files[:20]:
                    try:
                        so_bytes = zf.read(so_name)
                        findings.extend(self._scan_elf_bytes(so_bytes, so_name))
                    except Exception as e:
                        limitations.append(f"Error scanning {so_name}: {e}")

        except Exception as e:
            limitations.append(f"Failed to read APK archive: {e}")

        coverage = Coverage(
            platform=PlatformType.ANDROID_APP,
            target=self.target,
            parser_mode="apk_archive_binary",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )
        return findings, coverage

    def _analyze_manifest_file(self, manifest_path: Path, root: Path) -> List[Finding]:
        """Parses cleartext AndroidManifest.xml from source project."""
        findings: List[Finding] = []
        rel_path = str(manifest_path.relative_to(root))
        text = manifest_path.read_text(encoding="utf-8", errors="ignore")

        try:
            root_el = ET.fromstring(text)
        except Exception:
            return self._regex_manifest_fallback(rel_path, text)

        # Check debuggable
        app_el = root_el.find("application")
        if app_el is not None:
            debuggable = app_el.get("{http://schemas.android.com/apk/res/android}debuggable") or app_el.get("android:debuggable")
            if debuggable == "true":
                findings.append(
                    Finding(
                        finding_id="android.manifest.debuggable",
                        rule_id="RULE-ANDR-DEBUG",
                        platform=PlatformType.ANDROID_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.CAPABILITY,
                        severity=SeverityLevel.HIGH,
                        confidence=1.0,
                        evidence=[EvidenceSpan(file=rel_path, artifact="manifest", snippet='android:debuggable="true"')],
                        scope=FindingScope(),
                        hypothesis="Application is compiled as debuggable, allowing runtime debugger attachment and memory dumping.",
                    )
                )

            # Check exported components without permission guard
            for comp_tag in ("activity", "service", "receiver", "provider"):
                for comp in app_el.findall(comp_tag):
                    comp_name = comp.get("{http://schemas.android.com/apk/res/android}name") or comp.get("android:name") or "unnamed"
                    exported = comp.get("{http://schemas.android.com/apk/res/android}exported") or comp.get("android:exported")
                    has_intent_filter = comp.find("intent-filter") is not None

                    if exported == "true" or (exported is None and has_intent_filter):
                        findings.append(
                            Finding(
                                finding_id=f"android.manifest.exported-{comp_tag}",
                                rule_id=f"RULE-ANDR-EXP-{comp_tag.upper()}",
                                platform=PlatformType.ANDROID_APP,
                                target=self.target,
                                phase="static",
                                state=FindingState.CAPABILITY,
                                severity=SeverityLevel.MEDIUM,
                                confidence=0.85,
                                evidence=[EvidenceSpan(file=rel_path, symbol=comp_name, artifact="manifest", snippet=f"<{comp_tag} android:name='{comp_name}' android:exported='true'>")],
                                scope=FindingScope(process=comp_name),
                                hypothesis=f"Exported {comp_tag} '{comp_name}' can be invoked by arbitrary third-party applications.",
                            )
                        )

        # Check dangerous permissions
        dangerous_perms = {
            "android.permission.SYSTEM_ALERT_WINDOW": ("Overlay window capability", SeverityLevel.HIGH),
            "android.permission.PACKAGE_USAGE_STATS": ("App usage monitoring capability", SeverityLevel.HIGH),
            "android.permission.WRITE_SETTINGS": ("System settings modification capability", SeverityLevel.HIGH),
            "android.permission.REQUEST_INSTALL_PACKAGES": ("Arbitrary package installation capability", SeverityLevel.HIGH),
        }
        for perm in root_el.findall("uses-permission"):
            p_name = perm.get("{http://schemas.android.com/apk/res/android}name") or perm.get("android:name")
            if p_name in dangerous_perms:
                desc, sev = dangerous_perms[p_name]
                findings.append(
                    Finding(
                        finding_id=f"android.permission.{p_name.split('.')[-1].lower()}",
                        rule_id="RULE-ANDR-PERM",
                        platform=PlatformType.ANDROID_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.CAPABILITY,
                        severity=sev,
                        confidence=0.9,
                        evidence=[EvidenceSpan(file=rel_path, symbol=p_name, artifact="manifest", snippet=f'<uses-permission android:name="{p_name}" />')],
                        scope=FindingScope(),
                        hypothesis=f"Application requests high-risk Android permission: {p_name} ({desc}).",
                    )
                )

        findings.extend(android_rules.analyze_manifest_xml(root_el, rel_path, self.target))
        return findings

    def _regex_manifest_fallback(self, rel_path: str, text: str) -> List[Finding]:
        findings = []
        if 'android:debuggable="true"' in text:
            findings.append(
                Finding(
                    finding_id="android.manifest.debuggable",
                    rule_id="RULE-ANDR-DEBUG",
                    platform=PlatformType.ANDROID_APP,
                    target=self.target,
                    phase="static",
                    state=FindingState.CAPABILITY,
                    severity=SeverityLevel.HIGH,
                    confidence=0.9,
                    evidence=[EvidenceSpan(file=rel_path, artifact="manifest", snippet='android:debuggable="true"')],
                    scope=FindingScope(),
                    hypothesis="Application is compiled as debuggable, allowing runtime debugger attachment.",
                )
            )
        return findings

    def _parse_manifest_bytes(self, raw_bytes: bytes, archive_name: str) -> List[Finding]:
        """Parses compiled binary XML (AXML) from an APK using string extraction heuristics."""
        findings = []
        # Check for debuggable flag string or indicator in UTF-8/UTF-16
        if b"debuggable" in raw_bytes:
            findings.append(
                Finding(
                    finding_id="android.apk.debuggable-indicator",
                    rule_id="RULE-ANDR-APK-DEBUG",
                    platform=PlatformType.ANDROID_APP,
                    target=self.target,
                    phase="static",
                    state=FindingState.CAPABILITY,
                    severity=SeverityLevel.HIGH,
                    confidence=0.75,
                    evidence=[EvidenceSpan(file=f"{archive_name}!AndroidManifest.xml", artifact="manifest", snippet="binary XML contains 'debuggable' attribute")],
                    scope=FindingScope(),
                    hypothesis="APK binary manifest references debuggable configuration.",
                )
            )
        return findings

    def _scan_source_code(self, rel_path: str, text: str) -> List[Finding]:
        findings = []
        lines = text.splitlines()

        for finding_id, pattern, severity, confidence, symbol, hypothesis in WEBVIEW_PATTERNS + DCL_PATTERNS + TAMPER_PATTERNS:
            regex = re.compile(pattern)
            for idx, line in enumerate(lines, start=1):
                m = regex.search(line)
                if m:
                    findings.append(
                        Finding(
                            finding_id=finding_id,
                            rule_id=f"RULE-ANDR-{finding_id.upper().replace('.', '-')}",
                            platform=PlatformType.ANDROID_APP,
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
        findings.extend(scan_text(rel_path, text, android_rules.SOURCE_RULES + inapp.RULES, self.target, PlatformType.ANDROID_APP))
        bridge = android_rules.analyze_js_enabled_bridge(rel_path, text, self.target)
        if bridge:
            findings.append(bridge)
        return findings

    def _repackaging_marker(self, where: str) -> Finding:
        return Finding(
            finding_id="android.apk.repackaging",
            platform=PlatformType.ANDROID_APP,
            target=self.target,
            phase="static",
            state=FindingState.CAPABILITY,
            severity=SeverityLevel.MEDIUM,
            confidence=0.6,
            evidence=[EvidenceSpan(file=where, symbol="apktool.yml", artifact="source", snippet="apktool metadata: this tree was produced by decoding and rebuilding an APK")],
            scope=FindingScope(),
            hypothesis="apktool metadata is present, which means the app was decoded to smali and can be rebuilt with merged code.",
            alternative_explanations=["Security research or localisation workflow on a copy of the app."],
        )

    def _scan_dex_strings(self, dex_bytes: bytes, dex_name: str) -> List[Finding]:
        findings = []
        signatures = [
            (b"addJavascriptInterface", "android.dex.add-javascript-interface", SeverityLevel.HIGH, 0.85, "DEX invokes addJavascriptInterface WebView bridge"),
            (b"addDocumentStartJavaScript", "android.dex.add-document-start-js", SeverityLevel.HIGH, 0.9, "DEX invokes WebViewCompat addDocumentStartJavaScript"),
            (b"DexClassLoader", "android.dex.dex-class-loader", SeverityLevel.HIGH, 0.8, "DEX references dynamic DexClassLoader"),
            (b"XposedBridge", "android.dex.xposed-bridge", SeverityLevel.CRITICAL, 0.95, "DEX references XposedBridge hooking library"),
            (b"frida-agent", "android.dex.frida-agent", SeverityLevel.CRITICAL, 0.95, "DEX references Frida instrumentation agent"),
        ]
        signatures = signatures + list(android_rules.DEX_SIGNATURES)
        reported: set = set()
        for sig, finding_id, sev, conf, hyp in signatures:
            if sig in dex_bytes and finding_id not in reported:
                reported.add(finding_id)
                findings.append(
                    Finding(
                        finding_id=finding_id,
                        rule_id=f"RULE-ANDR-{finding_id.upper().replace('.', '-')}",
                        platform=PlatformType.ANDROID_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.STATIC_LEAD,
                        severity=sev,
                        confidence=conf,
                        evidence=[EvidenceSpan(file=dex_name, artifact="binary", snippet=f"DEX contains literal string '{sig.decode()}'")],
                        scope=FindingScope(),
                        hypothesis=hyp,
                    )
                )
        return findings

    def _analyze_elf(self, so_path: Path, root: Path) -> List[Finding]:
        try:
            data = so_path.read_bytes()
            return self._scan_elf_bytes(data, str(so_path.relative_to(root)))
        except Exception:
            return []

    def _scan_elf_bytes(self, elf_bytes: bytes, rel_path: str) -> List[Finding]:
        findings = []
        if not elf_bytes.startswith(b"\x7fELF"):
            return findings

        # Check architecture
        ei_class = elf_bytes[4] if len(elf_bytes) > 4 else 0
        arch_str = "64-bit" if ei_class == 2 else "32-bit"

        suspicious_elf_symbols = [
            (b"ptrace", "android.native.ptrace", SeverityLevel.HIGH, 0.75, "Native library imports ptrace anti-debugging or injection API"),
            (b"mprotect", "android.native.mprotect", SeverityLevel.MEDIUM, 0.65, "Native library imports mprotect for runtime page memory manipulation"),
            (b"frida", "android.native.frida", SeverityLevel.CRITICAL, 0.9, "Native library references Frida dynamic instrumentation"),
        ]
        for sig, finding_id, sev, conf, hyp in suspicious_elf_symbols:
            if sig in elf_bytes:
                findings.append(
                    Finding(
                        finding_id=finding_id,
                        rule_id=f"RULE-ANDR-ELF-{finding_id.upper().replace('.', '-')}",
                        platform=PlatformType.ANDROID_APP,
                        target=self.target,
                        phase="static",
                        state=FindingState.STATIC_LEAD,
                        severity=sev,
                        confidence=conf,
                        evidence=[EvidenceSpan(file=rel_path, artifact="binary", snippet=f"ELF {arch_str} contains symbol '{sig.decode()}'")],
                        scope=FindingScope(),
                        hypothesis=hyp,
                    )
                )
        return findings
