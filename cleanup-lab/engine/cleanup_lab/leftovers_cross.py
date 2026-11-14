"""Read-only Linux and Windows app leftovers (CLN-10).

Linux installed identity comes from fixed-argv dpkg, rpm, Flatpak and Snap
queries. Windows identity comes from read-only uninstall registry keys. Candidate
names use CLN-09's component-aware confidence rules; uncertain inventories
produce `unknown` rather than an orphan claim.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess

from .catalog import expand
from .clean import fingerprint_path
from .leftovers_macos import _normal_name, classify
from .paths import platform_id

LINUX_COMMANDS = {
    "dpkg": ("dpkg-query", "-W", "-f=${binary:Package}\\n"),
    "rpm": ("rpm", "-qa", "--qf", "%{NAME}\\n"),
    "flatpak": ("flatpak", "list", "--app", "--columns=application"),
    "snap": ("snap", "list"),
}


class LeftoverError(ValueError):
    """A detector configuration or inventory read failed."""


def _config(root, platform, env):
    with open(os.path.join(root, "cleanup-lab", "catalog", "signatures", "cross-platform-leftovers.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != 1 or data.get("family") != "leftovers":
        raise LeftoverError("Invalid cross-platform leftover catalog")
    answer = []
    for item in data.get("roots", {}).get(platform, []):
        if item.get("kind") not in ("config", "share", "cache", "appdata", "localappdata") or not isinstance(item.get("path"), str):
            raise LeftoverError("Invalid leftover root")
        path, _ = expand(item["path"], platform, env)
        if path:
            answer.append((item["kind"], path))
    return answer


def _identity(value):
    value = value.strip()
    if not value:
        return None
    return {"bundleId": value.casefold(), "names": {_normal_name(value)}, "teamId": None}


def linux_inventory(*, env=None, which=shutil.which, runner=subprocess.run):
    env = os.environ if env is None else env
    installed, sources, errors = [], [], []
    for source, argv in LINUX_COMMANDS.items():
        executable = which(argv[0], path=env.get("PATH", ""))
        if not executable:
            continue
        try:
            result = runner([executable, *argv[1:]], shell=False, capture_output=True,
                            text=True, timeout=10, stdin=subprocess.DEVNULL, check=False, env=dict(env))
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append("{0}: {1}".format(source, exc))
            continue
        if result.returncode != 0:
            errors.append("{0}: inventory command failed".format(source))
            continue
        sources.append(source)
        lines = result.stdout.splitlines()
        if source == "snap" and lines and lines[0].lower().startswith("name "):
            lines = lines[1:]
        for line in lines:
            name = line.split()[0] if line.split() else ""
            identity = _identity(name)
            if identity:
                installed.append(identity)
    return installed, sources, errors


def _read_windows_registry():
    import winreg
    entries = []
    roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    paths = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
    for hive in roots:
        for path in paths:
            try:
                parent = winreg.OpenKey(hive, path)
            except OSError:
                continue
            with parent:
                count = winreg.QueryInfoKey(parent)[0]
                for index in range(count):
                    try:
                        key_name = winreg.EnumKey(parent, index)
                        with winreg.OpenKey(parent, key_name) as child:
                            display, _ = winreg.QueryValueEx(child, "DisplayName")
                        if isinstance(display, str) and display.strip():
                            entries.append({"displayName": display, "key": key_name})
                    except OSError:
                        continue
    return entries


def windows_inventory(*, reader=None):
    """Read uninstall keys, with an injected reader for generated fixtures."""
    try:
        rows = (reader or _read_windows_registry)()
    except (ImportError, OSError) as exc:
        return [], [], ["registry: {0}".format(exc)]
    installed = []
    for row in rows:
        name = row.get("displayName")
        if not isinstance(name, str) or not name.strip():
            continue
        identity = _identity(name)
        key = row.get("key", "")
        if isinstance(key, str) and "." in key:
            identity["bundleId"] = key.casefold()
        installed.append(identity)
    return installed, ["uninstall-registry"], []


def scan(root, *, platform=None, env=None, cancel=None, which=shutil.which,
         runner=subprocess.run, registry_reader=None, root_override=None):
    env = os.environ if env is None else env
    platform = platform or platform_id()
    if platform not in ("linux", "windows"):
        return {"available": False, "reason": "Linux or Windows only", "items": [], "cancelled": False}
    if platform == "linux":
        installed, sources, errors = linux_inventory(env=env, which=which, runner=runner)
    else:
        installed, sources, errors = windows_inventory(reader=registry_reader)
    roots = _config(root, platform, env) if root_override is None else root_override
    items, unreadable = [], []
    for kind, directory in roots:
        if not os.path.isdir(directory) or os.path.islink(directory):
            continue
        try:
            with os.scandir(directory) as iterator:
                children = list(iterator)
        except OSError:
            unreadable.append(directory)
            continue
        for child in children:
            if cancel is not None and cancel.is_set():
                return {"available": True, "items": items, "inventorySources": sources,
                        "inventoryErrors": errors, "unreadable": unreadable, "cancelled": True}
            try:
                mode = child.stat(follow_symlinks=False).st_mode
            except OSError:
                unreadable.append(child.path)
                continue
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                continue
            status, confidence, rule = classify(child.name, "bundle", installed)
            if status == "orphan" and errors:
                status, confidence, rule = "unknown", 0.0, "inventory-incomplete"
            measure = fingerprint_path(child.path, cancel=cancel)
            if measure is None:
                return {"available": True, "items": items, "inventorySources": sources,
                        "inventoryErrors": errors, "unreadable": unreadable, "cancelled": True}
            if measure["kind"] not in ("dir", "file"):
                continue
            items.append({"id": "leftovers.{0}.{1}".format(platform, kind), "name": child.name,
                          "path": child.path, "status": status, "confidence": confidence,
                          "rule": rule, "sizeBytes": measure["bytes"],
                          "sizeOnDiskBytes": measure["onDiskBytes"], "reportOnly": True})
    return {"available": True, "items": items, "inventorySources": sources,
            "inventoryErrors": errors, "unreadable": unreadable, "cancelled": False}
