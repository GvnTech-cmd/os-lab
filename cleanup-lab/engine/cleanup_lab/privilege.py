"""CLN-20: typed privileged actions and the macOS disk-access probe.

System maintenance that needs root or admin — apt's package cache, a journald
vacuum, ``apt-get autoremove``, a Spotlight index rebuild, DISM's component
store cleanup — is deliberately **not** a plan → clean path item: an elevated
``rm`` would bypass the Trash rules (rule 3) and the ownership guard, which is
exactly the bug class the lab refuses. Instead the cleaning happens inside the
tool itself, behind the same pattern as the CLN-08 container actions: fixed argv
from a validated allowlist (mirrored by
``cleanup-lab/catalog/actions/privileged.json``), a fingerprinted preview, a
single-use confirmation id, a fresh candidate check and an audited run. The
page sends an action id and a preview id — never a command string and never a
path. No password is stored or asked by the engine: elevation uses the
desktop's own mechanism (polkit ``pkexec``, ``sudo -n``, the ``osascript``
administrator dialog, or the UAC prompt through ``ShellExecuteExW``).

``disk_access`` ports the read-only macOS Full Disk Access check: it tries to
list TCC-protected folders in the user's Library and reports what it can prove,
with guidance. Everywhere else it reports ``applicable: False``, so the
dashboard hides it per [[lat.md/ux-readiness.md]].
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass

from . import paths

#: Every fixed-argv probe answers within this many seconds or counts as absent.
PROBE_TIMEOUT = 5.0
#: An elevated run answers within this many seconds or the job fails honestly.
RUN_TIMEOUT = 900.0
#: A preview lives ten minutes, like the container previews.
PREVIEW_TTL = 600
OUTPUT_LIMIT = 2000

#: ``(previewArgv | None, runArgv)`` per action id; the catalog file must mirror
#: this table exactly, and :func:`_actions` refuses any drift.
ALLOWED = {
    "linux": {
        "apt-cache": (None, ("apt-get", "clean")),
        "journal-vacuum": (("journalctl", "--disk-usage"), ("journalctl", "--vacuum-size=100M")),
        "apt-autoremove": (
            ("apt-get", "autoremove", "--purge"),
            ("apt-get", "autoremove", "--purge", "-y"),
        ),
    },
    "macos": {
        "spotlight-rebuild": (("mdutil", "-s", "/"), ("mdutil", "-E", "/")),
    },
    "windows": {
        "dism-cleanup": (
            ("Dism.exe", "/online", "/Cleanup-Image", "/AnalyzeComponentStore"),
            ("Dism.exe", "/online", "/Cleanup-Image", "/StartComponentCleanup"),
        ),
    },
}

#: Read-only measurement root for the file-backed previews.
MEASURE_PATHS = {"linux": {"apt-cache": "/var/cache/apt/archives"}}


class PrivilegeError(ValueError):
    """An unavailable mechanism, a stale preview, or a failed command."""


@dataclass(frozen=True)
class PrivilegedPreview:
    """One fingerprinted privileged action, ready to be confirmed once."""

    platform: str
    action_id: str
    risk: str
    preview_argv: tuple[str, ...] | None
    run_argv: tuple[str, ...]
    elevation: str
    elevation_argv: tuple[str, ...]
    digest: str
    count: int | None
    total_bytes: int | None
    created_at: float


def _load_catalog(root):
    path = os.path.join(root, "cleanup-lab", "catalog", "actions", "privileged.json")
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != 1 or set(data.get("platforms", {})) != set(ALLOWED):
        raise PrivilegeError("Privileged action catalog is invalid")
    for name, entries in data["platforms"].items():
        if set(entries) != set(ALLOWED[name]):
            raise PrivilegeError("Privileged action catalog is invalid")
        for key, action in entries.items():
            allowed_preview, allowed_run = ALLOWED[name][key]
            mode = action.get("previewMode")
            valid = (
                action.get("id") == "privileged.{0}.{1}".format(name, key)
                and action.get("risk") in ("low", "medium", "high")
                and isinstance(action.get("name"), str) and action["name"]
                and isinstance(action.get("impact"), str) and action["impact"]
                and tuple(action.get("run", ())) == allowed_run
                and (allowed_preview is None) == (action.get("preview") is None)
                and (allowed_preview is None or tuple(action["preview"]) == allowed_preview)
                and mode == ("files" if allowed_preview is None else action.get("previewMode"))
                and mode in ("files", "text", "packages")
                and (mode != "files" or action.get("measurePath") == MEASURE_PATHS[name][key])
            )
            if not valid:
                raise PrivilegeError("Privileged action catalog is invalid")
    return data["platforms"]


def _actions(root, platform):
    if platform not in ALLOWED:
        raise PrivilegeError("{0} has no typed privileged actions".format(platform))
    return _load_catalog(root)[platform]


def _run(argv, *, timeout, env, runner=subprocess.run):
    try:
        return runner(
            list(argv), shell=False, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, check=False, env=dict(env),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PrivilegeError("Privileged command failed: {0}".format(exc)) from exc


def _trimmed(value):
    return (value or "").strip()[:OUTPUT_LIMIT]


def _measure_path(path):
    """Read-only size and file count of one folder; unreadable parts are noted."""
    total = 0
    count = 0
    notes = []

    def walk(current):
        nonlocal total, count
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            notes.append("{0}: {1}".format(current, exc.strerror or exc))
            return
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    walk(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                    count += 1
            except OSError as exc:
                notes.append("{0}: {1}".format(entry.path, exc.strerror or exc))

    walk(path)
    return {
        "count": count,
        "totalBytes": total,
        "missing": not os.path.isdir(path),
        "notes": notes[:20],
    }


def _parse_autoremove(text):
    """Package names from ``apt-get autoremove --purge``'s REMOVED section only."""
    names = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("The following"):
            in_section = "will be REMOVED" in line
            continue
        if not in_section:
            continue
        if not line.strip():
            in_section = False
            continue
        if line.startswith(("  ", "\t")):
            names.extend(part.rstrip("*").rstrip(":") for part in line.split())
            continue
        in_section = False
    return sorted(set(names))


