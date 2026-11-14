"""Relocating a cache to another volume behind a symlink (CLN-27).

Two pure pieces:

* :func:`classify` reads (``lstat`` / ``readlink`` only) the state of a
  home path and its store counterpart;
* :func:`plan_move` / :func:`plan_restore` return the ordered, typed steps a
  console job runs after the user confirms. This module never executes them.

The private implementation this was ported from copied with ``ditto``, then
immediately ran ``rm -rf`` on the original **without verifying the copy**, and
on any error retried the whole thing as an elevated shell script assembled by
string interpolation. Its "prepare" and "link" actions also ``rm -rf``-ed
whatever was at the home path. The plans below fix the order instead:

    copy → verify (file count + bytes) → rename original aside → symlink
         → verify link → remove the set-aside original

so at every step either the original or a verified copy exists, and a failed
step stops the job with the original still on disk. There is no elevated
fallback: a step that needs privilege fails with a reason (CLN-20 decides
whether a privileged plan is offered).
"""

from __future__ import annotations

import enum
import os
import stat
from dataclasses import dataclass

ASIDE_SUFFIX = ".oslab-moving"
RESTORE_SUFFIX = ".oslab-restoring"
#: Extra free space required on the destination beyond the measured size.
DEFAULT_PAD_BYTES = 256 * 1024 * 1024


class FolderStatus(enum.Enum):
    LOCAL_ONLY = "local_only"        # real folder at home, nothing on the store
    LINKED_OK = "linked_ok"          # home is a symlink to the store copy, which exists
    MISSING_LINK = "missing_link"    # store copy exists, home path absent
    BROKEN_LINK = "broken_link"      # home is a symlink whose target is missing
    WRONG_TARGET = "wrong_target"    # home is a symlink to somewhere else that exists
    CONFLICT = "conflict"            # real folder at home AND a store copy
    MISSING = "missing"              # neither side exists


class RelocationError(ValueError):
    """The plan cannot be built. The message is safe to show."""


def _lexists(path: str) -> bool:
    return os.path.lexists(path)


def _is_link(path: str) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        return False


def _link_target(link: str) -> str:
    target = os.readlink(link)
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(link), target)
    return os.path.normpath(target)


def _same(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def classify(home_path: str, store_path: str) -> FolderStatus:
    store_exists = _lexists(store_path) and not _is_link(store_path)
    if _is_link(home_path):
        try:
            target = _link_target(home_path)
        except OSError:
            return FolderStatus.BROKEN_LINK
        if not os.path.exists(target):
            return FolderStatus.BROKEN_LINK
        if _same(target, store_path):
            return FolderStatus.LINKED_OK
        return FolderStatus.WRONG_TARGET
    home_exists = _lexists(home_path)
    if home_exists and store_exists:
        return FolderStatus.CONFLICT
    if store_exists:
        return FolderStatus.MISSING_LINK
    if home_exists:
        return FolderStatus.LOCAL_ONLY
    return FolderStatus.MISSING


@dataclass(frozen=True)
class Step:
    #: copy | verify_copy | rename | symlink | verify_link | remove_tree | remove_link
    op: str
    src: str
    dst: str = ""


def tree_fingerprint(root: str) -> tuple[int, int]:
    """``(regular_file_count, total_bytes)`` under ``root``; symlinks are counted, never followed."""
    files = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames + [d for d in dirnames if _is_link(os.path.join(dirpath, d))]:
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            files += 1
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return files, total


def plan_move(
    home_path: str,
    store_path: str,
    *,
    size_bytes: int,
    free_bytes: int,
    pad_bytes: int = DEFAULT_PAD_BYTES,
) -> list[Step]:
    """Steps to move ``home_path`` to ``store_path`` and leave a symlink behind.

    Paths must already be validated (``path_policy.validate_copy``) by the caller.
    """
    status = classify(home_path, store_path)
    if status is not FolderStatus.LOCAL_ONLY:
        raise RelocationError(f"Cannot move: state is {status.value}, expected local_only.")
    if free_bytes < size_bytes + pad_bytes:
        raise RelocationError(
            f"Not enough free space on the destination (need {size_bytes + pad_bytes} bytes, have {free_bytes})."
        )
    if _lexists(home_path + ASIDE_SUFFIX):
        raise RelocationError(f"A previous move was interrupted: {home_path + ASIDE_SUFFIX} exists.")
    aside = home_path + ASIDE_SUFFIX
    return [
        Step("copy", home_path, store_path),
        Step("verify_copy", home_path, store_path),
        Step("rename", home_path, aside),
        Step("symlink", home_path, store_path),
        Step("verify_link", home_path, store_path),
        Step("remove_tree", aside),
    ]


def plan_restore(home_path: str, store_path: str, *, keep_store_copy: bool = True) -> list[Step]:
    """Steps to bring a relocated folder back to ``home_path``."""
    status = classify(home_path, store_path)
    if status not in (FolderStatus.LINKED_OK, FolderStatus.MISSING_LINK, FolderStatus.BROKEN_LINK):
        raise RelocationError(f"Cannot restore: state is {status.value}.")
    if status is FolderStatus.BROKEN_LINK:
        raise RelocationError("Cannot restore: the store copy is missing. Remove the broken link instead.")
    staging = home_path + RESTORE_SUFFIX
    if _lexists(staging):
        raise RelocationError(f"A previous restore was interrupted: {staging} exists.")
    steps = [Step("copy", store_path, staging), Step("verify_copy", store_path, staging)]
    if status is FolderStatus.LINKED_OK:
        steps.append(Step("remove_link", home_path))
    steps.append(Step("rename", staging, home_path))
    if not keep_store_copy:
        steps.append(Step("remove_tree", store_path))
    return steps


def plan_relink(home_path: str, store_path: str) -> list[Step]:
    """Repair a missing or wrong link. Never removes a real folder (that is a CONFLICT for the user)."""
    status = classify(home_path, store_path)
    if status is FolderStatus.MISSING_LINK:
        return [Step("symlink", home_path, store_path), Step("verify_link", home_path, store_path)]
    if status in (FolderStatus.WRONG_TARGET, FolderStatus.BROKEN_LINK) and os.path.exists(store_path):
        return [Step("remove_link", home_path), Step("symlink", home_path, store_path),
                Step("verify_link", home_path, store_path)]
    raise RelocationError(f"Cannot relink: state is {status.value}.")
