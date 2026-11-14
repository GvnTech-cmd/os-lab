"""CLNP-23: the Space Explorer — a read-only size tree over registered roots.

The dua-like view needs one thing the catalog scan does not provide: a
**parent-summed size tree** of a folder. This module walks it with exactly
the scan job's honesty rules:

* read-only ``lstat``: a symlink is never followed or recursed into, a hard
  link is counted once per ``(device, inode)`` pair, apparent size only;
* one filesystem: the walk never descends across a mount boundary
  (``st_dev`` of the root);
* budgets: a node cap and a depth cap bound the walk; hitting one marks the
  result ``truncated`` instead of lying about completeness;
* **registered roots only.** A walk names a root id from ``deep-roots.json``
  or the CLNP-20 custom overlay — never a path from the page. A drill-down
  walks a relative subpath that must stay inside that same root
  (:func:`safety.is_contained`), so no request can steer the walker anywhere
  the registry does not allow.

The explorer never deletes anything: it measures, and its UI links cleaning
back to the plan → confirm → run flow.
"""
from __future__ import annotations

import json
import os
import time

from . import safety
from .paths import platform_id

#: Walk budgets: a tree bigger than this is reported truncated, not walked forever.
MAX_NODES = 20000
MAX_DEPTH = 14


class ExplorerError(ValueError):
    """An unknown root id, an out-of-scope subpath, or an unavailable root."""


def _load_deep_roots(root):
    with open(os.path.join(root, "cleanup-lab", "deep-roots.json"), encoding="utf-8") as handle:
        return json.load(handle)


def roots(root, *, platform=None, env=None):
    """Selectable roots: the deep-scan registry plus the custom overlay entries."""
    env = os.environ if env is None else env
    platform = platform or platform_id()
    answer = []
    for root_id, template in _load_deep_roots(root).items():
        path, reason = _resolve_template(template, platform, env)
        answer.append({"id": root_id, "name": root_id.replace("-", " ").capitalize(),
                       "source": "deep-roots", "path": path, "available": not reason,
                       "reason": reason or ""})
    try:
        from . import custom_catalog

        overlay = custom_catalog.load(env=env)
        for entry in overlay["entries"]:
            template = entry["paths"].get(platform, [None])[0]
            path, reason = _resolve_template(template, platform, env) if template else (None, "no path on this platform")
            answer.append({"id": entry["id"], "name": entry["name"], "source": "custom",
                           "path": path, "available": not reason, "reason": reason or ""})
    except Exception:
        pass  # an unreadable overlay removes its entries, never breaks the registry
    return answer


def _resolve_template(template, platform, env):
    from .catalog import expand

    try:
        path, reason = expand(template, platform, env)
    except Exception as exc:
        return None, str(exc)
    if not path:
        return None, reason or "the path is not configured on this platform"
    try:
        path = safety.validate_scan_root(path)
    except safety.PathPolicyError as exc:
        return None, str(exc)
    return path, ""


def resolve_root(root, root_id, *, platform=None, env=None):
    """The absolute path for a registered root id; refuses anything else."""
    if not isinstance(root_id, str) or not root_id:
        raise ExplorerError("rootId must name a registered root")
    for item in roots(root, platform=platform, env=env):
        if item["id"] == root_id:
            if not item["available"] or not item["path"]:
                raise ExplorerError("This root is not available: {0}".format(item["reason"]))
            return item["path"]
    raise ExplorerError("Unknown root id: {0}".format(root_id))


def _subtree_path(root_path, relative):
    """The drill-down target: a relative path that must stay inside the root."""
    if not isinstance(relative, str) or not relative:
        raise ExplorerError("relative must be a non-empty path relative to the root")
    if relative.startswith("/") or os.path.isabs(relative) \
            or ".." in relative.split(os.sep) or ".." in relative.split("/"):
        raise ExplorerError("relative must stay inside the root")
    candidate = os.path.join(root_path, relative)
    if not safety.is_contained(candidate, root_path):
        raise ExplorerError("relative must stay inside the root")
    return candidate


