"""Import resolution over a VFS.

``Resolver`` turns a specifier into another file in the tree or marks it
external; unresolved local imports are ``missing``.  It takes the same
:class:`~sourcemap.vfs.FileSystem` contract as ``RepoMap.generate``, so it
probes archives (``app.asar!/...`` members), the unpacked overlay on disk and
real files without any disk extraction beyond what the VFS already serves.

Per-language resolution policy:

- **ts/js** — relative paths with extension and ``index`` probing; ``@/`` and
  ``~/`` aliases to the root; ``tsconfig`` ``baseUrl``/``paths``; package
  imports are external.  From inside an archive the order is: member,
  unpacked overlay (``<name>.asar.unpacked/``), then missing; ``node_modules``
  stays external.
- **python** — leading-dot imports, package ``__init__.py``, ``src/`` layout;
  absolute imports that do not resolve are external.
- **objc** — quoted ``#import "Local.h"`` probes the importer directory, then
  the target header roots, then the header basename index; angle imports are
  external frameworks; ``@import Module;`` is an external module.
- **swift** — module imports (incl. ``@testable``) are always external:
  local files belong to a target, not an import path.
- **kotlin/java** — package/import paths are probed across every Gradle
  source root (``app/src/main/java|kotlin`` and library modules); wildcards
  resolve to the package directory; imports outside the project's own
  packages are external, unresolved project-internal imports are missing.
- **php** — PSR-4 from ``composer.json`` plus ``require``/``include``.
- **rust** — the ``mod`` tree, ``crate::``, ``super::`` and ``self::``.
"""

from __future__ import annotations

import json
import posixpath
from typing import Dict, List, Optional, Set, Tuple

from .model import FileMap, ImportRef
from .vfs import FileSystem

_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".css", ".html")
_KT_EXTS = (".kt", ".java", ".kts")