def _elevation(platform, argv, env, which=shutil.which):
    """The desktop's own elevation mechanism: the engine never asks for a password."""
    if platform == "linux":
        for name in ("pkexec", "sudo"):
            found = which(name, path=env.get("PATH", ""))
            if not found:
                continue
            if name == "pkexec":
                return name, [found, "--disable-internal-agent", *argv]
            return name, [found, "-n", *argv]
        raise PrivilegeError(
            "No elevation mechanism: install polkit's pkexec (or cache sudo credentials) to run this action"
        )
    if platform == "macos":
        found = which("osascript", path=env.get("PATH", ""))
        if not found:
            raise PrivilegeError("No elevation mechanism: osascript was not found")
        script = "do shell script {0} with administrator privileges".format(
            shlex.quote(" ".join(shlex.quote(part) for part in argv))
        )
        return "osascript", [found, "-e", script]
    if platform == "windows":
        return "uac", list(argv)
    raise PrivilegeError("{0} has no typed elevation mechanism".format(platform))


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _candidates(action, env, runner):
    """Read-only preview material: measured files, tool text, or package names."""
    mode = action.get("previewMode")
    if mode == "files":
        return _measure_path(action["measurePath"])
    result = _run(action["preview"], timeout=PROBE_TIMEOUT, env=env, runner=runner)
    if result.returncode != 0:
        raise PrivilegeError(
            _trimmed(result.stderr) or "The preview command returned an error"
        )
    if mode == "packages":
        names = _parse_autoremove(result.stdout)
        return {"candidates": names, "count": len(names)}
    return {"output": _trimmed(result.stdout), "count": None, "totalBytes": None}


def preview(root, action_id, *, platform=None, env=None, which=shutil.which,
            runner=subprocess.run, measure=None, clock=time.time):
    """Fingerprint one action's candidates; read-only except the tool's own probe."""
    platform = platform or paths.platform_id()
    env = os.environ if env is None else env
    actions = _actions(root, platform)
    key = action_id.rsplit(".", 1)[-1]
    if action_id != "privileged.{0}.{1}".format(platform, key) or key not in actions:
        raise PrivilegeError("Unknown or unavailable privileged action id")
    action = actions[key]
    measure = measure or _measure_path
    if action["previewMode"] == "files":
        material = measure(action["measurePath"])
    else:
        material = _candidates(action, env, runner)
    elevation, elevation_argv = _elevation(platform, action["run"], env, which=which)
    plan = PrivilegedPreview(
        platform=platform,
        action_id=action["id"],
        risk=action["risk"],
        preview_argv=tuple(action["preview"]) if action.get("preview") else None,
        run_argv=tuple(action["run"]),
        elevation=elevation,
        elevation_argv=tuple(elevation_argv),
        digest=_digest(material),
        count=material.get("count"),
        total_bytes=material.get("totalBytes"),
        created_at=clock(),
    )
    return plan, material


