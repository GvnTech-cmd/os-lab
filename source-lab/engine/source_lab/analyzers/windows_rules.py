"""Windows rules from the research: PE structure, injection chains, hook engines, CLR weaving, DLL proxies, WebView2, Electron.

The Windows paper and the Playbook list the cross-process injection primitives, the hook engines and the Electron
hardening switches. Imports are read from the PE import table, so a symbol that only appears as text is reported at lower
confidence as a possible dynamic resolution instead of as an import.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from source_lab.evidence.schema import EvidenceSpan, Finding, FindingScope, FindingState, PlatformType, SeverityLevel, TargetIdentity

from ._common import Rule, make_finding
from .binfmt import PEInfo, parse_pe

P = PlatformType.WINDOWS_APP
SEV = SeverityLevel

#: api -> (meaning, severity, confidence)
INJECTION_APIS: Dict[str, Tuple[str, SeverityLevel, float]] = {
    "VirtualAllocEx": ("Process memory allocation in foreign process", SEV.HIGH, 0.7),
    "VirtualProtectEx": ("Page protection change in foreign process", SEV.HIGH, 0.7),
    "WriteProcessMemory": ("Process memory manipulation in foreign process", SEV.HIGH, 0.75),
    "NtAllocateVirtualMemory": ("Native memory allocation (often used to evade user-mode hooks)", SEV.MEDIUM, 0.5),
    "NtWriteVirtualMemory": ("Native cross-process memory write", SEV.HIGH, 0.75),
    "NtMapViewOfSection": ("Section mapping into another process", SEV.HIGH, 0.7),
    "NtUnmapViewOfSection": ("Image unmapping, the first step of process hollowing", SEV.HIGH, 0.7),
    "CreateRemoteThread": ("Remote thread injection", SEV.CRITICAL, 0.85),
    "CreateRemoteThreadEx": ("Remote thread injection (extended)", SEV.CRITICAL, 0.85),
    "NtCreateThreadEx": ("Native remote thread creation", SEV.CRITICAL, 0.85),
    "QueueUserAPC": ("Asynchronous Procedure Call (APC) injection", SEV.HIGH, 0.8),
    "NtQueueApcThread": ("Native APC injection", SEV.HIGH, 0.8),
    "SetThreadContext": ("Thread execution hijacking / process hollowing", SEV.CRITICAL, 0.85),
    "SetWindowsHookExW": ("Global Windows desktop message hook", SEV.HIGH, 0.75),
    "SetWindowsHookExA": ("Global Windows desktop message hook", SEV.HIGH, 0.75),
    "AdjustTokenPrivileges": ("Privilege adjustment, used to enable SeDebugPrivilege", SEV.MEDIUM, 0.5),
}

_CHAIN_CLASSIC = ("OpenProcess", "VirtualAllocEx", "WriteProcessMemory")
_CHAIN_THREAD = ("CreateRemoteThread", "CreateRemoteThreadEx", "NtCreateThreadEx")

SYSTEM_DLLS = {
    "version.dll", "winmm.dll", "dxgi.dll", "dinput8.dll", "d3d9.dll", "d3d11.dll", "xinput1_3.dll", "xinput1_4.dll", "winhttp.dll",
    "msimg32.dll", "dbghelp.dll", "wtsapi32.dll", "iphlpapi.dll", "cryptsp.dll", "dwmapi.dll", "winspool.drv", "lpk.dll", "uxtheme.dll", "msvcp140.dll",
}

# (needle, finding id, severity, confidence, meaning)
_STRING_RULES: Tuple[Tuple[bytes, str, SeverityLevel, float, str], ...] = (
    (b"DetourAttach", "windows.pe.hook-engine.detours", SEV.HIGH, 0.75, "Microsoft Detours inline hook engine"),
    (b"DetourTransactionBegin", "windows.pe.hook-engine.detours", SEV.HIGH, 0.75, "Microsoft Detours inline hook engine"),
    (b"MH_CreateHook", "windows.pe.hook-engine.minhook", SEV.HIGH, 0.75, "MinHook inline hook engine"),
    (b"MH_EnableHook", "windows.pe.hook-engine.minhook", SEV.HIGH, 0.75, "MinHook inline hook engine"),
    (b"HarmonyLib", "windows.clr.il-weaving", SEV.HIGH, 0.65, "Harmony runtime IL patching"),
    (b"0Harmony", "windows.clr.il-weaving", SEV.HIGH, 0.65, "Harmony runtime IL patching"),
    (b"Mono.Cecil", "windows.clr.il-weaving", SEV.MEDIUM, 0.55, "Mono.Cecil IL rewriting"),
    (b"MonoMod", "windows.clr.il-weaving", SEV.HIGH, 0.65, "MonoMod runtime detours"),
    (b"CORECLR_PROFILER", "windows.clr.profiler-hook", SEV.HIGH, 0.75, "CLR profiler environment hook"),
    (b"COR_ENABLE_PROFILING", "windows.clr.profiler-hook", SEV.HIGH, 0.75, "CLR profiler environment hook"),
    (b"DOTNET_STARTUP_HOOKS", "windows.clr.startup-hook", SEV.HIGH, 0.75, ".NET startup hook that loads an assembly into every managed process"),
    (b"AddScriptToExecuteOnDocumentCreated", "windows.webview2.document-created-script", SEV.HIGH, 0.75, "WebView2 document-created script injection"),
    (b"AddHostObjectToScript", "windows.webview2.host-object-bridge", SEV.MEDIUM, 0.7, "WebView2 host object exposed to web content"),
    (b"ExecuteScriptAsync", "windows.webview2.execute-script", SEV.MEDIUM, 0.6, "WebView2 on-demand script execution"),
    (b"ExecuteScriptWithResultAsync", "windows.webview2.execute-script", SEV.MEDIUM, 0.6, "WebView2 on-demand script execution with results"),
)


def _contains(data: bytes, needle: bytes) -> bool:
    return needle in data or needle.decode("ascii", errors="ignore").encode("utf-16-le") in data


def _offset(data: bytes, needle: bytes) -> int:
    i = data.find(needle)
    return i if i != -1 else data.find(needle.decode("ascii", errors="ignore").encode("utf-16-le"))


def _binary_span(rel: str, symbol: str, data: bytes, needle: bytes, note: str) -> EvidenceSpan:
    return EvidenceSpan(file=rel, symbol=symbol, artifact="binary", binary_path=rel, offset=hex(max(_offset(data, needle), 0)), snippet=note[:180])


def analyze_pe(rel: str, data: bytes, target: TargetIdentity) -> List[Finding]:
    """Findings for one PE file; a file that does not parse as PE falls back to a string search at lower confidence."""
    if len(data) < 64 or data[:2] != b"MZ":
        return []
    info = parse_pe(data)
    findings: List[Finding] = []
    imports = info.all_imports() if info else set()

    for api, (meaning, severity, confidence) in INJECTION_APIS.items():
        needle = api.encode("ascii")
        if info and api.lower() in imports:
            dll = info.imported(api) or "?"
            findings.append(make_finding(
                f"windows.pe.injection-api.{api.lower()}", P, target, severity, min(confidence + 0.05, 0.95),
                f"{meaning} capability: the binary imports {api} from {dll}.",
                _binary_span(rel, api, data, needle, f"Imported '{api}' from {dll} (import table)"),
                scope=FindingScope(process="foreign"), alternatives=["Debugger, crash reporter, profiler, game overlay or security software."],
            ))
        elif _contains(data, needle):
            reduced = round(confidence * (0.6 if info else 1.0), 3)
            note = "referenced as text only, possibly resolved dynamically with GetProcAddress" if info else "string reference in a file that did not parse as PE"
            findings.append(make_finding(
                f"windows.pe.injection-api.{api.lower()}", P, target, severity, reduced,
                f"{meaning} capability: {api} is {note}.",
                _binary_span(rel, api, data, needle, f"'{api}' {note}"),
                scope=FindingScope(process="foreign"), alternatives=["Debugger, crash reporter, profiler, game overlay or security software."],
                limitations=[f"{api} is not in the import table; this is weaker evidence than an import."] if info else [],
            ))
    if not info:
        return findings

    # Injection chains from the import table
    def have(*names: str) -> bool:
        return all(n.lower() in imports for n in names)

    if have(*_CHAIN_CLASSIC) and any(n.lower() in imports for n in _CHAIN_THREAD):
        findings.append(make_finding("windows.pe.classic-dll-injection", P, target, SEV.CRITICAL, 0.9,
            "The imports form the classic DLL injection chain: OpenProcess, VirtualAllocEx, WriteProcessMemory and a remote thread call.",
            _binary_span(rel, "injection chain", data, b"WriteProcessMemory", "OpenProcess + VirtualAllocEx + WriteProcessMemory + remote thread"),
            scope=FindingScope(process="foreign"), alternatives=["Debugger or EDR agent."]))
    if any(n.lower() in imports for n in ("NtUnmapViewOfSection", "ZwUnmapViewOfSection")) and have("WriteProcessMemory") and any(n.lower() in imports for n in ("SetThreadContext", "NtSetContextThread")):
        findings.append(make_finding("windows.pe.process-hollowing", P, target, SEV.CRITICAL, 0.85,
            "The imports match process hollowing: unmap the target image, write a new one, then redirect the thread.",
            _binary_span(rel, "process hollowing", data, b"WriteProcessMemory", "NtUnmapViewOfSection + WriteProcessMemory + SetThreadContext"),
            scope=FindingScope(process="foreign"), alternatives=["Packer or self-updating loader."]))
    if any(n.lower() in imports for n in ("CreateProcessW", "CreateProcessA")) and any(n.lower() in imports for n in ("QueueUserAPC", "NtQueueApcThread")) and have("ResumeThread"):
        findings.append(make_finding("windows.pe.early-bird-apc", P, target, SEV.HIGH, 0.7,
            "The imports match Early Bird APC injection: create a suspended process, queue an APC, resume it.",
            _binary_span(rel, "early bird", data, b"QueueUserAPC", "CreateProcess + QueueUserAPC + ResumeThread"),
            scope=FindingScope(process="foreign"), alternatives=["Launcher that starts a helper process."]))
    if _contains(data, b"SeDebugPrivilege") and have("AdjustTokenPrivileges"):
        findings.append(make_finding("windows.pe.se-debug-privilege", P, target, SEV.HIGH, 0.7,
            "The binary enables SeDebugPrivilege through AdjustTokenPrivileges, which lets it open almost any process.",
            _binary_span(rel, "SeDebugPrivilege", data, b"SeDebugPrivilege", "SeDebugPrivilege + AdjustTokenPrivileges"),
            scope=FindingScope(process="foreign"), alternatives=["Task manager, debugger or system utility."]))

    # Strings: hook engines, CLR weaving, WebView2 inside binaries
    seen = set()
    for needle, fid, severity, confidence, meaning in _STRING_RULES:
        if fid in seen or not _contains(data, needle):
            continue
        seen.add(fid)
        state = FindingState.STATIC_LEAD if fid.startswith("windows.webview2") else FindingState.CAPABILITY
        findings.append(make_finding(fid, P, target, severity, confidence, f"{meaning} is referenced in the binary ('{needle.decode()}').",
            _binary_span(rel, needle.decode(), data, needle, f"binary references '{needle.decode()}'"), state=state,
            scope=FindingScope(process="renderer" if fid.startswith("windows.webview2") else "host", world="MAIN" if fid.startswith("windows.webview2") else None),
            alternatives=["Legitimate hybrid application bridge." if fid.startswith("windows.webview2") else "Game mod loader, profiler or compatibility layer."]))

    # DLL proxy: a system-named DLL shipped with the app whose exports forward elsewhere
    name = rel.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name in SYSTEM_DLLS and info.is_dll:
        if info.forwarders:
            sample = ", ".join(f"{n}->{t}" for n, t in info.forwarders[:2])
            findings.append(make_finding("windows.pe.dll-proxy", P, target, SEV.HIGH, 0.8,
                f"{name} sits beside the application, shares a system DLL's name and forwards {len(info.forwarders)} export(s) to another module: the shape of a DLL proxy or side-loading shim.",
                EvidenceSpan(file=rel, symbol=name, artifact="binary", binary_path=rel, snippet=f"{len(info.forwarders)} forwarded exports, e.g. {sample}"[:180]),
                scope=FindingScope(process="host"), alternatives=["Deliberate game mod (BepInEx, ReShade) or compatibility shim."]))
        elif not info.has_signature:
            findings.append(make_finding("windows.pe.dll-proxy", P, target, SEV.MEDIUM, 0.5,
                f"{name} shares a system DLL's name, ships with the application and carries no Authenticode signature.",
                EvidenceSpan(file=rel, symbol=name, artifact="binary", binary_path=rel, snippet="system-named DLL in the app directory, unsigned"),
                scope=FindingScope(process="host"), alternatives=["Legacy compatibility copy of a system library."]))
    if info.is_managed and any(f.finding_id.startswith("windows.clr.") for f in findings):
        findings.append(make_finding("windows.pe.managed-clr", P, target, SEV.INFO, 0.9,
            "The binary is a managed (.NET) assembly; its IL can be rewritten or patched at runtime.", EvidenceSpan(file=rel, symbol="CLR header", artifact="binary", binary_path=rel, snippet="IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR present")))

    if not info.has_signature and any(f.severity in (SEV.HIGH, SEV.CRITICAL) for f in findings):
        findings.append(make_finding("windows.pe.unsigned", P, target, SEV.LOW, 0.5,
            "The binary carries no Authenticode signature, so its publisher cannot be verified.", EvidenceSpan(file=rel, symbol="Security directory", artifact="binary", binary_path=rel, snippet="no IMAGE_DIRECTORY_ENTRY_SECURITY"),
            alternatives=["Internal build or open-source tool distributed without code signing."]))
    return findings


# ---------------------------------------------------------------------------------------------------------------------
# Electron
# ---------------------------------------------------------------------------------------------------------------------

ELECTRON_RULES: Tuple[Rule, ...] = (
    Rule("windows.electron.node-integration", r"nodeIntegration(InWorker|InSubFrames)?\s*:\s*true", SEV.HIGH, 0.8, "nodeIntegration: true",
         "Enables Node.js runtime access directly in Electron renderer processes.", ("Local-only app that never loads remote content.",), process="renderer"),
    Rule("windows.electron.context-isolation-disabled", r"contextIsolation\s*:\s*false", SEV.HIGH, 0.85, "contextIsolation: false",
         "Disables context isolation, exposing preload script privileges to untrusted page scripts.", process="renderer"),
    Rule("windows.electron.sandbox-disabled", r"\bsandbox\s*:\s*false", SEV.HIGH, 0.8, "sandbox: false",
         "Turns off the renderer sandbox, so a renderer compromise reaches the operating system.", process="renderer"),
    Rule("windows.electron.web-security-disabled", r"webSecurity\s*:\s*false", SEV.HIGH, 0.85, "webSecurity: false",
         "Disables the same-origin policy for the window.", process="renderer"),
    Rule("windows.electron.insecure-content", r"allowRunningInsecureContent\s*:\s*true", SEV.HIGH, 0.75, "allowRunningInsecureContent: true",
         "Allows mixed content to run, so network attackers can inject script.", process="renderer"),
    Rule("windows.electron.remote-module", r"enableRemoteModule\s*:\s*true", SEV.HIGH, 0.8, "enableRemoteModule: true",
         "Exposes the main-process remote module to renderers.", process="renderer"),
    Rule("windows.electron.preload-script", r"\bpreload\s*:\s*", SEV.MEDIUM, 0.6, "webPreferences.preload",
         "Registers a preload script that runs before page scripts with access to privileged APIs.", ("Standard contextBridge pattern.",), process="renderer"),
)

FUSE_SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
# v1 fuse wire order and what each switch means; (name, id suffix, dangerous state, severity, confidence, hypothesis)
_FUSES: Tuple[Tuple[str, str, str, SeverityLevel, float, str], ...] = (
    ("RunAsNode", "run-as-node", "1", SEV.HIGH, 0.8, "ELECTRON_RUN_AS_NODE is honoured, so the signed binary can be run as a plain Node.js interpreter."),
    ("EnableCookieEncryption", "cookie-encryption", "0", SEV.LOW, 0.5, "Cookies are stored unencrypted."),
    ("EnableNodeOptionsEnvironmentVariable", "node-options-env", "1", SEV.MEDIUM, 0.7, "NODE_OPTIONS is honoured and can inject code into the main process."),
    ("EnableNodeCliInspectArguments", "node-cli-inspect", "1", SEV.MEDIUM, 0.7, "--inspect arguments are honoured, allowing a debugger to attach."),
    ("EnableEmbeddedAsarIntegrityValidation", "asar-integrity-disabled", "0", SEV.HIGH, 0.75, "The ASAR integrity check is off, so app.asar can be repackaged without detection."),
    ("OnlyLoadAppFromAsar", "load-app-from-folder", "0", SEV.MEDIUM, 0.65, "The app may load code from a plain app/ folder instead of app.asar, which makes it trivially replaceable."),
    ("LoadBrowserProcessSpecificV8Snapshot", "v8-snapshot", "x", SEV.INFO, 0.3, ""),
    ("GrantFileProtocolExtraPrivileges", "file-protocol-privileges", "1", SEV.MEDIUM, 0.65, "file:// pages receive extra privileges."),
)


def analyze_electron_fuses(rel: str, data: bytes, target: TargetIdentity) -> List[Finding]:
    """Reads the Electron fuse wire from an Electron binary and reports switches that weaken the app."""
    at = data.find(FUSE_SENTINEL)
    if at == -1:
        return []
    start = at + len(FUSE_SENTINEL)
    if start + 2 > len(data):
        return []
    version, length = data[start], data[start + 1]
    wire = data[start + 2 : start + 2 + length]
    if version != 1 or len(wire) < length:
        return [make_finding("windows.electron.fuse.unreadable", P, target, SEV.INFO, 0.4, f"The Electron fuse wire has unsupported version {version}.",
                             EvidenceSpan(file=rel, symbol="fuse wire", artifact="binary", binary_path=rel, offset=hex(at), snippet=f"version={version} length={length}"),
                             limitations=["Fuse switches were not interpreted."])]
    findings: List[Finding] = []
    for index, (name, suffix, dangerous, severity, confidence, hypothesis) in enumerate(_FUSES):
        if index >= len(wire) or dangerous == "x":
            continue
        state_char = chr(wire[index])
        if state_char == dangerous:
            findings.append(make_finding(
                f"windows.electron.fuse.{suffix}", P, target, severity, confidence, hypothesis,
                EvidenceSpan(file=rel, symbol=name, artifact="binary", binary_path=rel, offset=hex(start + 2 + index), snippet=f"fuse {name} = {'enabled' if state_char == '1' else 'disabled'}"),
                scope=FindingScope(process="main"), alternatives=["Default fuse value in an Electron build that has not been hardened."],
            ))
    return findings
