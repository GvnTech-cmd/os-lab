"""The catalog size scan (CLN-03): bounded-parallel, honest, cancellable.

Ports the *behaviour* of Qleaner's ``start_scan`` / ``cancel_scan`` /
``get_scan_results`` and ``get_directory_size`` (see ``cleanup-lab/PARITY.md``),
with the contract of ``cleanup-lab/README.md``:

* **Read-only.** Every size comes from ``lstat``; a symlink is never followed and
  never recursed into — a symlink loop is therefore impossible by construction
  (tests prove it anyway). Sockets, FIFOs and device nodes have nothing to
  reclaim and are not measured.
* **Honest.** A path the engine cannot read is reported in ``unreadable``, not
  swallowed; apparent size and on-disk size are reported separately (the on-disk
  figure is ``null`` where the OS does not expose one); a hard link is counted
  once per scan, keyed by ``(device, inode)``.
* **Cancellable.** ``cancel`` is a :class:`threading.Event` (or any object with
  ``is_set``); the walk polls it between entries, so a cancelled scan returns
  promptly with the partial result and ``"cancelled": true`` — never an error.
* **Bounded parallelism.** One worker per top-level path, at most
  :data:`MAX_WORKERS` threads; the parallel *deep* walk is the native backend's
  job (CLN-21).

The scan returns plain dicts, JSON-ready for ``GET /api/cleanup/jobs/<id>``.
Nothing here writes, deletes or moves anything.
"""
from __future__ import annotations

import os
import stat as stat_mod
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .catalog import load, resolve
from .paths import platform_id

PROGRESS_INTERVAL = 0.12  # seconds between progress callbacks (qrust-scan: 120 ms)
DEFAULT_WORKERS = 4
MAX_WORKERS = 16
CANCEL_EVERY = 128  # listing entries polled between cancel checks inside one walk

_ENTRY_FIELDS = (
    "id",
    "name",
    "family",
    "category",
    "risk",
    "hint",
    "impact",
    "defaultSelected",
    "needsPrivilege",
    "owningProcesses",
    "detector",
)


class ScanError(ValueError):
    """The scan request itself was wrong (unknown entry id, bad worker count)."""


class _Progress:
    """Aggregated, throttled progress shared by the scan's worker threads.

    ``tick`` folds one worker's deltas into the shared counters and calls the
    callback at most every :data:`PROGRESS_INTERVAL` seconds (plus ``final``),
    outside the lock.
    """

    def __init__(self, total, callback=None):
        self._lock = threading.Lock()
        self._callback = callback
        self._last = 0.0
        self.paths_done = 0
        self.total = total
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
            if now - self._last >= PROGRESS_INTERVAL and self._callback is not None:
                self._last = now
                payload = self._snapshot_locked()
        if payload is not None:
            self._callback(payload)

    def finish_path(self):
        with self._lock:
            self.paths_done += 1
            return self._snapshot_locked()

    def final(self):
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        return {
            "phase": "scanning",
            "pathsDone": self.paths_done,
            "pathsTotal": self.total,
            "bytesSeen": self.bytes_seen,
            "filesSeen": self.files_seen,
            "currentPath": self.current,
        }


def _cancelled(cancel):
    return cancel is not None and cancel.is_set()


def _stat_size(stat):
    """(apparent size, on-disk size or ``None``) from one ``lstat`` result."""
    on_disk = getattr(stat, "st_blocks", None)
    return stat.st_size, (on_disk * 512 if on_disk is not None else None)


def _is_unique_file(stat):
    """True for a regular file that should be counted (hard-link aware).

    ``st_ino`` is 0 on filesystems without an inode number, where de-duplication
    would merge unrelated files, so every file counts.
    """
    return stat_mod.S_ISREG(stat.st_mode) and stat.st_ino != 0


