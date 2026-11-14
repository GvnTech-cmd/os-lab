"""Path policy: canonical paths, protected roots and symlink-safe containment.

Every configurable or destructive path in Cleanup Lab goes through here first.

Differences from the private implementation this was ported from (both were
bugs there and must not come back):

* Containment is decided on **resolved** paths (``os.path.realpath``). The
  original compared standardized strings, so ``<allowed root>/link`` pointing at
  ``/etc`` counted as "inside" the allowed root.
* Containment compares **path components** (``os.path.commonpath``), never a
  bare string prefix, so ``/data/cache-old`` is not inside ``/data/cache``.
* A purge target may not be an allowed root itself unless the caller says so;
  the original only refused ``/`` and the home directory, which left every other
  folder in the home (Documents, Desktop …) purgeable.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


class PathPolicyError(ValueError):
    """A path was rejected. The message is safe to show to the user."""


def _home(home: str | os.PathLike[str] | None) -> str:
    return os.fspath(home) if home is not None else os.path.expanduser("~")


def canonical(raw: str | os.PathLike[str], *, home: str | os.PathLike[str] | None = None) -> str:
    """Trim, expand a leading ``~`` and normalise. Does not touch the disk.

    Relative paths are refused: the page and the catalog must always name a
    path absolutely (or relative to ``~``).
    """
    text = os.fspath(raw).strip()
    if not text:
        raise PathPolicyError("A filesystem path cannot be empty.")
    if "\x00" in text:
        raise PathPolicyError("A filesystem path cannot contain NUL bytes.")
    if text == "~" or text.startswith("~/") or text.startswith("~\\"):
        text = _home(home) + text[1:]
    if not os.path.isabs(text):
        raise PathPolicyError(f"Filesystem paths must be absolute: {raw}")
    return os.path.normpath(text)


def resolved(raw: str | os.PathLike[str], *, home: str | os.PathLike[str] | None = None) -> str:
    """:func:`canonical`, then resolve every symlink on the way."""
    return os.path.realpath(canonical(raw, home=home))


def protected_roots(*, home: str | os.PathLike[str] | None = None) -> set[str]:
    """Paths Cleanup Lab never operates on as a whole: the filesystem root(s) and the home."""
    roots = {os.path.realpath(os.path.abspath(os.sep)), os.path.realpath(_home(home))}
    if os.name == "nt":  # every drive root, e.g. C:\ and D:\
        roots.update(f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return roots


def is_contained(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> bool:
    """True when the resolved ``path`` equals or lies under the resolved ``root``."""
    p = os.path.realpath(os.fspath(path))
    r = os.path.realpath(os.fspath(root))
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:  # different drives on Windows, or mixed abs/rel
        return False


def validate_managed_path(raw: str | os.PathLike[str], *, home: str | os.PathLike[str] | None = None) -> str:
    """Resolved path that is not a protected root."""
    path = resolved(raw, home=home)
    if path in protected_roots(home=home):
        raise PathPolicyError(f"Refusing to operate on protected root {path}.")
    return path


def validate_scan_root(raw: str | os.PathLike[str], *, home: str | os.PathLike[str] | None = None) -> str:
    """A folder the user chose to explore read-only (CLN-23).

    Must exist, be a directory, be readable and listable, and must not be the
    whole disk or the home root ("choose a specific folder").
    """
    path = validate_managed_path(raw, home=home)
    if not os.path.lexists(path):
        raise PathPolicyError(f"That folder doesn't exist: {path}")
    if not os.path.isdir(path):
        raise PathPolicyError(f"Choose a folder, not a file: {path}")
    if not os.access(path, os.R_OK | os.X_OK):
        raise PathPolicyError(f"That folder isn't readable: {path}")
    return path


def validate_target(
    raw: str | os.PathLike[str],
    allowed_roots: Iterable[str | os.PathLike[str]],
    *,
    home: str | os.PathLike[str] | None = None,
    allow_root_itself: bool = False,
) -> str:
    """Resolved purge/relocation target that lies inside one of ``allowed_roots``.

    ``allowed_roots`` come from the catalog (per OS), never from the page.
    The target itself must exist; a vanished path is reported, not ignored.
    """
    path = validate_managed_path(raw, home=home)
    if not os.path.lexists(canonical(raw, home=home)):
        raise PathPolicyError(f"Path no longer exists: {path}")
    roots = [resolved(r, home=home) for r in allowed_roots]
    for root in roots:
        if is_contained(path, root) and (allow_root_itself or path != root):
            return path
    raise PathPolicyError(f"Path is outside every allowed root: {path}")


def validate_copy(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    destination_root: str | os.PathLike[str],
    *,
    home: str | os.PathLike[str] | None = None,
) -> tuple[str, str]:
    """Source/destination pair for a relocation (CLN-27).

    The destination must be inside its managed root, differ from the source,
    and neither path may contain the other (copying a folder into itself).
    """
    src = validate_managed_path(source, home=home)
    # The destination usually does not exist yet: resolve its parent, keep its name.
    dst_canonical = Path(canonical(destination, home=home))
    dst = os.path.join(os.path.realpath(dst_canonical.parent), dst_canonical.name)
    if dst in protected_roots(home=home):
        raise PathPolicyError(f"Refusing to operate on protected root {dst}.")
    root = validate_managed_path(destination_root, home=home)
    if src == dst:
        raise PathPolicyError(f"Source and destination must be different paths: {src}")
    if is_contained(dst, src) or is_contained(src, dst):
        raise PathPolicyError("Source and destination must not contain each other.")
    if not is_contained(dst, root):
        raise PathPolicyError(f"Destination is outside its managed root: {dst}")
    return src, dst
