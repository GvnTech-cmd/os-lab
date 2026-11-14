"""Browser extension static analyzer.

Extracts:
- Manifest V2/V3 permissions, host_permissions, content_scripts, web_accessible_resources
- Code injection call-sites:
  - createElement('script')
  - chrome.scripting.executeScript / registerContentScripts / tabs.executeScript
  - chrome.runtime.getURL bridge
  - window.postMessage / CustomEvent cross-world dispatch
  - API hooking: window.fetch, XMLHttpRequest, WebSocket, addEventListener
  - Dynamic evaluation: eval, new Function, setTimeout with string
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

from . import browser_rules
from ._common import scan_text

JS_TS_EXTS = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}


class BrowserExtensionAnalyzer:
    """Static analyzer for browser extensions."""

    def __init__(self, target_identity: Optional[TargetIdentity] = None):
        self.target = target_identity or TargetIdentity("browser-extension")

    def identify(self, root: Path) -> bool:
        """Determines if the directory is a browser extension."""
        for name in ("manifest.json", "src/manifest.json", "extension/manifest.json", "app/manifest.json"):
            if (root / name).is_file():
                return True
        return False

    def locate_manifest(self, root: Path) -> Optional[Path]:
        for name in ("manifest.json", "src/manifest.json", "extension/manifest.json", "app/manifest.json"):
            p = root / name
            if p.is_file():
                return p
        return None

    def analyze(self, root: Path) -> Tuple[List[Finding], Coverage]:
        """Runs full static analysis on extension root."""
        root = Path(root)
        single_file: Optional[Path] = None
        if root.is_file():  # a lone userscript (.user.js) is analysed on its own
            single_file, root = root, root.parent
        findings: List[Finding] = []
        scanned_files = 0
        skipped_files = 0
        limitations: List[str] = []

        manifest_path = None if single_file else self.locate_manifest(root)
        manifest_data: Dict[str, Any] = {}
        if manifest_path:
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8", errors="ignore"))
                mf_findings = self._analyze_manifest(manifest_path, manifest_data, root)
                findings.extend(mf_findings)
                findings.extend(browser_rules.analyze_manifest(str(manifest_path.relative_to(root)), manifest_data, self.target, root))
            except Exception as e:
                limitations.append(f"Failed to parse manifest: {e}")
        elif not single_file:
            limitations.append("No manifest.json found in recognized paths (NOT_EXTENSION)")

        # Scan JavaScript/TypeScript files
        source_files: List[Path] = []
        for p in ([single_file] if single_file else root.rglob("*")):
            if p.is_file() and p.suffix.lower() in JS_TS_EXTS:
                # Skip vendor / dist / node_modules
                parts = p.parts
                if any(x in parts for x in ("node_modules", ".git", "dist", "build", "coverage", ".next")):
                    skipped_files += 1
                    continue
                source_files.append(p)

        for src in source_files[:500]:  # Cap at 500 files
            scanned_files += 1
            try:
                text = src.read_text(encoding="utf-8", errors="ignore")
                src_rel = str(src.relative_to(root))
                file_findings = self._analyze_source_file(src_rel, text)
                findings.extend(file_findings)
                findings.extend(scan_text(src_rel, text, browser_rules.SOURCE_RULES, self.target, PlatformType.BROWSER_EXTENSION))
                findings.extend(browser_rules.analyze_userscript(src_rel, text, self.target))
                shim = browser_rules.analyze_shim_path(src_rel, self.target)
                if shim:
                    findings.append(shim)
            except Exception as e:
                limitations.append(f"Error reading {src.name}: {e}")

        coverage = Coverage(
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            parser_mode="regex_ast_hybrid",
            scanned_files=scanned_files,
            skipped_files=skipped_files,
            limitations=limitations,
        )

        return findings, coverage

    def _analyze_manifest(self, manifest_path: Path, manifest: Dict[str, Any], root: Path) -> List[Finding]:
        findings: List[Finding] = []
        rel_path = str(manifest_path.relative_to(root))
        mv = manifest.get("manifest_version", 2)

        # 1. Broad permissions
        perms = manifest.get("permissions", []) or []
        host_perms = manifest.get("host_permissions", []) or []
        all_perms = set(perms) | set(host_perms)

        if "<all_urls>" in all_perms or "*://*/*" in all_perms or "*://*/*" in str(all_perms):
            span = EvidenceSpan(
                file=rel_path,
                symbol="<all_urls>",
                artifact="manifest",
                snippet=f"Permissions include wide match pattern: <all_urls>",
            )
            findings.append(Finding(
                finding_id="browser.manifest.broad-host-permissions",
                rule_id="H2a",
                platform=PlatformType.BROWSER_EXTENSION,
                target=self.target,
                phase="static",
                state=FindingState.CAPABILITY,
                severity=SeverityLevel.HIGH,
                confidence=0.5,
                evidence=[span],
                scope=FindingScope(origin="<all_urls>", frame="all", world="MAIN"),
                hypothesis="Extension requests access to all web origins, enabling script injection across any website.",
                alternative_explanations=["Ad-blocker, password manager, or privacy extension requiring universal tab access."],
                remediation="Scope permissions to specific target domains or use activeTab.",
            ))

        # 2. Content scripts
        content_scripts = manifest.get("content_scripts", []) or []
        for idx, cs in enumerate(content_scripts):
            matches = cs.get("matches", [])
            js_files = cs.get("js", [])
            all_frames = cs.get("all_frames", False)
            run_at = cs.get("run_at", "document_idle")
            world = cs.get("world", "ISOLATED")

            span = EvidenceSpan(
                file=rel_path,
                symbol=f"content_scripts[{idx}]",
                artifact="manifest",
                snippet=f"matches={matches}, js={js_files}, run_at={run_at}, world={world}",
            )

            sev = SeverityLevel.HIGH if run_at == "document_start" or world == "MAIN" else SeverityLevel.MEDIUM
            findings.append(Finding(
                finding_id=f"browser.manifest.content-script-registration",
                rule_id="H3",
                platform=PlatformType.BROWSER_EXTENSION,
                target=self.target,
                phase="static",
                state=FindingState.CAPABILITY,
                severity=sev,
                confidence=0.6,
                evidence=[span],
                scope=FindingScope(
                    origin=",".join(matches[:3]),
                    frame="all" if all_frames else "top",
                    world=world,
                ),
                hypothesis=f"Declared content script automatically injected at '{run_at}' into execution world '{world}'.",
                alternative_explanations=["Legitimate extension feature requiring DOM interaction on matching pages."],
            ))

        # 3. Web accessible resources
        war = manifest.get("web_accessible_resources", []) or []
        if war:
            span = EvidenceSpan(
                file=rel_path,
                symbol="web_accessible_resources",
                artifact="manifest",
                snippet=f"Exposed assets: {war}",
            )
            findings.append(Finding(
                finding_id="browser.manifest.web-accessible-resources",
                rule_id="WAR",
                platform=PlatformType.BROWSER_EXTENSION,
                target=self.target,
                phase="static",
                state=FindingState.CAPABILITY,
                severity=SeverityLevel.LOW,
                confidence=0.4,
                evidence=[span],
                scope=FindingScope(world="MAIN"),
                hypothesis="Exposes internal extension resources to web page contexts, facilitating two-stage bridge injection.",
            ))

        return findings

    def _analyze_source_file(self, rel_path: str, text: str) -> List[Finding]:
        findings: List[Finding] = []
        lines = text.splitlines()

        # Regex patterns for high-confidence injection leads
        rules = [
            (
                "browser.dom-script-injection",
                r"document\s*\.\s*createElement\s*\(\s*['\"]script['\"]\s*\)",
                SeverityLevel.HIGH,
                0.7,
                "DOM <script> creation call site",
                "Extension dynamically creates and injects a <script> element into the host page DOM.",
                ["Injecting polyfill or client-side bridge script."],
            ),
            (
                "browser.two-stage-bridge.geturl",
                r"(chrome|browser)\s*\.\s*runtime\s*\.\s*getURL\s*\(",
                SeverityLevel.HIGH,
                0.75,
                "chrome.runtime.getURL invocation",
                "Resolves internal extension assets for consumption or injection into the host page context.",
                ["Loading extension icons, web fonts, or iframe panels."],
            ),
            (
                "browser.programmatic-injection",
                r"(chrome|browser)\s*\.\s*(scripting|tabs)\s*\.\s*(executeScript|registerContentScripts)\s*\(",
                SeverityLevel.HIGH,
                0.8,
                "Programmatic script injection API call",
                "Calls dynamic scripting API to inject arbitrary code or registered scripts into web tabs.",
                ["On-demand user triggered action (e.g. clicking the extension toolbar icon)."],
            ),
            (
                "browser.cross-world-messaging",
                r"(window|top|parent)\s*\.\s*postMessage\s*\(",
                SeverityLevel.MEDIUM,
                0.55,
                "window.postMessage call",
                "Dispatches messages across execution world boundaries (isolated world to main world or frame).",
                ["Standard inter-frame or content-to-page communication channel."],
            ),
            (
                "browser.custom-event-bridge",
                r"dispatchEvent\s*\(\s*new\s+CustomEvent\s*\(",
                SeverityLevel.MEDIUM,
                0.6,
                "CustomEvent dispatch bridge",
                "Dispatches custom DOM events to bridge data between extension and web page realms.",
                ["Page communication without direct window property mutation."],
            ),
            (
                "browser.prototype-wrapping.fetch",
                r"(window\s*\.\s*fetch|window\[['\"]fetch['\"]\])\s*=",
                SeverityLevel.CRITICAL,
                0.85,
                "window.fetch monkeypatch assignment",
                "Overrides the global fetch API to intercept, inspect, or modify outbound HTTP network requests.",
                ["Telemetry logger, mock server, or ad request blocker."],
            ),
            (
                "browser.prototype-wrapping.xhr",
                r"XMLHttpRequest\s*\.\s*prototype\s*\.\s*(open|send)\s*=",
                SeverityLevel.CRITICAL,
                0.85,
                "XMLHttpRequest prototype hook",
                "Hooks XMLHttpRequest lifecycle methods to intercept page network communications.",
                ["Network request logger or legacy ad blocker."],
            ),
            (
                "browser.dynamic-eval",
                r"(\beval\s*\(|new\s+Function\s*\()",
                SeverityLevel.HIGH,
                0.7,
                "Dynamic code evaluation",
                "Evaluates dynamic strings into executable code, bypassing static manifest review.",
                ["Template rendering or bundled parser engine."],
            ),
        ]

        for finding_id, pattern_str, severity, confidence, symbol_name, hypothesis, alt_exps in rules:
            regex = re.compile(pattern_str)
            for line_idx, line in enumerate(lines, 1):
                match = regex.search(line)
                if match:
                    span = EvidenceSpan(
                        file=rel_path,
                        line=line_idx,
                        col=match.start() + 1,
                        symbol=symbol_name,
                        artifact="source",
                        snippet=line.strip()[:180],
                    )
                    findings.append(Finding(
                        finding_id=finding_id,
                        rule_id=finding_id.split(".")[-1],
                        platform=PlatformType.BROWSER_EXTENSION,
                        target=self.target,
                        phase="static",
                        state=FindingState.STATIC_LEAD,
                        severity=severity,
                        confidence=confidence,
                        evidence=[span],
                        scope=FindingScope(world="MAIN"),
                        hypothesis=hypothesis,
                        alternative_explanations=alt_exps,
                        remediation="Avoid runtime script injection or API monkeypatching; use declarative webRequest or messaging.",
                    ))
                    # Avoid spamming dozens of identical hits per file
                    if len([f for f in findings if f.finding_id == finding_id and f.evidence[0].file == rel_path]) >= 3:
                        break

        return findings
