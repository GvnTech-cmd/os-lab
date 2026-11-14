"""CLNP-01: typed permission probes and the reactive unreadable-path classification.

macOS gates parts of the user's own folders behind TCC privacy grants. The
engine cannot and must not grant anything — it can only prove what it can read
and say which grant would fix what it cannot. This module owns that surface:

* **Proactive probes stay non-intrusive.** Only the two classic Full Disk
  Access folders (``~/Library/Safari``, ``~/Library/Mail``) are listed up
  front: a denial there answers silently, while probing the Desktop /
  Documents / Downloads folders would raise the macOS consent dialog on the
  user's screen. Those three are decided *reactively* — a scan-time
  ``PermissionError`` on a root inside them is the evidence.
* **Read-only probes only.** ``os.listdir`` on fixed paths; no shell, no
  subprocess, no writes, nothing a page can steer.
* **Classification never guesses.** A path is classified only when this
  process can still prove it unreadable *right now* (a fresh ``os.lstat`` /
  ``os.listdir``), and only to a permission whose scope demonstrably contains
  it. Everything else stays unclassified with its own reason.

Every permission record: ``{id, name, applicable, granted, probePaths,
results[{path, readable, reason}], guidance, grantUrl}``. ``granted`` is
``True``/``False`` only when proven; ``None`` means "no evidence yet".
``grantUrl`` is a settings deep link the *dashboard* renders as a plain link;
the engine never opens System Settings itself.
"""
from __future__ import annotations

import os

from . import paths

#: macOS settings deep link for Full Disk Access (client-side render only).
FDA_GRANT_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
FDA_GUIDANCE = (
    "Grant the app running the console Full Disk Access under "
    "System Settings → Privacy & Security → Full Disk Access, then re-check."
)
FOLDER_GUIDANCE = (
    "Grant the app access under System Settings → Privacy & Security → "
    "Files and Folders (or the {0} pane), then re-check."
)
HIDDEN_GUIDANCE = {
    "macos": (
        "Some hidden folders are TCC-protected; Full Disk Access covers them. "
        "Others only need to be owned by your user."
    ),
    "windows": (
        "Hidden folders under your profile are normally readable; an access "
        "error here usually means another account owns the folder."
    ),
    "linux": (
        "A hidden folder you cannot read is usually owned by another user; "
        "check its owner and group permissions."
    ),
}
HIDDEN_GRANT_URL = FDA_GRANT_URL  # only rendered on macOS, where FDA applies

#: The proactive FDA probe: these fail *silently* under TCC (no consent dialog).
FDA_PROBES = ("Library", "Safari"), ("Library", "Mail")
#: TCC-protected Library folders whose denial is evidence about Full Disk Access.
FDA_COVERED_LIBRARY = ("Safari", "Mail", "Messages", "Cookies", "Metadata")
#: Reactive-only macOS folder grants: probing them proactively would prompt.
FOLDER_GRANTS = {
    "macos-desktop-folder": ("Desktop",),
    "macos-documents-folder": ("Documents",),
    "macos-downloads-folder": ("Downloads",),
}
#: Registry order and display names.
NAMES = {
    "macos-full-disk-access": "Full Disk Access",
    "macos-desktop-folder": "Desktop folder access",
    "macos-documents-folder": "Documents folder access",
    "macos-downloads-folder": "Downloads folder access",
    "hidden-roots": "Hidden folders",
}


def _hidden(path, platform=None):
    """Whether a path is hidden: a dot component, or macOS ``~/Library``."""
    parts = os.path.normpath(path).split(os.sep)
    if any(part.startswith(".") for part in parts[1:]):
        return True
    if (platform or paths.platform_id()) == "macos":
        return "Library" in parts
    return False


def _listdir_check(path, prober):
    """One read-only readability probe: ``(readable, reason)``."""
    try:
        (prober or os.listdir)(path)
    except PermissionError as exc:
        return False, exc.strerror or "Permission denied"
    except FileNotFoundError:
        return None, "not present"
    except OSError as exc:
        return None, str(exc)
    return True, ""


def fda(platform=None, env=None, *, prober=None):
    """The read-only macOS Full Disk Access probe (the CLN-20 payload, moved here).

    ``privilege.disk_access`` delegates to this so its payload shape stays
    byte-compatible for existing consumers.
    """
    platform = platform or paths.platform_id()
    if platform != "macos":
        return {
            "applicable": False, "granted": None, "paths": [], "guidance": "",
            "reason": "Full Disk Access is a macOS privacy setting.",
        }
    home = paths.home_dir(env)
    results = []
    granted = None
    for parts in FDA_PROBES:
        path = os.path.join(home, *parts)
        readable, reason = _listdir_check(path, prober)
        results.append({"path": path, "readable": readable, "reason": reason})
        if readable is False:
            granted = False
        elif readable is True and granted is None:
            granted = True
    return {
        "applicable": True,
        "granted": granted,
        "paths": results,
        "guidance": FDA_GUIDANCE if granted is False else "",
    }


