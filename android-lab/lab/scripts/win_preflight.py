#!/usr/bin/env python3
"""Windows no-admin lab preflight (PENT-23).

Read-only virtualization readiness check for the Windows zero-admin lab:
VT-x/AMD-V, the Windows hypervisor (Hyper-V/VBS), VirtualBox, WSL, Podman,
PowerShell execution policy, RAM, disk and Python. Every finding carries a
remediation and says whether that fix needs Administrator rights, so a student
on a locked-down machine knows what they can fix alone and what to ask IT for.

The tool is split in two so it can be tested on any OS:

* ``gather_facts()`` probes the host (Windows only, no elevation, no writes)
  and returns a plain dict.
* ``evaluate(facts)`` is pure: facts in, checks + usable lab models out.
  ``--facts FILE`` evaluates a saved facts file, which is how the test suite
  replays known failure scenarios.

Usage:
    python scripts/win_preflight.py                 human-readable report
    python scripts/win_preflight.py --json          JSON report
    python scripts/win_preflight.py --save-facts f  also write raw facts
    python scripts/win_preflight.py --facts f       evaluate a saved facts file
    python scripts/win_preflight.py --strict        exit 1 on warnings too

Exit code: 0 when no check failed, 1 when one did (or a warning with --strict).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional

SCHEMA_VERSION = 1
LAB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK, INFO, WARN, FAIL, SKIP = "ok", "info", "warn", "fail", "skip"
_RANK = {OK: 0, SKIP: 0, INFO: 0, WARN: 1, FAIL: 2}

# Thresholds follow docs/HOW_TO_USE_CHEATSHEET.md (host minimum 8 GB RAM /
# 20 GB disk, recommended 16 GB / 40 GB) and lab.ps1 (10 GB hard floor).
RAM_MIN_GB, RAM_REC_GB = 8, 16
RAM_FAIL_GB = 4
DISK_FAIL_GB, DISK_MIN_GB = 10, 20
PYTHON_MIN = (3, 11)
BLOCKING_POLICIES = {"restricted", "allsigned"}
VBOX_DEFAULT = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
PROBE_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Parsing helpers (pure, unit-tested)
# ---------------------------------------------------------------------------
def decode_console(raw: bytes) -> str:
    """Decode console output; wsl.exe writes UTF-16LE unless WSL_UTF8=1."""
    if not raw:
        return ""
    if raw.startswith(b"\xff\xfe") or (len(raw) > 1 and raw[1:2] == b"\x00"):
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\ufeff", "").replace("\x00", "")


def parse_wsl_list(text: str) -> list[dict[str, Any]]:
    """Parse ``wsl -l -v`` into [{name, state, version, default}]."""
    distros = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        default = line.lstrip().startswith("*")
        parts = line.replace("*", " ", 1).split() if default else line.split()
        if len(parts) < 3 or parts[0].upper() == "NAME":
            continue
        version = parts[-1]
        if not version.isdigit():
            continue
        distros.append({
            "name": " ".join(parts[:-2]),
            "state": parts[-2],
            "version": int(version),
            "default": default,
        })
    return distros


def wsl_not_installed(text: str, returncode: int) -> bool:
    """True when wsl.exe answers that the WSL feature is not installed."""
    low = text.lower()
    markers = ("not installed", "wsl --install", "yüklü değil", "is not enabled")
    return returncode != 0 and any(m in low for m in markers)


def wsl_no_distros(text: str) -> bool:
    """True when WSL is installed but answers that it has no distributions."""
    low = text.lower()
    return "no installed distributions" in low or "has no installed" in low


def parse_podman_machines(text: str) -> list[dict[str, Any]]:
    """Parse ``podman machine list --format json``."""
    try:
        data = json.loads(text or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    machines = []
    for m in data:
        if not isinstance(m, dict):
            continue
        running = bool(m.get("Running")) or str(m.get("LastUp", "")).lower() == "currently running"
        machines.append({"name": str(m.get("Name", "")).rstrip("*"), "running": running})
    return machines


def parse_version(text: str) -> Optional[str]:
    m = re.search(r"\d+(?:\.\d+)+", text or "")
    return m.group(0) if m else None


def _to_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    return None


# ---------------------------------------------------------------------------
# Probing (Windows only, read-only, no elevation)
# ---------------------------------------------------------------------------
def _system_exe(*parts: str) -> Optional[str]:
    """Absolute path to a Windows system binary under %SystemRoot%\\System32."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    path = os.path.join(root, "System32", *parts)
    return path if os.path.isfile(path) else None


