"""CLNP-20: the per-install catalog overlay — user-defined cleanup entries.

Custom paths join the bookmark system as **catalog entries**, not as a
parallel path list: the overlay stores full detector records under the
``custom`` family (``custom.<slug>`` ids), validated by the shipped catalog's
own ``_check_entry`` rules, merged after the shipped catalog by
:func:`catalog.load`. Every safeguard that applies to shipped entries —
roots containment, protected-root refusal, the owning-app guard, plan
fingerprinting, the permission classification — therefore applies unchanged.

The raw path exists exactly once: as a validated field of the create request.
After that, only ``custom.<slug>`` ids travel through the API.

Conservative defaults for user-defined entries: risk ``low`` only (the user
chose the folder; the machine did not prove anything about it),
``defaultSelected: False`` (never pre-selected in presets),
``needsPrivilege: False`` (no elevated fallback), detector ``paths``. The
path is validated at creation: absolute, an existing folder (never a
symlink), and not a protected root or a system directory — the same
classification the safety guard enforces at plan time, so a custom entry can
never point anywhere the plan would refuse anyway.
"""
from __future__ import annotations

import json
import os
import re
import stat as stat_module
import time

from . import safety
from .catalog import _check_entry
from .paths import state_dir

STORE = "custom-catalog.json"
VERSION = 1
FAMILY = "custom"
MAX_ENTRIES = 50
ALLOWED_RISKS = ("low",)
DEFAULT_IMPACT = "The contents of this folder move to the Trash."
DEFAULT_HINT = "A folder you added to Cleanup Lab."


class CustomCatalogError(ValueError):
    """An overlay entry was refused; ``message`` says exactly why."""


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


