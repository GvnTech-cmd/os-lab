"""Browser extension rules from the research beyond the basic injection call sites.

Covers the Browser paper and the Playbook: privileged permissions, MAIN-world and document_start registration, persistent
background, CSP relaxations, remote code, native prototype wrapping and spoofing, the userScripts API, multi-extension
shims, and Tampermonkey-style userscripts. Manifest checks return findings directly; source checks are `Rule` tables.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from source_lab.evidence.schema import (
    EvidenceSpan,
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
)

from ._common import Rule, make_finding, scan_text

P = PlatformType.BROWSER_EXTENSION
SEV = SeverityLevel

BROAD_PATTERNS = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*", "*://*", "file:///*"}

#: permission -> (severity, confidence, meaning)
PRIVILEGED_PERMISSIONS: Dict[str, Tuple[SeverityLevel, float, str]] = {
    "scripting": (SEV.HIGH, 0.6, "inject scripts into pages programmatically (chrome.scripting)"),
    "webRequestBlocking": (SEV.HIGH, 0.7, "block and rewrite network requests synchronously"),
    "webRequest": (SEV.MEDIUM, 0.5, "observe every network request"),
    "declarativeNetRequest": (SEV.MEDIUM, 0.5, "rewrite or block requests and headers declaratively"),
    "declarativeNetRequestWithHostAccess": (SEV.HIGH, 0.6, "rewrite requests and headers on hosts it has access to"),
    "debugger": (SEV.CRITICAL, 0.8, "attach the DevTools protocol to any tab"),
    "userScripts": (SEV.HIGH, 0.7, "register user scripts that run in the USER_SCRIPT world"),
    "nativeMessaging": (SEV.HIGH, 0.65, "talk to native applications outside the browser sandbox"),
    "cookies": (SEV.MEDIUM, 0.55, "read and write cookies of permitted hosts"),
    "proxy": (SEV.HIGH, 0.65, "route browser traffic through a proxy it controls"),
    "management": (SEV.MEDIUM, 0.5, "inspect, disable or uninstall other extensions"),
    "history": (SEV.MEDIUM, 0.4, "read the browsing history"),
}

SOURCE_RULES: Tuple[Rule, ...] = (
    Rule(
        "browser.main-world-injection",
        r"world\s*:\s*['\"]MAIN['\"]",
        SEV.HIGH,
        0.8,
        "world: 'MAIN'",
        "Runs injected code in the page's own JavaScript world, where it shares globals with the site and can wrap native APIs.",
        ("Page-integrated feature such as a wallet provider or a debugging bridge.",),
        world="MAIN",
    ),
    Rule(
        "browser.userscripts-api",
        r"(chrome|browser)\s*\.\s*userScripts\s*\.\s*(register|update|configureWorld|getScripts)|['\"]USER_SCRIPT['\"]",
        SEV.HIGH,
        0.8,
        "userScripts API",
        "Registers user scripts through the userScripts API, which executes arbitrary strings in the dedicated USER_SCRIPT world.",
        ("A userscript manager running scripts the user installed.",),
        world="USER_SCRIPT",
    ),
    Rule(
        "browser.prototype-wrapping.websocket",
        r"(window\s*\.\s*WebSocket|globalThis\s*\.\s*WebSocket|WebSocket\s*\.\s*prototype\s*\.\s*(send|close))\s*=(?!=)",
        SEV.CRITICAL,
        0.8,
        "WebSocket hook",
        "Replaces WebSocket or its send/close methods to read or alter real-time page traffic.",
        ("Debugging or mocking tool.",),
        world="MAIN",
    ),
    Rule(
        "browser.prototype-wrapping.eventtarget",
        r"EventTarget\s*\.\s*prototype\s*\.\s*addEventListener\s*=(?!=)|document\s*\.\s*addEventListener\s*=(?!=)",
        SEV.HIGH,
        0.8,
        "EventTarget.prototype.addEventListener hook",
        "Wraps addEventListener so every listener the page registers can be observed or replaced, including key and input handlers.",
        ("Event-tracing developer tool.",),
        world="MAIN",
    ),
    Rule(
        "browser.prototype-wrapping.response",
        r"(Response|Request)\s*\.\s*prototype\s*\.\s*(json|text|blob|arrayBuffer|clone)\s*=(?!=)",
        SEV.HIGH,
        0.75,
        "Response/Request prototype hook",
        "Wraps Response or Request body readers to intercept every fetched payload after the network layer.",
        ("Response caching or mock layer.",),
        world="MAIN",
    ),
    Rule(
        "browser.prototype-wrapping.define-property",
        r"Object\s*\.\s*defineProperty\s*\(\s*(window|globalThis|XMLHttpRequest\s*\.\s*prototype)\s*,\s*['\"](fetch|XMLHttpRequest|WebSocket|open|send)['\"]",
        SEV.HIGH,
        0.75,
        "defineProperty on a native API",
        "Redefines a native network API with Object.defineProperty, a way to hook it that survives simple assignment checks.",
        ("Polyfill installation.",),
        world="MAIN",
    ),
    Rule(
        "browser.prototype-wrapping.proxy-native",
        r"new\s+Proxy\s*\(\s*(window\s*\.\s*|globalThis\s*\.\s*)?(fetch|XMLHttpRequest|WebSocket)\b",
        SEV.HIGH,
        0.8,
        "Proxy around a native API",
        "Wraps a native network API in a Proxy so calls can be intercepted while the object still looks native.",
        ("Request instrumentation.",),
        world="MAIN",
    ),
    Rule(
        "browser.prototype-wrapping.tostring-spoof",
        r"Function\s*\.\s*prototype\s*\.\s*toString\s*=(?!=)|\.toString\s*=\s*(function\s*\(\s*\)|\(\s*\)\s*=>)[^;]*native code",
        SEV.CRITICAL,
        0.85,
        "Function.prototype.toString spoof",
        "Overrides toString so hooked functions still print as native code, defeating the simplest in-page hook detection.",
        ("Anti-fingerprinting or privacy extension hiding its own hooks.",),
        world="MAIN",
    ),
    Rule(
        "browser.debugger-attach",
        r"(chrome|browser)\s*\.\s*debugger\s*\.\s*(attach|sendCommand)\s*\(",
        SEV.CRITICAL,
        0.85,
        "chrome.debugger",
        "Attaches the DevTools protocol to a tab, which can read, modify and inject into any page it controls.",
        ("Developer tool, automated testing or accessibility extension.",),
    ),
    Rule(
        "browser.webrequest-blocking",
        r"['\"](blocking|responseHeaders|requestBody)['\"]",
        SEV.HIGH,
        0.65,
        "blocking webRequest listener",
        "Registers a blocking webRequest listener that can cancel or rewrite requests and responses in flight.",
        ("Content blocker or request redirector.",),
        requires=r"webRequest\s*\.\s*on\w+\s*\.\s*addListener",
    ),
    Rule(
        "browser.dnr-dynamic-rules",
        r"declarativeNetRequest\s*\.\s*(updateDynamicRules|updateSessionRules)",
        SEV.MEDIUM,
        0.55,
        "declarativeNetRequest dynamic rules",
        "Changes network rewriting rules at runtime, so the effective behaviour is not fixed by the packaged rule files.",
        ("Content blocker updating its filter lists.",),
    ),
    Rule(
        "browser.remote-code.importscripts",
        r"importScripts\s*\(\s*['\"`]https?://",
        SEV.HIGH,
        0.85,
        "importScripts from a remote URL",
        "Loads and runs code fetched from a remote server, so the code that runs can differ from what was reviewed.",
        ("Remote configuration or analytics library.",),
    ),
    Rule(
        "browser.remote-code.dynamic-import",
        r"\bimport\s*\(\s*['\"`]https?://",
        SEV.HIGH,
        0.85,
        "dynamic import from a remote URL",
        "Imports a module from a remote origin at runtime.",
        ("Remote module federation.",),
    ),
    Rule(
        "browser.remote-code.fetch-eval",
        r"fetch\s*\([^)]*\)[^;\n]*\.then\s*\([^)]*\b(eval|Function)\b|\b(eval|new\s+Function)\s*\(\s*await\s+",
        SEV.HIGH,
        0.7,
        "fetch then eval",
        "Fetches text and evaluates it as code, a remote-code-execution pattern that bypasses store review.",
        ("Remote rule engine evaluating expressions.",),
    ),
    Rule(
        "browser.remote-code.script-src",
        r"\.src\s*=\s*['\"`]https?://",
        SEV.HIGH,
        0.6,
        "script element with a remote src",
        "Injects a script element whose source is a remote URL, loading code from outside the package.",
        ("CDN-hosted library.",),
        requires=r"createElement\s*\(\s*['\"]script['\"]\s*\)",
    ),
    Rule(
        "browser.storage-wrapper",
        r"(chrome|browser)\s*\.\s*(storage\s*\.\s*(local|sync|session|managed)\s*\.\s*(get|set|remove)|runtime\s*\.\s*(getURL|sendMessage|getManifest))\s*=(?!=)",
        SEV.HIGH,
        0.75,
        "extension API wrapper",
        "Replaces chrome.storage or chrome.runtime functions with wrappers, the multiplexing technique used to merge several extensions into one.",
        ("Extension merger or compatibility shim.",),
    ),
)

# A file layout is a shim signature on its own: qx/shim.js and cs/<slug>-<idx>.js come from the multiplexing architecture.
_SHIM_PATHS = (
    (re.compile(r"(^|/)qx/shim\.js$"), "qx/shim.js runtime multiplexer"),
    (re.compile(r"(^|/)cs/[^/]+-\d+\.js$"), "cs/<slug>-<idx>.js relocated content script"),
)


def analyze_manifest(rel_path: str, manifest: Dict[str, Any], target: TargetIdentity, root: Path) -> List[Finding]:
    """Manifest findings beyond host breadth: permissions, content-script flags, background, CSP, externally_connectable, DNR rules."""
    findings: List[Finding] = []
    mv = int(manifest.get("manifest_version", 2) or 2)

    def span(symbol: str, snippet: str) -> EvidenceSpan:
        return EvidenceSpan(file=rel_path, symbol=symbol, artifact="manifest", snippet=snippet[:180])

    # 1. Privileged permissions
    declared = list(manifest.get("permissions", []) or []) + list(manifest.get("optional_permissions", []) or [])
    for perm in declared:
        if isinstance(perm, str) and perm in PRIVILEGED_PERMISSIONS:
            severity, confidence, meaning = PRIVILEGED_PERMISSIONS[perm]
            findings.append(make_finding(
                f"browser.manifest.privileged-permission.{perm.lower()}", P, target, severity, confidence,
                f"The extension can use the '{perm}' permission to {meaning}.", span(perm, f"permissions include '{perm}'"),
                rule_id="H2b", scope=FindingScope(world="background"),
                alternatives=["The permission is part of a declared, user-visible feature."],
                remediation=f"Drop '{perm}' or move it to optional_permissions requested at the moment of use.",
            ))

    # 2. Broad host patterns declared in content scripts (host_permissions are covered by the base rule)
    for idx, cs in enumerate(manifest.get("content_scripts", []) or []):
        if not isinstance(cs, dict):
            continue
        matches = [m for m in cs.get("matches", []) or [] if isinstance(m, str)]
        broad = [m for m in matches if m in BROAD_PATTERNS]
        run_at = cs.get("run_at", "document_idle")
        world = cs.get("world", "ISOLATED")
        frames = bool(cs.get("all_frames")) or bool(cs.get("match_about_blank")) or bool(cs.get("match_origin_as_fallback"))
        sym = f"content_scripts[{idx}]"
        if broad:
            findings.append(make_finding(
                "browser.manifest.broad-host-permissions", P, target, SEV.HIGH, 0.55,
                "A content script matches every web origin, so it runs on any page the user opens.", span(sym, f"matches={broad}"),
                rule_id="H1", scope=FindingScope(origin=broad[0], frame="all" if frames else "top", world=world),
                alternatives=["Ad blocker, password manager or accessibility extension."],
            ))
        if world == "MAIN":
            findings.append(make_finding(
                "browser.manifest.main-world-content-script", P, target, SEV.HIGH, 0.8,
                "A declared content script runs in the page's MAIN world, sharing globals with the site.", span(sym, f"world=MAIN, matches={matches[:3]}"),
                rule_id="H3", scope=FindingScope(origin=",".join(matches[:3]), frame="all" if frames else "top", world="MAIN"),
                alternatives=["Page-integrated provider (wallet) or bridge that must reach page JavaScript."],
            ))
        if run_at == "document_start" and frames:
            findings.append(make_finding(
                "browser.manifest.document-start-all-frames", P, target, SEV.HIGH if broad else SEV.MEDIUM, 0.7,
                "A content script runs before the DOM is parsed and in every frame, so it can hook the page before any site script runs.",
                span(sym, f"run_at=document_start, all_frames/about:blank, matches={matches[:3]}"),
                rule_id="H3", scope=FindingScope(origin=",".join(matches[:3]), frame="all", world=world),
                alternatives=["Early hooks needed by an ad blocker or a dark-mode engine."],
            ))

    # 3. Background persistence (H4)
    background = manifest.get("background")
    if isinstance(background, dict):
        persistent = background.get("persistent")
        if mv == 2 and background.get("scripts") and persistent is not False:
            findings.append(make_finding(
                "browser.manifest.persistent-background", P, target, SEV.MEDIUM if persistent else SEV.LOW, 0.5 if persistent else 0.35,
                "The background page stays alive for the whole browser session (Manifest V2 persistent background).",
                span("background", f"persistent={persistent!r}, scripts={background.get('scripts')}"), rule_id="H4", scope=FindingScope(world="background"),
                alternatives=["Event listeners that the extension cannot register lazily."],
            ))

    # 4. externally_connectable
    ext = manifest.get("externally_connectable")
    if isinstance(ext, dict):
        matches = [m for m in ext.get("matches", []) or [] if isinstance(m, str)]
        ids = [i for i in ext.get("ids", []) or [] if isinstance(i, str)]
        if any(m in BROAD_PATTERNS for m in matches) or "*" in ids:
            findings.append(make_finding(
                "browser.manifest.externally-connectable", P, target, SEV.MEDIUM, 0.55,
                "Any web page or extension can message this extension through externally_connectable.", span("externally_connectable", f"matches={matches}, ids={ids}"),
                rule_id="H1", scope=FindingScope(origin=",".join(matches[:3])),
                alternatives=["A first-party web app that talks to its own extension."],
            ))

    # 5. Content security policy relaxations (H5)
    csp = manifest.get("content_security_policy")
    policies: List[Tuple[str, str]] = []
    if isinstance(csp, str):
        policies.append(("content_security_policy", csp))
    elif isinstance(csp, dict):
        policies.extend((f"content_security_policy.{k}", v) for k, v in csp.items() if isinstance(v, str))
    for name, policy in policies:
        if "extension_pages" in name or name == "content_security_policy":
            if "'unsafe-eval'" in policy:
                findings.append(make_finding("browser.manifest.csp-unsafe-eval", P, target, SEV.HIGH, 0.8,
                    "The extension CSP allows 'unsafe-eval', so strings can be evaluated as code.", span(name, policy), rule_id="H5", scope=FindingScope(world="background"),
                    alternatives=["A bundled template engine or parser that needs eval."]))
            if "'wasm-unsafe-eval'" in policy:
                findings.append(make_finding("browser.manifest.csp-wasm-unsafe-eval", P, target, SEV.MEDIUM, 0.5,
                    "The extension CSP allows WebAssembly compilation ('wasm-unsafe-eval').", span(name, policy), rule_id="H5", scope=FindingScope(world="background"),
                    alternatives=["Bundled WebAssembly module."]))
            remote = re.findall(r"script-src[^;]*", policy)
            if any(re.search(r"https?://", part) for part in remote):
                findings.append(make_finding("browser.manifest.csp-remote-script-src", P, target, SEV.HIGH, 0.75,
                    "The extension CSP allows scripts from remote origins, so code can be loaded from outside the package.", span(name, policy), rule_id="H5",
                    scope=FindingScope(world="background"), alternatives=["Remote analytics library the vendor documents."]))

    # 6. DNR rule files that strip security headers
    dnr = manifest.get("declarative_net_request")
    if isinstance(dnr, dict):
        for resource in (dnr.get("rule_resources", []) or [])[:10]:
            path = resource.get("path") if isinstance(resource, dict) else None
            if not isinstance(path, str):
                continue
            rules_file = (root / path) if (root / path).is_file() else (root / Path(rel_path).parent / path)
            try:
                rules = json.loads(rules_file.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            stripped = set()
            for rule in rules if isinstance(rules, list) else []:
                headers = (((rule or {}).get("action") or {}).get("responseHeaders") or []) if isinstance(rule, dict) else []
                for h in headers:
                    if isinstance(h, dict) and str(h.get("operation")) == "remove" and str(h.get("header", "")).lower() in {"content-security-policy", "x-frame-options", "content-security-policy-report-only"}:
                        stripped.add(str(h["header"]).lower())
            if stripped:
                findings.append(make_finding(
                    "browser.dnr-header-stripping", P, target, SEV.HIGH, 0.75,
                    f"A declarativeNetRequest rule file removes {', '.join(sorted(stripped))} from responses, weakening the page's own defences so injected code can run.",
                    EvidenceSpan(file=str(rules_file.relative_to(root)) if rules_file.is_relative_to(root) else path, symbol="responseHeaders remove", artifact="manifest", snippet=f"removes {sorted(stripped)}"),
                    rule_id="H2b", scope=FindingScope(world="MAIN"),
                    alternatives=["Dev tool that lets a site be embedded in an iframe."],
                ))
    return findings


def analyze_shim_path(rel_path: str, target: TargetIdentity) -> Optional[Finding]:
    """A finding when the file's path is a multi-extension shim signature (qx/shim.js, cs/<slug>-<idx>.js)."""
    posix = rel_path.replace("\\", "/")
    for regex, label in _SHIM_PATHS:
        if regex.search(posix):
            return make_finding(
                "browser.shim.runtime-multiplexer", P, target, SEV.MEDIUM, 0.7,
                f"The package contains {label}: the layout produced by merging several extensions into one runtime, which relocates their content scripts and wraps the extension APIs.",
                EvidenceSpan(file=posix, symbol=label, artifact="source", snippet=f"file path matches {label}"),
                rule_id="H4", scope=FindingScope(world="ISOLATED"),
                alternatives=["A deliberate bundle of a vendor's own extensions."],
            )
    return None