def walk(root_path, *, cancel=None, progress_callback=None, max_nodes=MAX_NODES,
         max_depth=MAX_DEPTH, seen_inodes=None, root_device=None, depth=0):
    """One read-only size tree. Returns the node plus walk counters.

    Apparent sizes from ``lstat``; symlinks never followed; hard links counted
    once; descent stops at a mount boundary or the budgets. ``truncated`` is
    honest: the tree may be incomplete when True.
    """
    node = {
        "name": os.path.basename(root_path) or root_path,
        "path": root_path,
        "sizeBytes": 0,
        "files": 0,
        "folders": 0,
        "children": [],
        "truncated": False,
        "unreadable": 0,
    }
    counters = {"nodes": 1, "truncated": False, "cancelled": False}
    try:
        stat_result = os.lstat(root_path)
    except OSError:
        node["unreadable"] = 1
        return node, counters
    if seen_inodes is None:
        seen_inodes = set()
        root_device = stat_result.st_dev
    if os.path.islink(root_path):
        return node, counters
    if depth >= max_depth or counters["nodes"] >= max_nodes:
        node["truncated"] = True
        counters["truncated"] = True
        return node, counters
    try:
        entries = list(os.scandir(root_path))
    except OSError:
        node["unreadable"] = 1
        return node, counters

    child_nodes = []
    for entry in entries:
        if cancel is not None and cancel.is_set():
            counters["cancelled"] = True
            break
        try:
            if entry.is_symlink():
                continue
            entry_stat = entry.stat(follow_symlinks=False)
        except OSError:
            node["unreadable"] += 1
            continue
        if entry_stat.st_dev != root_device:
            continue  # one filesystem: never descend across a mount
        is_dir = entry_stat.st_mode & 0o170000 == 0o040000
        if is_dir:
            if counters["nodes"] >= max_nodes:
                node["truncated"] = True
                counters["truncated"] = True
                break
            counters["nodes"] += 1
            child, child_counters = walk(
                entry.path, cancel=cancel, progress_callback=progress_callback,
                max_nodes=max_nodes, max_depth=max_depth, seen_inodes=seen_inodes,
                root_device=root_device, depth=depth + 1,
            )
            child_nodes.append(child)
            counters["nodes"] += child_counters["nodes"] - 1
            counters["truncated"] = counters["truncated"] or child_counters["truncated"]
            counters["cancelled"] = counters["cancelled"] or child_counters["cancelled"]
        elif entry_stat.st_mode & 0o170000 == 0o100000:  # regular file
            key = (entry_stat.st_dev, entry_stat.st_ino)
            if key not in seen_inodes:
                seen_inodes.add(key)
                node["sizeBytes"] += entry_stat.st_size
                node["files"] += 1
        if progress_callback is not None and counters["nodes"] % 500 == 0:
            progress_callback({"currentPath": entry.path, "nodes": counters["nodes"]})

    node["children"] = sorted(child_nodes, key=lambda item: (item["sizeBytes"], item["name"]), reverse=True)
    for child in child_nodes:
        node["sizeBytes"] += child["sizeBytes"]
        node["files"] += child["files"]
        node["folders"] += child["folders"]
        node["unreadable"] += child["unreadable"]
        if child["truncated"]:
            node["truncated"] = True
    node["folders"] += len(child_nodes)
    return node, counters


def explore(root, root_id, *, platform=None, env=None, cancel=None, progress_callback=None,
            max_nodes=MAX_NODES, max_depth=MAX_DEPTH, relative=None, clock=time.time):
    """The typed payload behind ``POST /api/cleanup/explorer/scan`` (and subtree)."""
    platform = platform or platform_id()
    env = os.environ if env is None else env
    root_path = resolve_root(root, root_id, platform=platform, env=env)
    if relative is not None:
        root_path = _subtree_path(root_path, relative)
    node, counters = walk(root_path, cancel=cancel, progress_callback=progress_callback,
                          max_nodes=max_nodes, max_depth=max_depth)
    return {
        "rootId": root_id,
        "path": root_path,
        "relative": relative,
        "tree": node,
        "nodes": counters["nodes"],
        "truncated": counters["truncated"],
        "cancelled": counters["cancelled"],
        "checkedAt": clock(),
    }


__all__ = ["ExplorerError", "explore", "resolve_root", "roots", "walk"]