def probe(platform=None, env=None, *, prober=None):
    """The typed permission list: one record per registry id, in registry order."""
    platform = platform or paths.platform_id()
    macos = platform == "macos"
    home = paths.home_dir(env)
    records = []

    # Proactive: Full Disk Access only — every other macOS grant is reactive,
    # because probing the user-folder grants would raise the consent dialog.
    fda_record = fda(platform, env, prober=prober)
    records.append({
        "id": "macos-full-disk-access",
        "name": NAMES["macos-full-disk-access"],
        "applicable": macos,
        "granted": fda_record["granted"] if macos else None,
        "probePaths": [item["path"] for item in fda_record["paths"]],
        "results": fda_record["paths"],
        "guidance": fda_record["guidance"],
        "grantUrl": FDA_GRANT_URL if macos and fda_record["granted"] is False else None,
    })

    # Reactive-only records: no proactive probe, no evidence until a scan
    # classifies one of their roots as unreadable.
    for id_, (folder,) in FOLDER_GRANTS.items():
        records.append({
            "id": id_,
            "name": NAMES[id_],
            "applicable": macos,
            "granted": None,
            "probePaths": [os.path.join(home, folder)],
            "results": [],
            "guidance": FOLDER_GUIDANCE.format(folder) if macos else "",
            "grantUrl": None,
        })

    records.append({
        "id": "hidden-roots",
        "name": NAMES["hidden-roots"],
        "applicable": platform in paths.SUPPORTED_PLATFORMS,
        "granted": None,
        "probePaths": [],
        "results": [],
        "guidance": HIDDEN_GUIDANCE.get(platform, "") if platform in paths.SUPPORTED_PLATFORMS else "",
        "grantUrl": HIDDEN_GRANT_URL if macos else None,
    })
    return {"platform": platform, "permissions": records}


def classify_unreadable(candidate_paths, *, platform=None, env=None, prober=None):
    """Re-probe unreadable scan paths and classify the still-unreadable ones.

    ``candidate_paths`` are plain path strings from a scan's ``unreadable``
    lists. A path is classified only when a fresh probe still fails with
    ``PermissionError`` — a recovered or vanished path is reported as such and
    makes no claim. The permission id is chosen by scope:

    * macOS, inside a TCC-protected Library folder → ``macos-full-disk-access``
    * macOS, inside Desktop/Documents/Downloads → that folder's permission
    * any platform, any dot component (or macOS ``~/Library``) → ``hidden-roots``
    * everything else → unmatched (a plain unreadable path is not a permission claim)
    """
    platform = platform or paths.platform_id()
    home = paths.home_dir(env)
    macos = platform == "macos"
    classified = []
    unmatched = []
    for path in candidate_paths:
        if not isinstance(path, str) or not path:
            continue
        readable, reason = _listdir_check(path, prober)
        if readable is not False:
            unmatched.append({"path": path, "permissionId": None, "state": "recovered" if readable else "unknown", "reason": reason})
            continue
        relative = os.path.relpath(os.path.abspath(path), home).split(os.sep)
        first = relative[0] if relative else ""
        permission = None
        if macos and len(relative) >= 2 and first == "Library" and relative[1] in FDA_COVERED_LIBRARY:
            permission = "macos-full-disk-access"
        elif macos:
            for id_, (folder,) in FOLDER_GRANTS.items():
                if first == folder:
                    permission = id_
                    break
        if permission is None and _hidden(path, platform):
            permission = "hidden-roots"
        if permission is None:
            unmatched.append({"path": path, "permissionId": None, "state": "permission-denied", "reason": reason})
        else:
            classified.append({"path": path, "permissionId": permission, "state": "permission-denied", "reason": reason})
    return {"platform": platform, "classified": classified, "unmatched": unmatched}


def report(candidate_paths=(), *, platform=None, env=None, prober=None):
    """The full ``GET /api/cleanup/permissions`` payload: probes + classification.

    ``candidate_paths`` are the unreadable paths of the latest scan (when the
    console process has one). Each classified path is folded into its
    permission record so one payload carries everything the card renders.
    """
    platform = platform or paths.platform_id()
    payload = probe(platform, env, prober=prober)
    if candidate_paths:
        classification = classify_unreadable(
            candidate_paths, platform=platform, env=env, prober=prober
        )
        payload["classification"] = classification
        by_id = {record["id"]: record for record in payload["permissions"]}
        for item in classification["classified"]:
            record = by_id.get(item["permissionId"])
            if record is None:
                continue
            record["results"].append({"path": item["path"], "readable": False, "reason": item["reason"]})
            if record["granted"] is None and record["applicable"]:
                record["granted"] = False
                if record["id"] == "macos-full-disk-access" or record["id"] in FOLDER_GRANTS:
                    record["grantUrl"] = FDA_GRANT_URL
                elif record["id"] == "hidden-roots" and platform == "macos":
                    record["grantUrl"] = HIDDEN_GRANT_URL
                if record["id"] in FOLDER_GRANTS:
                    folder = FOLDER_GRANTS[record["id"]][0]
                    record["guidance"] = FOLDER_GUIDANCE.format(folder)
    return payload


__all__ = [
    "FDA_GRANT_URL", "classify_unreadable", "fda", "probe", "report",
]
