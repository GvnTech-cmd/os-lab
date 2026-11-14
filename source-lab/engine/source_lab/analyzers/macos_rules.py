"""macOS rules from the research: code-signature entitlements, load commands, rpaths, interposition, injection symbols.

The macOS paper and the Playbook describe the static triage an auditor does with `codesign`, `otool -l` and `otool -L`.
These rules read the same data from the Mach-O itself: the hardened-runtime and ad-hoc flags and entitlements from the
embedded signature, LC_LOAD_DYLIB / LC_LOAD_WEAK_DYLIB / LC_REEXPORT_DYLIB, LC_RPATH, the section table and the undefined
symbols. Nothing is executed.
"""

from __future__ import annotations

import plistlib
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from source_lab.evidence.schema import EvidenceSpan, Finding, FindingScope, FindingState, PlatformType, SeverityLevel, TargetIdentity

from ._common import Rule, make_finding
from .binfmt import MachOInfo, parse_macho

P = PlatformType.MACOS_APP
SEV = SeverityLevel

#: entitlement -> (finding id suffix, severity, confidence, meaning)
ENTITLEMENTS: Dict[str, Tuple[str, SeverityLevel, float, str]] = {
    "com.apple.security.cs.disable-library-validation": ("disable-library-validation", SEV.HIGH, 0.8, "loads plug-ins or dylibs signed by any developer, which exposes it to @rpath dylib hijacking and proxy dylibs"),
    "com.apple.security.cs.allow-dyld-environment-variables": ("allow-dyld-environment-variables", SEV.HIGH, 0.8, "honours DYLD_INSERT_LIBRARIES and other DYLD_* variables, so a library can be preloaded into it"),
    "com.apple.security.get-task-allow": ("get-task-allow", SEV.HIGH, 0.75, "lets any same-user process obtain its task port and inject threads"),
    "com.apple.security.cs.allow-unsigned-executable-memory": ("allow-unsigned-executable-memory", SEV.HIGH, 0.7, "disables W^X enforcement, permitting inline code patching without vm_remap"),
    "com.apple.security.cs.disable-executable-page-protection": ("disable-executable-page-protection", SEV.HIGH, 0.7, "disables executable page protection"),
    "com.apple.security.cs.allow-jit": ("allow-jit", SEV.MEDIUM, 0.5, "may map writable and executable memory for JIT compilation"),
    "com.apple.security.cs.debugger": ("debugger", SEV.MEDIUM, 0.6, "may attach to other processes as a debugger"),
}

#: undefined symbol -> (severity, confidence, meaning)
INJECTION_SYMBOLS: Dict[str, Tuple[SeverityLevel, float, str]] = {
    "task_for_pid": (SEV.HIGH, 0.8, "obtains another process's Mach task port"),
    "mach_vm_allocate": (SEV.MEDIUM, 0.5, "allocates memory in a Mach task"),
    "mach_vm_write": (SEV.HIGH, 0.75, "writes memory into a Mach task"),
    "mach_vm_protect": (SEV.MEDIUM, 0.55, "changes page protections in a Mach task"),
    "mach_vm_remap": (SEV.HIGH, 0.7, "remaps pages, used by inline hooking engines to respect W^X"),
    "vm_remap": (SEV.HIGH, 0.7, "remaps pages, used by inline hooking engines to respect W^X"),
    "thread_create_running": (SEV.HIGH, 0.8, "creates a running thread inside another task"),
    "thread_set_state": (SEV.HIGH, 0.7, "sets another thread's register state"),
    "ptrace": (SEV.MEDIUM, 0.55, "attaches to or hides from a debugger"),
    "dlopen": (SEV.LOW, 0.35, "loads a dynamic library at runtime"),
    "rebind_symbols": (SEV.HIGH, 0.8, "fishhook-style symbol rebinding of lazy and GOT pointers"),
    "rebind_symbols_image": (SEV.HIGH, 0.8, "fishhook-style symbol rebinding of one image"),
}

_SUSPICIOUS_PREFIXES = ("/tmp", "/private/tmp", "/var/", "/private/var", "/Users/", "/Library/Application Support", "/Volumes/")
_SYSTEM_PREFIXES = ("/usr/lib", "/System/Library", "/Library/Frameworks")


def _span(rel: str, symbol: str, snippet: str, offset: Optional[int] = None) -> EvidenceSpan:
    return EvidenceSpan(file=rel, symbol=symbol, artifact="binary", binary_path=rel, offset=hex(offset) if offset is not None else None, snippet=snippet[:180])


def _bundle_exec_dir(path: Path) -> Path:
    for parent in path.parents:
        if parent.suffix == ".app":
            return parent / "Contents" / "MacOS"
    return path.parent