# ---------------------------------------------------------------------------------------------------------------------
# Userscripts (Tampermonkey / Greasemonkey / Violentmonkey metadata blocks)
# ---------------------------------------------------------------------------------------------------------------------

_HEADER = re.compile(r"//\s*==UserScript==(.*?)//\s*==/UserScript==", re.S)
_KEYVAL = re.compile(r"^//\s*@([\w:-]+)\s*(.*)$", re.M)
_BROAD_MATCH = re.compile(r"^(\*|\*://\*|\*://\*/\*|https?\*?://\*/?\*?|https?://\*/\*|<all_urls>|\*://\*\.?\*/\*|http\*://\*)$")
_PRIV_GRANTS = {"GM_xmlhttpRequest", "GM.xmlHttpRequest", "GM_cookie", "GM.cookie", "GM_download", "GM.download", "GM_openInTab", "unsafeWindow"}


def parse_userscript_header(text: str) -> Optional[Dict[str, List[str]]]:
    """The `// @key value` pairs of a ==UserScript== block; None when the text has no block."""
    head = _HEADER.search(text[:20000])
    if not head:
        return None
    meta: Dict[str, List[str]] = {}
    for key, value in _KEYVAL.findall(head.group(1)):
        meta.setdefault(key, []).append(value.strip())
    return meta


