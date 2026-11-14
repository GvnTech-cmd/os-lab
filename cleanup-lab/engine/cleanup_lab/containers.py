"""CLN-08 typed container prune previews and executions; no shell strings."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass


class ContainerError(ValueError):
    """Unavailable engine, stale preview, or failed command."""


ALLOWED = {
    "docker": {
        "build-cache": (("buildx", "du", "--format=json"), ("builder", "prune", "--force")),
        "dangling-images": (("image", "ls", "--filter", "dangling=true", "--format", "{{json .}}"), ("image", "prune", "--force")),
        "stopped-containers": (("ps", "-a", "--filter", "status=exited", "--format", "{{json .}}"), ("container", "prune", "--force")),
        "dangling-volumes": (("volume", "ls", "--filter", "dangling=true", "--format", "{{json .}}"), ("volume", "prune", "--all", "--force")),
    },
    "podman": {
        "dangling-images": (("image", "ls", "--filter", "dangling=true", "--format", "json"), ("image", "prune", "--force")),
        "stopped-containers": (("ps", "-a", "--filter", "status=exited", "--format", "json"), ("container", "prune", "--force")),
        "dangling-volumes": (("volume", "ls", "--filter", "dangling=true", "--format", "json"), ("volume", "prune", "--all", "--force")),
    },
}


@dataclass(frozen=True)
class Preview:
    engine: str
    executable: str
    action_id: str
    preview_argv: tuple[str, ...]
    prune_argv: tuple[str, ...]
    digest: str
    count: int
    created_at: float
    risk: str


def _run(argv, *, timeout, env, runner=subprocess.run):
    try:
        result = runner(list(argv), shell=False, capture_output=True, text=True,
                        timeout=timeout, stdin=subprocess.DEVNULL, check=False, env=dict(env))
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContainerError("Container command failed: {0}".format(exc)) from exc
    if result.returncode != 0:
        raise ContainerError(result.stderr.strip()[:500] or "Container command returned an error")
    return result.stdout


def _actions(root):
    with open(os.path.join(root, "cleanup-lab", "catalog", "actions", "containers.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != 1 or set(data.get("engines", {})) != {"docker", "podman"}:
        raise ContainerError("Container action catalog is invalid")
    for engine, entries in data["engines"].items():
        if not isinstance(entries, dict):
            raise ContainerError("Container action catalog is invalid")
        if set(entries) != set(ALLOWED[engine]):
            raise ContainerError("Container action catalog is invalid")
        for key, action in entries.items():
            if (action.get("id") != "containers.{0}.{1}".format(engine, key) or
                action.get("risk") not in ("low", "medium", "high") or
                any(not isinstance(action.get(field), list) or not action[field] or
                    any(not isinstance(part, str) or not part for part in action[field])
                    for field in ("preview", "prune")) or
                (tuple(action["preview"]), tuple(action["prune"])) != ALLOWED[engine][key]):
                raise ContainerError("Container action catalog is invalid")
    return data["engines"]


def detect(*, env=None, which=shutil.which, runner=subprocess.run):
    """Prefer responsive Docker; fall back to responsive Podman."""
    env = os.environ if env is None else env
    for name in ("docker", "podman"):
        executable = which(name, path=env.get("PATH", ""))
        if not executable:
            continue
        try:
            _run([executable, "info"], timeout=5, env=env, runner=runner)
        except ContainerError:
            continue
        return name, executable
    return None


def capabilities(root, *, env=None, which=shutil.which, runner=subprocess.run):
    found = detect(env=env, which=which, runner=runner)
    if found is None:
        return {"available": False, "engine": None, "actions": [],
                "reason": "Neither Docker nor Podman is responding."}
    engine, _ = found
    actions = _actions(root)[engine]
    return {"available": True, "engine": engine, "reason": "", "actions": [
        {"id": action["id"], "risk": action["risk"], "defaultSelected": False,
         "pruneArgv": [engine, *action["prune"]]}
        for action in actions.values()
    ]}


def _rows(output):
    if not output.strip():
        return []
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        rows = parsed
    elif isinstance(parsed, dict):
        rows = [parsed]
    else:
        try:
            rows = [json.loads(line) for line in output.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise ContainerError("Container preview returned invalid JSON") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise ContainerError("Container preview returned invalid records")
    return rows


def preview(root, action_id, *, env=None, which=shutil.which, runner=subprocess.run, clock=time.time):
    """Preview a fixed action and fingerprint its candidate list."""
    env = os.environ if env is None else env
    found = detect(env=env, which=which, runner=runner)
    if found is None:
        raise ContainerError("Neither Docker nor Podman is responding")
    engine, executable = found
    actions = {entry["id"]: entry for entry in _actions(root)[engine].values()}
    if action_id not in actions:
        raise ContainerError("Unknown or unavailable container action id")
    action = actions[action_id]
    rows = _rows(_run([executable, *action["preview"]], timeout=10, env=env, runner=runner))
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return Preview(engine, executable, action_id, tuple(action["preview"]),
                   tuple(action["prune"]), digest, len(rows), clock(), action["risk"]), rows


def execute(root, plan, *, env=None, which=shutil.which, runner=subprocess.run, clock=time.time):
    """Re-preview immediately, then run exactly the stored action if unchanged."""
    env = os.environ if env is None else env
    if clock() - plan.created_at > 600:
        raise ContainerError("Container preview expired")
    fresh, _ = preview(root, plan.action_id, env=env, which=which, runner=runner, clock=clock)
    if (fresh.engine != plan.engine or fresh.executable != plan.executable or
        fresh.preview_argv != plan.preview_argv or fresh.prune_argv != plan.prune_argv or
        fresh.digest != plan.digest):
        raise ContainerError("Container candidates changed; preview again")
    if plan.count == 0:
        raise ContainerError("There are no candidates to prune")
    stdout = _run([plan.executable, *plan.prune_argv], timeout=120, env=env, runner=runner)
    return {"actionId": plan.action_id, "engine": plan.engine, "status": "completed",
            "candidateCount": plan.count, "command": [plan.engine, *plan.prune_argv],
            "output": stdout.strip()[:2000], "bytesRemoved": None}
