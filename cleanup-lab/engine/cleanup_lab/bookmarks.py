"""CLNP-14: the bookmark store — prioritized cleanup items with behaviours.

A bookmark is a **catalog-entry reference**, never a raw path: every clean
result and scan finding already carries its ``entryId``, and the plan → clean
executor accepts ids only. One bookmark per entry, persisted as atomic JSON
in the private state folder (same folder rules as the audit history), with:

* ``priority`` (1 = first) — the order quick cleanup and the auto-clean hook
  build their plans in;
* ``quickClean`` — include in the one-click quick cleanup;
* ``autoCleanHook`` — clean this entry (Trash-only) when the monitor's
  free-space hook fires (CLNP-16); the plan executor, the safety guard and
  the owning-app check still apply, and the run is audited;
* ``sizeAlert`` — notify when the entry's measured size crosses a threshold
  (CLNP-17's ``bookmark-size`` trigger).

Risk classes follow the catalog's own refusal rule: ``high``, ``credentials``
and ``privacy`` entries can be bookmarked (a favourite is a review aid), but
:func:`plan_entry_ids` refuses them for quick cleanup and the hook, with a
reason — the same classes the catalog refuses to pre-select.

Corruption never guesses: an unreadable store yields an empty list plus an
``error`` the UI reports, and a save always validates every record first.
"""
from __future__ import annotations

import json
import os

from .catalog import NEVER_PRESELECTED
from .paths import state_dir

STORE = "bookmarks.json"
VERSION = 1
MAX_BOOKMARKS = 100
DEFAULT_SIZE_ALERT_BYTES = 1024 * 1024 * 1024  # 1 GiB


class BookmarksError(ValueError):
    """The bookmark store cannot be trusted or written."""


def default_size_alert():
    return {"enabled": False, "thresholdBytes": DEFAULT_SIZE_ALERT_BYTES, "armed": True, "lastAlertAt": None}


def default_hook():
    return {"enabled": False, "lastRunAt": None}


def _normalize_alert(value):
    if value is None:
        return default_size_alert()
    if not isinstance(value, dict):
        raise BookmarksError("sizeAlert must be an object")
    unknown = set(value) - {"enabled", "thresholdBytes", "armed", "lastAlertAt"}
    if unknown:
        raise BookmarksError("Unknown sizeAlert key(s): {0}".format(", ".join(sorted(unknown))))
    enabled = value.get("enabled", False)
    threshold = value.get("thresholdBytes", DEFAULT_SIZE_ALERT_BYTES)
    armed = value.get("armed", True)
    last = value.get("lastAlertAt")
    if not isinstance(enabled, bool):
        raise BookmarksError("sizeAlert enabled must be true or false")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or threshold < 0:
        raise BookmarksError("sizeAlert thresholdBytes must be a whole number of bytes")
    if not isinstance(armed, bool):
        raise BookmarksError("sizeAlert armed must be true or false")
    if last is not None and not isinstance(last, (int, float)):
        raise BookmarksError("sizeAlert lastAlertAt must be a timestamp")
    return {"enabled": enabled, "thresholdBytes": threshold, "armed": armed, "lastAlertAt": last}


def _normalize_hook(value):
    if value is None:
        return default_hook()
    if not isinstance(value, dict):
        raise BookmarksError("autoCleanHook must be an object")
    unknown = set(value) - {"enabled", "lastRunAt"}
    if unknown:
        raise BookmarksError("Unknown autoCleanHook key(s): {0}".format(", ".join(sorted(unknown))))
    enabled = value.get("enabled", False)
    last = value.get("lastRunAt")
    if not isinstance(enabled, bool):
        raise BookmarksError("autoCleanHook enabled must be true or false")
    if last is not None and not isinstance(last, (int, float)):
        raise BookmarksError("autoCleanHook lastRunAt must be a timestamp")
    return {"enabled": enabled, "lastRunAt": last}


