"""CLNP-09: the optional background monitor and its trigger registry.

An opt-in daemon-side checker: the console runs it on a thread (CLNP-10) and
this module owns everything the thread needs as pure, testable functions —
the trigger registry, the config schema, the evaluation, and the private
state store (atomic JSON in :mod:`cleanup_lab.paths` state folder, like the
audit history's folder rules).

The first trigger is ``disk-free-space``: per-volume absolute and percent
floors chosen from the CLN-28 volume inventory, with **re-arm hysteresis**
(warning fires once on crossing below the threshold; it re-arms only after
free space recovers above the threshold plus a margin) and a cooldown so a
flapping volume cannot spam. More triggers join the registry as registry
entries — the runner never grows a second scheduler.

The monitor is read-only: it probes volumes exactly like CLN-28 does and
never cleans anything. Its warnings surface on the dashboard with a link
into the existing plan → confirm → clean flow.

Evaluation is a pure function over ``(config, previous state, volume
snapshot, now)``; the clock and the volume source are injectable so tests
never touch a real disk. An unreadable volume yields a per-volume error
event, never a runner failure.
"""
from __future__ import annotations

import json
import os
import time

from .paths import state_dir

STORE = "monitor.json"
VERSION = 1
#: Bounds that keep a bad config from doing damage.
MIN_INTERVAL = 60
MAX_INTERVAL = 3600
MAX_VOLUMES = 8
MAX_EVENTS = 100
#: Re-arm margin: free space must recover this far above the threshold before
#: the next crossing warns again (fraction of the volume's capacity).
REARM_MARGIN = 0.01
#: Default warning floor: the home volume, below 10 % free or 10 GiB free.
DEFAULT_MIN_FREE_BYTES = 10 * 1024 * 1024 * 1024
DEFAULT_MIN_FREE_PERCENT = 10.0
DEFAULT_INTERVAL = 300
#: One warning per volume per cooldown window, even after re-arm.
DEFAULT_COOLDOWN = 3600

KINDS = ("warning", "recovered", "error")


class MonitorConfigError(ValueError):
    """A config the schema refused; ``message`` says exactly what is wrong."""


def default_config():
    """Off by default; the dashboard prefills these values for activation."""
    return {
        "enabled": False,
        "intervalSeconds": DEFAULT_INTERVAL,
        "cooldownSeconds": DEFAULT_COOLDOWN,
        "volumes": [{
            "mountPoint": "",  # "" means "the volume holding the home folder"
            "minFreeBytes": DEFAULT_MIN_FREE_BYTES,
            "minFreePercent": DEFAULT_MIN_FREE_PERCENT,
            "enabled": True,
        }],
    }


