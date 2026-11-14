"""The plan → confirm → clean executor (CLN-13).

Ports the *behaviour* of Qleaner's ``clean_items`` / ``clean_leftovers`` /
``retry_remove`` (see ``cleanup-lab/PARITY.md``) without its bugs
(``cleanup-lab/README.md``, "Do not port"):

* **Trash by default.** Qleaner silently fell back to ``remove_dir_all`` when the
  Trash move failed and still counted the bytes. Here a failed Trash is a failed
  item: the file stays where it was, nothing is counted, and the error says why.
  Permanent deletion is a mode the plan must state explicitly — never a fallback.
* **Plan → confirm → run.** A plan is built from catalog entry ids (never a path
  list from the page), lists every item with its size, mode and refusal reason,
  and carries a fingerprint per item. Running re-measures first: an item that
  changed or vanished since the plan was made expires the whole plan. A plan is
  single-use and short-lived (:data:`PLAN_TTL`).
* **Honest results.** Per item one of ``trashed`` / ``deleted`` / ``skipped``
  (with a stable ``code`` and reason) / ``failed`` (with the error). Bytes are
  credited only when the item is really gone from its original path, and only in
  the amount measured in this run — never the plan's estimate, never a failed
  item's size. Transient ``OSError``s (EBUSY, ETXTBSY, …) are retried with a
  short backoff (:func:`retry`).
* **Guarded.** Every item goes through ``safety.check_target`` (CLN-12): resolved
  containment, ownership, running apps, privilege. The fingerprint walk never
  follows symlinks (rule 1).

Trash targets come from :func:`cleanup_lab.paths.trash_dir`: macOS ``~/.Trash``,
the freedesktop Trash (with ``.trashinfo``) on Linux. Windows has no folder the
engine may address, so a trash-mode item there fails with that reason instead of
being deleted (rule 3). A cross-volume item is copied, verified against a fresh
walk of the original, and only then removed from the source — and when removing
the original fails, the verified copy stays in the Trash instead of being
discarded, because it may hold the item's only remaining bytes.

Nothing here writes outside the Trash: planning and verifying are read-only.
"""
from __future__ import annotations

import errno
import os
import shutil
import stat as stat_mod
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import safety
from . import scan
from .catalog import load, resolve as catalog_resolve
from .paths import platform_id, trash_dir

#: The modes a plan may name. ``trash`` is the default and the only automatic
#: choice; ``delete`` must be requested explicitly and is executed exactly as
#: planned (Qleaner's bug was the *fallback*, not the mode).
MODES = ("trash", "delete")
DEFAULT_MODE = "trash"
#: A plan expires after this many seconds even when nothing changed.
PLAN_TTL = 600.0
#: Transient-error retries (Qleaner's ``retry_remove``, minus the silent swallow).
RETRY_ATTEMPTS = 3
RETRY_DELAY = 0.15
TRANSIENT_ERRNOS = frozenset(
    {errno.EBUSY, errno.ETXTBSY, errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR, errno.ENOTEMPTY}
)
CANCEL_EVERY = 128  # listing entries polled between cancel checks inside one walk


class PlanError(ValueError):
    """A plan request or run was refused. ``code`` is stable; the page translates it.

    Codes: ``plan-invalid`` (bad request), ``unknown-plan``, ``expired`` (past
    :data:`PLAN_TTL`), ``stale`` (an item changed since the plan was made),
    ``used`` (the plan was already run), ``cancelled``.
    """

    def __init__(self, message, code="plan-invalid"):
        super().__init__(message)
        self.code = code


class CleanError(ValueError):
    """One item could not be cleaned; its ``str`` is the per-item error."""


@dataclass
class Plan:
    """A confirmable plan: the JSON payload plus the fingerprints that expire it.

    ``payload`` is ``None`` for a plan build that was cancelled before it
    finished; ``fingerprints`` maps each ready item's resolved path to the tuple
    :func:`_fingerprint_key` compares again right before the run.
    """

    id: str
    mode: str
    created_at: float
    expires_at: float
    payload: dict | None
    fingerprints: dict
    progress: dict

    def to_dict(self):
        return self.payload


