"""Load the detector catalog: validate it, then resolve paths for one operating system.

The catalog is **data**, not code (``cleanup-lab/README.md``): one JSON file per
family under ``cleanup-lab/catalog``. No engine module may hardcode a target path;
every detector reads its entries from here.

Two things this module refuses to do:

* guess. A template whose environment variable is unset is reported as
  unresolved, with the variable name, instead of silently becoming ``/`` or the
  home folder (rule 4 and rule 6: every skip carries a reason);
* pre-select a risky item. ``defaultSelected`` is rejected for the ``high``,
  ``credentials`` and ``privacy`` classes, so rule 5 is enforced by the loader
  instead of by each page.

Template syntax (see ``cleanup-lab/catalog/README.md``):

``~``                 the user's home folder (``~`` or ``~/...`` only)
``{home}``            the same, inside a longer path
``{cache}``           ``~/Library/Caches``, ``$XDG_CACHE_HOME`` or ``~/.cache``, ``%LOCALAPPDATA%``
``{localappdata}``    ``%LOCALAPPDATA%`` (Windows)
``{appdata}``         ``%APPDATA%`` (Windows)
``{tmp}``             ``$TMPDIR`` / ``%TEMP%``, ``/tmp`` elsewhere
``${NAME}``           environment variable; unresolved when unset
``${NAME:-fallback}`` environment variable, fallback when unset or empty
``%NAME%``            Windows-style environment variable
"""
from __future__ import annotations

import json
import glob
import stat
import ntpath
import os
import shutil
import posixpath
import re

from .paths import home_dir, platform_id
from . import devcache

CATALOG_VERSION = 1
PLATFORMS = ("macos", "linux", "windows")
RISKS = ("low", "medium", "high", "credentials", "privacy")
CATEGORIES = (
    "system",
    "browser",
    "developer",
    "project",
    "container",
    "vm",
    "leftover",
    "package",
    "simulator",
)
DETECTORS = ("paths", "profile-glob", "temp", "spotlight", "artifacts", "signatures", "tool")
NEVER_PRESELECTED = ("high", "credentials", "privacy")
FAMILY_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+$")
SCHEMA_FILE = "schema.json"
ENV_BRACED = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
ENV_PERCENT = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
CONTEXT = re.compile(r"\{([a-z]+)\}")
REQUIRED_ENTRY_KEYS = (
    "id",
    "name",
    "category",
    "risk",
    "hint",
    "impact",
    "defaultSelected",
    "needsPrivilege",
    "paths",
)
OPTIONAL_ENTRY_KEYS = ("owningProcesses", "detector", "note", "toolName", "cleanable", "cacheEnv", "envSuffix", "probeArgv")


class CatalogError(ValueError):
    """The catalog is malformed. The message names the file and the entry."""


def _path_module(platform):
    return ntpath if platform == "windows" else posixpath


def cache_dir(platform, env):
    """The platform's cache root, or ``None`` when it cannot be known."""
    if platform == "macos":
        return posixpath.join(home_dir(env), "Library", "Caches")
    if platform == "windows":
        return env.get("LOCALAPPDATA") or None
    return env.get("XDG_CACHE_HOME") or posixpath.join(home_dir(env), ".cache")


def context(platform, env):
    """Values the ``{...}`` placeholders expand to; ``None`` means "not available"."""
    temp = env.get("TMPDIR") or env.get("TEMP")
    if not temp and platform != "windows":
        temp = "/tmp"
    return {
        "home": home_dir(env),
        "cache": cache_dir(platform, env),
        "localappdata": env.get("LOCALAPPDATA") or None,
        "appdata": env.get("APPDATA") or None,
        "tmp": temp or None,
    }