def _slug_from(name, taken):
    """A stable ``custom.<slug>`` id derived from the display name."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "folder"
    slug = base[:40].strip("-") or "folder"
    candidate = slug
    index = 2
    while "{0}.{1}".format(FAMILY, candidate) in taken:
        candidate = "{0}-{1}".format(slug, index)
        index += 1
    return "{0}.{1}".format(FAMILY, candidate)


def validate_creation_path(raw, platform, env=None):
    """Canonicalize and classify the user's path; returns the canonical path.

    Refusals are explicit: relative paths, symlinks (a target the user did
    not type), missing paths, non-folders, protected roots and system
    directories. ``env`` exists so tests can point ``~`` at a temp home.
    """
    home = None
    if env is not None:
        home = env.get("HOME") or env.get("USERPROFILE")
    try:
        canonical = safety.canonical(raw, home=home)
    except safety.PathPolicyError as exc:
        raise CustomCatalogError(str(exc)) from exc
    resolved = os.path.realpath(canonical)
    if resolved in safety.protected_roots(home=home):
        raise CustomCatalogError("Refusing to add a protected root ({0}).".format(resolved))
    if resolved in safety.system_roots(platform):
        raise CustomCatalogError("Refusing to add a system directory ({0}).".format(resolved))
    try:
        stat_result = os.lstat(canonical)
    except FileNotFoundError as exc:
        raise CustomCatalogError("The path does not exist: {0}".format(canonical)) from exc
    except OSError as exc:
        raise CustomCatalogError("The path cannot be inspected: {0}".format(exc.strerror or exc)) from exc
    if stat_module.S_ISLNK(stat_result.st_mode):
        raise CustomCatalogError("Symlinks are never added; add the real folder instead.")
    if not stat_module.S_ISDIR(stat_result.st_mode):
        raise CustomCatalogError("Only folders can be added, not files.")
    return canonical


def build_entry(name, path, platform, *, env=None, taken=(), clock=time.time):
    """A full detector record for one custom folder, shaped like a shipped entry."""
    if not isinstance(name, str) or not name.strip():
        raise CustomCatalogError("A display name is required")
    canonical = validate_creation_path(path, platform, env)
    entry_id = _slug_from(name.strip(), set(taken))
    record = {
        "id": entry_id,
        "name": name.strip()[:80],
        "category": "system",
        "risk": "low",
        "hint": DEFAULT_HINT,
        "impact": DEFAULT_IMPACT,
        "defaultSelected": False,
        "needsPrivilege": False,
        "owningProcesses": [],
        "detector": "paths",
        "note": "Added by you on this computer.",
        "cleanable": True,
        "paths": {platform: [canonical]},
    }
    # The shipped validator has the final word — same rules, zero drift.
    checked = _check_entry(record, FAMILY, "<overlay>", 0)
    return dict(checked, createdAt=float(clock()))


def load(env=None, platform=None):
    """The stored overlay entries, validated; corruption yields empty + reason."""
    path = _store_path(env, platform)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return {"entries": [], "error": None}
    except (OSError, ValueError) as exc:
        return {"entries": [], "error": "The custom-catalog store is unreadable: {0}".format(exc)}
    if not isinstance(raw, dict) or raw.get("version") != VERSION or not isinstance(raw.get("entries"), list):
        return {"entries": [], "error": "The custom-catalog store has an unknown shape; defaults apply."}
    entries = []
    try:
        for record in raw["entries"]:
            if not isinstance(record, dict) or not isinstance(record.get("entry"), dict) \
                    or not isinstance(record.get("createdAt"), (int, float)):
                raise CustomCatalogError("each store record carries entry and createdAt")
            checked = _check_entry(record["entry"], FAMILY, "<overlay>", 0)
            entries.append(dict(checked, createdAt=record["createdAt"]))
    except Exception as exc:  # the shipped validator raises CatalogError
        return {"entries": [], "error": "The custom catalog is invalid: {0}".format(exc)}
    return {"entries": sorted(entries, key=lambda item: item["createdAt"]), "error": None}


def save(entries, *, env=None, platform=None):
    """Validate every record, then persist atomically.

    The keys the shipped validator derives or normalizes (``family``,
    ``file``, ``toolName``, ``cacheEnv``, ``envSuffix``, ``probeArgv``) and
    the store's own ``createdAt`` are stripped before writing: they are
    re-derived on load, and some (an empty ``cacheEnv``) cannot round-trip
    through the validator. A stored record carries only what the creator
    chose.
    """
    seen = set()
    for entry in entries:
        if entry["id"] in seen:
            raise CustomCatalogError("duplicate custom id {0}".format(entry["id"]))
        seen.add(entry["id"])
    if len(entries) > MAX_ENTRIES:
        raise CustomCatalogError("at most {0} custom entries are kept".format(MAX_ENTRIES))
    ordered = sorted(entries, key=lambda item: item["createdAt"])
    _write_atomic(_store_path(env, platform), {
        "version": VERSION,
        "entries": [
            {"entry": {key: value for key, value in entry.items()
                       if key not in ("createdAt", "family", "file", "toolName",
                                      "cacheEnv", "envSuffix", "probeArgv")},
             "createdAt": entry["createdAt"]}
            for entry in ordered
        ],
    })
    return {"entries": ordered, "error": None}


def add(name, path, existing, *, platform, env=None, catalog_ids=(), clock=time.time):
    """Create one custom entry; the id avoids shipped ids and existing customs."""
    if len(existing) >= MAX_ENTRIES:
        raise CustomCatalogError("at most {0} custom entries are kept".format(MAX_ENTRIES))
    canonical = validate_creation_path(path, platform, env)
    if any(entry["paths"].get(platform) == [canonical] for entry in existing):
        raise CustomCatalogError("This folder is already in your custom catalog")
    entry = build_entry(name, canonical, platform, env=env, taken=(
        set(catalog_ids) | {item["id"] for item in existing}
    ), clock=clock)
    return save(existing + [entry], env=env, platform=platform)


def remove(entry_id, existing, *, env=None, platform=None):
    """Remove one custom entry by id."""
    remaining = [entry for entry in existing if entry["id"] != entry_id]
    if len(remaining) == len(existing):
        raise CustomCatalogError("No custom entry named {0}".format(entry_id))
    return save(remaining, env=env, platform=platform)


__all__ = [
    "ALLOWED_RISKS", "CustomCatalogError", "add", "build_entry", "load", "remove", "save",
    "validate_creation_path",
]