def analyze_userscript(rel_path: str, text: str, target: TargetIdentity) -> List[Finding]:
    """Findings for a userscript: scope of @match/@include, run time, grants and @connect."""
    meta = parse_userscript_header(text)
    if meta is None:
        return []
    findings: List[Finding] = []
    header_line = next((i for i, line in enumerate(text.splitlines(), 1) if "==UserScript==" in line), 1)

    def span(symbol: str, snippet: str) -> EvidenceSpan:
        return EvidenceSpan(file=rel_path, line=header_line, symbol=symbol, artifact="source", snippet=snippet[:180])

    name = (meta.get("name") or [rel_path])[0]
    matches = (meta.get("match") or []) + (meta.get("include") or [])
    grants = meta.get("grant") or []
    findings.append(make_finding(
        "browser.userscript.metadata", P, target, SEV.INFO, 0.9,
        f"Userscript '{name}' declares {len(matches)} match pattern(s) and {len(grants)} grant(s).",
        span("==UserScript==", f"name={name}; match={matches[:3]}; grant={grants[:5]}"), rule_id="USERSCRIPT", scope=FindingScope(world="USER_SCRIPT"),
    ))
    broad = [m for m in matches if _BROAD_MATCH.match(m.strip())]
    if broad:
        findings.append(make_finding(
            "browser.userscript.broad-match", P, target, SEV.HIGH, 0.7,
            "The userscript runs on every site it is allowed on, not on a specific service.", span("@match", f"@match {broad[0]}"),
            rule_id="USERSCRIPT-H1", scope=FindingScope(origin=broad[0], world="USER_SCRIPT"),
            alternatives=["Utility script for any page, such as a dark mode or reader mode."],
        ))
    run_at = (meta.get("run-at") or [""])[0]
    if run_at == "document-start":
        findings.append(make_finding(
            "browser.userscript.document-start", P, target, SEV.MEDIUM, 0.6,
            "The userscript runs at document-start, before the page's own scripts, so it can hook the page first.", span("@run-at", "@run-at document-start"),
            rule_id="USERSCRIPT-H3", scope=FindingScope(world="USER_SCRIPT", frame="top"),
        ))
    page_world = "none" in [g.lower() for g in grants] or (meta.get("inject-into") or [""])[0] == "page" or "unsafeWindow" in text
    if page_world:
        findings.append(make_finding(
            "browser.userscript.page-world", P, target, SEV.MEDIUM, 0.6,
            "The userscript runs in the page's own world (@grant none, @inject-into page or unsafeWindow), sharing globals with the site.",
            span("@grant none / unsafeWindow", "page-world execution"), rule_id="USERSCRIPT-H3", scope=FindingScope(world="MAIN"),
        ))
    privileged = [g for g in grants if g in _PRIV_GRANTS]
    connects = meta.get("connect") or []
    if privileged:
        wildcard = "*" in connects
        findings.append(make_finding(
            "browser.userscript.privileged-grant", P, target, SEV.HIGH if wildcard or not connects else SEV.MEDIUM, 0.7,
            f"The userscript uses privileged grants ({', '.join(privileged)}), which can send data cross-origin outside the page's same-origin policy.",
            span("@grant", f"@grant {privileged[0]}; @connect {connects[:3]}"), rule_id="USERSCRIPT-H2", scope=FindingScope(world="USER_SCRIPT"),
            alternatives=["Script that syncs data with the vendor's own API."],
        ))
    if "*" in connects:
        findings.append(make_finding(
            "browser.userscript.wildcard-connect", P, target, SEV.HIGH, 0.75,
            "The userscript may send requests to any host (@connect *).", span("@connect", "@connect *"), rule_id="USERSCRIPT-H2", scope=FindingScope(world="USER_SCRIPT"),
        ))
    return findings