def validate_bookmark(record, catalog_ids):
    """One record, normalized: a known entry id, a positive priority, flags."""
    if not isinstance(record, dict):
        raise BookmarksError("a bookmark must be an object")
    unknown = set(record) - {"entryId", "createdAt", "priority", "quickClean", "autoCleanHook", "sizeAlert"}
    if unknown:
        raise BookmarksError("Unknown bookmark key(s): {0}".format(", ".join(sorted(unknown))))
    entry_id = record.get("entryId")
    if not isinstance(entry_id, str) or not entry_id:
        raise BookmarksError("entryId must name a catalog entry")
    if catalog_ids is not None and entry_id not in catalog_ids:
        raise BookmarksError("Unknown catalog entry: {0}".format(entry_id))
    created = record.get("createdAt")
    if not isinstance(created, (int, float)):
        raise BookmarksError("createdAt must be a timestamp")
    priority = record.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
        raise BookmarksError("priority must be a whole number from 1")
    quick = record.get("quickClean", False)
    if not isinstance(quick, bool):
        raise BookmarksError("quickClean must be true or false")
    return {
        "entryId": entry_id,
        "createdAt": created,
        "priority": priority,
        "quickClean": quick,
        "autoCleanHook": _normalize_hook(record.get("autoCleanHook")),
        "sizeAlert": _normalize_alert(record.get("sizeAlert")),
    }


def _store_path(env=None, platform=None):
    return os.path.join(state_dir(env, platform), STORE)


def _write_atomic(path, payload):
    folder = os.path.dirname(path)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    temporary = "{0}.tmp-{1}".format(path, os.getpid())
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load(env=None, platform=None):
    """The validated bookmarks, or an empty list plus the reason it cannot be read."""
    path = _store_path(env, platform)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return {"bookmarks": [], "error": None}
    except (OSError, ValueError) as exc:
        return {"bookmarks": [], "error": "The bookmark store is unreadable: {0}".format(exc)}
    if not isinstance(raw, dict) or raw.get("version") != VERSION or not isinstance(raw.get("bookmarks"), list):
        return {"bookmarks": [], "error": "The bookmark store has an unknown shape; defaults apply."}
    bookmarks = []
    seen = set()
    try:
        for record in raw["bookmarks"]:
            validated = validate_bookmark(record, catalog_ids=None)
            if validated["entryId"] in seen:
                raise BookmarksError("entry {0!r} is bookmarked twice".format(validated["entryId"]))
            seen.add(validated["entryId"])
            bookmarks.append(validated)
    except BookmarksError as exc:
        return {"bookmarks": [], "error": "The bookmark store is invalid: {0}".format(exc)}
    return {"bookmarks": sorted(bookmarks, key=lambda item: (item["priority"], item["createdAt"])), "error": None}


def save(bookmarks, *, env=None, platform=None, catalog_ids=None):
    """Validate every record, then persist atomically. Raises BookmarksError."""
    seen = set()
    validated = []
    for record in bookmarks:
        item = validate_bookmark(record, catalog_ids)
        if item["entryId"] in seen:
            raise BookmarksError("entry {0!r} is bookmarked twice".format(item["entryId"]))
        seen.add(item["entryId"])
        validated.append(item)
    if len(validated) > MAX_BOOKMARKS:
        raise BookmarksError("at most {0} bookmarks are kept".format(MAX_BOOKMARKS))
    _write_atomic(_store_path(env, platform), {
        "version": VERSION,
        "bookmarks": sorted(validated, key=lambda item: (item["priority"], item["createdAt"])),
    })
    return {"bookmarks": sorted(validated, key=lambda item: (item["priority"], item["createdAt"])), "error": None}


def add(entry_id, current, *, clock, catalog_ids=None):
    """Bookmark one entry (once per entry) at the end of the priority order."""
    if any(item["entryId"] == entry_id for item in current):
        raise BookmarksError("This entry is already bookmarked")
    priority = max((item["priority"] for item in current), default=0) + 1
    record = validate_bookmark({
        "entryId": entry_id, "createdAt": clock(), "priority": priority,
    }, catalog_ids=catalog_ids)
    return save(current + [record], env=None, catalog_ids=catalog_ids)


def update(entry_id, changes, current, *, catalog_ids=None):
    """Apply typed field changes to one bookmark and persist."""
    updated = False
    records = []
    for item in current:
        if item["entryId"] != entry_id:
            records.append(item)
            continue
        updated = True
        merged = dict(item)
        unknown = set(changes) - {"priority", "quickClean", "autoCleanHook", "sizeAlert"}
        if unknown:
            raise BookmarksError("Unknown change key(s): {0}".format(", ".join(sorted(unknown))))
        if "priority" in changes:
            merged["priority"] = changes["priority"]
        if "quickClean" in changes:
            merged["quickClean"] = changes["quickClean"]
        if "autoCleanHook" in changes:
            merged["autoCleanHook"] = _normalize_hook(changes["autoCleanHook"])
        if "sizeAlert" in changes:
            merged["sizeAlert"] = _normalize_alert(changes["sizeAlert"])
        records.append(merged)
    if not updated:
        raise BookmarksError("No bookmark for {0}".format(entry_id))
    return save(records, env=None, catalog_ids=catalog_ids)