def retry(operation, *, attempts=RETRY_ATTEMPTS, delay=RETRY_DELAY, sleep=time.sleep):
    """Run ``operation``; retry transient ``OSError``s with a doubling backoff.

    Returns ``(value, attempts_used)``. A non-transient error, or a transient one
    on the last attempt, is raised — never swallowed (Qleaner ignored the final
    error and still reported success).
    """
    used = 0
    for attempt in range(1, attempts + 1):
        used = attempt
        try:
            return operation(), used
        except OSError as exc:
            if attempt >= attempts or exc.errno not in TRANSIENT_ERRNOS:
                raise
            sleep(delay * (2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def _cancelled(cancel):
    return cancel is not None and cancel.is_set()


# ── Fingerprint: one read-only pass for the preview and the expiry check ────


def fingerprint_path(path, *, cancel=None, progress=None):
    """Measure ``path`` once, read-only, and describe it for the plan.

    Returns a dict with ``kind`` (``file`` / ``dir`` / ``other`` / ``missing`` /
    ``unreadable``), the size preview (``bytes``, ``onDiskBytes`` or ``None``,
    ``files``, ``folders``) and the fingerprint inputs (``symlinks``, ``special``,
    ``unreadable``, ``maxMtimeNs``, ``dev``, ``ino``). Symlinks are counted,
    never followed; sockets, FIFOs and device nodes are ``other``. ``None`` when
    the cancel fired mid-walk.
    """
    try:
        root_stat = os.lstat(path)
    except FileNotFoundError:
        return {"kind": "missing"}
    except OSError:
        return {"kind": "unreadable"}
    measure = {
        "kind": "other",
        "bytes": 0,
        "onDiskBytes": None,
        "files": 0,
        "folders": 0,
        "symlinks": 0,
        "special": 0,
        "unreadable": 0,
        "maxMtimeNs": root_stat.st_mtime_ns,
        "dev": root_stat.st_dev,
        "ino": root_stat.st_ino,
    }
    mode = root_stat.st_mode
    if stat_mod.S_ISLNK(mode):
        # check_target already resolved the path, so a link here means it was
        # swapped in between; the plan skips rather than follow an unseen link.
        measure["kind"] = "missing"
        return measure
    if stat_mod.S_ISREG(mode):
        measure["kind"] = "file"
        measure["bytes"] = root_stat.st_size
        blocks = getattr(root_stat, "st_blocks", None)
        if blocks is not None:
            measure["onDiskBytes"] = blocks * 512
        measure["files"] = 1
        return measure
    if not stat_mod.S_ISDIR(mode):
        return measure  # a socket, FIFO or device node: "other"
    measure["kind"] = "dir"
    return _walk_fingerprint(path, measure, cancel=cancel, progress=progress)


def _walk_fingerprint(root, measure, *, cancel, progress):
    """Depth-first ``lstat`` walk of one folder; never follows links."""
    poll = 0
    has_blocks = False
    seen_inodes = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if _cancelled(cancel):
            return None
        try:
            with os.scandir(current) as iterator:
                listing = list(iterator)
        except OSError:
            measure["unreadable"] += 1
            if progress is not None:
                progress.tick(current=current)
            continue
        measure["folders"] += 1
        poll += len(listing)
        if poll >= CANCEL_EVERY:
            poll = 0
            if _cancelled(cancel):
                return None
        for child in listing:
            try:
                stat = child.stat(follow_symlinks=False)
            except OSError:
                measure["unreadable"] += 1
                continue
            child_mode = stat.st_mode
            if stat_mod.S_ISLNK(child_mode):
                measure["symlinks"] += 1
                continue
            if stat_mod.S_ISDIR(child_mode):
                stack.append(child.path)
                measure["maxMtimeNs"] = max(measure["maxMtimeNs"], stat.st_mtime_ns)
                continue
            if stat_mod.S_ISREG(child_mode):
                if stat.st_ino != 0:
                    key = (stat.st_dev, stat.st_ino)
                    if key in seen_inodes:
                        continue  # a hard link to a file already counted
                    seen_inodes.add(key)
                measure["bytes"] += stat.st_size
                blocks = getattr(stat, "st_blocks", None)
                if blocks is not None:
                    measure["onDiskBytes"] = (measure["onDiskBytes"] or 0) + blocks * 512
                    has_blocks = True
                measure["files"] += 1
                measure["maxMtimeNs"] = max(measure["maxMtimeNs"], stat.st_mtime_ns)
                if progress is not None:
                    progress.tick(apparent_delta=stat.st_size, files_delta=1, current=current)
            else:
                measure["special"] += 1
    if not has_blocks:
        measure["onDiskBytes"] = None
    return measure


def _fingerprint_key(measure):
    """The comparable fingerprint; any component changing means "the plan is stale"."""
    kind = measure["kind"]
    if kind in ("missing", "unreadable"):
        return (kind,)
    return (
        kind,
        measure["bytes"],
        measure["onDiskBytes"],
        measure["files"],
        measure["folders"],
        measure["symlinks"],
        measure["special"],
        measure["unreadable"],
        measure["maxMtimeNs"],
        measure["dev"],
        measure["ino"],
    )


class _PlanProgress:
    """Throttled planning progress: the scan progress keys with phase ``planning``."""

    def __init__(self, total, callback=None):
        self._lock = threading.Lock()
        self._callback = callback
        self._last = 0.0
        self.total = total
        self.done = 0
        self.bytes_seen = 0
        self.files_seen = 0
        self.current = ""

    def tick(self, apparent_delta=0, files_delta=0, current=""):
        now = time.monotonic()
        payload = None
        with self._lock:
            self.bytes_seen += apparent_delta
            self.files_seen += files_delta
            if current:
                self.current = current
            if now - self._last >= scan.PROGRESS_INTERVAL and self._callback is not None:
                self._last = now
                payload = self._snapshot_locked()
        if payload is not None:
            self._callback(payload)

    def finish_path(self):
        with self._lock:
            self.done += 1

    def final(self):
        snapshot = self._final_snapshot()
        snapshot["phase"] = "done"
        return snapshot

    def final_cancelled(self):
        snapshot = self._final_snapshot()
        snapshot["phase"] = "cancelled"
        return snapshot

    def _final_snapshot(self):
        with self._lock:
            snapshot = self._snapshot_locked()
        return snapshot

    def _snapshot_locked(self):
        return {
            "phase": "planning",
            "pathsDone": self.done,
            "pathsTotal": self.total,
            "bytesSeen": self.bytes_seen,
            "filesSeen": self.files_seen,
            "currentPath": self.current,
        }


# ── Planning ─────────────────────────────────────────────────────────────────


def _plan_item(entry, template, path, status, *, mode, code="", reason="", source="catalog"):
    return {
        "entryId": entry["id"],
        "entryName": entry["name"],
        "risk": entry["risk"],
        "template": template,
        "path": path,
        "source": source,
        "status": status,
        "code": code,
        "reason": reason,
        "privileged": bool(entry.get("needsPrivilege")),
        "mode": mode,
        "sizeBytes": 0,
        "sizeOnDiskBytes": None,
        "files": 0,
        "folders": 0,
    }


def _trash_relation(path, trash_target):
    """How a planned path relates to the Trash target, or ``None`` when unrelated."""
    if trash_target is None:
        return None
    if path == trash_target:
        return "same"
    if safety.is_contained(trash_target, path):
        return "contains-trash"
    if safety.is_contained(path, trash_target):
        return "inside-trash"
    return None


_TRASH_RELATION_REASONS = {
    "same": "This item is the Trash itself; emptying it is a permanent delete, not a move.",
    "inside-trash": "This item is already inside the Trash.",
    "contains-trash": "This item contains the Trash folder.",
}


def build_plan(
    root,
    entry_ids,
    *,
    mode=DEFAULT_MODE,
    env=None,
    platform=None,
    workers=None,
    cancel=None,
    progress_callback=None,
    catalog_entries=None,
    uid=None,
    lstat=None,
    names=None,
    runner=None,
    clock=None,
):
    """Plan the cleaning of catalog entries: guard, measure, fingerprint — read-only.

    ``entry_ids`` must be a non-empty list of catalog ids (the console never
    accepts a path list). Every resolved path goes through ``safety.check_target``;
    every ready item is measured and fingerprinted in one read-only walk. Returns
    a :class:`Plan`; its ``payload`` is ``None`` when the build was cancelled.
    """
    clock = time.time if clock is None else clock
    env = os.environ if env is None else env
    target = platform or platform_id()
    if mode not in MODES:
        raise PlanError("mode must be one of {0}".format(", ".join(MODES)))
    if (
        not isinstance(entry_ids, (list, tuple))
        or not entry_ids
        or any(not isinstance(item, str) or not item for item in entry_ids)
    ):
        raise PlanError("entryIds must be a non-empty list of detector ids")
    if len(set(entry_ids)) != len(entry_ids):
        raise PlanError("entryIds contains duplicates")
    workers = scan.DEFAULT_WORKERS if workers is None else int(workers)
    if workers < 1 or workers > scan.MAX_WORKERS:
        raise PlanError("workers must be between 1 and {0}".format(scan.MAX_WORKERS))

    entries = catalog_entries if catalog_entries is not None else load(root, env)
    by_id = {entry["id"]: entry for entry in entries}
    unknown = [eid for eid in entry_ids if eid not in by_id]
    if unknown:
        raise PlanError("Unknown detector id(s): {0}".format(", ".join(sorted(unknown))))

    if names is None and any(by_id[eid].get("owningProcesses") for eid in entry_ids):
        # One process-table read per plan, not one per path.
        names = safety.process_names(platform=target, runner=runner)

    items = []
    pending = []
    seen_paths = set()
    for entry_id in entry_ids:
        entry = by_id[entry_id]
        privileged = bool(entry.get("needsPrivilege"))
        if not entry.get("cleanable", True):
            items.append(_plan_item(entry, "", None, "skipped", mode=mode,
                                    code="not-cleanable", reason="This is toolchain or configuration data; cleaning is disabled."))
            continue
        if not entry["paths"].get(target):
            items.append(
                _plan_item(
                    entry, "", None, "skipped", mode=mode,
                    code="no-path", reason="This entry has no path for this system.",
                )
            )
            continue
        for resolved in catalog_resolve(entry, target, env):
            template, path, reason = resolved["template"], resolved["path"], resolved["reason"]
            if path is None:
                items.append(
                    _plan_item(entry, template, None, "skipped", mode=mode, code="no-path", reason=reason,
                               source=resolved["source"])
                )
                continue
            if privileged:
                items.append(
                    _plan_item(
                        entry, template, path, "skipped", mode=mode,
                        code="privileged", source=resolved["source"],
                        reason="This entry needs administrator rights; a privileged plan arrives in a later task.",
                    )
                )
                continue
            verdict = safety.check_target(
                path, entry, env=env, platform=target, uid=uid, lstat=lstat, names=names, runner=runner
            )
            if not verdict.ok:
                items.append(
                    _plan_item(
                        entry, template, verdict.path or path, "skipped", mode=mode,
                        code=verdict.code, reason=verdict.reason, source=resolved["source"],
                    )
                )
                continue
            if verdict.path in seen_paths:
                items.append(
                    _plan_item(
                        entry, template, verdict.path, "skipped", mode=mode,
                        code="duplicate", reason="This path is already in the plan.", source=resolved["source"],
                    )
                )
                continue
            seen_paths.add(verdict.path)
            item = _plan_item(entry, template, verdict.path, "ready", mode=mode,
                              source=resolved["source"])
            items.append(item)
            pending.append(item)

    trash_target = trash_dir(env, target)
    if mode == "trash" and trash_target is not None:
        for item in pending:
            relation = _trash_relation(item["path"], trash_target)
            if relation is not None:
                item["status"] = "skipped"
                item["code"] = "trash-nesting"
                item["reason"] = _TRASH_RELATION_REASONS[relation]
    pending = [item for item in pending if item["status"] == "ready"]

    progress = _PlanProgress(len(pending), progress_callback)

    def walk_one(item):
        measure = fingerprint_path(item["path"], cancel=cancel, progress=progress)
        progress.finish_path()
        return measure

    walked = _run_walks(pending, walk_one, workers=workers)
    if _cancelled(cancel):
        return Plan(
            id=uuid.uuid4().hex[:12],
            mode=mode,
            created_at=clock(),
            expires_at=clock() + PLAN_TTL,
            payload=None,
            fingerprints={},
            progress=progress.final_cancelled(),
        )

    fingerprints = {}
    for item, measure in zip(pending, walked):
        if measure is None or measure["kind"] == "missing":
            item["status"], item["code"] = "skipped", "missing"
            item["reason"] = "The path no longer exists."
            continue
        if measure["kind"] == "unreadable":
            item["status"], item["code"] = "skipped", "unreadable"
            item["reason"] = "The path cannot be read."
            continue
        if measure["kind"] == "other":
            item["status"], item["code"] = "skipped", "not-cleanable"
            item["reason"] = "Not a regular file or folder; there is nothing to clean here."
            continue
        item["sizeBytes"] = measure["bytes"]
        item["sizeOnDiskBytes"] = measure["onDiskBytes"]
        item["files"] = measure["files"]
        item["folders"] = measure["folders"]
        fingerprints[item["path"]] = _fingerprint_key(measure)

    # A ready item inside another ready item would be removed by its parent; the
    # later one yields and says so instead of failing mid-run.
    ready = [item for item in items if item["status"] == "ready"]
    for index, item in enumerate(ready):
        for other in ready[:index]:
            if item["path"] != other["path"] and safety.is_contained(item["path"], other["path"]):
                item["status"] = "skipped"
                item["code"] = "nested"
                item["reason"] = "This path is inside another planned item."
                fingerprints.pop(item["path"], None)
                break

    ready = [item for item in items if item["status"] == "ready"]
    built_at = clock()
    payload = {
        "planId": uuid.uuid4().hex[:12],
        "createdAt": built_at,
        "expiresAt": built_at + PLAN_TTL,
        "ttlSeconds": PLAN_TTL,
        "mode": mode,
        "platform": target,
        "items": items,
        "totals": {
            "items": len(items),
            "ready": len(ready),
            "skipped": len(items) - len(ready),
            "bytes": sum(item["sizeBytes"] for item in ready),
            "files": sum(item["files"] for item in ready),
            "folders": sum(item["folders"] for item in ready),
        },
    }
    return Plan(
        id=payload["planId"],
        mode=mode,
        created_at=built_at,
        expires_at=built_at + PLAN_TTL,
        payload=payload,
        fingerprints=fingerprints,
        progress=progress.final(),
    )


def _run_walks(pending, walk_one, *, workers):
    """Measure the pending items with the scan's bounded parallelism (1–16)."""
    if not pending:
        return []
    if len(pending) == 1 or workers == 1:
        return [walk_one(item) for item in pending]
    with ThreadPoolExecutor(max_workers=min(workers, len(pending))) as pool:
        futures = [pool.submit(walk_one, item) for item in pending]
        return [future.result() for future in futures]


# ── Verification: the plan expires when the items change ────────────────────


def verify_plan(plan, *, cancel=None, clock=None):
    """Re-measure every ready item right before the run; any change expires the plan.

    Returns ``{path: measure}`` — the numbers the run credits when an item is
    really removed. Raises :class:`PlanError` (``expired`` / ``stale`` /
    ``cancelled``) without touching anything.
    """
    clock = time.time if clock is None else clock
    if plan.mode not in MODES:
        raise PlanError("The plan names an unknown mode.", "plan-invalid")
    if plan.expires_at < clock():
        raise PlanError("This plan expired; build a new one.", "expired")
    measures = {}
    for item in plan.payload["items"]:
        if item["status"] != "ready":
            continue
        if _cancelled(cancel):
            raise PlanError("The clean was cancelled before anything was removed.", "cancelled")
        fresh = fingerprint_path(item["path"], cancel=cancel)
        if fresh is None:
            raise PlanError("The clean was cancelled before anything was removed.", "cancelled")
        path = item["path"]
        if fresh["kind"] == "missing":
            raise PlanError(
                "The plan expired: {0} is gone since it was confirmed. Build a new plan.".format(path),
                "stale",
            )
        if fresh["kind"] == "unreadable":
            raise PlanError(
                "The plan expired: {0} cannot be read anymore. Build a new plan.".format(path),
                "stale",
            )
        if _fingerprint_key(fresh) != plan.fingerprints.get(path):
            raise PlanError(
                "The plan expired: {0} changed since it was confirmed. Build a new plan.".format(path),
                "stale",
            )
        measures[path] = fresh
    return measures


# ── Execution: trash (default) or delete, honest per item ────────────────────


def _trash_layout(trash_target, platform, makedirs):
    """``(files_dir, info_dir)`` for this platform's Trash, created when missing.

    The Trash folders are infrastructure the platform expects, not user data.
    Linux gets the freedesktop ``files``/``info`` pair; macOS the Trash itself.
    """
    if trash_target is None:
        raise CleanError(
            "This platform has no Trash folder the engine can address, "
            "so the item was left in place."
        )
    try:
        if platform == "linux":
            files_dir = os.path.join(trash_target, "files")
            info_dir = os.path.join(trash_target, "info")
            makedirs(files_dir, exist_ok=True)
            makedirs(info_dir, exist_ok=True)
            return files_dir, info_dir
        makedirs(trash_target, exist_ok=True)
        return trash_target, None
    except OSError as exc:
        raise CleanError("The Trash folder cannot be used: {0}".format(exc.strerror or exc)) from exc


def _unique_destination(folder, name, lexists):
    """A name in the Trash that is free; ``name.1``, ``name.2`` … on collision."""
    candidate = os.path.join(folder, name)
    if not lexists(candidate):
        return candidate
    base, extension = os.path.splitext(name)
    for counter in range(1, 1000):
        candidate = os.path.join(folder, "{0}.{1}{2}".format(base, counter, extension))
        if not lexists(candidate):
            return candidate
    raise CleanError("The Trash already holds too many items named {0}.".format(name))


def _write_trashinfo(info_dir, name, original_path, when):
    """The freedesktop ``.trashinfo`` sidecar; written before the move, removed on failure."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(when))
    body = "[Trash Info]\nPath={0}\nDeletionDate={1}\n".format(
        urllib.parse.quote(original_path), stamp
    )
    info_path = os.path.join(info_dir, name + ".trashinfo")
    with open(info_path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return info_path


def _rmtree(root, *, unlink=os.unlink, rmdir=os.rmdir, sleep=time.sleep):
    """Remove a directory tree iteratively, retrying transient errors per entry.

    Returns the ``(path, error)`` pairs that could not be removed — every failure
    is reported, and the caller counts nothing that is still present.
    """
    errors = []
    directories = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                listing = list(iterator)
        except OSError as exc:
            errors.append((current, exc))
            continue
        directories.append(current)
        for child in listing:
            try:
                mode = child.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                errors.append((child.path, exc))
                continue
            if stat_mod.S_ISDIR(mode):
                stack.append(child.path)
                continue
            try:
                retry(lambda path=child.path: unlink(path), sleep=sleep)
            except OSError as exc:
                errors.append((child.path, exc))
    for directory in reversed(directories):
        try:
            retry(lambda path=directory: rmdir(path), sleep=sleep)
        except OSError as exc:
            errors.append((directory, exc))
    return errors


def _discard(path, *, unlink=os.unlink, rmdir=os.rmdir, sleep=time.sleep):
    """Best-effort removal of the engine's own partial copy; errors are ignored."""
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        return
    if stat_mod.S_ISDIR(mode):
        _rmtree(path, unlink=unlink, rmdir=rmdir, sleep=sleep)
    else:
        try:
            unlink(path)
        except OSError:
            pass


def _copy_verified(path, destination, *, copy_tree):
    """Cross-volume copy into the Trash, verified against a fresh walk of the original."""
    copy_tree(path, destination, symlinks=True)
    source_view = fingerprint_path(path)
    copy_view = fingerprint_path(destination)
    if None in (source_view, copy_view):
        raise CleanError("The Trash copy could not be verified.")
    for field in ("bytes", "files", "folders", "symlinks", "special", "unreadable"):
        if source_view[field] != copy_view[field]:
            raise CleanError(
                "The copy in the Trash does not match the original; the original was not removed."
            )


def _remove_original(path, *, unlink, rmdir, sleep):
    """Remove the original after a verified Trash copy; every failure is a CleanError."""
    try:
        mode = os.lstat(path).st_mode
    except OSError as exc:
        raise CleanError("The original cannot be read anymore: {0}".format(exc)) from exc
    if stat_mod.S_ISDIR(mode):
        errors = _rmtree(path, unlink=unlink, rmdir=rmdir, sleep=sleep)
        if errors:
            location, exc = errors[0]
            raise CleanError(
                "{0} entr{1} could not be removed, first: {2}: {3}".format(
                    len(errors), "y" if len(errors) == 1 else "ies", location, exc
                )
            )
    else:
        try:
            retry(lambda: unlink(path), sleep=sleep)
        except OSError as exc:
            raise CleanError("The original could not be removed: {0}".format(exc)) from exc


def _run_trash(
    path,
    *,
    trash_target,
    platform,
    now,
    rename,
    unlink,
    rmdir,
    makedirs,
    lexists,
    sleep,
    copy_tree,
):
    """Move one item into the Trash. Never deletes permanently — a failure raises.

    Two phases. Phase 1 puts a verified copy into the Trash (a same-volume
    rename, or a cross-volume copy that is verified against a fresh walk); if it
    fails, the engine removes only what it created there — never the original.
    Phase 2 (cross-volume only) removes the original; a failure keeps the
    verified copy and its trashinfo, because they may hold the item's only
    remaining bytes.
    """
    files_dir, info_dir = _trash_layout(trash_target, platform, makedirs)
    name = os.path.basename(path.rstrip(os.sep)) or path
    destination = _unique_destination(files_dir, name, lexists)
    info_path = None
    if info_dir is not None:
        info_path = _write_trashinfo(info_dir, os.path.basename(destination), path, now)
    copied = False
    try:
        try:
            retry(lambda: rename(path, destination), sleep=sleep)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            copied = True
            _copy_verified(path, destination, copy_tree=copy_tree)
    except BaseException:
        # Phase 1 failed: the Trash holds at most a partial copy of ours.
        _discard(destination, unlink=unlink, rmdir=rmdir, sleep=sleep)
        if info_path is not None:
            try:
                unlink(info_path)
            except OSError:
                pass
        raise
    if copied:
        try:
            _remove_original(path, unlink=unlink, rmdir=rmdir, sleep=sleep)
        except CleanError as exc:
            raise CleanError(
                "The item was copied to the Trash ({0}) but the original could not be removed "
                "({1}); the verified copy stays in the Trash and nothing was counted.".format(
                    destination, exc
                )
            ) from exc
        if lexists(path):
            raise CleanError("The original is still present after the copy; nothing was counted.")
    if lexists(path):
        raise CleanError("The item is still present after moving it to the Trash.")
    return destination


def _run_delete(path, *, unlink, rmdir, lexists, lstat, sleep):
    """Remove one item permanently — only ever run with the plan's explicit delete mode."""
    try:
        mode = lstat(path).st_mode
    except OSError as exc:
        raise CleanError("The item cannot be read: {0}".format(exc)) from exc
    if stat_mod.S_ISDIR(mode):
        errors = _rmtree(path, unlink=unlink, rmdir=rmdir, sleep=sleep)
        if errors:
            location, exc = errors[0]
            raise CleanError(
                "{0} entr{1} could not be removed, first: {2}: {3}".format(
                    len(errors), "y" if len(errors) == 1 else "ies", location, exc
                )
            )
    else:
        try:
            retry(lambda: unlink(path), sleep=sleep)
        except OSError as exc:
            raise CleanError("The item could not be removed: {0}".format(exc)) from exc
    if lexists(path):
        raise CleanError("The item is still present after deletion.")


def _result_item(item, status, *, code="", reason="", error=None, measure=None, trash_path=None):
    filled = measure or {"bytes": 0, "files": 0, "folders": 0}
    return {
        "entryId": item["entryId"],
        "entryName": item["entryName"],
        "template": item["template"],
        "path": item["path"],
        "source": item.get("source", "catalog"),
        "mode": item["mode"],
        "status": status,
        "code": code,
        "reason": reason,
        "error": error,
        "bytes": filled["bytes"],
        "files": filled["files"],
        "folders": filled["folders"],
        "trashPath": trash_path,
    }


def execute_plan(
    plan,
    measures,
    *,
    env=None,
    platform=None,
    cancel=None,
    progress_callback=None,
    rename=os.rename,
    unlink=os.unlink,
    rmdir=os.rmdir,
    makedirs=os.makedirs,
    lexists=os.path.lexists,
    lstat=os.lstat,
    sleep=time.sleep,
    copy_tree=shutil.copytree,
    clock=time.time,
):
    """Run a verified plan; every item reports ``trashed``/``deleted``/``skipped``/``failed``.

    ``measures`` comes from :func:`verify_plan`; bytes are credited per item only
    after that item is really gone from its original path. A cancel stops before
    the next item; everything still waiting is skipped with that reason. The mode
    is whatever the plan named — a trash failure never becomes a delete.
    """
    clock = time.time if clock is None else clock
    target = platform or platform_id()
    env = os.environ if env is None else env
    items = plan.payload["items"]
    trash_target = trash_dir(env, target)
    started = clock()
    progress = {
        "phase": "cleaning",
        "itemsDone": 0,
        "itemsTotal": len(items),
        "bytesRemoved": 0,
        "currentPath": "",
    }

    def emit():
        if progress_callback is not None:
            progress_callback(dict(progress))

    emit()
    results = []
    counts = {"trashed": 0, "deleted": 0, "skipped": 0, "failed": 0}
    totals = {"bytes": 0, "files": 0, "folders": 0}
    cancelled = False
    now = clock()
    for item in items:
        if not cancelled and _cancelled(cancel):
            cancelled = True
        if item["status"] != "ready":
            results.append(_result_item(item, "skipped", code=item["code"], reason=item["reason"]))
            counts["skipped"] += 1
        elif cancelled:
            results.append(
                _result_item(
                    item, "skipped", code="cancelled",
                    reason="The clean was cancelled before this item.",
                )
            )
            counts["skipped"] += 1
        else:
            path = item["path"]
            measure = measures.get(path)
            progress["currentPath"] = path
            emit()
            try:
                if measure is None:  # defensive: verify_plan measures every ready item
                    raise CleanError("The plan verification did not measure this item.")
                if plan.mode == "trash":
                    destination = _run_trash(
                        path,
                        trash_target=trash_target, platform=target, now=now,
                        rename=rename, unlink=unlink, rmdir=rmdir, makedirs=makedirs,
                        lexists=lexists, sleep=sleep, copy_tree=copy_tree,
                    )
                    results.append(_result_item(item, "trashed", measure=measure, trash_path=destination))
                    counts["trashed"] += 1
                else:
                    _run_delete(
                        path, unlink=unlink, rmdir=rmdir, lexists=lexists, lstat=lstat, sleep=sleep
                    )
                    results.append(_result_item(item, "deleted", measure=measure))
                    counts["deleted"] += 1
                totals["bytes"] += measure["bytes"]
                totals["files"] += measure["files"]
                totals["folders"] += measure["folders"]
            except (OSError, CleanError) as exc:
                results.append(
                    _result_item(item, "failed", error="{0}: {1}".format(type(exc).__name__, exc))
                )
                counts["failed"] += 1
        progress["itemsDone"] += 1
        progress["bytesRemoved"] = totals["bytes"]
        emit()

    finished = clock()
    progress["phase"] = "cancelled" if cancelled else "done"
    return {
        "planId": plan.id,
        "mode": plan.mode,
        "platform": target,
        "startedAt": started,
        "finishedAt": finished,
        "durationMs": int(round((finished - started) * 1000)),
        "cancelled": cancelled,
        "results": results,
        "progress": progress,
        "totals": {
            "items": len(items),
            "trashed": counts["trashed"],
            "deleted": counts["deleted"],
            "skipped": counts["skipped"],
            "failed": counts["failed"],
            "bytes": totals["bytes"],
            "files": totals["files"],
            "folders": totals["folders"],
        },
    }
