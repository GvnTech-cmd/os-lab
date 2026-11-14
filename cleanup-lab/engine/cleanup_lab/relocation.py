"""CLN-27: move a cache or toolchain to another volume behind a symlink, and back.

Ported from ``cleanup-lab/reference/python/cleanup_ref/relocation.py``, which
fixed the private implementation's order: it copied with ``ditto`` and then ran
``rm -rf`` on the original **without verifying the copy**, and retried failures
as an elevated shell script built by string interpolation.

The order here is the fix:

    copy → verify (file count + bytes) → rename original aside → symlink
         → verify link → remove the set-aside original

so at every step either the original or a verified copy exists, and a failed
step stops the job with the original still on disk. There is no elevated
fallback: on Windows a symlink needs Developer Mode or a privilege, and that
fails with a reason (CLN-20 decides whether a privileged plan is offered).

The seven link states of :func:`classify` are ``local_only``, ``linked_ok``,
``missing_link``, ``broken_link``, ``wrong_target``, ``conflict`` and
``missing``. An interrupted move leaves ``<home>.oslab-moving`` behind;
:func:`plan_resume` continues it safely instead of guessing, and a new move
refuses to start while it exists.

Targets are catalog entries only (the page sends an entry id), stores are
``<volume>/oslab-caches/<entry id>`` (the page sends a volume mount point from
CLN-28's inventory), the source/destination pair passes
:func:`cleanup_lab.safety.validate_copy`, and the entry's owning application
must not be running (CLN-12's lock).
"""
from __future__ import annotations

import enum
import os
import shutil
import stat
import time
from dataclasses import dataclass

from . import paths, volumes
from .catalog import load as catalog_load, resolve as catalog_resolve
from .safety import running_processes, validate_copy

ASIDE_SUFFIX = ".oslab-moving"
RESTORE_SUFFIX = ".oslab-restoring"
#: Extra free space required on the destination beyond the measured size.
DEFAULT_PAD_BYTES = 256 * 1024 * 1024
#: Where a relocated folder lives on the destination volume.
STORE_DIRNAME = "oslab-caches"
#: The typed actions the console accepts.
ACTIONS = ("move", "restore", "relink", "resume")


class RelocationError(ValueError):
    """The plan cannot be built or a step failed. The message is safe to show."""


class FolderStatus(enum.Enum):
    LOCAL_ONLY = "local_only"        # real folder at home, nothing on the store
    LINKED_OK = "linked_ok"          # home is a symlink to the store copy, which exists
    MISSING_LINK = "missing_link"    # store copy exists, home path absent
    BROKEN_LINK = "broken_link"      # home is a symlink whose target is missing
    WRONG_TARGET = "wrong_target"    # home is a symlink to somewhere else that exists
    CONFLICT = "conflict"            # real folder at home AND a store copy
    MISSING = "missing"              # neither side exists


def _lexists(path):
    return os.path.lexists(path)


def _is_link(path):
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except OSError:
        return False


def _link_target(link):
    target = os.readlink(link)
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(link), target)
    return os.path.normpath(target)