def _which_trusted(name: str) -> Optional[str]:
    """shutil.which, but never a binary sitting in the current or lab directory.

    On Windows a bare command name can resolve from the current directory, so a
    planted e.g. podman.exe next to the lab would otherwise be executed.
    """
    path = shutil.which(name)
    if not path:
        return None
    folder = os.path.normcase(os.path.dirname(os.path.abspath(path)))
    untrusted = {os.path.normcase(os.path.abspath(d)) for d in (os.getcwd(), LAB_DIR)}
    return None if folder in untrusted else path


def _run(cmd: list[str], env: Optional[dict] = None) -> tuple[int, str]:
    """Run a fixed argv (list form, never a shell) with a timeout.

    Every caller passes an absolute executable path and constant arguments;
    no user, file or network input reaches the command line.
    """
    try:
        # Audited: argv list, no shell, absolute path from _system_exe/_which_trusted,
        # constant arguments only (see the callers below).
        proc = subprocess.run(cmd, capture_output=True, timeout=PROBE_TIMEOUT,  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit
                              env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {PROBE_TIMEOUT}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, f"could not start: {exc.__class__.__name__}"
    return proc.returncode, decode_console(proc.stdout) + decode_console(proc.stderr)


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:160]
    return ""


def _probe_error(tool: str, code: int, out: str) -> str:
    detail = _first_line(out) or "no output"
    return f"{tool} failed (exit {code}): {detail}"


_CIM_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue';"
    "$p=Get-CimInstance Win32_Processor|Select-Object -First 1;"
    "$c=Get-CimInstance Win32_ComputerSystem;"
    "$o=Get-CimInstance Win32_OperatingSystem;"
    "[pscustomobject]@{cpu=$p.Name;vfe=$p.VirtualizationFirmwareEnabled;"
    "vmx=$p.VMMonitorModeExtensions;slat=$p.SecondLevelAddressTranslationExtensions;"
    "hyp=$c.HypervisorPresent;ram=$c.TotalPhysicalMemory;caption=$o.Caption;"
    "build=$o.BuildNumber;arch=$o.OSArchitecture;"
    # Skip the Process scope: this probe itself runs with -ExecutionPolicy Bypass.
    # -List is in precedence order, so the first defined scope is the effective one.
    "ep=[string]$e.ExecutionPolicy;eps=[string]$e.Scope}"
    "|ConvertTo-Json -Compress"
)
_CIM_PREFIX = (
    "$e=Get-ExecutionPolicy -List|Where-Object{[string]$_.Scope -ne 'Process' -and "
    "[string]$_.ExecutionPolicy -ne 'Undefined'}|Select-Object -First 1;"
)
GPO_SCOPES = {"machinepolicy", "userpolicy"}


def _probe_cim() -> dict[str, Any]:
    shell = (_system_exe("WindowsPowerShell", "v1.0", "powershell.exe")
             or _which_trusted("pwsh"))
    if not shell:
        return {}
    # -ExecutionPolicy Bypass applies to this one child process only.
    code, out = _run([shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                      "Bypass", "-Command", _CIM_PREFIX + _CIM_SCRIPT])
    if code != 0:
        return {}
    start = out.find("{")
    try:
        return json.loads(out[start:]) if start >= 0 else {}
    except ValueError:
        return {}


def _probe_admin() -> Optional[bool]:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return None


