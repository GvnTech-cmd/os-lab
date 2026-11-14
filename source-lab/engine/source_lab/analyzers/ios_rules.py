"""iOS rules from the research: provisioning identity, injected frameworks, hook symbols, entitlements, user-script worlds.

The iOS paper and the Playbook describe repackaging detection (a re-signed bundle carries the attacker's Team ID and an
injected FridaGadget.dylib), jailbreak tweak engines (Substrate, Substitute, ElleKit, libhooker) and the difference between
WKContentWorld.page and the isolated defaultClient world. The analyzer reports the Team ID and profile type for the auditor
to compare with the publisher; it cannot know the expected Team ID itself.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from source_lab.evidence.schema import EvidenceSpan, Finding, FindingScope, FindingState, PlatformType, SeverityLevel, TargetIdentity

from ._common import Rule, make_finding
from .binfmt import parse_macho

P = PlatformType.IOS_APP
SEV = SeverityLevel

HOOK_NAME = re.compile(r"(FridaGadget|frida-gadget|libsubstrate|CydiaSubstrate|MobileSubstrate|libsubstitute|Substitute|ElleKit|ellekit|libhooker|SSLKillSwitch|libMobileGestalt_hook)", re.I)
JAILBREAK_PATHS = (b"/Library/MobileSubstrate", b"/var/jb/", b"/usr/lib/substrate", b"/Library/Frameworks/CydiaSubstrate.framework")

HOOK_SYMBOLS: Dict[str, Tuple[SeverityLevel, float, str]] = {
    "MSHookFunction": (SEV.HIGH, 0.85, "installs an inline hook with Cydia Substrate"),
    "MSHookMessageEx": (SEV.HIGH, 0.85, "replaces an Objective-C method with Cydia Substrate"),
    "substitute_hook_functions": (SEV.HIGH, 0.85, "installs an inline hook with Substitute"),
    "rebind_symbols": (SEV.HIGH, 0.8, "rebinds lazy and GOT pointers (fishhook)"),
    "rebind_symbols_image": (SEV.HIGH, 0.8, "rebinds symbols of one image (fishhook)"),
    "vm_remap": (SEV.HIGH, 0.7, "remaps pages, the W^X-friendly way tweak engines patch code"),
    "mach_vm_remap": (SEV.HIGH, 0.7, "remaps pages, the W^X-friendly way tweak engines patch code"),
    "task_for_pid": (SEV.HIGH, 0.75, "obtains another process's task port"),
    "ptrace": (SEV.MEDIUM, 0.55, "debugger attachment or anti-debugging (PT_DENY_ATTACH)"),
    "dlopen": (SEV.LOW, 0.35, "loads a dynamic library at runtime"),
}

SOURCE_RULES: Tuple[Rule, ...] = (
    Rule("ios.wkwebview.user-script-document-start", r"WKUserScriptInjectionTimeAtDocumentStart|injectionTime\s*:\s*\.atDocumentStart", SEV.MEDIUM, 0.7, "WKUserScript at document start",
         "Injects the user script before the page's own scripts run, so it can hook the page first.", ("Web3 wallet provider or autofill helper.",), world="MAIN", rule_id="RULE-IOS-USER-SCRIPT-DOCUMENT-START"),
    Rule("ios.wkwebview.content-world-main", r"WKContentWorld\s*\.\s*(page|pageWorld)\b|\[\s*WKContentWorld\s+pageWorld\s*\]|WKContentWorld\s+pageWorld", SEV.HIGH, 0.8, "WKContentWorld.page",
         "Executes injected scripts directly in the page's own JavaScript world, where their globals and bridges are visible to page scripts.", ("EIP-1193 provider that must be visible to the page.",), world="MAIN", rule_id="RULE-IOS-CONTENT-WORLD-PAGE"),
    Rule("ios.wkwebview.content-world-isolated", r"WKContentWorld\s*\.\s*(defaultClient|world\s*\()|\[\s*WKContentWorld\s+(defaultClientWorld|worldWithName)|WKContentWorld\s+defaultClientWorld", SEV.LOW, 0.5, "WKContentWorld.defaultClient",
         "Runs the script in an isolated world: its globals are invisible to the page, but its DOM changes and listeners are still observable on the shared document.", ("Safer isolated helper.",), world="ISOLATED", rule_id="RULE-IOS-CONTENT-WORLD-ISOLATED"),
    Rule("ios.jailbreak-path", r"/Library/MobileSubstrate|/var/jb/|/usr/lib/substrate", SEV.HIGH, 0.7, "jailbreak tweak path",
         "References the MobileSubstrate or rootless jailbreak tweak directories, which only exist on jailbroken devices.", ("Jailbreak-detection code that checks for these paths.",), rule_id="RULE-IOS-JAILBREAK-PATH"),
)


def analyze_mobileprovision(plist_obj: Dict[str, Any], file_name: str, target: TargetIdentity) -> List[Finding]:
    """Team identity, profile type and entitlements from a decoded embedded.mobileprovision."""
    findings: List[Finding] = []

    def span(symbol: str, snippet: str) -> EvidenceSpan:
        return EvidenceSpan(file=file_name, symbol=symbol, artifact="manifest", snippet=snippet[:180])

    team = plist_obj.get("TeamIdentifier") or []
    team_id = team[0] if isinstance(team, list) and team else (str(team) if team else None)
    entitlements = plist_obj.get("Entitlements", {}) or {}
    devices = plist_obj.get("ProvisionedDevices") or []
    enterprise = plist_obj.get("ProvisionsAllDevices") is True
    if team_id:
        findings.append(make_finding("ios.provision.team-identity", P, target, SEV.INFO, 0.95,
            f"The bundle is signed under Team ID {team_id} ({plist_obj.get('TeamName', 'unnamed team')}). A repackaged IPA carries the re-signer's Team ID, not the publisher's.",
            span("TeamIdentifier", f"Team ID {team_id}; AppIDName={plist_obj.get('AppIDName')}; expires {plist_obj.get('ExpirationDate')}"),
            rule_id="RULE-IOS-TEAM-IDENTITY", limitations=["Compare the Team ID with the publisher's official App Store Team ID; the analyzer does not know the expected value."]))
    if enterprise:
        findings.append(make_finding("ios.provision.profile-type", P, target, SEV.MEDIUM, 0.6,
            "The profile is an enterprise distribution profile (ProvisionsAllDevices): the app is installed outside the App Store and can be re-signed by anyone with an enterprise certificate.",
            span("ProvisionsAllDevices", "ProvisionsAllDevices = true"), rule_id="RULE-IOS-PROFILE-TYPE", alternatives=["Genuine in-house enterprise app."]))
    elif devices:
        kind = "development" if entitlements.get("get-task-allow") is True else "ad-hoc"
        findings.append(make_finding("ios.provision.profile-type", P, target, SEV.LOW, 0.5,
            f"The profile is a {kind} profile bound to {len(devices)} device(s), not an App Store profile.", span("ProvisionedDevices", f"{kind} profile, {len(devices)} devices"),
            rule_id="RULE-IOS-PROFILE-TYPE", alternatives=["Pre-release test build."]))
    if entitlements.get("dynamic-codesigning") is True:
        findings.append(make_finding("ios.entitlement.dynamic-codesigning", P, target, SEV.HIGH, 0.7,
            "The profile grants dynamic-codesigning, which lets the app create executable memory at runtime (a W^X relaxation).", span("dynamic-codesigning", "dynamic-codesigning = true"),
            rule_id="RULE-IOS-DYNAMIC-CODESIGNING", alternatives=["JIT engine such as a browser or emulator."]))
    return findings


def analyze_framework_name(path: str, target: TargetIdentity, container: Optional[str] = None) -> Optional[Finding]:
    """A finding when a bundle path names a known injection or hooking library."""
    norm = path.replace("\\", "/").rstrip("/")
    leaf = norm.rsplit("/", 1)[-1]
    if not HOOK_NAME.search(leaf) or not (leaf.endswith((".dylib", ".framework")) or "/Frameworks/" in norm or "/DynamicLibraries/" in norm):
        return None
    where = f"{container}!{norm}" if container else norm
    return make_finding("ios.framework.injected", P, target, SEV.CRITICAL, 0.9,
        f"The bundle contains {leaf}, a hooking or instrumentation library. Repackaged apps add FridaGadget.dylib or a tweak engine next to the real code.",
        EvidenceSpan(file=where, symbol=leaf, artifact="binary", binary_path=norm, snippet="bundle file name matches a hooking framework"), rule_id="RULE-IOS-INJECTED-FRAMEWORK",
        alternatives=["Instrumented test build."], scope=FindingScope(process="app"))


def analyze_macho_bytes(rel: str, data: bytes, target: TargetIdentity) -> List[Finding]:
    """Findings from a Mach-O's load commands, undefined symbols and code signature."""
    findings: List[Finding] = []
    seen: set = set()
    for info in parse_macho(data):
        for command, path in info.dylibs:
            if HOOK_NAME.search(path) and ("hook-lib", path) not in seen:
                seen.add(("hook-lib", path))
                findings.append(make_finding("ios.macho.hook-framework-ref", P, target, SEV.CRITICAL, 0.9,
                    f"The binary has a {command} load command for {path}: it loads a hooking library at launch.",
                    EvidenceSpan(file=rel, symbol=path, artifact="binary", binary_path=rel, snippet=f"{command} {path}"), state=FindingState.STATIC_LEAD, rule_id="RULE-IOS-HOOK-FW",
                    alternatives=["Instrumented test build."]))
        for symbol in info.undefined_symbols:
            if symbol in HOOK_SYMBOLS and ("sym", symbol) not in seen:
                seen.add(("sym", symbol))
                severity, confidence, meaning = HOOK_SYMBOLS[symbol]
                findings.append(make_finding(f"ios.macho.hook-symbol.{symbol}", P, target, severity, confidence, f"The binary imports {symbol}, which {meaning}.",
                    EvidenceSpan(file=rel, symbol=symbol, artifact="binary", binary_path=rel, snippet=f"undefined symbol _{symbol} ({info.cpu})"), rule_id="RULE-IOS-HOOK-SYMBOL",
                    alternatives=["Anti-tamper code, analytics SDK or developer tooling."]))
        sig = info.signature
        if sig and sig.entitlements.get("dynamic-codesigning") and ("dyncs", rel) not in seen:
            seen.add(("dyncs", rel))
            findings.append(make_finding("ios.entitlement.dynamic-codesigning", P, target, SEV.HIGH, 0.75,
                "The code signature carries dynamic-codesigning, so the app can create executable memory at runtime.",
                EvidenceSpan(file=rel, symbol="dynamic-codesigning", artifact="binary", binary_path=rel, snippet="entitlement dynamic-codesigning = true"), rule_id="RULE-IOS-DYNAMIC-CODESIGNING"))
        if sig and sig.entitlements.get("get-task-allow") and ("gta", rel) not in seen:
            seen.add(("gta", rel))
            findings.append(make_finding("ios.entitlement.get-task-allow", P, target, SEV.HIGH, 0.8,
                "The code signature carries get-task-allow, so a same-user process can obtain the app's task port.",
                EvidenceSpan(file=rel, symbol="get-task-allow", artifact="binary", binary_path=rel, snippet="entitlement get-task-allow = true"), rule_id="RULE-IOS-GET-TASK-ALLOW"))
    return findings
