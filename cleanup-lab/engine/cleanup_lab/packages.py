"""Read-only package review candidates and typed uninstall previews (CLN-11).

Homebrew's dry-run autoremove identifies unneeded dependencies. Pip's
`--not-required` and RubyGems' installed list identify packages for review,
not proven orphans. No uninstall command is executed by this module or API.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from .paths import platform_id

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+@/-]*$")
PLAIN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+@-]*$")


class PackageError(ValueError):
    """An inventory command failed or returned invalid data."""


def _run(executable, args, env, runner):
    try:
        result = runner([executable, *args], shell=False, capture_output=True, text=True,
                        timeout=15, stdin=subprocess.DEVNULL, check=False, env=dict(env))
    except (OSError, subprocess.SubprocessError) as exc:
        raise PackageError(str(exc)) from exc
    if result.returncode != 0:
        raise PackageError(result.stderr.strip()[:400] or "inventory command failed")
    return result.stdout


def _brew(stdout, executable):
    """Accept only standalone formula names from `brew autoremove --dry-run`."""
    items = []
    for line in stdout.splitlines():
        name = line.strip()
        if not NAME.fullmatch(name) or name.lower() in ("would", "uninstall", "formulae", "formula"):
            continue
        items.append({"id": "packages.homebrew-orphans", "name": name,
                      "status": "unneeded-dependency", "source": "brew autoremove --dry-run",
                      "uninstallArgv": [executable, "uninstall", "--formula", name],
                      "risk": "medium", "reportOnly": True})
    return items


def _pip(stdout, executable):
    try:
        rows = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise PackageError("pip returned invalid JSON") from exc
    if not isinstance(rows, list):
        raise PackageError("pip returned an invalid package list")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not isinstance(name, str) or not PLAIN_NAME.fullmatch(name):
            continue
        items.append({"id": "packages.pip-global", "name": name,
                      "version": row.get("version") if isinstance(row.get("version"), str) else None,
                      "status": "top-level-review", "source": "pip list --not-required",
                      "uninstallArgv": [executable, "uninstall", name],
                      "risk": "medium", "reportOnly": True})
    return items


def _gems(stdout, executable):
    items = []
    for line in stdout.splitlines():
        name = line.strip()
        if not PLAIN_NAME.fullmatch(name):
            continue
        items.append({"id": "packages.gem-global", "name": name,
                      "status": "installed-review", "source": "gem list --local --no-versions",
                      "uninstallArgv": [executable, "uninstall", name],
                      "risk": "medium", "reportOnly": True})
    return items


def inventory(*, env=None, platform=None, which=shutil.which, runner=subprocess.run):
    """Inventory three package managers and return exact argv suggestions only."""
    env = os.environ if env is None else env
    platform = platform or platform_id()
    commands = [
        ("brew", ("autoremove", "--dry-run"), _brew),
        ("pip3", ("list", "--not-required", "--format=json"), _pip),
        ("gem", ("list", "--local", "--no-versions"), _gems),
    ]
    items, sources, errors = [], [], []
    for name, argv, parser in commands:
        if name == "brew" and platform not in ("macos", "linux"):
            continue
        executable = which(name, path=env.get("PATH", ""))
        if not executable:
            continue
        try:
            output = _run(executable, argv, env, runner)
            parsed = parser(output, executable)
        except PackageError as exc:
            errors.append({"tool": name, "error": str(exc)})
            continue
        sources.append({"tool": name, "path": executable})
        items.extend(parsed)
    return {"available": bool(sources), "items": items, "sources": sources,
            "errors": errors, "note": "Pip and gem entries are review candidates, not proven orphans."}