def _probe_wsl() -> dict[str, Any]:
    exe = _system_exe("wsl.exe")
    if not exe:
        return {"installed": False, "distros": []}
    env = dict(os.environ, WSL_UTF8="1")
    code, out = _run([exe, "-l", "-v"], env=env)
    if wsl_not_installed(out, code):
        return {"installed": False, "distros": []}
    distros = parse_wsl_list(out)
    if code != 0 and not distros and not wsl_no_distros(out):
        # Timeout, launch failure or an unrecognized error: do not guess.
        return {"installed": None, "distros": [], "error": _probe_error("wsl -l -v", code, out)}
    return {"installed": True, "distros": distros}


def _probe_podman() -> dict[str, Any]:
    exe = _which_trusted("podman")
    if not exe:
        return {"installed": False, "version": None, "machines": []}
    vcode, ver = _run([exe, "--version"])
    if vcode != 0:
        return {"installed": True, "version": None, "machines": [],
                "error": _probe_error("podman --version", vcode, ver)}
    mcode, ml = _run([exe, "machine", "list", "--format", "json"])
    if mcode != 0:
        return {"installed": True, "version": parse_version(ver), "machines": [],
                "error": _probe_error("podman machine list", mcode, ml)}
    return {"installed": True, "version": parse_version(ver),
            "machines": parse_podman_machines(ml[ml.find("["):] if "[" in ml else "")}


def _probe_virtualbox() -> dict[str, Any]:
    on_default = os.path.isfile(VBOX_DEFAULT)
    exe = VBOX_DEFAULT if on_default else _which_trusted("VBoxManage")
    if not exe:
        return {"installed": False, "version": None}
    code, ver = _run([exe, "--version"])
    facts = {"installed": True, "version": parse_version(ver), "path": exe,
             # lab.ps1's vbox-* commands only use the default install path.
             "default_path": on_default}
    if code != 0:
        facts["error"] = _probe_error("VBoxManage --version", code, ver)
    return facts


def _probe_zone_id(path: str) -> Optional[int]:
    """Mark-of-the-Web zone of a file (3 = Internet), read from its NTFS stream."""
    try:
        with open(path + ":Zone.Identifier", encoding="utf-8", errors="replace") as fh:
            m = re.search(r"ZoneId\s*=\s*(\d+)", fh.read())
    except OSError:
        return None
    return int(m.group(1)) if m else None


def _free_gb(path: str) -> Optional[float]:
    try:
        return round(shutil.disk_usage(path).free / 1024 ** 3, 1)
    except OSError:
        return None


def gather_facts(lab_dir: str = LAB_DIR) -> dict[str, Any]:
    """Collect host facts. Read-only; on non-Windows only the basics are filled."""
    is_windows = sys.platform == "win32"
    facts: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "platform": "windows" if is_windows else sys.platform,
        "arch": platform.machine(),
        "python": {"version": platform.python_version()},
        "disk_free_gb": _free_gb(lab_dir),
    }
    if not is_windows:
        return facts
    # VirtualBox VMs (lab.ps1 vbox-create) and WSL/Podman images live under the
    # user profile, which may be on another volume than the lab checkout.
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    same_volume = (os.path.splitdrive(os.path.abspath(profile))[0].lower()
                   == os.path.splitdrive(os.path.abspath(lab_dir))[0].lower())
    cim = _probe_cim()
    ram = cim.get("ram")
    facts.update({
        "os_caption": cim.get("caption"),
        "os_build": cim.get("build"),
        "is_admin": _probe_admin(),
        "cpu": {
            "name": (cim.get("cpu") or "").strip() or None,
            "virtualization_firmware_enabled": _to_bool(cim.get("vfe")),
            "vmx_extensions": _to_bool(cim.get("vmx")),
            "slat": _to_bool(cim.get("slat")),
        },
        "hypervisor_present": _to_bool(cim.get("hyp")),
        "ram_gb": round(int(ram) / 1024 ** 3, 1) if str(ram or "").isdigit() else None,
        # Empty means every non-Process scope is Undefined -> the OS default applies.
        "execution_policy": cim.get("ep") or ("Undefined" if cim else None),
        "execution_policy_scope": cim.get("eps") or None,
        "lab_ps1_zone_id": _probe_zone_id(os.path.join(lab_dir, "lab.ps1")),
        "vm_disk_free_gb": None if same_volume else _free_gb(profile),
        "wsl": _probe_wsl(),
        "podman": _probe_podman(),
        "virtualbox": _probe_virtualbox(),
    })
    return facts