def execute(root, plan, *, env=None, which=shutil.which, runner=subprocess.run,
            measure=None, clock=time.time, executor=None):
    """Re-preview, refuse changed candidates, then run the confirmed action once."""
    env = os.environ if env is None else env
    if clock() - plan.created_at > PREVIEW_TTL:
        raise PrivilegeError("Privileged preview expired")
    fresh, _ = preview(
        root, plan.action_id, platform=plan.platform, env=env, which=which,
        runner=runner, measure=measure, clock=clock,
    )
    if (fresh.platform != plan.platform or fresh.action_id != plan.action_id
            or fresh.preview_argv != plan.preview_argv or fresh.run_argv != plan.run_argv
            or fresh.digest != plan.digest):
        raise PrivilegeError("Privileged candidates changed; preview again")
    if plan.count == 0:
        raise PrivilegeError("There are no candidates for this action")
    if plan.platform == "windows":
        outcome = (executor or _shell_execute_runas)(list(plan.run_argv), RUN_TIMEOUT)
    else:
        result = _run(plan.elevation_argv, timeout=RUN_TIMEOUT, env=env, runner=runner)
        if result.returncode != 0:
            raise PrivilegeError(_trimmed(result.stderr) or "The privileged command failed")
        outcome = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    return {
        "actionId": plan.action_id,
        "platform": plan.platform,
        "status": "completed",
        "candidateCount": plan.count,
        "command": list(plan.elevation_argv if plan.platform != "windows" else plan.run_argv),
        "elevation": plan.elevation,
        "output": _trimmed(outcome.get("stdout", "")) or (
            "The elevated process finished; a UAC run has no console output."
            if plan.platform == "windows" else ""
        ),
        "bytesRemoved": None,
    }


def disk_access(platform=None, env=None, *, prober=None):
    """The read-only macOS Full Disk Access probe; ``applicable: False`` elsewhere."""
    platform = platform or paths.platform_id()
    if platform != "macos":
        return {
            "applicable": False, "granted": None, "paths": [], "guidance": "",
            "reason": "Full Disk Access is a macOS privacy setting.",
        }
    env = os.environ if env is None else env
    home = paths.home_dir(env)
    probes = [
        os.path.join(home, "Library", "Safari"),
        os.path.join(home, "Library", "Mail"),
    ]
    check = prober or os.listdir
    results = []
    granted = None
    for path in probes:
        try:
            check(path)
        except PermissionError:
            results.append({"path": path, "readable": False, "reason": "Permission denied"})
            granted = False
            continue
        except FileNotFoundError:
            results.append({"path": path, "readable": None, "reason": "not present"})
            continue
        except OSError as exc:
            results.append({"path": path, "readable": None, "reason": str(exc)})
            continue
        results.append({"path": path, "readable": True, "reason": ""})
        granted = True
    return {
        "applicable": True,
        "granted": granted,
        "paths": results,
        "guidance": (
            "Grant the app running the console Full Disk Access under System Settings → Privacy & Security → Full Disk Access, then re-check."
            if granted is False else ""
        ),
    }


def capabilities(root, *, platform=None, env=None, which=shutil.which,
                 runner=subprocess.run):
    """The typed ``GET /api/cleanup/privileged`` payload."""
    platform = platform or paths.platform_id()
    env = os.environ if env is None else env
    applicable = platform in ALLOWED
    payload = {
        "platform": platform,
        "applicable": applicable,
        "elevation": None,
        "actions": [],
        "diskAccess": disk_access(platform, env),
    }
    if not applicable:
        return payload
    try:
        elevation, _ = _elevation(platform, ["true"], env, which=which)
    except PrivilegeError:
        elevation = None
    payload["elevation"] = elevation
    for key, action in _actions(root, platform).items():
        payload["actions"].append({
            "id": action["id"],
            "name": action["name"],
            "risk": action["risk"],
            "impact": action["impact"],
            "previewMode": action["previewMode"],
            "previewArgv": action.get("preview"),
            "runArgv": action["run"],
        })
    return payload


def _shell_execute_runas(argv, timeout):
    """UAC through ``ShellExecuteExW``; no shell, no stored password, waits for exit."""
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NO_CONSOLE = 0x00008000
    WAIT_TIMEOUT = 0x00000102
    STILL_ACTIVE = 259

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    kernel32 = ctypes.windll.kernel32
    shell32 = ctypes.windll.shell32
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.lpVerb = "runas"
    info.lpFile = argv[0]
    info.lpParameters = subprocess.list2cmdline(argv[1:]) if len(argv) > 1 else None
    info.nShow = 1  # SW_SHOWNORMAL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        raise PrivilegeError("The elevation prompt was refused or is not available")
    handle = info.hProcess
    if not handle:
        return {"returncode": 0, "stdout": "", "stderr": ""}
    code = wintypes.DWORD(STILL_ACTIVE)
    waited = kernel32.WaitForSingleObject(handle, int(timeout * 1000))
    if waited == WAIT_TIMEOUT:
        kernel32.CloseHandle(handle)
        raise PrivilegeError("The elevated command timed out")
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    if code.value != 0:
        raise PrivilegeError("The elevated command exited with code {0}".format(code.value))
    return {"returncode": code.value, "stdout": "", "stderr": ""}