class _InodeSet:
    """The ``(device, inode)`` pairs already counted, safe across worker threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._seen = set()

    def claim(self, stat):
        """True the first time this file is seen, False for a later hard link."""
        key = (stat.st_dev, stat.st_ino)
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True


def _claim_inode(seen, stat):
    if not _is_unique_file(stat) or seen is None:
        return True
    claim = getattr(seen, "claim", None)
    if claim is not None:
        return claim(stat)
    key = (stat.st_dev, stat.st_ino)
    if key in seen:
        return False
    seen.add(key)
    return True


def _walk(root, *, cancel, seen_inodes, progress):
    """Depth-first ``lstat`` walk of one top-level directory. Never follows links.

    Returns ``(counters, aborted)``; ``aborted`` is true when the cancel fired.
    """
    counters = {
        "sizeBytes": 0,
        "sizeOnDiskBytes": None,
        "files": 0,
        "folders": 0,
        "unreadable": [],
    }
    has_blocks = False
    poll = 0
    stack = [root]
    while stack:
        current = stack.pop()
        if _cancelled(cancel):
            return counters, True
        try:
            with os.scandir(current) as iterator:
                listing = list(iterator)
        except FileNotFoundError:
            # An entry vanished between listing and stat: reported, not fatal.
            counters["unreadable"].append(current)
            progress.tick(current=current)
            continue
        except OSError:
            counters["unreadable"].append(current)
            progress.tick(current=current)
            continue
        counters["folders"] += 1
        poll += len(listing)
        if poll >= CANCEL_EVERY:
            poll = 0
            if _cancelled(cancel):
                return counters, True
        for child in listing:
            try:
                stat = child.stat(follow_symlinks=False)
            except OSError:
                counters["unreadable"].append(child.path)
                continue
            mode = stat.st_mode
            if stat_mod.S_ISDIR(mode):
                stack.append(child.path)
                continue
            if stat_mod.S_ISLNK(mode):
                # A symlink is a pointer, not data: never followed, never sized.
                continue
            if stat_mod.S_ISREG(mode):
                if not _claim_inode(seen_inodes, stat):
                    continue  # a hard link to a file already counted
                apparent, on_disk = _stat_size(stat)
                counters["sizeBytes"] += apparent
                if on_disk is not None:
                    counters["sizeOnDiskBytes"] = (counters["sizeOnDiskBytes"] or 0) + on_disk
                    has_blocks = True
                counters["files"] += 1
                progress.tick(apparent_delta=apparent, files_delta=1, current=current)
    counters["sizeOnDiskBytes"] = counters["sizeOnDiskBytes"] if has_blocks else None
    return counters, False


def measure_path(path, *, cancel=None, seen_inodes=None, progress=None):
    """Size one top-level path read-only. Returns its report dict.

    The report never raises: an unreadable or vanished path is described, and a
    cancelled walk reports the partial counters with ``measured: false``.
    """
    report = {
        "path": path,
        "reason": "",
        "missing": False,
        "symlink": False,
        "sizeBytes": 0,
        "sizeOnDiskBytes": None,
        "files": 0,
        "folders": 0,
        "unreadable": [],
        "error": None,
        "measured": False,
    }
    try:
        stat = os.lstat(path)
    except FileNotFoundError:
        report["missing"] = True
        report["reason"] = "The path does not exist."
        return report
    except OSError as exc:
        report["reason"] = "The path cannot be read: {0}".format(exc.strerror or exc)
        report["unreadable"] = [path]
        return report
    if stat_mod.S_ISLNK(stat.st_mode):
        report["symlink"] = True
        report["reason"] = "A symlink is never followed; nothing was measured."
        return report
    if not stat_mod.S_ISDIR(stat.st_mode):
        if not stat_mod.S_ISREG(stat.st_mode):
            # Sockets, FIFOs and device nodes have nothing to reclaim.
            report["reason"] = "Not a regular file or folder; nothing was measured."
            return report
        if not _claim_inode(seen_inodes, stat):
            report.update(measured=True)
            report["reason"] = "This file was already counted (hard link)."
            return report
        apparent, on_disk = _stat_size(stat)
        report.update(measured=True, sizeBytes=apparent, files=1)
        if on_disk is not None:
            report["sizeOnDiskBytes"] = on_disk
        return report
    counters, aborted = _walk(path, cancel=cancel, seen_inodes=seen_inodes, progress=progress)
    report.update(counters, measured=not aborted)
    if aborted:
        report["reason"] = "The scan was cancelled while measuring this path."
    return report


def _path_report(template, path, reason, *, missing=False, symlink=False, source="catalog"):
    return {
        "template": template,
        "path": path,
        "reason": reason,
        "source": source,
        "missing": missing,
        "symlink": symlink,
        "sizeBytes": 0,
        "sizeOnDiskBytes": None,
        "files": 0,
        "folders": 0,
        "unreadable": [],
        "error": None,
        "measured": False,
    }


def scan_catalog(
    root,
    entry_ids=None,
    *,
    cancel=None,
    progress_callback=None,
    workers=None,
    env=None,
    platform=None,
    catalog_entries=None,
):
    """Scan the catalog's resolved paths for this operating system.

    ``entry_ids`` restricts the scan to catalog ids that must all exist; ``None``
    scans every entry that names a path on this platform. Returns the JSON-ready
    result dict; a cancelled scan carries the partial per-path reports and
    ``"cancelled": true``. One unreadable path never fails the scan.
    """
    env = os.environ if env is None else env
    target = platform or platform_id()
    started = time.time()
    workers = DEFAULT_WORKERS if workers is None else int(workers)
    if workers < 1 or workers > MAX_WORKERS:
        raise ScanError("workers must be between 1 and {0}".format(MAX_WORKERS))

    entries = catalog_entries if catalog_entries is not None else load(root, env)
    by_id = {entry["id"]: entry for entry in entries}
    if entry_ids is not None:
        unknown = [eid for eid in entry_ids if eid not in by_id]
        if unknown:
            raise ScanError("Unknown detector id(s): {0}".format(", ".join(sorted(unknown))))
        wanted = [by_id[eid] for eid in entry_ids]
    else:
        wanted = entries

    results = []
    pending = []  # reports a worker must fill in
    for entry in wanted:
        result = {field: entry.get(field) for field in _ENTRY_FIELDS}
        result["paths"] = []
        results.append(result)
        if not entry["paths"].get(target):
            result["paths"].append(
                _path_report("", None, "This entry has no path for this system.", missing=True)
            )
            continue
        for item in resolve(entry, target, env):
            if item["path"] is None:
                result["paths"].append(
                    _path_report(item["template"], None, item["reason"], missing=True)
                )
                continue
            report = _path_report(item["template"], item["path"], "", source=item.get("source", "catalog"))
            result["paths"].append(report)
            pending.append(report)

    progress = _Progress(len(pending), progress_callback)
    seen_inodes = _InodeSet()
    cancelled_seen = _cancelled(cancel)

    def run_one(report):
        return measure_path(report["path"], cancel=cancel, seen_inodes=seen_inodes, progress=progress)

    if len(pending) == 1 or workers == 1:
        for report in pending:
            if _cancelled(cancel):
                report["reason"] = "The scan was cancelled before this path was measured."
                continue
            report.update(run_one(report))
            progress.finish_path()
    elif pending:
        with ThreadPoolExecutor(max_workers=min(workers, len(pending))) as pool:
            futures = [(report, pool.submit(run_one, report)) for report in pending]
            for report, future in futures:
                # After a cancel every walk returns promptly with its partial
                # counters, so all futures are collected — nothing is dropped.
                try:
                    report.update(future.result())
                except Exception as exc:  # one broken path never ends the scan
                    report["error"] = "{0}: {1}".format(type(exc).__name__, exc)
                    report["reason"] = "This path could not be measured."
                else:
                    progress.finish_path()
        cancelled_seen = _cancelled(cancel)

    for result in results:
        measured = [p for p in result["paths"] if p["path"]]
        result["sizeBytes"] = sum(p["sizeBytes"] for p in measured)
        disks = [p["sizeOnDiskBytes"] for p in measured if p["sizeOnDiskBytes"] is not None]
        result["sizeOnDiskBytes"] = sum(disks) if disks else None
        result["files"] = sum(p["files"] for p in measured)
        result["folders"] = sum(p["folders"] for p in measured)
        result["unreadable"] = [item for p in measured for item in p["unreadable"]]
        result["missing"] = all(p["missing"] for p in result["paths"]) if result["paths"] else False

    finished = time.time()
    cancelled = cancelled_seen or _cancelled(cancel)
    final_progress = progress.final()
    final_progress["phase"] = "cancelled" if cancelled else "done"
    return {
        "startedAt": started,
        "finishedAt": finished,
        "durationMs": int(round((finished - started) * 1000)),
        "platform": target,
        "cancelled": cancelled,
        "entries": results,
        "progress": final_progress,
        "totals": {
            "sizeBytes": sum(r["sizeBytes"] for r in results),
            "sizeOnDiskBytes": (
                sum(r["sizeOnDiskBytes"] for r in results if r["sizeOnDiskBytes"] is not None)
                if any(r["sizeOnDiskBytes"] is not None for r in results)
                else None
            ),
            "files": sum(r["files"] for r in results),
            "folders": sum(r["folders"] for r in results),
            "paths": sum(len(r["paths"]) for r in results),
            "unreadable": sum(len(r["unreadable"]) for r in results),
            "entries": len(results),
        },
    }
