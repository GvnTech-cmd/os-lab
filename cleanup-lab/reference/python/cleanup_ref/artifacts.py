"""Project build-artifact signatures, verified by marker files (CLN-24).

A directory called ``target`` is not necessarily a Rust build directory and a
directory called ``build`` is very often somebody's work. A name match is a
*hint*; this module only reports a directory as a regenerable artifact when the
project around it proves it:

* ``node_modules`` next to a ``package.json``;
* ``target`` next to a ``Cargo.toml`` (Rust) or a ``pom.xml`` (Maven);
* ``.venv`` / ``venv`` that contain a ``pyvenv.cfg``;
* any directory that carries a valid ``CACHEDIR.TAG``
  (https://bford.info/cachedir/), which is how pytest, mypy, ruff, Cargo and
  others mark caches on purpose.

The scan engine this came from matched ``target`` and ``venv`` by name alone;
one of its ports already required ``Cargo.toml`` for ``target``. Both lessons
are kept here.

Everything is read-only: ``os.scandir`` / ``lstat`` only, symlinks are never
followed, a matched directory is not descended into, and unreadable
directories are skipped and counted. Sizing is the scan job's work (CLN-03 /
CLN-21), not this module's.
"""

from __future__ import annotations

import os
import stat
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

CACHEDIR_TAG = "CACHEDIR.TAG"
CACHEDIR_SIGNATURE = b"Signature: 8a477f597d28d172789f06886806bc55"


@dataclass(frozen=True)
class ArtifactSignature:
    """One kind of regenerable project artifact."""

    id: str
    names: tuple[str, ...]
    ecosystem: str
    regenerate: str
    #: At least one of these must exist in the parent directory (the project).
    sibling_markers: tuple[str, ...] = ()
    #: At least one of these must exist inside the matched directory.
    inner_markers: tuple[str, ...] = ()

    def requires_marker(self) -> bool:
        return bool(self.sibling_markers or self.inner_markers)


SIGNATURES: tuple[ArtifactSignature, ...] = (
    ArtifactSignature("node_modules", ("node_modules",), "Node.js", "npm / pnpm / yarn / bun install",
                      sibling_markers=("package.json",)),
    ArtifactSignature("rust_target", ("target",), "Rust", "cargo build", sibling_markers=("Cargo.toml",)),
    ArtifactSignature("maven_target", ("target",), "Java (Maven)", "mvn package", sibling_markers=("pom.xml",)),
    ArtifactSignature("gradle_project_cache", (".gradle",), "Java/Kotlin (Gradle)", "gradle build",
                      sibling_markers=("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")),
    ArtifactSignature("gradle_build", ("build",), "Java/Kotlin (Gradle)", "gradle build",
                      sibling_markers=("build.gradle", "build.gradle.kts")),
    ArtifactSignature("python_venv", (".venv", "venv"), "Python", "python -m venv + pip install -r …",
                      inner_markers=("pyvenv.cfg",)),
    ArtifactSignature("python_tox", (".tox",), "Python", "tox", sibling_markers=("tox.ini", "pyproject.toml", "setup.cfg")),
    ArtifactSignature("python_pycache", ("__pycache__",), "Python", "regenerated on import"),
    ArtifactSignature("next_build", (".next",), "Next.js", "next build", sibling_markers=("package.json",)),
    ArtifactSignature("nuxt_build", (".nuxt", ".output"), "Nuxt", "nuxt build", sibling_markers=("nuxt.config.ts", "nuxt.config.js")),
    ArtifactSignature("svelte_kit", (".svelte-kit",), "SvelteKit", "vite build", sibling_markers=("svelte.config.js", "svelte.config.ts")),
    ArtifactSignature("js_tool_cache", (".turbo", ".parcel-cache", ".angular"), "JavaScript tooling", "rebuilt by the next build",
                      sibling_markers=("package.json",)),
    ArtifactSignature("dart_tool", (".dart_tool",), "Dart/Flutter", "dart pub get", sibling_markers=("pubspec.yaml",)),
    ArtifactSignature("swiftpm_build", (".build",), "Swift Package Manager", "swift build", sibling_markers=("Package.swift",)),
    ArtifactSignature("zig_cache", ("zig-cache", ".zig-cache", "zig-out"), "Zig", "zig build", sibling_markers=("build.zig",)),
    ArtifactSignature("elixir_build", ("_build", "deps"), "Elixir", "mix deps.get && mix compile", sibling_markers=("mix.exs",)),
    ArtifactSignature("terraform_providers", (".terraform",), "Terraform", "terraform init",
                      sibling_markers=("main.tf", "versions.tf", "terraform.tf")),
)

CACHEDIR_TAGGED = ArtifactSignature("cachedir_tag", (), "Any (CACHEDIR.TAG)", "tool that wrote the tag regenerates it")