# ---------------------------------------------------------------------------
# Evaluation (pure)
# ---------------------------------------------------------------------------
def fix(text: str, admin: bool = False) -> dict[str, Any]:
    """One remediation step; ``admin`` says whether that step needs elevation/IT."""
    return {"text": text, "admin": admin}


def _check(cid: str, status: str, message: str,
           fixes: Optional[list[Any]] = None) -> dict[str, Any]:
    steps = [f if isinstance(f, dict) else fix(f) for f in (fixes or [])]
    return {"id": cid, "status": status, "message": message, "remediation": steps,
            # True when the primary fix (first step) needs admin/IT; later steps are
            # workarounds and carry their own per-step "admin" flag.
            "needs_admin": bool(steps) and steps[0]["admin"]}


def _version_tuple(text: Optional[str]) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text or ""))[:3]


def ps_quote(value: str) -> str:
    """Quote a value as a PowerShell single-quoted literal (safe to copy/paste)."""
    return "'" + str(value).replace("'", "''") + "'"


_CONTROL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x1f\x7f-\x9f]")


def clean(text: Any) -> str:
    """Strip ANSI escapes and control characters from fact-derived text."""
    return _CONTROL.sub("", str(text))


def _vtx_state(facts: dict[str, Any]) -> str:
    """'hypervisor' | 'enabled' | 'disabled' | 'unsupported' | 'unknown'.

    When the Windows hypervisor is running, Win32_Processor reports
    VMMonitorModeExtensions=False and SLAT=False even though VT-x is on
    (Windows owns it; seen on Windows 11 build 26300), so HypervisorPresent
    must be read before concluding the CPU lacks VT-x.
    """
    cpu = facts.get("cpu") or {}
    if facts.get("hypervisor_present") is True:
        return "hypervisor"
    if cpu.get("vmx_extensions") is False:
        return "unsupported"
    vfe = cpu.get("virtualization_firmware_enabled")
    if vfe is True:
        return "enabled"
    if vfe is False:
        return "disabled"
    return "unknown"


def _is_x64(facts: dict[str, Any]) -> bool:
    arch = str(facts.get("arch") or "").upper()
    return not arch or arch in ("AMD64", "X86_64", "64-BIT", "64 BIT")


def _disk_check(cid: str, label: str, gb: Any, add) -> None:
    if not isinstance(gb, (int, float)):
        return
    if gb < DISK_FAIL_GB:
        add(_check(cid, FAIL, f"{label}: {gb} GB free, below the {DISK_FAIL_GB} GB floor.",
                   ["Free space on that drive (Disk Cleanup, empty Downloads/Recycle Bin)."]))
    elif gb < DISK_MIN_GB:
        add(_check(cid, WARN, f"{label}: {gb} GB free, below the {DISK_MIN_GB} GB minimum for images.",
                   ["Free space before pulling emulator/VM images."]))
    else:
        add(_check(cid, OK, f"{label}: {gb} GB free."))