def _resolve_rpath(entry: str, file_path: Path) -> Optional[Path]:
    if entry.startswith("@executable_path"):
        return (_bundle_exec_dir(file_path) / entry[len("@executable_path"):].lstrip("/")).resolve()
    if entry.startswith("@loader_path"):
        return (file_path.parent / entry[len("@loader_path"):].lstrip("/")).resolve()
    return None


def analyze_macho_file(rel: str, data: bytes, file_path: Path, target: TargetIdentity) -> Tuple[List[Finding], bool]:
    """(findings, was_macho) for one file; `was_macho` is False when the bytes are not a Mach-O image."""
    slices = parse_macho(data)
    if not slices:
        return [], False
    findings: List[Finding] = []
    seen: set = set()

    def add(finding: Finding) -> None:
        key = (finding.finding_id, finding.evidence[0].symbol, finding.evidence[0].file)
        if key not in seen:
            seen.add(key)
            findings.append(finding)

    for info in slices:
        sig = info.signature
        if sig:
            for key, (suffix, severity, confidence, meaning) in ENTITLEMENTS.items():
                if sig.entitlements.get(key):
                    add(make_finding(f"macos.entitlement.{suffix}", P, target, severity, confidence, f"The code signature grants {key}: the app {meaning}.",
                        _span(rel, key, f"entitlement {key} = true ({info.cpu})"), rule_id="H1", scope=FindingScope(process="host"),
                        alternatives=["Developer build, plug-in host or an app that needs JIT."]))
            if sig.adhoc:
                add(make_finding("macos.macho.adhoc-signature", P, target, SEV.MEDIUM, 0.6,
                    "The binary is ad-hoc signed (no developer identity), so its publisher cannot be verified and it can be re-signed freely.",
                    _span(rel, "CodeDirectory flags", f"flags=0x{sig.flags:x} (adhoc)"), rule_id="H4", alternatives=["Locally built or open-source binary."]))
            elif info.filetype == "executable" and not sig.hardened_runtime:
                add(make_finding("macos.macho.hardened-runtime-missing", P, target, SEV.LOW, 0.45,
                    "The signed executable does not enable the hardened runtime, which is what blocks DYLD injection and unsigned code.",
                    _span(rel, "CodeDirectory flags", f"flags=0x{sig.flags:x} (no runtime flag)"), rule_id="H5"))
        elif info.filetype == "executable":
            add(make_finding("macos.macho.unsigned", P, target, SEV.LOW, 0.4, "The executable carries no code signature.",
                _span(rel, "LC_CODE_SIGNATURE", "no LC_CODE_SIGNATURE load command"), rule_id="H4"))

        for command, path in info.dylibs:
            if command == "LC_REEXPORT_DYLIB" and not path.startswith(_SYSTEM_PREFIXES):
                add(make_finding("macos.macho.reexport-dylib", P, target, SEV.HIGH, 0.7,
                    f"The image re-exports {path}, the Mach-O equivalent of a DLL proxy that forwards a library's symbols.",
                    _span(rel, path, f"{command} {path}"), rule_id="H4", alternatives=["Umbrella framework that re-exports its sub-libraries."]))
            if path.startswith(_SUSPICIOUS_PREFIXES):
                add(make_finding("macos.macho.non-system-dylib", P, target, SEV.HIGH, 0.8,
                    f"The image loads {path} from a user-writable location instead of a system or bundle path.",
                    _span(rel, path, f"{command} {path}"), rule_id="H4", alternatives=["Developer build linked against a local library."]))

        for entry in info.rpaths:
            if entry.startswith(_SUSPICIOUS_PREFIXES):
                add(make_finding("macos.macho.rpath", P, target, SEV.HIGH, 0.7,
                    f"LC_RPATH points at the user-writable directory {entry}, where a hijacked dylib could be planted.",
                    _span(rel, entry, f"LC_RPATH {entry}"), rule_id="H4"))
                continue
            resolved = _resolve_rpath(entry, file_path)
            if resolved is not None and not resolved.exists():
                add(make_finding("macos.macho.rpath", P, target, SEV.MEDIUM, 0.5,
                    f"LC_RPATH {entry} resolves to a directory that does not exist in the bundle, so an attacker who creates it controls which @rpath libraries load.",
                    _span(rel, entry, f"LC_RPATH {entry} -> missing"), rule_id="H4", limitations=["The bundle may be incomplete; confirm against the installed app."]))

        if info.has_section("__interpose"):
            add(make_finding("macos.macho.dyld-interposition", P, target, SEV.CRITICAL, 0.9,
                "The Mach-O declares a __DATA,__interpose section, a table of symbol replacements applied by dyld at load time.",
                _span(rel, "__interpose", "section __interpose in the section table", data.find(b"__interpose") if data.find(b"__interpose") != -1 else None),
                scope=FindingScope(process="dyld"), rule_id="H3", alternatives=["Security probe, memory sanitizer or custom allocator."]))
        if info.has_section("__mod_init_func") and info.filetype in ("dylib", "bundle"):
            add(make_finding("macos.macho.constructor", P, target, SEV.LOW, 0.45,
                "The library registers static constructors (__mod_init_func) that run when it is loaded, before the host's code calls it.",
                _span(rel, "__mod_init_func", "section __mod_init_func present"), rule_id="H3", alternatives=["Ordinary C++ static initialisers."]))
        for env in info.dyld_environment:
            add(make_finding("macos.macho.dyld-environment", P, target, SEV.HIGH, 0.8,
                f"An LC_DYLD_ENVIRONMENT command bakes {env.split('=')[0]} into the binary.", _span(rel, env, f"LC_DYLD_ENVIRONMENT {env}"), rule_id="H1"))

        for symbol in info.undefined_symbols:
            if symbol in INJECTION_SYMBOLS:
                severity, confidence, meaning = INJECTION_SYMBOLS[symbol]
                add(make_finding(f"macos.macho.injection-symbol.{symbol}", P, target, severity, confidence,
                    f"The binary imports {symbol}, which {meaning}.", _span(rel, symbol, f"undefined symbol _{symbol} ({info.cpu})"), rule_id="H2",
                    alternatives=["Debugger, profiler, crash reporter or developer tool."]))
    return findings, True


