"""CLN-08 read-only VM bundle inventory; never offers deletion."""
from __future__ import annotations

import json
import os
import stat

from .catalog import expand
from .clean import fingerprint_path
from .paths import platform_id


class VMError(ValueError):
    """The VM detector catalog is invalid."""


def inventory(root, *, platform=None, env=None, cancel=None):
    env = os.environ if env is None else env
    platform = platform or platform_id()
    with open(os.path.join(root, "cleanup-lab", "catalog", "actions", "vms.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != 1 or data.get("family") != "vms" or not isinstance(data.get("entries"), list):
        raise VMError("Invalid VM catalog")
    items, seen, unavailable = [], set(), []
    for entry in data["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].startswith("vms."):
            raise VMError("Invalid VM entry")
        extensions = entry.get("extensions")
        if not isinstance(extensions, list) or not extensions or any(not isinstance(x, str) or not x.startswith(".") or "/" in x for x in extensions):
            raise VMError("Invalid VM extension list")
        for template in entry.get("roots", {}).get(platform, []):
            path, reason = expand(template, platform, env)
            if not path or not os.path.isdir(path) or os.path.islink(path):
                unavailable.append({"id": entry["id"], "root": path, "reason": reason or "Root unavailable"})
                continue
            try:
                with os.scandir(path) as iterator:
                    children = list(iterator)
            except OSError as exc:
                unavailable.append({"id": entry["id"], "root": path, "reason": str(exc)})
                continue
            for child in children:
                if cancel is not None and cancel.is_set():
                    return {"items": items, "unavailable": unavailable, "cancelled": True}
                try:
                    mode = child.stat(follow_symlinks=False).st_mode
                except OSError:
                    continue
                if stat.S_ISLNK(mode):
                    continue
                direct = any(child.name.lower().endswith(ext.lower()) for ext in extensions)
                nested = False
                if stat.S_ISDIR(mode) and not direct:
                    try:
                        with os.scandir(child.path) as inner:
                            nested = any(item.is_file(follow_symlinks=False) and
                                         any(item.name.lower().endswith(ext.lower()) for ext in extensions)
                                         for item in inner)
                    except OSError:
                        continue
                if not direct and not nested:
                    continue
                target = child.path
                if target in seen:
                    continue
                seen.add(target)
                measure = fingerprint_path(target, cancel=cancel)
                if measure is None:
                    return {"items": items, "unavailable": unavailable, "cancelled": True}
                if measure["kind"] not in ("dir", "file"):
                    continue
                items.append({"id": entry["id"], "name": child.name, "path": target,
                              "sizeBytes": measure["bytes"], "sizeOnDiskBytes": measure["onDiskBytes"],
                              "files": measure["files"], "reportOnly": True})
    return {"items": items, "unavailable": unavailable, "cancelled": False}