def evaluate(facts: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    add = checks.append

    # 1. Platform
    if facts.get("platform") != "windows":
        add(_check("platform", SKIP, f"Not a Windows host ({clean(facts.get('platform'))}); "
                   "this preflight targets the Windows zero-admin lab.",
                   ["On Linux/macOS use scripts/preflight.sh instead."]))
        return _summarize(facts, checks, vtx="unknown")
    arch = str(facts.get("arch") or "").upper()
    caption = clean(facts.get("os_caption") or "Windows")
    if not _is_x64(facts):
        add(_check("platform", WARN, f"{caption} on {clean(arch)}: the emulator, VM and container "
                   "images are x86_64 only.",
                   ["Use Model 1 (native userland, static workflows) on this host."]))
    else:
        add(_check("platform", OK, f"{caption} (build {clean(facts.get('os_build') or '?')}), "
                   f"{clean(arch) or 'x64'}"))

    # 2. Privilege
    admin = facts.get("is_admin")
    if admin is True:
        add(_check("privilege", INFO, "Running elevated. The lab is designed for a standard user.",
                   ["Re-run from a normal (non-admin) PowerShell to see what a student sees."]))
    elif admin is False:
        add(_check("privilege", OK, "Standard user (non-admin) confirmed."))
    else:
        add(_check("privilege", INFO, "Could not determine elevation."))

    # 3. VT-x / AMD-V
    vtx = _vtx_state(facts)
    cpu_name = clean((facts.get("cpu") or {}).get("name") or "CPU")
    if vtx == "hypervisor":
        add(_check("vtx", OK, "Hardware virtualization is on and owned by the Windows hypervisor "
                   "(Hyper-V / WSL2 / VBS)."))
    elif vtx == "enabled":
        add(_check("vtx", OK, f"VT-x/AMD-V enabled in firmware ({cpu_name})."))
    elif vtx == "disabled":
        add(_check("vtx", FAIL, "VT-x/AMD-V is DISABLED in BIOS/UEFI: VirtualBox 64-bit guests, "
                   "WSL2 and Podman machines cannot start.",
                   [fix("Enable 'Intel Virtualization Technology' / 'SVM Mode' in BIOS/UEFI "
                        "(needs firmware access: ask IT on a managed PC).", admin=True),
                    fix("Until then use Model 1 (native userland): .\\lab.ps1 setup, then wf1.")]))
    elif vtx == "unsupported":
        add(_check("vtx", FAIL, f"{cpu_name} has no VT-x/AMD-V extensions.",
                   ["Only Model 1 (native userland, static analysis) is possible on this CPU."]))
    else:
        add(_check("vtx", WARN, "Could not read the virtualization state (CIM query failed).",
                   ["Check Task Manager > Performance > CPU > 'Virtualization: Enabled'."]))
    vt_usable = vtx in ("hypervisor", "enabled")

    # 4. VirtualBox (and its clash with the Windows hypervisor)
    vbox = facts.get("virtualbox") or {}
    ver = clean(vbox.get("version") or "?")
    if vbox.get("error"):
        add(_check("virtualbox", WARN, f"VirtualBox found but could not be queried: "
                   f"{clean(vbox['error'])}",
                   ["Run 'VBoxManage --version' yourself to see the error; reinstall if it persists."]))
    elif vbox.get("installed") and vbox.get("default_path") is False:
        add(_check("virtualbox", WARN, f"VirtualBox {ver} found at {clean(vbox.get('path'))}, but the "
                   f"lab.ps1 vbox-* commands only use {VBOX_DEFAULT}.",
                   [fix("Reinstall VirtualBox to the default folder so lab.ps1 can find it.", admin=True)]))
    elif vbox.get("installed"):
        if vtx == "hypervisor":
            steps = [fix("Prefer the Podman/WSL2 path (Model 3), which shares the Windows hypervisor."),
                     fix("VirtualBox 6.1.16+ / 7.x can run on Hyper-V via the Windows Hypervisor "
                         "Platform, but slowly and without nested VT-x (the in-guest Android "
                         "emulator will not boot).")]
            if _version_tuple(ver) and _version_tuple(ver) < (6, 1, 16):
                steps.insert(0, fix("Upgrade VirtualBox to 7.x: older versions fail with "
                                    "VERR_VMX_NO_VMX / VERR_NEM_* while Hyper-V is on.", admin=True))
            steps.append(fix("SECURITY DOWNGRADE, not recommended: 'bcdedit /set hypervisorlaunchtype "
                             "off' plus turning off Memory Integrity removes VBS/HVCI kernel "
                             "protection (and disables WSL2). Only with IT approval.", admin=True))
            add(_check("virtualbox", WARN, f"VirtualBox {ver} found, but the Windows hypervisor is "
                       "active: VirtualBox falls back to the slow NEM mode.", steps))
        elif vt_usable:
            add(_check("virtualbox", OK, f"VirtualBox {ver} installed; VT-x available to it."))
        else:
            add(_check("virtualbox", WARN, f"VirtualBox {ver} installed, but VT-x is not usable, "
                       "so 64-bit guests will not start.", ["Fix the 'vtx' check first."]))
    else:
        add(_check("virtualbox", INFO, "VirtualBox not installed (Model 2 unavailable).",
                   [fix("Optional. The VirtualBox installer needs admin once; ask IT if you want "
                        "Model 2.", admin=True)]))

    # 5. WSL
    wsl = facts.get("wsl") or {}
    distros = wsl.get("distros") or []
    wsl2 = [d for d in distros if d.get("version") == 2]
    if wsl.get("error"):
        add(_check("wsl", WARN, f"Could not query WSL: {clean(wsl['error'])}",
                   ["Run 'wsl -l -v' yourself to see the error; 'wsl --update' often fixes it."]))
    elif not wsl.get("installed"):
        add(_check("wsl", WARN, "WSL is not installed (Podman needs WSL2).",
                   [fix("'wsl --install' needs Administrator once (it enables Windows features "
                        "and reboots): ask IT.", admin=True),
                    fix("Meanwhile use Model 1 (native userland).")]))
    elif not distros:
        add(_check("wsl", WARN, "WSL is installed but has no distribution.",
                   ["wsl --install -d Ubuntu   (per-user, no admin once the feature is on)"]))
    elif not wsl2:
        names = ", ".join(clean(d["name"]) for d in distros)
        add(_check("wsl", WARN, f"Only WSL1 distributions ({names}); containers need WSL2.",
                   [f"wsl --set-version {ps_quote(clean(distros[0]['name']))} 2",
                    "wsl --set-default-version 2"]))
    elif not vt_usable and vtx != "unknown":
        add(_check("wsl", FAIL, "WSL2 distributions exist but VT-x is off, so they cannot start.",
                   ["Fix the 'vtx' check first."]))
    else:
        add(_check("wsl", OK, "WSL2 ready: " + ", ".join(
            f"{clean(d['name'])} ({clean(d['state'])})" for d in wsl2)))

    # 6. Podman
    pod = facts.get("podman") or {}
    machines = pod.get("machines") or []
    pver = clean(pod.get("version") or "")
    if pod.get("error"):
        add(_check("podman", WARN, f"Podman found but could not be queried: {clean(pod['error'])}",
                   ["Run 'podman machine list' yourself to see the error."]))
    elif not pod.get("installed"):
        add(_check("podman", INFO, "Podman not installed (Model 3 unavailable).",
                   ["Install Podman Desktop with the per-user ('for me only') option: no admin needed."]))
    elif not wsl2:
        add(_check("podman", WARN, f"Podman {pver} found, but there is no WSL2 backend for its "
                   "machine.", ["Fix the 'wsl' check first."]))
    elif not machines:
        add(_check("podman", WARN, "Podman installed but no machine is initialized.",
                   ["podman machine init", "podman machine start"]))
    elif not any(m["running"] for m in machines):
        add(_check("podman", WARN, f"Podman machine '{clean(machines[0]['name'])}' is stopped.",
                   ["podman machine start"]))
    else:
        add(_check("podman", OK, f"Podman {pver} machine running."))

    # 7. PowerShell execution policy (+ Group Policy scope, + Mark-of-the-Web)
    policy = facts.get("execution_policy")
    scope = str(facts.get("execution_policy_scope") or "")
    if policy and policy.lower() == "undefined":
        # No scope sets a policy: Windows client defaults to Restricted, Server to RemoteSigned.
        policy = "RemoteSigned" if "server" in caption.lower() else "Restricted"
    zone = facts.get("lab_ps1_zone_id")
    from_internet = isinstance(zone, int) and zone >= 3
    unblock = fix("Unblock the downloaded script once, no admin: Unblock-File .\\lab.ps1")
    if policy and policy.lower() in BLOCKING_POLICIES and scope.lower() in GPO_SCOPES:
        add(_check("execution_policy", WARN, f"Execution policy '{clean(policy)}' is enforced by "
                   f"Group Policy ({clean(scope)}): .\\lab.ps1 is blocked and no user setting or "
                   "-ExecutionPolicy switch can override it.",
                   [fix("Ask IT to allow RemoteSigned for your user, or to sign lab.ps1.", admin=True),
                    fix("Meanwhile run the Python tools directly: python scripts\\win_preflight.py")]))
    elif policy and policy.lower() in BLOCKING_POLICIES:
        steps = [fix("One-off, no admin: powershell -ExecutionPolicy Bypass -File .\\lab.ps1 win-preflight"),
                 fix("Persistent, no admin: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned")]
        if from_internet:
            steps.append(unblock)
        add(_check("execution_policy", WARN, f"PowerShell execution policy is '{clean(policy)}': "
                   ".\\lab.ps1 is blocked ('running scripts is disabled on this system').", steps))
    elif policy and policy.lower() == "remotesigned" and from_internet:
        add(_check("execution_policy", WARN, "Policy 'RemoteSigned', but lab.ps1 is marked as "
                   f"downloaded from the Internet (zone {zone}), so PowerShell refuses the unsigned "
                   "script.", [unblock]))
    elif policy and policy.lower() == "unrestricted" and from_internet:
        add(_check("execution_policy", INFO, "Policy 'Unrestricted': lab.ps1 is marked as downloaded, "
                   "so PowerShell will ask for confirmation each run.", [unblock]))
    elif policy:
        add(_check("execution_policy", OK, f"Execution policy '{clean(policy)}' allows lab.ps1."))

    # 8. RAM
    ram = facts.get("ram_gb")
    if isinstance(ram, (int, float)):
        if ram < RAM_FAIL_GB:
            add(_check("ram", FAIL, f"{ram} GB RAM: too little for any VM or container.",
                       ["Use Model 1 (static workflows only)."]))
        elif ram < RAM_MIN_GB:
            add(_check("ram", WARN, f"{ram} GB RAM: below the {RAM_MIN_GB} GB minimum for the emulator.",
                       ["Give the VM at most half: .\\lab.ps1 vbox-create -Memory 2048",
                        "Or limit WSL2 in %UserProfile%\\.wslconfig: [wsl2] memory=3GB"]))
        else:
            note = "" if ram >= RAM_REC_GB else f" (recommended {RAM_REC_GB} GB)"
            add(_check("ram", OK, f"{ram} GB RAM{note}."))

    # 9. Disk: lab checkout, and (if on another volume) the profile drive that holds
    #    VirtualBox VMs and WSL/Podman images.
    _disk_check("disk", "Lab drive", facts.get("disk_free_gb"), add)
    _disk_check("vm_disk", "Profile drive (VM / WSL images)", facts.get("vm_disk_free_gb"), add)

    # 10. Python
    pyver = (facts.get("python") or {}).get("version")
    if pyver:
        if _version_tuple(pyver)[:2] < PYTHON_MIN:
            add(_check("python", FAIL, f"Python {clean(pyver)} is older than "
                       f"{PYTHON_MIN[0]}.{PYTHON_MIN[1]}.",
                       ["Install Python 3.11+ from python.org with 'Install for me only'."]))
        else:
            add(_check("python", OK, f"Python {clean(pyver)}."))

    return _summarize(facts, checks, vtx=vtx)


def _models(facts: dict[str, Any], checks: list[dict[str, Any]], vtx: str) -> dict[str, str]:
    """Readiness per lab model; a model is only 'ready' if every host floor it needs holds."""
    by_id = {c["id"]: c["status"] for c in checks}
    failed = {cid for cid, st in by_id.items() if st == FAIL}
    vt_usable = vtx in ("hypervisor", "enabled")

    # Model 1 runs Python tools on the host: needs Python and room on the lab drive.
    native = "blocked" if failed & {"python", "disk"} else "ready"

    # Models 2/3 run x86_64 guests: need x64, VT-x, and the RAM/disk floors.
    host_ok = _is_x64(facts) and vt_usable and not failed & {"ram", "disk", "vm_disk"}

    vbox_facts = facts.get("virtualbox") or {}
    if vbox_facts.get("error"):
        vbox = "unknown"
    elif not host_ok:
        vbox = "unavailable"
    elif not vbox_facts.get("installed"):
        vbox = "not-installed"
    elif vbox_facts.get("default_path") is False:
        vbox = "needs-setup"
    elif vtx == "hypervisor":
        vbox = "degraded"
    else:
        vbox = "ready"

    if (facts.get("podman") or {}).get("error") or (facts.get("wsl") or {}).get("error"):
        podman = "unknown"
    elif not host_ok:
        podman = "unavailable"
    elif by_id.get("podman") == OK:
        podman = "ready"
    else:
        podman = "needs-setup"
    return {"native_userland": native, "virtualbox": vbox, "podman_wsl2": podman}


def _summarize(facts: dict[str, Any], checks: list[dict[str, Any]], vtx: str) -> dict[str, Any]:
    worst = max((_RANK[c["status"]] for c in checks), default=0)
    overall = {0: OK, 1: WARN, 2: FAIL}[worst]
    models = _models(facts, checks, vtx) if facts.get("platform") == "windows" else {}
    order = [("podman_wsl2", "Model 3: Podman/WSL2"), ("virtualbox", "Model 2: VirtualBox"),
             ("native_userland", "Model 1: native userland")]
    recommended = next((label for key, label in order if models.get(key) == "ready"), None)
    return {
        "tool": "win_preflight",
        "task": "PENT-23",
        "schema": SCHEMA_VERSION,
        "overall": overall,
        "vtx_state": vtx,
        "recommended_model": recommended,
        "models": models,
        # Problems (WARN/FAIL) that only admin/IT can resolve. Optional INFO items such as
        # "VirtualBox not installed" are excluded on purpose; their steps still carry admin=True.
        "admin_only_fixes": [c["id"] for c in checks if c["needs_admin"] and c["status"] in (WARN, FAIL)],
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
_TAGS = {OK: "[OK]  ", INFO: "[INFO]", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}


def format_report(report: dict[str, Any]) -> str:
    lines = ["=== Windows No-Admin Lab Preflight (PENT-23) ==="]
    for c in report["checks"]:
        lines.append(f"  {_TAGS[c['status']]} {c['id']:<17} {clean(c['message'])}")
        for step in c["remediation"]:
            lines.append(f"           -> {clean(step['text'])}" + ("  [admin]" if step["admin"] else ""))
    if report["models"]:
        lines.append("")
        lines.append("Lab models: " + ", ".join(f"{k}={v}" for k, v in report["models"].items()))
        lines.append(f"Recommended: {report['recommended_model'] or 'none (fix the FAIL items)'}")
    if report["admin_only_fixes"]:
        lines.append("Needs IT/admin: " + ", ".join(report["admin_only_fixes"]))
    lines.append(f"Overall: {report['overall'].upper()}")
    return "\n".join(lines)


def save_facts(facts: dict[str, Any], path: str) -> None:
    """Write facts atomically: a temp file in the same folder, then os.replace."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".facts-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(facts, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Windows no-admin lab preflight (PENT-23).")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--facts", help="evaluate a saved facts JSON instead of probing this host")
    ap.add_argument("--save-facts", help="write the probed facts to this JSON file")
    ap.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    args = ap.parse_args(argv)

    if args.facts:
        with open(args.facts, encoding="utf-8") as fh:
            facts = json.load(fh)
    else:
        facts = gather_facts()
    if args.save_facts:
        save_facts(facts, args.save_facts)

    report = evaluate(facts)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
    if report["overall"] == FAIL or (args.strict and report["overall"] == WARN):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
