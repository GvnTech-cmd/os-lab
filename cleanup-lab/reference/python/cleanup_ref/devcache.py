"""Where each developer tool really keeps its cache (CLN-25).

Hard-coded default paths are wrong as soon as a user sets ``npm_config_cache``,
``GOMODCACHE`` or ``PIP_CACHE_DIR``, or runs the tool on another OS. The tool
itself knows. Resolution order, per kind:

1. the tool's own environment variable, if set;
2. the tool's answer to a **fixed argv** probe (``npm config get cache``,
   ``go env GOCACHE`` …) — only when the binary is on ``PATH``; run without a
   shell, with a timeout, and validated (one absolute path, no error text);
3. the documented per-OS default.

Ported from the maintainer's private cleanup app, which probed first and read
the environment second for some tools, and only knew macOS defaults. Toolchains
(rustup, cargo home) are a separate ``toolchain`` class: they may be relocated
(CLN-27) but are never offered as cache to delete.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

# Templates use {home}, {cache} (XDG cache / Library/Caches / %LOCALAPPDATA%),
# {localappdata} and {gopath}.

@dataclass(frozen=True)
class CacheKind:
    id: str
    title: str
    #: "cache" (regenerable, may be cleaned) or "toolchain" (relocate only).
    risk_class: str
    env_vars: tuple[str, ...] = ()
    #: Appended to the env var's value (e.g. CARGO_HOME → CARGO_HOME/registry).
    env_suffix: str = ""
    probe: tuple[str, ...] | None = None
    defaults: Mapping[str, str] | None = None  # os key: "darwin" | "linux" | "win32"


KINDS: tuple[CacheKind, ...] = (
    CacheKind("npm", "npm cache", "cache", ("npm_config_cache", "NPM_CONFIG_CACHE"), "",
              ("npm", "config", "get", "cache"),
              {"darwin": "{home}/.npm", "linux": "{home}/.npm", "win32": "{localappdata}/npm-cache"}),
    CacheKind("pnpm", "pnpm store", "cache", ("PNPM_STORE_DIR",), "", ("pnpm", "store", "path"),
              {"darwin": "{home}/Library/pnpm/store", "linux": "{home}/.local/share/pnpm/store",
               "win32": "{localappdata}/pnpm/store"}),
    CacheKind("yarn", "Yarn cache", "cache", ("YARN_CACHE_FOLDER",), "", ("yarn", "cache", "dir"),
              {"darwin": "{home}/Library/Caches/Yarn", "linux": "{cache}/yarn", "win32": "{localappdata}/Yarn/Cache"}),
    CacheKind("bun", "Bun install cache", "cache", ("BUN_INSTALL_CACHE_DIR",), "", None,
              {"darwin": "{home}/.bun/install/cache", "linux": "{home}/.bun/install/cache",
               "win32": "{home}/.bun/install/cache"}),
    CacheKind("pip", "pip cache", "cache", ("PIP_CACHE_DIR",), "", ("pip3", "cache", "dir"),
              {"darwin": "{home}/Library/Caches/pip", "linux": "{cache}/pip", "win32": "{localappdata}/pip/Cache"}),
    CacheKind("homebrew", "Homebrew downloads", "cache", ("HOMEBREW_CACHE",), "", ("brew", "--cache"),
              {"darwin": "{home}/Library/Caches/Homebrew", "linux": "{cache}/Homebrew"}),
    CacheKind("go_build", "Go build cache", "cache", ("GOCACHE",), "", ("go", "env", "GOCACHE"),
              {"darwin": "{home}/Library/Caches/go-build", "linux": "{cache}/go-build", "win32": "{localappdata}/go-build"}),
    CacheKind("go_mod", "Go module cache", "cache", ("GOMODCACHE",), "", ("go", "env", "GOMODCACHE"),
              {"darwin": "{gopath}/pkg/mod", "linux": "{gopath}/pkg/mod", "win32": "{gopath}/pkg/mod"}),
    CacheKind("cargo_registry", "Cargo registry", "cache", ("CARGO_HOME",), "/registry", None,
              {"darwin": "{home}/.cargo/registry", "linux": "{home}/.cargo/registry", "win32": "{home}/.cargo/registry"}),
    CacheKind("gradle", "Gradle caches", "cache", ("GRADLE_USER_HOME",), "/caches", None,
              {"darwin": "{home}/.gradle/caches", "linux": "{home}/.gradle/caches", "win32": "{home}/.gradle/caches"}),
    CacheKind("playwright", "Playwright browsers", "cache", ("PLAYWRIGHT_BROWSERS_PATH",), "", None,
              {"darwin": "{home}/Library/Caches/ms-playwright", "linux": "{cache}/ms-playwright",
               "win32": "{localappdata}/ms-playwright"}),
    CacheKind("deno", "Deno cache", "cache", ("DENO_DIR",), "", None,
              {"darwin": "{home}/Library/Caches/deno", "linux": "{cache}/deno", "win32": "{localappdata}/deno"}),
    CacheKind("cocoapods", "CocoaPods cache", "cache", ("CP_CACHE_DIR",), "", None,
              {"darwin": "{home}/Library/Caches/CocoaPods"}),
    CacheKind("rustup", "rustup toolchains", "toolchain", ("RUSTUP_HOME",), "", None,
              {"darwin": "{home}/.rustup", "linux": "{home}/.rustup", "win32": "{home}/.rustup"}),
    CacheKind("cargo_home", "Cargo home", "toolchain", ("CARGO_HOME",), "", None,
              {"darwin": "{home}/.cargo", "linux": "{home}/.cargo", "win32": "{home}/.cargo"}),
)

KINDS_BY_ID = {k.id: k for k in KINDS}

#: Text some tools print instead of a path (compared against the start of the line).
_NOT_A_PATH = ("undefined", "usage error", "error", "unknown", "not found")


@dataclass(frozen=True)
class Resolution:
    kind_id: str
    path: str | None
    #: "env:NAME", "probe:<argv>", "default" or "unsupported".
    source: str


ProbeRunner = Callable[[Sequence[str]], "str | None"]
Which = Callable[[str], "str | None"]


def run_probe(argv: Sequence[str], *, timeout: float = 5.0) -> str | None:
    """Run a fixed argv (never through a shell) and return its first stdout line, or ``None``."""
    exe = shutil.which(argv[0])
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, *argv[1:]], shell=False, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return lines[0] if len(lines) == 1 else None


def _os_key(os_name: str) -> str:
    if os_name.startswith("win"):
        return "win32"
    if os_name == "darwin":
        return "darwin"
    return "linux"


def _template_vars(os_name: str, env: Mapping[str, str], home: str) -> dict[str, str]:
    key = _os_key(os_name)
    localappdata = env.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    if key == "darwin":
        cache = os.path.join(home, "Library", "Caches")
    elif key == "win32":
        cache = localappdata
    else:
        cache = env.get("XDG_CACHE_HOME") or os.path.join(home, ".cache")
    gopath = (env.get("GOPATH") or os.path.join(home, "go")).split(os.pathsep)[0]
    return {"home": home, "cache": cache, "localappdata": localappdata, "gopath": gopath}


def _valid_probe_output(text: str | None, home: str) -> str | None:
    if not text:
        return None
    if text.lower().startswith(_NOT_A_PATH):
        return None
    if text.startswith("~"):
        text = home + text[1:]
    return os.path.normpath(text) if os.path.isabs(text) else None


def resolve(
    kind: CacheKind,
    *,
    env: Mapping[str, str] | None = None,
    os_name: str = sys.platform,
    home: str | None = None,
    probe: ProbeRunner = run_probe,
    which: Which = shutil.which,
) -> Resolution:
    """Resolve one cache kind. Pure apart from the injected ``probe`` and ``which``."""
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    for var in kind.env_vars:
        value = env.get(var, "").strip()
        if value and os.path.isabs(os.path.expanduser(value)):
            return Resolution(kind.id, os.path.normpath(os.path.expanduser(value) + kind.env_suffix), f"env:{var}")
    if kind.probe is not None and which(kind.probe[0]) is not None:
        path = _valid_probe_output(probe(kind.probe), home)
        if path is not None:
            return Resolution(kind.id, path, "probe:" + " ".join(kind.probe))
    template = (kind.defaults or {}).get(_os_key(os_name))
    if template is None:
        return Resolution(kind.id, None, "unsupported")
    path = template.format(**_template_vars(os_name, env, home))
    return Resolution(kind.id, os.path.normpath(path), "default")


def resolve_all(**kwargs) -> list[Resolution]:
    return [resolve(k, **kwargs) for k in KINDS]