def validate_config(config):
    """The engine-side schema every config passes before it is stored.

    The console validates the request first; this re-validation runs on load
    too, so a hand-edited store can never arm a nonsense monitor.
    """
    if not isinstance(config, dict):
        raise MonitorConfigError("The monitor config must be an object")
    unknown = set(config) - {"enabled", "intervalSeconds", "cooldownSeconds", "volumes"}
    if unknown:
        raise MonitorConfigError("Unknown key(s): {0}".format(", ".join(sorted(unknown))))
    enabled = config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise MonitorConfigError("enabled must be true or false")
    interval = config.get("intervalSeconds", DEFAULT_INTERVAL)
    if not isinstance(interval, int) or isinstance(interval, bool) or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise MonitorConfigError("intervalSeconds must be between {0} and {1}".format(MIN_INTERVAL, MAX_INTERVAL))
    cooldown = config.get("cooldownSeconds", DEFAULT_COOLDOWN)
    if not isinstance(cooldown, int) or isinstance(cooldown, bool) or not 0 <= cooldown <= 86400:
        raise MonitorConfigError("cooldownSeconds must be between 0 and 86400")
    volumes = config.get("volumes")
    if not isinstance(volumes, list) or not volumes or len(volumes) > MAX_VOLUMES:
        raise MonitorConfigError("volumes must list between 1 and {0} volumes".format(MAX_VOLUMES))
    seen = set()
    for volume in volumes:
        if not isinstance(volume, dict):
            raise MonitorConfigError("each volume must be an object")
        unknown = set(volume) - {"mountPoint", "minFreeBytes", "minFreePercent", "enabled"}
        if unknown:
            raise MonitorConfigError("Unknown volume key(s): {0}".format(", ".join(sorted(unknown))))
        mount = volume.get("mountPoint", "")
        if not isinstance(mount, str):
            raise MonitorConfigError("mountPoint must be a string")
        if mount in seen:
            raise MonitorConfigError("mountPoint {0!r} is listed twice".format(mount))
        seen.add(mount)
        floor = volume.get("minFreeBytes", DEFAULT_MIN_FREE_BYTES)
        if not isinstance(floor, int) or isinstance(floor, bool) or floor < 0:
            raise MonitorConfigError("minFreeBytes must be a whole number of bytes")
        percent = volume.get("minFreePercent", DEFAULT_MIN_FREE_PERCENT)
        if not isinstance(percent, (int, float)) or isinstance(percent, bool) or not 0 <= percent <= 100:
            raise MonitorConfigError("minFreePercent must be between 0 and 100")
        volume_enabled = volume.get("enabled", True)
        if not isinstance(volume_enabled, bool):
            raise MonitorConfigError("volume enabled must be true or false")
    return {
        "enabled": enabled,
        "intervalSeconds": interval,
        "cooldownSeconds": cooldown,
        "volumes": [
            {
                "mountPoint": volume.get("mountPoint", ""),
                "minFreeBytes": volume.get("minFreeBytes", DEFAULT_MIN_FREE_BYTES),
                "minFreePercent": volume.get("minFreePercent", DEFAULT_MIN_FREE_PERCENT),
                "enabled": volume.get("enabled", True),
            }
            for volume in volumes
        ],
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
    """The persisted config + state, validated; corruption disables, never guesses."""
    path = _store_path(env, platform)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return {"config": default_config(), "state": _fresh_state(), "configError": None}
    except (OSError, ValueError) as exc:
        return {"config": default_config(), "state": _fresh_state(),
                "configError": "The monitor store is unreadable: {0}".format(exc)}
    if not isinstance(raw, dict) or raw.get("version") != VERSION:
        return {"config": default_config(), "state": _fresh_state(),
                "configError": "The monitor store has an unknown version; defaults apply."}
    try:
        config = validate_config(raw.get("config"))
    except MonitorConfigError as exc:
        return {"config": default_config(), "state": _fresh_state(),
                "configError": "The monitor config is invalid: {0}".format(exc)}
    state = raw.get("state") if isinstance(raw.get("state"), dict) else {}
    return {"config": config, "state": _clean_state(state), "configError": None}


def save_config(config, *, env=None, platform=None):
    """Validate, persist, and return the resulting store payload."""
    validated = validate_config(config)
    loaded = load(env, platform)
    loaded["config"] = validated
    _write_atomic(_store_path(env, platform), {
        "version": VERSION, "config": validated, "state": loaded["state"],
    })
    return loaded


def _fresh_state():
    return {"volumes": {}, "events": [], "lastEvaluationAt": None, "lastError": None}


def _clean_state(state):
    """Keep only the shape the evaluator produces; drop anything else."""
    volumes = state.get("volumes") if isinstance(state.get("volumes"), dict) else {}
    events = state.get("events") if isinstance(state.get("events"), list) else []
    cleaned = []
    for event in events[-MAX_EVENTS:]:
        if isinstance(event, dict) and event.get("kind") in KINDS and isinstance(event.get("at"), (int, float)):
            cleaned.append({
                "at": event["at"], "kind": event["kind"],
                "volume": event.get("volume") if isinstance(event.get("volume"), str) else None,
                # CLNP-17: bookmark-size events carry the entry id instead of a volume.
                "bookmark": event.get("bookmark") if isinstance(event.get("bookmark"), str) else None,
                "freeBytes": event.get("freeBytes") if isinstance(event.get("freeBytes"), int) else None,
                "thresholdBytes": event.get("thresholdBytes") if isinstance(event.get("thresholdBytes"), int) else None,
                "sizeBytes": event.get("sizeBytes") if isinstance(event.get("sizeBytes"), int) else None,
                "message": event.get("message") if isinstance(event.get("message"), str) else "",
            })
    return {
        "volumes": {str(key): value for key, value in volumes.items() if isinstance(value, dict)},
        "events": cleaned,
        "lastEvaluationAt": state.get("lastEvaluationAt") if isinstance(state.get("lastEvaluationAt"), (int, float)) else None,
        "lastError": state.get("lastError") if isinstance(state.get("lastError"), str) else None,
    }


def _append_event(events, event):
    events.append(event)
    return events[-MAX_EVENTS:]


def _volume_key(mount):
    return "volumes:{0}".format(mount)


def evaluate(config, state, volumes, now, *, cooldown=None):
    """One pure evaluation: returns the new state and the events it produced.

    ``volumes`` is the CLN-28 snapshot (``inventory()["volumes"]``). A volume
    entry with ``mountPoint: ""`` means the home volume. Volumes that vanished
    since the config was written record an error event; a volume the snapshot
    could not measure does the same, without failing the evaluation.
    """
    cooldown = config.get("cooldownSeconds", DEFAULT_COOLDOWN) if cooldown is None else cooldown
    volume_state = dict(state.get("volumes", {}))
    events = list(state.get("events", []))
    by_mount = {volume["mountPoint"]: volume for volume in volumes if volume.get("mountPoint")}
    home_volume = next((volume for volume in volumes if volume.get("isHome")), None)
    for entry in config["volumes"]:
        if not entry["enabled"]:
            continue
        mount = entry["mountPoint"] or (home_volume or {}).get("mountPoint")
        if not mount:
            events = _append_event(events, {
                "at": now, "kind": "error", "volume": entry["mountPoint"] or None,
                "freeBytes": None, "thresholdBytes": None,
                "message": "The home volume is not in the inventory; nothing was checked.",
            })
            continue
        volume = by_mount.get(mount)
        if volume is None:
            events = _append_event(events, {
                "at": now, "kind": "error", "volume": mount,
                "freeBytes": None, "thresholdBytes": None,
                "message": "The configured volume is not mounted; nothing was checked.",
            })
            continue
        free = volume.get("freeBytes")
        total = volume.get("totalBytes")
        if volume.get("error") or not isinstance(free, int) or not isinstance(total, int) or total <= 0:
            events = _append_event(events, {
                "at": now, "kind": "error", "volume": mount,
                "freeBytes": free if isinstance(free, int) else None, "thresholdBytes": None,
                "message": volume.get("error") or "The volume could not be measured.",
            })
            continue
        threshold = max(entry["minFreeBytes"], int(round(total * entry["minFreePercent"] / 100.0)))
        margin = int(round(total * REARM_MARGIN))
        key = _volume_key(mount)
        previous = volume_state.get(key) or {}
        armed = previous.get("armed", True)
        last_warning = previous.get("lastWarningAt")
        if free < threshold and armed:
            on_cooldown = last_warning is not None and now - last_warning < cooldown
            volume_state[key] = {"armed": False, "lastWarningAt": last_warning if on_cooldown else now,
                                 "state": "warning"}
            if not on_cooldown:
                events = _append_event(events, {
                    "at": now, "kind": "warning", "volume": mount,
                    "freeBytes": free, "thresholdBytes": threshold,
                    "message": "Free space is below the warning threshold.",
                })
        elif free >= threshold + margin and not armed:
            volume_state[key] = {"armed": True, "lastWarningAt": last_warning, "state": "ok"}
            events = _append_event(events, {
                "at": now, "kind": "recovered", "volume": mount,
                "freeBytes": free, "thresholdBytes": threshold,
                "message": "Free space recovered above the threshold.",
            })
        else:
            volume_state[key] = {"armed": armed, "lastWarningAt": last_warning,
                                 "state": "warning" if not armed else "ok"}
    return {
        "volumes": volume_state,
        "events": events,
        "lastEvaluationAt": now,
        "lastError": None,
    }


def active_warnings(state):
    """The volumes currently below their threshold, newest first."""
    warnings = []
    for key, volume in state.get("volumes", {}).items():
        if volume.get("state") == "warning":
            warnings.append({"volume": key[len("volumes:"):] if key.startswith("volumes:") else key,
                             "lastWarningAt": volume.get("lastWarningAt")})
    return warnings


def run_evaluation(*, env=None, platform=None, inventory=None, clock=time.time):
    """Load, probe volumes, evaluate, persist — what one runner tick does.

    Returns ``newEvents``: only the events this tick produced, so the console
    runner can react to a fresh crossing (the auto-clean hook) instead of the
    whole history.
    """
    loaded = load(env, platform)
    if not loaded["config"]["enabled"]:
        return dict(loaded, evaluated=False, newEvents=[])
    volumes = (inventory or _inventory)()["volumes"]
    before = len(loaded["state"]["events"])
    state = evaluate(loaded["config"], loaded["state"], volumes, clock())
    _write_atomic(_store_path(env, platform), {
        "version": VERSION, "config": loaded["config"], "state": state,
    })
    return {"config": loaded["config"], "state": state,
            "configError": loaded["configError"], "evaluated": True,
            "newEvents": state["events"][before:]}


def _inventory():
    from . import volumes

    return volumes.inventory()


def append_events(events, *, env=None, platform=None):
    """Persist foreign events (e.g. CLNP-17's bookmark-size alerts) into the store."""
    if not events:
        return
    loaded = load(env, platform)
    state = loaded["state"]
    for event in events:
        state["events"] = _append_event(state["events"], event)
    _write_atomic(_store_path(env, platform), {
        "version": VERSION, "config": loaded["config"], "state": state,
    })


def status(*, env=None, platform=None, inventory=None, clock=time.time):
    """The typed ``GET /api/cleanup/monitor`` payload (read-only)."""
    loaded = load(env, platform)
    if loaded["config"]["enabled"]:
        try:
            snapshot = (inventory or _inventory)()
        except Exception as exc:  # a failed probe is reported, not raised
            snapshot = {"volumes": [], "error": str(exc)}
    else:
        snapshot = {"volumes": []}
    volumes = {}
    for volume in snapshot.get("volumes", []):
        mount = volume.get("mountPoint")
        if mount:
            volumes[mount] = volume
    # Resolve each configured mount against the live inventory for display.
    home_volume = next((volume for volume in snapshot.get("volumes", []) if volume.get("isHome")), None)
    resolved = []
    for entry in loaded["config"]["volumes"]:
        mount = entry["mountPoint"] or (home_volume or {}).get("mountPoint") or entry["mountPoint"]
        live = volumes.get(mount)
        resolved.append(dict(entry, mountPoint=mount, volume=None if live is None else {
            "freeBytes": live.get("freeBytes"), "totalBytes": live.get("totalBytes"),
            "usage": live.get("usage"), "kind": live.get("kind"),
        }))
    return {
        "enabled": loaded["config"]["enabled"],
        "intervalSeconds": loaded["config"]["intervalSeconds"],
        "cooldownSeconds": loaded["config"]["cooldownSeconds"],
        "volumes": resolved,
        "state": loaded["state"],
        "activeWarnings": active_warnings(loaded["state"]),
        "configError": loaded["configError"],
        "checkedAt": clock(),
    }


__all__ = [
    "MonitorConfigError", "active_warnings", "append_events", "default_config", "evaluate",
    "load", "run_evaluation", "save_config", "status", "validate_config",
]