def expand(template, platform, env=None):
    """Expand one template to ``(path, reason)``.

    ``path`` is ``None`` and ``reason`` names the missing variable or form when
    the template cannot be resolved without guessing.
    """
    env = os.environ if env is None else env
    values = context(platform, env)
    missing = []

    def from_context(match):
        key = match.group(1)
        value = values.get(key)
        if value is None:
            missing.append("{%s} is not available on this system" % key)
            return match.group(0)
        return value

    text = CONTEXT.sub(from_context, template)

    def from_braced(match):
        name, fallback = match.group(1), match.group(2)
        value = env.get(name)
        if value:
            return value
        if fallback:
            return fallback
        missing.append("${%s} is not set" % name)
        return match.group(0)

    def from_percent(match):
        name = match.group(1)
        value = env.get(name)
        if value:
            return value
        missing.append("%%%s%% is not set" % name)
        return match.group(0)

    text = ENV_BRACED.sub(from_braced, text)
    text = ENV_PERCENT.sub(from_percent, text)
    if missing:
        return None, missing[0]
    if text == "~":
        text = values["home"]
    elif text.startswith(("~/", "~\\")):
        text = _path_module(platform).join(values["home"], text[2:])
    elif text.startswith("~"):
        return None, "only '~' and '~/...' are supported"
    module = _path_module(platform)
    if not module.isabs(text):
        return None, "resolves to a relative path"
    return module.normpath(text), ""


def _check_file(document, name):
    if not isinstance(document, dict):
        raise CatalogError("{0}: the file must be a JSON object".format(name))
    unknown = set(document) - {"$schema", "version", "family", "entries"}
    if unknown:
        raise CatalogError("{0}: unknown key(s) {1}".format(name, ", ".join(sorted(unknown))))
    if document.get("version") != CATALOG_VERSION:
        raise CatalogError("{0}: version must be {1}".format(name, CATALOG_VERSION))
    family = document.get("family")
    if not isinstance(family, str) or not FAMILY_PATTERN.match(family):
        raise CatalogError("{0}: family must match {1}".format(name, FAMILY_PATTERN.pattern))
    entries = document.get("entries")
    if not isinstance(entries, list) or not entries:
        raise CatalogError("{0}: entries must be a non-empty list".format(name))
    return family, entries