#: Directories never descended into during a sweep (system and app-data trees,
#: VCS metadata). Hidden directories are skipped too unless a signature names them.
SKIP_NAMES = frozenset({
    ".git", ".hg", ".svn", "Library", "AppData", "Applications", "System", "Windows",
    "Program Files", "Program Files (x86)", "ProgramData", "$Recycle.Bin", ".Trash", "proc", "sys", "dev",
})

_SIGNATURES_BY_NAME: dict[str, tuple[ArtifactSignature, ...]] = {}
for _sig in SIGNATURES:
    for _name in _sig.names:
        _SIGNATURES_BY_NAME[_name] = _SIGNATURES_BY_NAME.get(_name, ()) + (_sig,)
_HIDDEN_ARTIFACT_NAMES = frozenset(n for n in _SIGNATURES_BY_NAME if n.startswith("."))


def has_cachedir_tag(directory: str) -> bool:
    """True when ``directory/CACHEDIR.TAG`` is a regular file starting with the spec signature."""
    tag = os.path.join(directory, CACHEDIR_TAG)
    try:
        st = os.lstat(tag)
        if not stat.S_ISREG(st.st_mode):
            return False
        with open(tag, "rb") as fh:
            return fh.read(len(CACHEDIR_SIGNATURE)) == CACHEDIR_SIGNATURE
    except OSError:
        return False


def _exists_no_follow(path: str) -> bool:
    try:
        os.lstat(path)
        return True
    except OSError:
        return False


def classify_dir(path: str) -> ArtifactSignature | None:
    """The signature ``path`` proves, or ``None``. ``path`` must be a real directory (not a symlink)."""
    try:
        if not stat.S_ISDIR(os.lstat(path).st_mode):
            return None
    except OSError:
        return None
    name = os.path.basename(os.path.normpath(path))
    parent = os.path.dirname(os.path.normpath(path))
    for sig in _SIGNATURES_BY_NAME.get(name, ()):
        if not sig.requires_marker():
            return sig
        if any(_exists_no_follow(os.path.join(parent, m)) for m in sig.sibling_markers):
            return sig
        if any(_exists_no_follow(os.path.join(path, m)) for m in sig.inner_markers):
            return sig
    if has_cachedir_tag(path):
        return CACHEDIR_TAGGED
    return None



@dataclass(frozen=True)
class Finding:
    path: str
    signature_id: str
    ecosystem: str
    regenerate: str
    project_dir: str
    #: Newest mtime among the project's marker files (seconds); ``None`` if unknown.
    project_mtime: float | None


@dataclass
class SweepStats:
    directories_visited: int = 0
    unreadable: int = 0
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)


def _project_mtime(project_dir: str, sig: ArtifactSignature) -> float | None:
    times = []
    for marker in sig.sibling_markers:
        try:
            times.append(os.lstat(os.path.join(project_dir, marker)).st_mtime)
        except OSError:
            pass
    return max(times) if times else None


def sweep(
    roots: Iterable[str],
    *,
    max_depth: int = 10,
    min_idle_days: float | None = None,
    now: float | None = None,
    should_cancel: Callable[[], bool] = lambda: False,
    stats: SweepStats | None = None,
) -> Iterator[Finding]:
    """Yield marker-verified artifacts under ``roots`` (already validated by the caller).

    ``min_idle_days`` keeps only projects whose marker files have not changed
    for that many days (the "inactive project" filter). Iterative, so deep trees
    cannot overflow the stack. Cancelling stops at the next directory.
    """
    stats = stats if stats is not None else SweepStats()
    now = time.time() if now is None else now
    stack: list[tuple[str, int]] = [(os.path.normpath(r), 0) for r in roots]
    while stack:
        if should_cancel():
            stats.cancelled = True
            return
        directory, depth = stack.pop()
        stats.directories_visited += 1
        try:
            with os.scandir(directory) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            stats.unreadable += 1
            stats.errors.append(f"{directory}: {exc.strerror or exc}")
            continue
        children = []
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            sig = classify_dir(entry.path)
            if sig is not None:
                mtime = _project_mtime(directory, sig)
                if min_idle_days is not None and mtime is not None and now - mtime < min_idle_days * 86_400:
                    continue  # active project: keep, and do not descend into its artifact
                yield Finding(entry.path, sig.id, sig.ecosystem, sig.regenerate, directory, mtime)
                continue  # never descend into a match
            if entry.name in SKIP_NAMES:
                continue
            if entry.name.startswith(".") and entry.name not in _HIDDEN_ARTIFACT_NAMES:
                continue
            if depth + 1 <= max_depth:
                children.append((entry.path, depth + 1))
        stack.extend(reversed(children))