class Resolver:
    def __init__(self, fs: FileSystem, *, files_index: Set[str],
                 source_roots: Optional[Dict[str, List[str]]] = None,
                 project_packages: Optional[Set[str]] = None,
                 header_index: Optional[Dict[str, List[str]]] = None,
                 tsconfig: Optional[dict] = None,
                 composer: Optional[dict] = None,
                 mod_files: Optional[Set[str]] = None):
        self.fs = fs
        self.files_index = files_index
        self.source_roots = source_roots or {}
        self.project_packages = project_packages or set()
        self.header_index = header_index or {}   # basename -> sorted paths
        self.tsconfig = tsconfig or {}
        self.composer = composer or {}
        self.mod_files = mod_files or set()

    # ------------------------------------------------------------------
    def resolve(self, importer: str, ref: ImportRef) -> None:
        lang = self._lang_of(importer)
        handler = {
            "tsx": self._resolve_ts, "ts": self._resolve_ts, "jsx": self._resolve_ts,
            "js": self._resolve_ts, "css": self._resolve_asset, "html": self._resolve_asset,
            "python": self._resolve_python, "objc": self._resolve_objc,
            "swift": self._resolve_swift, "kotlin": self._resolve_kt,
            "java": self._resolve_kt, "php": self._resolve_php, "rust": self._resolve_rust,
        }.get(lang)
        if handler is None:
            # no policy for this language (storyboard, plist, json, xml, ...):
            # keep the extractor-provided reason; the engine post-processes it.
            return
        handler(importer, ref)

    def _lang_of(self, path: str) -> str:
        from .registry import detect
        spec = detect(path)
        return spec.name if spec else ""

    # -- ts / js ---------------------------------------------------------
    def _resolve_ts(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier
        if spec.startswith(("./", "../")):
            self._resolve_ts_relative(importer, ref)
            return
        if spec.startswith(("http://", "https://")):
            ref.resolved, ref.external, ref.reason = None, True, "url"
            return
        if spec.startswith("@/") or spec.startswith("~/"):
            base = spec[2:]
            marker = self._archive_marker(importer)
            hit = None
            if marker:
                prefix, unpacked_root = marker
                hit = self._probe_extensions(prefix + "!/" + base)
                if not hit:
                    hit = self._probe_extensions(
                        posixpath.normpath(unpacked_root + "/" + base))
            else:
                # Legacy alias order: src/* first, then the repository root.
                hit = (self._probe_extensions(posixpath.join("src", base))
                       or self._probe_extensions(base))
            if hit:
                ref.resolved, ref.external, ref.reason = hit, False, "alias"
            else:
                ref.resolved, ref.external, ref.reason = None, False, "missing"
            return
        mapped = self._tsconfig_paths(spec)
        if mapped:
            ref.resolved, ref.external, ref.reason = mapped, False, "paths"
            return
        if spec.startswith("@") and "/" in spec:
            ref.resolved, ref.external, ref.reason = None, True, "package"
            return
        ref.resolved, ref.external, ref.reason = None, True, "package"

    def _tsconfig_paths(self, spec: str) -> Optional[str]:
        base_url = self.tsconfig.get("baseUrl")
        paths = self.tsconfig.get("paths") or {}
        for pattern, targets in sorted(paths.items()):
            prefix = pattern.replace("*", "")
            if pattern.endswith("*") and spec.startswith(prefix):
                for target in targets:
                    candidate = target.replace("*", spec[len(prefix):])
                    hit = self._probe_extensions(candidate)
                    if hit:
                        return hit
            elif pattern == spec:
                for target in targets:
                    hit = self._probe_extensions(target)
                    if hit:
                        return hit
        if base_url and not spec.startswith("."):
            hit = self._probe_extensions(posixpath.join(base_url, spec))
            if hit:
                return hit
        return None

    def _resolve_ts_relative(self, importer: str, ref: ImportRef) -> None:
        directory = posixpath.dirname(importer)
        marker = self._archive_marker(importer)
        if marker:
            prefix, unpacked_root = marker
            member_dir = directory[len(prefix) + 2:] if directory.startswith(prefix + "!/") else ""
            base = posixpath.normpath(posixpath.join(member_dir, ref.specifier)) \
                if member_dir else posixpath.normpath(ref.specifier)
            hit = self._probe_extensions(prefix + "!/" + base)
            if hit:
                ref.resolved, ref.external, ref.reason = hit, False, "relative"
                return
            overlay = posixpath.normpath(unpacked_root + "/" + base)
            hit = self._probe_extensions(overlay)
            if hit:
                ref.resolved, ref.external, ref.reason = hit, False, "unpacked"
                return
            ref.resolved, ref.external, ref.reason = None, False, "missing"
            return
        base = posixpath.normpath(posixpath.join(directory, ref.specifier))
        hit = self._probe_extensions(base)
        if hit:
            ref.resolved, ref.external, ref.reason = hit, False, "relative"
            return
        ref.resolved, ref.external, ref.reason = None, False, "missing"

    @staticmethod
    def _archive_marker(path: str) -> Optional[Tuple[str, str]]:
        """For 'res/app.asar!/x/y.js' return ('res/app.asar', 'res/app.asar.unpacked')."""
        if "!/" not in path:
            return None
        prefix = path.split("!/", 1)[0]
        if prefix.endswith(".asar"):
            return prefix, prefix + ".unpacked"
        return None

    def _probe_extensions(self, base: str) -> Optional[str]:
        if base in self.files_index:
            return base
        for ext in _TS_EXTS:
            candidate = base + ext
            if candidate in self.files_index:
                return candidate
        for ext in _TS_EXTS:
            candidate = posixpath.join(base, "index" + ext)
            if candidate in self.files_index:
                return candidate
        return None

    def _resolve_asset(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier
        if spec.startswith(("http://", "https://", "//", "data:")):
            ref.resolved, ref.external, ref.reason = None, True, "url"
            return
        directory = posixpath.dirname(importer)
        base = posixpath.normpath(posixpath.join(directory, spec)) if spec.startswith(".") else spec.lstrip("/")
        if base in self.files_index:
            ref.resolved, ref.external, ref.reason = base, False, "relative"
        else:
            ref.resolved, ref.external, ref.reason = None, False, "missing"

    # -- python ------------------------------------------------------------
    def _resolve_python(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier
        if spec.startswith("."):
            directory = posixpath.dirname(importer)
            level = len(spec) - len(spec.lstrip("."))
            module = spec.lstrip(".")
            base = directory
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            candidate_base = posixpath.normpath(posixpath.join(base, module)) if module else base
            hit = self._py_probe(candidate_base)
            if hit:
                ref.resolved, ref.external, ref.reason = hit, False, "relative"
            else:
                ref.resolved, ref.external, ref.reason = None, False, "missing"
            return
        hit = self._py_probe(spec)
        if not hit:
            hit = self._py_probe(posixpath.join("src", spec))
        if hit:
            ref.resolved, ref.external, ref.reason = hit, False, "package"
            return
        ref.resolved, ref.external, ref.reason = None, True, "package"

    def _py_probe(self, module: str) -> Optional[str]:
        candidate = module.replace(".", "/")
        for ext in (".py",):
            if candidate + ext in self.files_index:
                return candidate + ext
            if posixpath.join(candidate, "__init__.py") in self.files_index:
                return posixpath.join(candidate, "__init__.py")
        return None

    # -- objc ----------------------------------------------------------------
    def _resolve_objc(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier
        if ref.reason == "framework" or spec.startswith("<"):
            ref.resolved, ref.external, ref.reason = None, True, "framework"
            return
        if ref.reason == "module":
            ref.resolved, ref.external, ref.reason = None, True, "module"
            return
        if "/" in spec or not spec.endswith(".h"):
            # quoted import with a subpath, or a non-header literal
            directory = posixpath.dirname(importer)
            candidate = posixpath.normpath(posixpath.join(directory, spec))
            if candidate in self.files_index:
                ref.resolved, ref.external, ref.reason = candidate, False, "quoted-header"
                return
            for root in self._roots_for(importer):
                candidate = posixpath.join(root, spec)
                if candidate in self.files_index:
                    ref.resolved, ref.external, ref.reason = candidate, False, "quoted-header"
                    return
            ref.resolved, ref.external, ref.reason = None, False, "missing"
            return
        directory = posixpath.dirname(importer)
        candidate = posixpath.join(directory, spec)
        if candidate in self.files_index:
            ref.resolved, ref.external, ref.reason = candidate, False, "quoted-header"
            return
        for root in self._roots_for(importer):
            candidate = posixpath.join(root, spec)
            if candidate in self.files_index:
                ref.resolved, ref.external, ref.reason = candidate, False, "quoted-header"
                return
        basename = posixpath.basename(spec)
        for candidate in self.header_index.get(basename, []):
            if candidate != importer:
                ref.resolved, ref.external, ref.reason = candidate, False, "quoted-header"
                return
        ref.resolved, ref.external, ref.reason = None, False, "missing"

    def _roots_for(self, path: str) -> List[str]:
        for platform, roots in sorted(self.source_roots.items()):
            for root in roots:
                if path == root or path.startswith(root + "/") or path.startswith(root + "!/"):
                    return roots
        all_roots: List[str] = []
        for platform in sorted(self.source_roots):
            all_roots.extend(self.source_roots[platform])
        return sorted(all_roots)

    # -- swift ---------------------------------------------------------------
    def _resolve_swift(self, importer: str, ref: ImportRef) -> None:
        # Swift modules are never file-resolved: local files belong to a
        # target, not an import path.  @testable import behaves the same.
        ref.resolved, ref.external, ref.reason = None, True, "swift-module"

    # -- kotlin / java ---------------------------------------------------
    def _resolve_kt(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier.rstrip(";")
        if spec.endswith(".*"):
            package_dir = spec[:-2].replace(".", "/")
            for root in self._roots_for(importer):
                candidate = posixpath.join(root, package_dir)
                if any(p.startswith(candidate + "/") for p in self.files_index):
                    ref.resolved, ref.external, ref.reason = candidate, False, "package"
                    return
            ref.resolved, ref.external, ref.reason = None, True, "package"
            return
        rel = spec.replace(".", "/")
        for ext in _KT_EXTS:
            candidate = rel + ext
            if candidate in self.files_index:
                ref.resolved, ref.external, ref.reason = candidate, False, "package"
                return
        for root in self._roots_for(importer):
            for ext in _KT_EXTS:
                candidate = posixpath.join(root, rel + ext)
                if candidate in self.files_index:
                    ref.resolved, ref.external, ref.reason = candidate, False, "package"
                    return
        for ext in _KT_EXTS:
            candidate = rel + ext
            if candidate in self.files_index:
                ref.resolved, ref.external, ref.reason = candidate, False, "package"
                return
        # package directory with any file inside counts as a package hit
        package_dir = rel.rsplit("/", 1)[0] if "/" in rel else rel
        for root in self._roots_for(importer):
            candidate = posixpath.join(root, package_dir)
            if any(p.startswith(candidate + "/") for p in self.files_index):
                ref.resolved, ref.external, ref.reason = candidate, False, "package"
                return
        first_segments = {".".join(spec.split(".")[:i]) for i in (1, 2)}
        if first_segments & self.project_packages:
            ref.resolved, ref.external, ref.reason = None, False, "missing"
        else:
            ref.resolved, ref.external, ref.reason = None, True, "package"

    # -- php / rust ---------------------------------------------------------
    def _resolve_php(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier
        if ref.reason == "require":
            directory = posixpath.dirname(importer)
            candidate = posixpath.normpath(posixpath.join(directory, spec)) if not spec.startswith("/") else spec.lstrip("/")
            if candidate in self.files_index:
                ref.resolved, ref.external, ref.reason = candidate, False, "require"
            else:
                ref.resolved, ref.external, ref.reason = None, False, "missing"
            return
        prefix = self.composer.get("psr-4") or {}
        dotted = spec.replace("\\", ".")
        for namespace, target in sorted(prefix.items()):
            ns = namespace.replace("\\", ".")
            ns = ns.rstrip(".")
            if dotted.startswith(ns + ".") or dotted == ns:
                rel = dotted[len(ns):].lstrip(".").replace(".", "/")
                candidate = posixpath.join(target, rel) + ".php"
                if candidate in self.files_index:
                    ref.resolved, ref.external, ref.reason = candidate, False, "psr4"
                    return
        ref.resolved, ref.external, ref.reason = None, True, "package"

    def _resolve_rust(self, importer: str, ref: ImportRef) -> None:
        spec = ref.specifier
        directory = posixpath.dirname(importer)
        if spec.startswith("crate::"):
            base = self._crate_root(importer)
            rel = spec[len("crate::"):].replace("::", "/")
            candidate = posixpath.join(base, rel)
        elif spec.startswith("super::"):
            base = posixpath.dirname(directory)
            rel = spec[len("super::"):].replace("::", "/")
            candidate = posixpath.join(base, rel)
        elif spec.startswith("self::"):
            rel = spec[len("self::"):].replace("::", "/")
            candidate = posixpath.join(directory, rel)
        else:
            rel = spec.replace("::", "/")
            candidate = posixpath.join(directory, rel)
        hit = self._rust_probe(candidate)
        if not hit:
            # ``use crate::foo::Bar;`` resolves to the module ``foo`` even
            # when the item (``Bar``) lives in that module.
            parts = rel.split("/")
            for index in range(len(parts) - 1, 0, -1):
                alternative = posixpath.join(base, "/".join(parts[:index])) \
                    if spec.startswith(("crate::", "super::", "self::")) else \
                    posixpath.join(directory, "/".join(parts[:index]))
                hit = self._rust_probe(alternative)
                if hit:
                    break
        if hit:
            ref.resolved, ref.external, ref.reason = hit, False, "rust"
        else:
            ref.resolved, ref.external, ref.reason = None, True, "package"

    def _crate_root(self, importer: str) -> str:
        current = posixpath.dirname(importer)
        last = current
        while current:
            if posixpath.join(current, "Cargo.toml") in self.files_index:
                return current
            last = current
            current = posixpath.dirname(current)
        # No Cargo.toml: honour the conventional ``src/`` layout used by the
        # legacy resolver (``rust/src/lib.rs`` -> ``rust/src``).
        parts = importer.split("/")
        if "src" in parts:
            cut = len(parts) - 1 - parts[::-1].index("src")
            return "/".join(parts[:cut + 1])
        return last

    def _rust_probe(self, base: str) -> Optional[str]:
        for candidate in (base + ".rs", posixpath.join(base, "mod.rs")):
            if candidate in self.files_index:
                return candidate
        return None


def load_tsconfig(fs: FileSystem, path: str = "tsconfig.json") -> dict:
    try:
        raw = fs.read(path)
    except (FileNotFoundError, OSError, ValueError):
        return {}
    try:
        text = raw.decode("utf-8-sig")
        text = json.loads(_strip_jsonc(text))
    except Exception:  # noqa: BLE001 - jsonc tolerated
        return {}
    compiler = text.get("compilerOptions") or {}
    return {"baseUrl": compiler.get("baseUrl"), "paths": compiler.get("paths")}


def load_composer(fs: FileSystem) -> dict:
    try:
        raw = fs.read("composer.json")
    except (FileNotFoundError, OSError, ValueError):
        return {}
    try:
        return json.loads(raw.decode("utf-8")).get("autoload") or {}
    except Exception:  # noqa: BLE001
        return {}


def _strip_jsonc(text: str) -> str:
    import re
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text