def _check_entry(entry, family, name, index):
    where = "{0}: entry {1}".format(name, entry.get("id") if isinstance(entry, dict) else index)
    if not isinstance(entry, dict):
        raise CatalogError("{0} must be an object".format(where))
    missing = [key for key in REQUIRED_ENTRY_KEYS if key not in entry]
    if missing:
        raise CatalogError("{0} is missing {1}".format(where, ", ".join(missing)))
    unknown = set(entry) - set(REQUIRED_ENTRY_KEYS) - set(OPTIONAL_ENTRY_KEYS)
    if unknown:
        raise CatalogError("{0} has unknown key(s) {1}".format(where, ", ".join(sorted(unknown))))
    entry_id = entry["id"]
    if not isinstance(entry_id, str) or not ID_PATTERN.match(entry_id):
        raise CatalogError("{0}: id must look like 'family.name'".format(where))
    if not entry_id.startswith(family + "."):
        raise CatalogError("{0}: id must start with '{1}.'".format(where, family))
    for key in ("name", "hint", "impact"):
        if not isinstance(entry[key], str) or not entry[key].strip():
            raise CatalogError("{0}: {1} must be a non-empty string".format(where, key))
    if entry["category"] not in CATEGORIES:
        raise CatalogError("{0}: category must be one of {1}".format(where, ", ".join(CATEGORIES)))
    if entry["risk"] not in RISKS:
        raise CatalogError("{0}: risk must be one of {1}".format(where, ", ".join(RISKS)))
    if not isinstance(entry["defaultSelected"], bool) or not isinstance(entry["needsPrivilege"], bool):
        raise CatalogError("{0}: defaultSelected and needsPrivilege must be booleans".format(where))
    if entry["defaultSelected"] and entry["risk"] in NEVER_PRESELECTED:
        raise CatalogError(
            "{0}: a {1}-risk entry can never be pre-selected".format(where, entry["risk"])
        )
    processes = entry.get("owningProcesses", [])
    if not isinstance(processes, list) or any(
        not isinstance(item, str) or not item.strip() for item in processes
    ):
        raise CatalogError("{0}: owningProcesses must be a list of process names".format(where))
    detector = entry.get("detector", "paths")
    if detector not in DETECTORS:
        raise CatalogError("{0}: detector must be one of {1}".format(where, ", ".join(DETECTORS)))
    note = entry.get("note", "")
    if not isinstance(note, str):
        raise CatalogError("{0}: note must be a string".format(where))
    tool_name = entry.get("toolName")
    if tool_name is not None and (not isinstance(tool_name, str) or not tool_name or "/" in tool_name or "\\" in tool_name):
        raise CatalogError("{0}: toolName must be an executable name, not a path".format(where))
    if not isinstance(entry.get("cleanable", True), bool):
        raise CatalogError("{0}: cleanable must be a boolean".format(where))
    cache_env = entry.get("cacheEnv", [])
    if "cacheEnv" in entry and (not isinstance(cache_env, list) or not cache_env or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        for name in cache_env
    ) or len(set(cache_env)) != len(cache_env)):
        raise CatalogError("{0}: cacheEnv must list distinct environment variable names".format(where))
    suffix = entry.get("envSuffix", "")
    if not isinstance(suffix, str) or suffix and not re.fullmatch(r"[A-Za-z0-9_-]+", suffix):
        raise CatalogError("{0}: envSuffix must be a single relative component".format(where))
    if suffix and not cache_env:
        raise CatalogError("{0}: envSuffix requires cacheEnv".format(where))
    probe = entry.get("probeArgv")
    if probe is not None and (
        not isinstance(probe, list) or tuple(probe) != devcache.PROBE_ALLOWLIST.get(entry_id)
    ):
        raise CatalogError("{0}: probeArgv is not on the fixed probe allowlist".format(where))
    if (cache_env or suffix or probe) and entry.get("detector") != "tool":
        raise CatalogError("{0}: dynamic cache metadata requires detector 'tool'".format(where))
    paths = entry["paths"]
    if not isinstance(paths, dict) or not paths:
        raise CatalogError("{0}: paths must name at least one operating system".format(where))
    unknown_platforms = set(paths) - set(PLATFORMS)
    if unknown_platforms:
        raise CatalogError(
            "{0}: unknown platform(s) {1}".format(where, ", ".join(sorted(unknown_platforms)))
        )
    for platform, templates in paths.items():
        if not isinstance(templates, list) or not templates:
            raise CatalogError("{0}: paths.{1} must be a non-empty list".format(where, platform))
        if any(not isinstance(item, str) or not item.strip() for item in templates):
            raise CatalogError("{0}: paths.{1} must contain non-empty strings".format(where, platform))
    return {
        "id": entry_id,
        "name": entry["name"],
        "category": entry["category"],
        "risk": entry["risk"],
        "hint": entry["hint"],
        "impact": entry["impact"],
        "defaultSelected": entry["defaultSelected"],
        "needsPrivilege": entry["needsPrivilege"],
        "owningProcesses": list(processes),
        "detector": detector,
        "note": note,
        "toolName": tool_name,
        "cleanable": entry.get("cleanable", True),
        "cacheEnv": list(cache_env),
        "envSuffix": suffix,
        "probeArgv": list(probe) if probe else None,
        "family": family,
        "file": name,
        "paths": {platform: list(templates) for platform, templates in paths.items()},
    }


