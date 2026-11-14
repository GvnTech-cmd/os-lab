"""Resolve tool cache paths: environment, fixed argv probe, catalog default.

Only the catalog's allowlisted probes run, without a shell and with a five-second
timeout. Target paths remain in catalog data; this module contains no defaults.
"""
from __future__ import annotations

import ntpath
import os
import posixpath
import shutil
import subprocess
from dataclasses import dataclass


PROBE_ALLOWLIST = {
    "developers.npm": ("npm", "config", "get", "cache"),
    "developers.pnpm": ("pnpm", "store", "path"),
    "developers.yarn": ("yarn", "cache", "dir"),
    "developers.pip": ("pip3", "cache", "dir"),
    "developers.homebrew": ("brew", "--cache"),
    "developers.go-build": ("go", "env", "GOCACHE"),
    "developers.go-mod": ("go", "env", "GOMODCACHE"),
}
BAD_PREFIXES = ("undefined", "usage error", "error", "unknown", "not found")


@dataclass(frozen=True)
class Resolution:
    path: str | None
    source: str


def valid_path(value, platform, home):
    """One absolute, non-root path; reject diagnostics and multiline output."""
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        return None
    text = value.strip()
    if not text or text.lower().startswith(BAD_PREFIXES):
        return None
    module = ntpath if platform == "windows" else posixpath
    if not module.isabs(text):
        return None
    path = module.normpath(text)
    if path == module.normpath(home) or path == module.dirname(path):
        return None
    return path


def run_probe(argv, env, *, which=shutil.which, run=subprocess.run):
    """Run only a caller-validated argv; failures fall back to the catalog path."""
    executable = which(argv[0], path=env.get("PATH", ""))
    if executable is None:
        return None
    try:
        result = run(
            [executable, *argv[1:]], shell=False, capture_output=True, text=True,
            timeout=5, stdin=subprocess.DEVNULL, check=False, env=dict(env),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    lines = result.stdout.splitlines()
    return lines[0].strip() if len(lines) == 1 else None


def resolve(entry, platform, env, home, default_path, *, probe=run_probe):
    """Resolve one catalog entry; metadata was validated by catalog.load."""
    module = ntpath if platform == "windows" else posixpath
    for name in entry.get("cacheEnv", []):
        value = valid_path(env.get(name), platform, home)
        if value:
            suffix = entry.get("envSuffix", "")
            return Resolution(module.join(value, suffix) if suffix else value, "env:" + name)
    argv = entry.get("probeArgv")
    if argv and tuple(argv) == PROBE_ALLOWLIST.get(entry["id"]):
        value = valid_path(probe(argv, env), platform, home)
        if value:
            return Resolution(value, "probe:" + " ".join(argv))
    return Resolution(default_path, "default" if default_path else "unresolved")
