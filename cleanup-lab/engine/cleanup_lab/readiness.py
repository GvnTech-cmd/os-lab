"""Read-only readiness probe for the Cleanup Lab.

`GET /api/cleanup/status` and `labctl cleanup status|doctor` print exactly what
this module returns. The probe only stats paths and looks up programs on `PATH`:
it never creates the state folder, never scans a user folder and never touches a
file it reports on, which is what rule 1 and rule 8 of the lab contract require
of anything that runs before a confirmed plan.
"""
from __future__ import annotations

import os
import shutil
import sys
import time

from . import __version__
from .paths import (
    home_dir,
    is_private_dir,
    is_writable_dir,
    platform_id,
    state_dir,
    trash_dir,
)

MIN_PYTHON = (3, 11)
PLATFORM_LABEL = {"macos": "macOS", "linux": "Linux", "windows": "Windows"}
CHECKED_TOOLS = (
    ("containers", "Container engine", ("docker", "podman")),
    ("package-managers", "Package managers", ("brew", "pip3", "gem")),
)


def repo_root():
    """The checkout that holds ``cleanup-lab/`` (four levels above this file)."""
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def _requirement(id_, label, found, hint, detail=""):
    return {
        "id": id_,
        "label": label,
        "found": bool(found),
        "required": True,
        "hint": hint,
        "detail": detail,
    }


def _capability(id_, label, found, detail):
    return {"id": id_, "label": label, "found": bool(found), "detail": detail}


def _python_version(version):
    if version is None:
        return tuple(sys.version_info[:3])
    return tuple(version)[:3]


def _detector_count(root):
    catalog = os.path.join(root, "cleanup-lab", "catalog")
    try:
        names = os.listdir(catalog)
    except OSError:
        return 0
    return sum(
        1
        for name in names
        if name.endswith(".json") and not name.startswith(("schema", "_"))
    )


def _first_on_path(env, names):
    path = env.get("PATH") if env is not None else None
    for name in names:
        found = shutil.which(name, path=path)
        if found:
            return name, found
    return None, None


def _simulator_tool(platform, env):
    """The tool that reports simulator runtimes, or ``None`` on this platform."""
    if platform == "macos":
        return _first_on_path(env, ("xcrun",))
    return _first_on_path(env, ("emulator", "avdmanager"))


def _trash_usable(platform, trash):
    """Whether items could actually be moved to this platform's Trash.

    A Trash folder that exists must be writable; one that does not exist yet is
    fine when its nearest existing ancestor is writable (a fresh Linux account
    has no ``~/.local/share/Trash`` until the first move). Windows uses the
    Recycle Bin through the shell, which has no path to check.
    """
    if trash is None:
        return platform == "windows"
    if os.path.isdir(trash):
        return os.access(trash, os.W_OK | os.X_OK)
    return is_writable_dir(trash)


def _privileged_capability(platform, env):
    """Whether this desktop's own elevation mechanism is present (CLN-20)."""
    if platform == "windows":
        return _capability(
            "privileged-actions", "Privileged actions", True,
            "Runs through the UAC prompt",
        )
    names = ("pkexec", "sudo") if platform == "linux" else ("osascript",)
    name, where = _first_on_path(env, names)
    return _capability(
        "privileged-actions", "Privileged actions", bool(name),
        "{0} at {1}".format(name, where) if name
        else "No {0} on PATH".format(" or ".join(names)),
    )


def _tool_capabilities(platform, env):
    items = []
    for id_, label, names in CHECKED_TOOLS:
        name, where = _first_on_path(env, names)
        items.append(
            _capability(
                id_,
                label,
                bool(name),
                "{0} at {1}".format(name, where) if name else "No {0} on PATH".format(" or ".join(names)),
            )
        )
    name, where = _simulator_tool(platform, env)
    items.append(
        _capability(
            "simulators",
            "Simulator tools",
            bool(name),
            "{0} at {1}".format(name, where) if name else "No simulator tool on PATH",
        )
    )
    items.append(_privileged_capability(platform, env))
    return items


def probe(root=None, env=None, sys_platform=None, version=None):
    """Report readiness without writing anything.

    ``env`` (a mapping), ``sys_platform`` and ``version`` exist so tests can run
    against a generated home tree and a fake `PATH` instead of this computer.
    """
    env = os.environ if env is None else env
    root = repo_root() if root is None else root
    platform = platform_id(sys_platform)
    supported = platform in PLATFORM_LABEL
    home = home_dir(env)
    state = state_dir(env, platform)
    trash = trash_dir(env, platform)
    python = _python_version(version)

    home_readable = os.path.isdir(home) and os.access(home, os.R_OK | os.X_OK)
    trash_ready = _trash_usable(platform, trash)
    trash_detail = trash or "Recycle Bin"
    state_ready = is_writable_dir(state) and is_private_dir(state)

    requirements = [
        _requirement(
            "platform",
            "Supported operating system",
            supported,
            "Cleanup Lab runs on macOS, Linux and Windows.",
            PLATFORM_LABEL.get(platform, platform),
        ),
        _requirement(
            "python",
            "Python 3.11 or newer",
            python[:2] >= MIN_PYTHON,
            "Use Python 3.11 or newer. In the desktop launcher, choose Get Python to install a managed copy.",
            ".".join(str(part) for part in python),
        ),
        _requirement(
            "home",
            "Home folder readable",
            home_readable,
            "The scan targets live under this folder; make it readable by your user.",
            home,
        ),
        _requirement(
            "trash",
            "Trash available",
            trash_ready,
            "Cleaning moves items to the Trash; a platform without one cannot clean.",
            trash_detail,
        ),
        _requirement(
            "state",
            "Private state folder writable",
            state_ready,
            "The audit history and the learned profile live here. Keep it writable by your user only, or set OSLAB_CLEANUP_STATE to such a folder.",
            state,
        ),
    ]
    reasons = [item["hint"] for item in requirements if item["required"] and not item["found"]]

    detectors = _detector_count(root)
    reference = os.path.isfile(
        os.path.join(root, "cleanup-lab", "reference", "qrust-scan", "Cargo.toml")
    )
    capabilities = [
        _capability(
            "detectors",
            "Detector catalog",
            detectors > 0,
            "{0} detector(s) in the catalog".format(detectors)
            if detectors
            else "No detector catalog yet",
        ),
        _capability(
            "native-scan",
            "Native scan backend",
            False,
            "Reference crate present; not wired into the app yet"
            if reference
            else "Not built",
        ),
    ] + _tool_capabilities(platform, env)

    if not supported:
        state_name = "unavailable"
    elif any(item["required"] and not item["found"] for item in requirements):
        state_name = "needs-setup"
    else:
        state_name = "ready"

    return {
        "engine": {
            "name": "cleanup-lab",
            "version": __version__,
            "python": ".".join(str(part) for part in python),
            "mode": "stdlib",
        },
        "state": state_name,
        "platform": {
            "id": platform,
            "label": PLATFORM_LABEL.get(platform, platform),
            "supported": supported,
        },
        "home": home,
        "stateDir": state,
        "requirements": requirements,
        "capabilities": capabilities,
        "reasons": reasons,
        "checkedAt": time.time(),
    }


__all__ = ["MIN_PYTHON", "probe", "repo_root"]
