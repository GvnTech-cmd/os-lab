"""Read-only CLN-07 project sweep and Xcode simulator inventory."""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import time

from .catalog import expand
from . import artifacts
from .clean import fingerprint_path
from .paths import platform_id
from .safety import PathPolicyError, is_contained, validate_scan_root

MAX_DEPTH = 12
MAX_VISITED = 100000
SKIP = frozenset({".git", ".hg", ".svn", "Library", "AppData", "System", "Windows", "node_modules", "target"})


class DeepError(ValueError):
    """Invalid root or sweep request."""


def roots(root, *, platform=None, env=None):
    """Offer configured root ids, with resolved path and availability."""
    env = os.environ if env is None else env
    platform = platform or platform_id()
    with open(os.path.join(root, "cleanup-lab", "deep-roots.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    answer = []
    for root_id, template in data.items():
        path, reason = expand(template, platform, env)
        if path:
            try:
                path = validate_scan_root(path, home=env.get("HOME"))
            except PathPolicyError as exc:
                reason = str(exc)
        answer.append({"id": root_id, "path": path, "available": not reason, "reason": reason})
    return answer


def sweep(root, root_ids, *, min_idle_days=0, platform=None, env=None, cancel=None, clock=time.time):
    """Find proved build outputs; never follow links or descend into a match."""
    if not isinstance(root_ids, list) or not root_ids or any(not isinstance(x, str) for x in root_ids) or len(root_ids) != len(set(root_ids)):
        raise DeepError("rootIds must be a non-empty list of unique configured ids")
    if not isinstance(min_idle_days, int) or isinstance(min_idle_days, bool) or not 0 <= min_idle_days <= 3650:
        raise DeepError("minIdleDays must be an integer from 0 to 3650")
    configured = {item["id"]: item for item in roots(root, platform=platform, env=env)}
    signatures = artifacts.load(root)
    if any(item not in configured or not configured[item]["available"] for item in root_ids):
        raise DeepError("Every rootId must name an available configured project root")
    results, unreadable, visited = [], [], 0
    now = clock()
    for root_id in root_ids:
        stack = [(configured[root_id]["path"], 0)]
        while stack:
            if cancel is not None and cancel.is_set():
                return {"items": results, "unreadable": unreadable, "visited": visited, "cancelled": True}
            parent, depth = stack.pop()
            visited += 1
            if visited > MAX_VISITED:
                raise DeepError("Project sweep reached its directory limit; select a narrower root")
            try:
                with os.scandir(parent) as iterator:
                    children = list(iterator)
            except OSError:
                unreadable.append(parent)
                continue
            for child in children:
                try:
                    mode = child.stat(follow_symlinks=False).st_mode
                except OSError:
                    unreadable.append(child.path)
                    continue
                if not stat.S_ISDIR(mode):
                    continue
                match = artifacts.classify_dir(child.path, signatures)
                if match:
                    try:
                        project_mtime = artifacts.project_mtime(parent, match)
                    except OSError:
                        unreadable.append(parent)
                        continue
                    idle_days = max(0, int((now - project_mtime) // 86400))
                    if idle_days >= min_idle_days:
                        measure = fingerprint_path(child.path, cancel=cancel)
                        if measure and measure["kind"] == "dir":
                            results.append({"id": match.id, "rootId": root_id, "path": child.path,
                                            "project": parent, "ecosystem": match.ecosystem, "regenerate": match.regenerate,
                                            "idleDays": idle_days, "sizeBytes": measure["bytes"],
                                            "sizeOnDiskBytes": measure["onDiskBytes"],
                                            "files": measure["files"], "folders": measure["folders"]})
                    continue
                if depth < MAX_DEPTH and child.name not in SKIP and not child.name.startswith("."):
                    stack.append((child.path, depth + 1))
    return {"items": results, "unreadable": unreadable, "visited": visited, "cancelled": False}


def simulators(root, *, platform=None, env=None, run=subprocess.run):
    """List Xcode simulator devices with availability; no shell or guessed paths."""
    if (platform or platform_id()) != "macos":
        return {"available": False, "reason": "Xcode simulators require macOS", "devices": []}
    try:
        result = run(["xcrun", "simctl", "list", "-j", "devices"], shell=False,
                     capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc), "devices": []}
    if result.returncode != 0:
        return {"available": False, "reason": result.stderr.strip() or "simctl failed", "devices": []}
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": False, "reason": "simctl returned invalid JSON", "devices": []}
    env = os.environ if env is None else env
    with open(os.path.join(root, "cleanup-lab", "simulator-roots.json"), encoding="utf-8") as handle:
        template = json.load(handle)["macos"]
    device_root, _ = expand(template, "macos", env)
    devices = []
    for runtime, group in data.get("devices", {}).items():
        if not isinstance(group, list):
            continue
        for device in group:
            if not isinstance(device, dict):
                continue
            udid = device.get("udid")
            size = None
            if isinstance(udid, str) and re.fullmatch(r"[0-9A-Fa-f-]{36}", udid) and device_root:
                path = os.path.join(device_root, udid)
                if is_contained(path, device_root) and not os.path.islink(path):
                    measure = fingerprint_path(path)
                    if measure and measure["kind"] == "dir":
                        size = measure["bytes"]
            devices.append({"id": udid, "name": device.get("name"), "runtime": runtime,
                            "state": device.get("state"), "available": device.get("isAvailable", True),
                            "sizeBytes": size})
    return {"available": True, "reason": "", "devices": devices}