def remove(entry_id, current, *, catalog_ids=None):
    """Remove one bookmark and close the priority gap."""
    remaining = [item for item in current if item["entryId"] != entry_id]
    if len(remaining) == len(current):
        raise BookmarksError("No bookmark for {0}".format(entry_id))
    order = {item["entryId"]: index + 1 for index, item in enumerate(remaining)}
    renumbered = [dict(item, priority=order[item["entryId"]]) for item in remaining]
    return save(renumbered, env=None, catalog_ids=catalog_ids)


def _flagged(item, flag):
    if flag == "quickClean":
        return item["quickClean"]
    if flag == "autoCleanHook":
        return item["autoCleanHook"]["enabled"]
    return False


def plan_entry_ids(bookmarks, catalog_entries, *, flag="quickClean"):
    """Ordered, flag-filtered ids plus honest refusals for the plan builder.

    Returns ``(ids, refusals)``: ``ids`` in priority order (ties by creation
    time) whose flag is set, and ``refusals`` naming every bookmarked entry
    the flag would have included but the risk classes forbid — the same
    ``high``/``credentials``/``privacy`` classes the catalog refuses to
    pre-select. Entries missing from the catalog are refused too, so a stale
    bookmark answers instead of vanishing.
    """
    ids = []
    refusals = []
    risks = {entry["id"]: entry.get("risk") for entry in catalog_entries}
    for item in sorted(bookmarks, key=lambda record: (record["priority"], record["createdAt"])):
        if not _flagged(item, flag):
            continue
        risk = risks.get(item["entryId"])
        if risk is None:
            refusals.append({"entryId": item["entryId"], "reason": "This entry is no longer in the catalog."})
        elif risk in NEVER_PRESELECTED:
            refusals.append({
                "entryId": item["entryId"],
                "reason": "A {0}-risk entry is never cleaned by {1}.".format(
                    risk, "quick cleanup" if flag == "quickClean" else "the automatic hook"),
            })
        else:
            ids.append(item["entryId"])
    return ids, refusals


def evaluate_size_alerts(bookmarks, measurements, now, *, clock=None):
    """The bookmark-size trigger (CLNP-17) as a pure function.

    ``measurements`` maps entry id → measured ``sizeBytes`` (``None`` when the
    entry could not be measured). A bookmark with ``sizeAlert.enabled`` warns
    once on crossing above its threshold and re-arms only after a later
    measurement falls back under it (hysteresis, like the volume trigger).
    Returns ``(updated bookmarks, events)``; events use the monitor's shape
    with ``bookmark`` set instead of ``volume``.
    """
    updated = []
    events = []
    for item in bookmarks:
        alert = item["sizeAlert"]
        record = dict(item)
        if alert["enabled"]:
            size = measurements.get(item["entryId"])
            if isinstance(size, int):
                if alert["armed"] and size > alert["thresholdBytes"]:
                    record["sizeAlert"] = dict(alert, armed=False, lastAlertAt=now)
                    events.append({
                        "at": now, "kind": "warning", "volume": None, "bookmark": item["entryId"],
                        "freeBytes": None, "thresholdBytes": alert["thresholdBytes"],
                        "sizeBytes": size,
                        "message": "The bookmarked item grew above its size threshold.",
                    })
                elif not alert["armed"] and size <= alert["thresholdBytes"]:
                    record["sizeAlert"] = dict(alert, armed=True)
                    events.append({
                        "at": now, "kind": "recovered", "volume": None, "bookmark": item["entryId"],
                        "freeBytes": None, "thresholdBytes": alert["thresholdBytes"],
                        "sizeBytes": size,
                        "message": "The bookmarked item is back under its size threshold.",
                    })
        updated.append(record)
    return updated, events


__all__ = [
    "BookmarksError", "add", "default_hook", "default_size_alert", "evaluate_size_alerts",
    "load", "plan_entry_ids", "remove", "save", "update", "validate_bookmark",
]