def analyze_info_plist_environment(rel: str, plist: Dict[str, Any], target: TargetIdentity) -> List[Finding]:
    """LSEnvironment (or a launchd EnvironmentVariables dict) that sets DYLD_* variables."""
    findings: List[Finding] = []
    for key in ("LSEnvironment", "EnvironmentVariables"):
        env = plist.get(key)
        if isinstance(env, dict):
            for name, value in env.items():
                if str(name).startswith("DYLD_"):
                    findings.append(make_finding("macos.bundle.lsenvironment", P, target, SEV.HIGH, 0.85,
                        f"The plist sets {name}={value} in the app's launch environment, preloading code into the process at every start.",
                        EvidenceSpan(file=rel, symbol=str(name), artifact="manifest", snippet=f"{key}: {name}={value}"[:180]), rule_id="H1", scope=FindingScope(process="dyld"),
                        alternatives=["Developer tooling such as a memory sanitizer."]))
    return findings


# Source rules beyond swizzling: fishhook, DYLD variables, constructors, user script timing and content world.
SOURCE_RULES: Tuple[Rule, ...] = (
    Rule("macos.fishhook.rebind-symbols", r"\brebind_symbols(_image)?\s*\(", SEV.HIGH, 0.8, "fishhook rebind_symbols",
         "Rebinds lazy and GOT symbol pointers (fishhook) to hook C functions at runtime.", ("Instrumentation or test harness.",), process="host"),
    Rule("macos.dyld.insert-libraries", r"DYLD_INSERT_LIBRARIES", SEV.HIGH, 0.75, "DYLD_INSERT_LIBRARIES",
         "References the dyld variable that preloads a dynamic library into another process.", ("Documentation or a test that clears the variable.",), process="dyld"),
    Rule("macos.objc.constructor", r"__attribute__\s*\(\(\s*constructor\s*\)\)|\+\s*\(void\)\s*load\b", SEV.LOW, 0.4, "constructor / +load",
         "Runs code when the image loads, before main, which is where injected libraries usually start.", ("Ordinary module initialisation.",), process="host"),
    Rule("macos.wkwebview.user-script-document-start", r"WKUserScriptInjectionTimeAtDocumentStart|injectionTime\s*:\s*\.atDocumentStart", SEV.MEDIUM, 0.7, "WKUserScript at document start",
         "Injects the user script before the page's own scripts run, so it can hook the page first.", ("Wallet provider or autofill helper.",), world="MAIN"),
    Rule("macos.wkwebview.content-world-page", r"WKContentWorld\s*\.\s*(page|pageWorld)\b|\[\s*WKContentWorld\s+pageWorld\s*\]", SEV.HIGH, 0.7, "WKContentWorld.page",
         "Runs the script in the page's own JavaScript world, where it shares globals with the site and its bridges are visible to page scripts.", ("EIP-1193 provider that must be visible to the page.",), world="MAIN"),
    Rule("macos.wkwebview.content-world-isolated", r"WKContentWorld\s*\.\s*(defaultClient|world\s*\()|\[\s*WKContentWorld\s+(defaultClientWorld|worldWithName)", SEV.LOW, 0.5, "WKContentWorld.defaultClient",
         "Runs the script in an isolated world: its globals are invisible to the page, but its DOM changes are not.", ("Safer isolated helper.",), world="ISOLATED"),
)