def load(root, env=None):
    """Every catalog entry in file order, validated. Platform filtering is separate."""
    env = os.environ if env is None else env
    folder = os.path.join(root, "cleanup-lab", "catalog")
    try:
        names = sorted(
            name for name in os.listdir(folder) if name.endswith(".json") and name != SCHEMA_FILE
        )
    except OSError as exc:
        raise CatalogError("cannot read {0}: {1}".format(folder, exc.strerror or exc)) from None
    entries, seen = [], {}
    for name in names:
        try:
            with open(os.path.join(folder, name), "r", encoding="utf-8") as handle:
                document = json.load(handle)
        except json.JSONDecodeError as exc:
            raise CatalogError("{0}: invalid JSON ({1})".format(name, exc.msg)) from None
        family, raw_entries = _check_file(document, name)
        for index, raw in enumerate(raw_entries):
            entry = _check_entry(raw, family, name, index)
            if entry["id"] in seen:
                raise CatalogError(
                    "{0}: duplicate id {1} (also in {2})".format(name, entry["id"], seen[entry["id"]])
                )
            seen[entry["id"]] = name
            entries.append(entry)
    return entries


def resolve(entry, platform, env=None):
    """The entry's paths for one platform, each resolved or carrying its reason."""
    env = os.environ if env is None else env
    resolved = []
    detector = entry.get("detector", "paths")
    for template in entry["paths"].get(platform, []):
        if detector == "spotlight" and template.endswith("/*/.Spotlight-V100"):
            parent_template = template[:-len("/*/.Spotlight-V100")]
            parent, reason = expand(parent_template, platform, env)
            if parent is None:
                resolved.append({"template": template, "path": None, "reason": reason, "source": "catalog"})
                continue
            try:
                with os.scandir(parent) as listing:
                    volumes = sorted(item.path for item in listing if item.is_dir())
            except OSError as exc:
                resolved.append({"template": template, "path": None, "reason": str(exc), "source": "catalog"})
                continue
            for volume in volumes:
                index = os.path.join(volume, ".Spotlight-V100")
                if os.path.lexists(index):
                    resolved.append({"template": template, "path": index, "reason": "", "source": "catalog"})
            continue
        path, reason = expand(template, platform, env)
        if detector == "tool" and entry.get("cacheEnv"):
            location = devcache.resolve(entry, platform, env, home_dir(env), path)
            resolved.append({"template": template, "path": location.path,
                             "reason": "" if location.path else reason,
                             "source": location.source})
            continue
        if path is not None and detector == "profile-glob":
            for match in sorted(glob.glob(path)):
                if os.path.lexists(match):
                    resolved.append({"template": template, "path": match, "reason": "", "source": "catalog"})
            continue
        if detector != "temp" or path is None:
            resolved.append({"template": template, "path": path, "reason": reason, "source": "catalog"})
            continue
        try:
            with os.scandir(path) as listing:
                candidates = sorted(listing, key=lambda item: item.name)
        except OSError as exc:
            resolved.append({"template": template, "path": None, "reason": str(exc), "source": "catalog"})
            continue
        for item in candidates:
            if item.name.lower().endswith((".lock", ".sock", ".pid")):
                continue
            try:
                info = item.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode) or not (
                stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_size >= 1024
            ):
                continue
            resolved.append({"template": template, "path": item.path, "reason": "", "source": "catalog"})
    return resolved


def for_platform(entries, platform):
    """Entries that name at least one path on this platform."""
    return [entry for entry in entries if entry["paths"].get(platform)]


def report(root, platform=None, env=None):
    """JSON-ready catalog for one operating system (`GET /api/cleanup/catalog`)."""
    env = os.environ if env is None else env
    target = platform or platform_id()
    entries = for_platform(load(root, env), target)
    return {
        "platform": target,
        "entries": [
            {
                "id": entry["id"],
                "name": entry["name"],
                "family": entry["family"],
                "category": entry["category"],
                "risk": entry["risk"],
                "hint": entry["hint"],
                "impact": entry["impact"],
                "defaultSelected": entry["defaultSelected"],
                "needsPrivilege": entry["needsPrivilege"],
                "owningProcesses": entry["owningProcesses"],
                "detector": entry["detector"],
                "note": entry["note"],
                "toolName": entry["toolName"],
                "toolPresent": (shutil.which(entry["toolName"], path=env.get("PATH", "")) is not None
                                if entry["toolName"] else None),
                "cleanable": entry["cleanable"],
                "paths": resolve(entry, target, env),
            }
            for entry in entries
        ],
    }
