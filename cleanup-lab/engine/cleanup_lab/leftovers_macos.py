"""Read-only macOS app leftover signatures (CLN-09).

Identity rules are component-aware: bundle ids match exactly or as a dotted child,
team ids match one whole 10-character prefix, and inferred names match after
case/space/punctuation normalization. No substring match can turn `Acme Pro`
into `Acme` or `com.acme.app2` into `com.acme.app`.
"""
from __future__ import annotations

import json
import os
import plistlib
import re
import stat

from .catalog import expand
from .clean import fingerprint_path
from .paths import platform_id

BUNDLE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+$")
TEAM = re.compile(r"^([A-Z0-9]{10})\.")


class LeftoverError(ValueError):
    """Invalid leftover signature catalog."""


def _config(root):
    with open(os.path.join(root, "cleanup-lab", "catalog", "signatures", "macos-leftovers.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    if (data.get("version") != 1 or data.get("family") != "leftovers.macos" or
        not isinstance(data.get("appRoots"), list) or
        not isinstance(data.get("candidateRoots"), list) or
        not isinstance(data.get("largeAppDataBytes"), int) or
        data["largeAppDataBytes"] < 1):
        raise LeftoverError("Invalid macOS leftover catalog")
    for item in data["candidateRoots"]:
        if (item.get("kind") not in ("container", "group-container", "preference", "app-support", "launch-agent", "cache", "library") or
            item.get("match") not in ("bundle", "team", "name") or
            not isinstance(item.get("path"), str)):
            raise LeftoverError("Invalid macOS leftover signature")
    return data


def _normal_name(value):
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _regular(path):
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def _app_info(bundle):
    info = os.path.join(bundle, "Contents", "Info.plist")
    if not _regular(info):
        return None
    try:
        with open(info, "rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ValueError, TypeError):
        return None
    bundle_id = data.get("CFBundleIdentifier")
    if not isinstance(bundle_id, str) or not BUNDLE.fullmatch(bundle_id):
        return None
    names = {bundle.rsplit("/", 1)[-1][:-4]}
    for key in ("CFBundleName", "CFBundleDisplayName"):
        if isinstance(data.get(key), str):
            names.add(data[key])
    team = data.get("TeamIdentifier") or data.get("CFBundleTeamIdentifier")
    return {"bundleId": bundle_id.casefold(), "names": {_normal_name(x) for x in names},
            "teamId": team if isinstance(team, str) and re.fullmatch(r"[A-Z0-9]{10}", team) else None}


def _apps(root_paths, cancel, unreadable):
    installed, hidden = [], []
    for root in root_paths:
        if not root or not os.path.isdir(root):
            continue
        stack = [(root, 0)]
        while stack:
            if cancel is not None and cancel.is_set():
                return installed, hidden, True
            current, depth = stack.pop()
            try:
                with os.scandir(current) as iterator:
                    children = list(iterator)
            except OSError:
                unreadable.append(current)
                continue
            for child in children:
                try:
                    if not child.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    unreadable.append(child.path)
                    continue
                if child.name.lower().endswith(".app"):
                    info = _app_info(child.path)
                    if info:
                        installed.append(info)
                    if child.name.startswith("."):
                        hidden.append((child.path, info))
                elif depth < 1 and not child.name.startswith("."):
                    stack.append((child.path, depth + 1))
    return installed, hidden, False


def classify(name, mode, installed):
    """Return `(status, confidence, rule)` for a candidate stem."""
    if not installed:
        return "unknown", 0.0, "installed-inventory-empty"
    key = name.casefold()
    if mode == "team":
        match = TEAM.match(name)
        if match:
            present = any(app["teamId"] == match.group(1) for app in installed)
            return ("installed" if present else "orphan", 0.75, "team-prefix")
        return "unknown", 0.25, "no-team-prefix"
    if mode == "bundle" and BUNDLE.fullmatch(name):
        present = any(key == app["bundleId"] or key.startswith(app["bundleId"] + ".") for app in installed)
        return ("installed" if present else "orphan", 0.95, "bundle-id")
    normalized = _normal_name(name)
    if normalized:
        present = any(normalized in app["names"] for app in installed)
        return ("installed" if present else "orphan", 0.55, "inferred-name")
    return "unknown", 0.0, "no-identity"


def scan(root, *, env=None, platform=None, cancel=None):
    """Inventory potential orphans, hidden apps and large app data; never delete."""
    env = os.environ if env is None else env
    if (platform or platform_id()) != "macos":
        return {"available": False, "reason": "macOS only", "items": [], "cancelled": False}
    config = _config(root)
    unreadable = []
    app_roots = [expand(template, "macos", env)[0] for template in config["appRoots"]]
    installed, hidden, cancelled = _apps(app_roots, cancel, unreadable)
    if cancelled:
        return {"available": True, "items": [], "unreadable": unreadable, "cancelled": True}
    items = []
    for path, info in hidden:
        items.append({"id": "leftovers.macos.hidden-app", "path": path,
                      "name": os.path.basename(path), "status": "hidden", "confidence": 1.0,
                      "rule": "hidden-app-bundle", "bundleId": info["bundleId"] if info else None,
                      "reportOnly": True})
    for signature in config["candidateRoots"]:
        directory, _ = expand(signature["path"], "macos", env)
        if not directory or not os.path.isdir(directory) or os.path.islink(directory):
            continue
        try:
            with os.scandir(directory) as iterator:
                children = list(iterator)
        except OSError:
            unreadable.append(directory)
            continue
        for child in children:
            if cancel is not None and cancel.is_set():
                return {"available": True, "installedCount": len(installed), "items": items,
                        "unreadable": unreadable, "cancelled": True}
            try:
                mode = child.stat(follow_symlinks=False).st_mode
            except OSError:
                unreadable.append(child.path)
                continue
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                continue
            suffix = signature.get("suffix", "")
            if suffix and not child.name.endswith(suffix):
                continue
            stem = child.name[:-len(suffix)] if suffix else child.name
            status, confidence, rule = classify(stem, signature["match"], installed)
            measure = fingerprint_path(child.path, cancel=cancel)
            if measure is None:
                return {"available": True, "installedCount": len(installed), "items": items,
                        "unreadable": unreadable, "cancelled": True}
            if measure["kind"] not in ("dir", "file"):
                continue
            base = {"id": "leftovers.macos." + signature["kind"], "path": child.path,
                    "name": child.name, "status": status, "confidence": confidence, "rule": rule,
                    "sizeBytes": measure["bytes"], "sizeOnDiskBytes": measure["onDiskBytes"],
                    "reportOnly": True}
            if signature["kind"] == "app-support" and measure["bytes"] >= config["largeAppDataBytes"]:
                base = dict(base, id="leftovers.macos.large-app-data", status="large-data",
                            orphanStatus=status, confidence=1.0, rule="measured-size")
            items.append(base)
    return {"available": True, "installedCount": len(installed), "items": items,
            "unreadable": unreadable, "cancelled": False}