def _same(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def classify(home_path, store_path):
    """The seven-state read-only classification of a home path and its store copy."""
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


def tree_fingerprint(root):
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


def plan_move(home_path, store_path, *, size_bytes, free_bytes, pad_bytes=DEFAULT_PAD_BYTES):
    """Steps to move ``home_path`` to ``store_path`` and leave a symlink behind."""
    status = classify(home_path, store_path)
    if status is not FolderStatus.LOCAL_ONLY:
        raise RelocationError("Cannot move: state is {0}, expected local_only.".format(status.value))
    if free_bytes < size_bytes + pad_bytes:
        raise RelocationError(
            "Not enough free space on the destination (need {0} bytes, have {1}).".format(
                size_bytes + pad_bytes, free_bytes)
        )
    if _lexists(home_path + ASIDE_SUFFIX):
        raise RelocationError(
            "A previous move was interrupted: {0} exists. Resume it instead.".format(
                home_path + ASIDE_SUFFIX)
        )
    aside = home_path + ASIDE_SUFFIX
    return [
        Step("copy", home_path, store_path),
        Step("verify_copy", home_path, store_path),
        Step("rename", home_path, aside),
        Step("symlink", home_path, store_path),
        Step("verify_link", home_path, store_path),
        Step("remove_tree", aside),
    ]


def plan_restore(home_path, store_path, *, keep_store_copy=True):
    """Steps to bring a relocated folder back to ``home_path``."""
    status = classify(home_path, store_path)
    if status not in (FolderStatus.LINKED_OK, FolderStatus.MISSING_LINK, FolderStatus.BROKEN_LINK):
        raise RelocationError("Cannot restore: state is {0}.".format(status.value))
    if status is FolderStatus.BROKEN_LINK:
        raise RelocationError(
            "Cannot restore: the store copy is missing. Remove the broken link instead."
        )
    staging = home_path + RESTORE_SUFFIX
    if _lexists(staging):
        raise RelocationError("A previous restore was interrupted: {0} exists.".format(staging))
    steps = [Step("copy", store_path, staging), Step("verify_copy", store_path, staging)]
    if status is FolderStatus.LINKED_OK:
        steps.append(Step("remove_link", home_path))
    steps.append(Step("rename", staging, home_path))
    if not keep_store_copy:
        steps.append(Step("remove_tree", store_path))
    return steps


def plan_relink(home_path, store_path):
    """Repair a missing or wrong link. Never removes a real folder (that is a CONFLICT for the user)."""
    status = classify(home_path, store_path)
    if status is FolderStatus.MISSING_LINK:
        return [Step("symlink", home_path, store_path), Step("verify_link", home_path, store_path)]
    if status in (FolderStatus.WRONG_TARGET, FolderStatus.BROKEN_LINK) and os.path.exists(store_path):
        return [Step("remove_link", home_path), Step("symlink", home_path, store_path),
                Step("verify_link", home_path, store_path)]
    raise RelocationError("Cannot relink: state is {0}.".format(status.value))


def plan_resume(home_path, store_path):
    """Continue an interrupted move; never removes the set-aside original before verifying the store."""
    aside = home_path + ASIDE_SUFFIX
    if not _lexists(aside):
        raise RelocationError("Nothing to resume: no interrupted move was found.")
    if _lexists(home_path) and not _is_link(home_path):
        if not os.path.isdir(store_path):
            raise RelocationError("Nothing to resume: the set-aside copy has no verified store copy.")
        return [
            Step("verify_copy", home_path, store_path),
            Step("rename", home_path, aside),
            Step("symlink", home_path, store_path),
            Step("verify_link", home_path, store_path),
            Step("remove_tree", aside),
        ]
    steps = []
    if not _is_link(home_path):
        steps.extend([Step("symlink", home_path, store_path), Step("verify_link", home_path, store_path)])
    steps.extend([Step("verify_copy", store_path, aside), Step("remove_tree", aside)])
    return steps


# ── Executor ────────────────────────────────────────────────────────────────


def _retry_writable(function, path, error):
    try:
        os.chmod(path, stat.S_IRWXU)
        function(path)
    except OSError as failure:
        raise RelocationError(
            "Could not remove {0}: {1}".format(path, failure.strerror or failure)
        ) from failure


def _remove_tree(path):
    try:
        shutil.rmtree(path, onerror=_retry_writable)
    except RelocationError:
        raise
    except OSError as exc:
        raise RelocationError("Could not remove {0}: {1}".format(path, exc.strerror or exc)) from exc


def copy_tree(src, dst):
    try:
        shutil.copytree(src, dst, symlinks=True)
    except OSError as exc:
        raise RelocationError("Could not copy {0}: {1}".format(src, exc.strerror or exc)) from exc


def verify_copy(src, dst):
    """File count and byte total must match; the copy is never trusted by existence alone."""
    left = tree_fingerprint(src)
    right = tree_fingerprint(dst)
    if left != right:
        raise RelocationError(
            "The copy does not match the original ({0} files / {1} bytes vs {2} files / {3} bytes).".format(
                right[0], right[1], left[0], left[1])
        )


def execute_steps(steps, *, progress_callback=None, cancel=None):
    """Run typed steps in order; a failure stops with the original still in place."""
    results = []
    total = len(steps)
    for step in steps:
        if cancel is not None and cancel.is_set():
            return {"cancelled": True, "stepsDone": len(results), "stepsTotal": total,
                    "steps": results, "remaining": [item.op for item in steps[len(results):]]}
        try:
            if step.op == "copy":
                copy_tree(step.src, step.dst)
            elif step.op == "verify_copy":
                verify_copy(step.src, step.dst)
            elif step.op == "rename":
                os.rename(step.src, step.dst)
            elif step.op == "symlink":
                os.symlink(step.dst, step.src)
            elif step.op == "verify_link":
                if not _is_link(step.src) or not _same(_link_target(step.src), step.dst):
                    raise RelocationError(
                        "The link at {0} does not point at {1}.".format(step.src, step.dst)
                    )
            elif step.op == "remove_link":
                if not _is_link(step.src):
                    raise RelocationError("Refusing to remove a real folder at {0}.".format(step.src))
                os.unlink(step.src)
            elif step.op == "remove_tree":
                _remove_tree(step.src)
            else:
                raise RelocationError("Unknown step {0}".format(step.op))
        except RelocationError:
            raise
        except OSError as exc:
            raise RelocationError(
                "Step {0} failed at {1}: {2}".format(step.op, step.src, exc.strerror or exc)
            ) from exc
        results.append({"op": step.op, "src": step.src, "dst": step.dst})
        if progress_callback is not None:
            progress_callback({"step": step.op, "stepsDone": len(results), "stepsTotal": total})
    return {"cancelled": False, "stepsDone": len(results), "stepsTotal": total, "steps": results}


# ── Console integration ─────────────────────────────────────────────────────


def _store_base(destination):
    return os.path.join(destination, STORE_DIRNAME)


def _first_folder(root, entry_id, platform, env):
    entry = next((item for item in catalog_load(root, env) if item["id"] == entry_id), None)
    if entry is None:
        raise RelocationError("Unknown catalog entry id")
    resolved = [item["path"] for item in catalog_resolve(entry, platform, env) if item.get("path")]
    if not resolved:
        raise RelocationError("This entry has no path on this platform")
    return entry, resolved[0]


def status(root, *, platform=None, env=None):
    """Every relocatable catalog entry (read-only ``lstat``/``readlink``) plus the volumes."""
    platform = platform or paths.platform_id()
    env = os.environ if env is None else env
    entries = []
    for entry in catalog_load(root, env):
        for item in catalog_resolve(entry, platform, env):
            path = item.get("path")
            if not path or not _lexists(path):
                continue
            interrupted = _lexists(path + ASIDE_SUFFIX) or _lexists(path + RESTORE_SUFFIX)
            entries.append({
                "entryId": entry["id"],
                "name": entry.get("name", entry["id"]),
                "path": path,
                "relocatable": os.path.isdir(path) and not _is_link(path),
                "interrupted": interrupted,
            })
    return {"platform": platform, "entries": entries, "destinations": destinations(platform, env=env)}


def destinations(platform=None, env=None, *, rows=None, usage_fn=None):
    """The local volumes a store may live on, with their free space (CLN-28's inventory)."""
    platform = platform or paths.platform_id()
    env = os.environ if env is None else env
    report = volumes.inventory(platform, env, rows=rows, usage_fn=usage_fn)
    return [
        {"mountPoint": volume["mountPoint"], "freeBytes": volume["freeBytes"],
         "totalBytes": volume["totalBytes"], "kind": volume["kind"]}
        for volume in report["volumes"]
        if volume["kind"] in ("root", "internal", "removable") and volume["freeBytes"] is not None
    ]


def build_plan(root, entry_id, destination, action, *, platform=None, env=None,
               fingerprint=None, free_bytes=None, process_list=None):
    """Validate one typed relocation and return its preview record.

    ``fingerprint`` and ``free_bytes`` are test seams; the real run measures the
    source tree read-only and asks the destination volume for free space.
    """
    if action not in ACTIONS:
        raise RelocationError("action must be one of {0}".format(", ".join(ACTIONS)))
    platform = platform or paths.platform_id()
    env = os.environ if env is None else env
    entry, home_path = _first_folder(root, entry_id, platform, env)
    store_path = os.path.join(_store_base(destination), entry_id)
    home, store = validate_copy(home_path, store_path, _store_base(destination),
                                home=paths.home_dir(env))
    busy = running_processes(entry.get("owningProcesses", ()), names=process_list,
                             platform=platform)
    if busy:
        raise RelocationError("The owning application is running: {0}".format(", ".join(sorted(busy))))
    files = size = None
    if action == "move":
        files, size = fingerprint(home) if fingerprint is not None else tree_fingerprint(home)
    free = free_bytes if free_bytes is not None else shutil.disk_usage(destination).free
    if action == "move":
        steps = plan_move(home, store, size_bytes=size, free_bytes=free)
    elif action == "restore":
        steps = plan_restore(home, store)
    elif action == "relink":
        steps = plan_relink(home, store)
    else:
        steps = plan_resume(home, store)
    return {
        "action": action,
        "entryId": entry_id,
        "entryName": entry.get("name", entry_id),
        "homePath": home,
        "storePath": store,
        "destination": destination,
        "files": files,
        "sizeBytes": size,
        "freeBytes": free,
        "state": classify(home, store).value,
        "steps": [{"op": step.op, "src": step.src, "dst": step.dst} for step in steps],
        "fingerprint": {"files": files, "bytes": size} if action == "move" else None,
    }


def execute(record, *, cancel=None, progress_callback=None, fingerprint=None):
    """Run a confirmed record: re-verify, execute the typed steps, report honestly."""
    action = record["action"]
    home = record["homePath"]
    store = record["storePath"]
    if record.get("fingerprint"):
        files, size = fingerprint(home) if fingerprint is not None else tree_fingerprint(home)
        expected = record["fingerprint"]
        if files != expected["files"] or size != expected["bytes"]:
            raise RelocationError("The folder changed since the preview; preview again.")
    steps = [Step(**item) for item in record["steps"]]
    outcome = execute_steps(steps, cancel=cancel, progress_callback=progress_callback)
    return {
        "entryId": record["entryId"],
        "action": action,
        "homePath": home,
        "storePath": store,
        "status": "completed",
        "bytesRelocated": record.get("sizeBytes"),
        "bytesRemoved": None,
        "cancelled": outcome["cancelled"],
        "stepsDone": outcome["stepsDone"],
        "stepsTotal": outcome["stepsTotal"],
    }
