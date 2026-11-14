"""CLN-24 marker-verified project artifact signatures stored as catalog data."""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass

CACHEDIR_SIGNATURE = b"Signature: 8a477f597d28d172789f06886806bc55"


class SignatureError(ValueError):
    """The project signature catalog is invalid."""


@dataclass(frozen=True)
class Signature:
    id: str
    names: tuple[str, ...]
    ecosystem: str
    regenerate: str
    sibling_markers: tuple[str, ...]
    inner_markers: tuple[str, ...]
    cachedir_tag: bool = False


def _names(value):
    return isinstance(value, list) and all(
        isinstance(x, str) and x and x not in (".", "..") and "/" not in x and "\\" not in x
        for x in value
    ) and len(value) == len(set(value))


def load(root):
    """Validate the separate project-signature catalog, preserving priority order."""
    filename = os.path.join(root, "cleanup-lab", "catalog", "signatures", "projects.json")
    with open(filename, encoding="utf-8") as handle:
        data = json.load(handle)
    if set(data) != {"version", "family", "entries"} or data["version"] != 1 or data["family"] != "projects" or not isinstance(data["entries"], list):
        raise SignatureError("Invalid project signature catalog header")
    signatures = []
    ids = set()
    for raw in data["entries"]:
        if not isinstance(raw, dict) or set(raw) - {"id", "names", "ecosystem", "regenerate", "siblingMarkers", "innerMarkers", "cachedirTag"}:
            raise SignatureError("Invalid project signature entry")
        sid = raw.get("id")
        names = raw.get("names")
        sibling = raw.get("siblingMarkers", [])
        inner = raw.get("innerMarkers", [])
        tag = raw.get("cachedirTag", False)
        if (not isinstance(sid, str) or not sid.startswith("projects.") or sid in ids or
            not _names(names) or not _names(sibling) or not _names(inner) or
            not isinstance(tag, bool) or (not names and not tag) or
            (names and not sibling and not inner) or
            any(not isinstance(raw.get(k), str) or not raw[k] for k in ("ecosystem", "regenerate"))):
            raise SignatureError("Invalid project signature: {0}".format(sid))
        ids.add(sid)
        signatures.append(Signature(sid, tuple(names), raw["ecosystem"], raw["regenerate"],
                                    tuple(sibling), tuple(inner), tag))
    return tuple(signatures)


def _regular(path):
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def has_cachedir_tag(directory):
    tag = os.path.join(directory, "CACHEDIR.TAG")
    if not _regular(tag):
        return False
    try:
        with open(tag, "rb") as handle:
            return handle.read(len(CACHEDIR_SIGNATURE)) == CACHEDIR_SIGNATURE
    except OSError:
        return False


def classify_dir(directory, signatures):
    """Return a proved signature, refusing symlink directories and marker links."""
    try:
        if not stat.S_ISDIR(os.lstat(directory).st_mode):
            return None
    except OSError:
        return None
    name = os.path.basename(os.path.normpath(directory))
    parent = os.path.dirname(os.path.normpath(directory))
    for sig in signatures:
        if name in sig.names and (
            any(_regular(os.path.join(parent, m)) for m in sig.sibling_markers) or
            any(_regular(os.path.join(directory, m)) for m in sig.inner_markers)
        ):
            return sig
        if sig.cachedir_tag and has_cachedir_tag(directory):
            return sig
    return None


def project_mtime(project_dir, signature):
    """Newest project marker time, falling back to the project directory time."""
    times = []
    for marker in signature.sibling_markers:
        path = os.path.join(project_dir, marker)
        if _regular(path):
            times.append(os.lstat(path).st_mtime)
    if times:
        return max(times)
    return os.lstat(project_dir).st_mtime
