"""The structural repository map.

One public class composes the package.  :meth:`RepoMap.generate` walks a
:class:`~sourcemap.vfs.FileSystem` (a ``DiskFS`` by default, or an archive
overlay -- extraction to disk is never needed), extracts symbols and imports
per language, resolves them, indexes types, classifies roles, detects
targets and writes ``repo-map.json``-shaped dicts.  Two runs over the same
tree produce byte-identical JSON: keys and arrays are sorted, and there are
no timestamps.

The legacy ``max_files``/``max_kb``/``detail``/``filter`` constructor and
bundle keys (``tree``, ``edges``, ``externals``) are kept so the crawler,
CLI and UI written against the first release keep working.
"""

from __future__ import annotations

import posixpath
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .archives import asar as asar_module
from .extract import android_xml, java, kotlin, markup, objc, php, plist, python_ast, rust, swift
from .extract import ts as ts_module
from .extract.common import Extracted
from .filter import MapFilter, filter_map
from .headers import pair_implementation
from .model import FileMap, ImportRef, Role, Symbol
from .rank import cycles, entrypoints, pagerank
from .registry import detect, is_binary_name, is_lockfile
from .resolve import Resolver, load_composer, load_tsconfig
from .roles import RoleContext, classify
from .targets import SKIP_DIRS, Target, detect_targets
from .types import build_type_index
from .vfs import ArchiveFS, DiskFS, FileSystem, OverlayFS

try:  # optional extra; presence is only recorded in toolchain
    import tree_sitter  # noqa: F401
    TREE_SITTER = "installed"
except Exception:  # noqa: BLE001
    TREE_SITTER = "not-installed"

DETAILS = {"files", "symbols", "full"}
SOURCE_SKIP_PREFIXES = ("size:", "large:", "generated: minified", "parse error",
                        "ambiguous header")


@dataclass
class Caps:
    files: int = 4000
    file_bytes: int = 512 * 1024
    symbols_per_file: int = 200
    budget_ms: int = 30_000
    cycles: int = 20
    asar_entries: int = 20_000
    asar_bytes: int = 64 * 1024 * 1024
    targets: int = 50
    type_names: int = 2000
    skipped_entries: int = 1000
    symbol_detail_files: int = 200


GENERATED_PATH = __import__("re").compile(
    r"(^|/)R\.kt$|(^|/)R\.java$|R\$[\w]+\.java$|(^|/)BuildConfig\.(java|kt)$"
    r"|(^|/)databinding/|Binding\.(java|kt)$|(^|/)generated/")

CONFIG_LANGS = {"json", "plist"}


def _run_extractor(spec, text: str, path: str) -> Tuple[Extracted, List[str], str]:
    """Extract one file; return the record, limits and the parser that ran."""
    if isinstance(spec.grammar, tuple) and spec.extractor in {"ts", "php", "rust"}:
        from .extract import treesitter
        if treesitter.available():
            result = treesitter.extract(spec, text.encode("utf-8"), path)
            if result is not None:
                symbols, imports, exports, limits = result
                return Extracted(symbols=symbols, imports=imports, exports=exports), limits, "tree-sitter"

    if spec.extractor == "ts":
        return ts_module.extract(text, spec.name), [], spec.parser
    if spec.extractor == "markup":
        return markup.extract(text, spec.name), [], spec.parser
    if spec.extractor == "android_xml":
        return android_xml.extract(text, path), [], spec.parser
    if spec.extractor == "python_ast":
        return python_ast.extract(text), [], spec.parser
    if spec.extractor == "php":
        return php.extract(text), [], spec.parser
    if spec.extractor == "rust":
        return rust.extract(text), [], spec.parser
    if spec.extractor == "swift":
        return swift.extract(text), [], spec.parser
    if spec.extractor == "objc":
        return objc.extract(text), [], spec.parser
    if spec.extractor == "kotlin":
        return kotlin.extract(text), [], spec.parser
    if spec.extractor == "java":
        return java.extract(text), [], spec.parser
    if spec.extractor in ("plist", "json"):
        return plist.extract(text, path), [], spec.parser
    raise ValueError(f"no extractor for {spec.extractor}")


def _is_source_lang(lang: str) -> bool:
    return lang not in CONFIG_LANGS and lang not in {"xml", "storyboard"}


def _contains(root: str, child: str) -> bool:
    root = (root or ".").rstrip("/")
    child = (child or ".").rstrip("/")
    if root == ".":
        return True
    return child == root or child.startswith(root + "/")


class RepoMap:
    """Platform-agnostic structural map of a source tree."""

    def __init__(self, *, max_files: int = 4000, max_kb: int = 512,
                 max_symbols: int = 200, detail: str = "full",
                 langs: Optional[Any] = None,
                 filter: Optional[MapFilter] = None,
                 target_classes: Optional[Any] = None,
                 budget_ms: int = 30_000,
                 caps: Optional[Caps] = None) -> None:
        if detail not in DETAILS:
            raise ValueError(f"detail must be one of {sorted(DETAILS)}")
        if caps is None:
            caps = Caps(files=max_files, file_bytes=max_kb * 1024,
                        symbols_per_file=max_symbols, budget_ms=budget_ms)
        self.caps = caps
        self.detail = detail
        self.langs = tuple(langs) if langs else None
        self.map_filter = filter
        self.target_classes = tuple(target_classes) if target_classes else None

    # ------------------------------------------------------------------
    def generate(self, root=None, *, fs: Optional[FileSystem] = None,
                 detail: Optional[str] = None,
                 langs: Optional[Any] = None,
                 target_classes: Optional[Any] = None) -> dict:
        caps = self.caps
        detail = detail or self.detail
        langs = tuple(langs) if langs else self.langs
        target_classes = tuple(target_classes) if target_classes else self.target_classes

        if fs is None:
            if root is None:
                raise ValueError("generate needs a root or an fs")
            path = Path(root).resolve()
            if path.is_file():
                return self._file_target_bundle(path)
            base_fs: FileSystem = DiskFS(path)
        else:
            base_fs = fs

        started = time.monotonic()
        limitations: List[str] = []
        skipped: List[Dict[str, str]] = []

        mounted, archive_notes = self._mount_archives(base_fs, caps, limitations)
        walk_fs: FileSystem = mounted

        targets = detect_targets(base_fs)
        if target_classes:
            targets = [t for t in targets if t.platform in target_classes]
            if not targets:
                targets = [Target(platform="repository", root=".", confidence=0.5)]

        # Electron entrypoints from the asar package.json (main + preload).
        explicit_entrypoints: Dict[str, str] = {}
        for target in targets:
            if target.platform != "windows-app":
                continue
            for note in archive_notes:
                prefix = note["prefix"]  # already ends with "!/"
                if not _contains(target.root, note["archive"]):
                    continue
                payload = _read_json_fs(walk_fs, prefix + "package.json")
                if not payload:
                    continue
                main = payload.get("main")
                if isinstance(main, str) and main:
                    explicit_entrypoints[prefix + main.lstrip("./")] = "package.json:main"
                preload = payload.get("preload")
                preloads = preload if isinstance(preload, list) else [preload]
                for item in preloads:
                    if isinstance(item, str) and item:
                        explicit_entrypoints[prefix + item.lstrip("./")] = "package.json:preload"
                target.entrypoints.update({p: r for p, r in explicit_entrypoints.items()
                                           if p.startswith(prefix)})

        walked, dirs_count, truncated = self._walk(walk_fs, caps)
        if target_classes:
            walked = [p for p in walked if self._in_targets(p, targets)]

        files: Dict[str, FileMap] = {}
        sources: Dict[str, str] = {}
        file_packages: Dict[str, str] = {}
        packages: Set[str] = set()
        manifest_components: Dict[str, dict] = {}
        parsers_seen: Dict[str, str] = {}

        for path in walked:
            if (time.monotonic() - started) * 1000 > caps.budget_ms:
                skipped.append({"path": path, "reason": "not_visited: budget"})
                truncated = True
                continue
            reason = self._skip_reason(walk_fs, path, caps, langs)
            if reason:
                skipped.append({"path": path, "reason": reason})
                continue
            spec = detect(path)
            if spec is None:
                skipped.append({"path": path, "reason": "language: unsupported"})
                continue
            lang = spec.name
            if lang == "h":
                lang = self._disambiguate_header(walk_fs, path, targets)
                if lang is None:
                    skipped.append({"path": path, "reason": "ambiguous header: c/c++/objc"})
                    continue
            try:
                raw = walk_fs.read(path)
            except (OSError, ValueError) as exc:
                skipped.append({"path": path, "reason": f"read error: {exc.__class__.__name__}"})
                continue
            if b"\x00" in raw[:8192]:
                skipped.append({"path": path, "reason": "binary: NUL byte"})
                continue
            text = raw.decode("utf-8", errors="replace")
            try:
                extracted, limits, parser = _run_extractor(spec, text, path)
            except Exception as exc:  # noqa: BLE001 - a parse error is a skip, never a crash
                skipped.append({"path": path, "reason": f"parse error: {exc}"})
                continue
            limitations.extend(limits)
            if extracted.package:
                packages.add(extracted.package)
                file_packages[path] = extracted.package
            loc = len(text.splitlines())
            sloc = sum(1 for line in text.splitlines() if line.strip())
            exports = list(extracted.exports)
            if "default" not in exports and re.search(r"^\s*export\s+default\b", text, re.M):
                exports.insert(0, "default")
            fm = FileMap(path=path, lang=lang, parser=parser, loc=loc, sloc=sloc,
                         exports=exports)
            fm.symbols = extracted.symbols[: caps.symbols_per_file]
            if len(extracted.symbols) > caps.symbols_per_file:
                limitations.append(f"symbols: {path} over {caps.symbols_per_file}")
            fm.imports = extracted.imports
            files[path] = fm
            sources[path] = text
            parsers_seen[lang] = parser
            # manifest components feed roles for the classes they declare
            if posixpath.basename(path) == "AndroidManifest.xml":
                for sym in fm.symbols:
                    if sym.kind in ("activity", "service", "receiver", "provider"):
                        manifest_components[sym.name] = {
                            "type": sym.kind,
                            "exported": bool(sym.meta.get("exported")),
                            "launcher": bool(sym.meta.get("launcher")),
                        }
                        manifest_components.setdefault(sym.name.rsplit(".", 1)[-1],
                                                       manifest_components[sym.name])

        # resolution
        header_index: Dict[str, List[str]] = {}
        for path in sorted(files):
            if path.endswith(".h"):
                header_index.setdefault(posixpath.basename(path), []).append(path)
        source_roots: Dict[str, List[str]] = {}
        for target in targets:
            if target.source_roots:
                source_roots.setdefault(target.platform, []).extend(target.source_roots)
        resolver = Resolver(walk_fs, files_index=set(files), source_roots=source_roots,
                            project_packages=packages, header_index=header_index,
                            tsconfig=load_tsconfig(walk_fs), composer=load_composer(walk_fs))
        for path in sorted(files):
            fm = files[path]
            for ref in fm.imports:
                resolver.resolve(path, ref)

        # objc header/implementation pairing (adds implicit deterministic edges)
        pair_implementation(files)

        type_index = build_type_index(files, limitations)

        # storyboard/xib class references become edges via the type index
        self._resolve_storyboards(files, type_index)

        # android launcher entrypoint
        class_to_file: Dict[str, str] = {}
        for path in sorted(files):
            fm = files[path]
            if fm.lang not in ("kotlin", "java"):
                continue
            pkg = file_packages.get(path, "")
            for sym in fm.symbols:
                if sym.kind == "class":
                    full = f"{pkg}.{sym.name}".lstrip(".")
                    class_to_file.setdefault(full, path)
        for comp_name, comp in sorted(manifest_components.items()):
            if comp.get("launcher") and comp_name in class_to_file:
                explicit_entrypoints.setdefault(class_to_file[comp_name], "manifest:launcher")

        ctx = RoleContext(manifest_components=manifest_components,
                          explicit={p: ("entrypoint", 0.95, r) for p, r in explicit_entrypoints.items()},
                          sources=sources)
        for path in sorted(files):
            fm = files[path]
            fm.role = classify(path, fm.lang, fm.symbols, ctx)

        self._apply_applicability(targets, files, skipped, archive_notes)

        scores = pagerank(files)
        eps = entrypoints(files, scores, explicit_entrypoints)
        cycle_list = cycles(files)[: caps.cycles]

        # Legacy bundle fields: explicit edge list and external package counts.
        edges: List[dict] = []
        externals: Dict[str, Dict[str, int]] = {}
        for path in sorted(files):
            seen: Set[str] = set()
            for imp in files[path].imports:
                if imp.resolved and not imp.external and imp.resolved != path:
                    if imp.resolved not in seen:
                        seen.add(imp.resolved)
                        edges.append({"from": path, "to": imp.resolved, "kind": "import"})
                elif imp.external:
                    name = self._package_name(imp.specifier)
                    externals.setdefault(name, {"imported_by": 0})["imported_by"] += 1

        stats = {
            "files": len(walked),
            "dirs": self._dir_count(walked),
            "source_files": len(files),
            "symbols": sum(len(fm.symbols) for fm in files.values()),
            "edges": len(edges),
            "unresolved": sum(1 for fm in files.values() for imp in fm.imports
                              if not imp.resolved and not imp.external),
            "truncated": truncated,
        }
        if len(skipped) > caps.skipped_entries:
            limitations.append(f"coverage: skipped entries truncated at {caps.skipped_entries}")
            skipped = skipped[: caps.skipped_entries]

        applicability = self._map_applicability(targets, skipped)
        coverage = {
            "files_scanned": len(walked),
            "files_parsed": len(files),
            "applicability": applicability,
            "skipped": sorted(skipped, key=lambda s: (s["path"], s["reason"])),
            "limitations": sorted(set(limitations)),
            "archives": archive_notes,
        }

        ranked_paths = [p for p, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]
        if detail == "full":
            keep_symbols = set(files)
        elif detail == "symbols":
            keep_symbols = set(ranked_paths[: caps.symbol_detail_files])
        else:
            keep_symbols = set()
        files_out: Dict[str, dict] = {}
        for path in sorted(files):
            fm = files[path]
            files_out[path] = fm.to_dict(with_symbols=path in keep_symbols)

        bundle = {
            "schema_version": 1,
            "root": getattr(walk_fs, "label", "repository"),
            "toolchain": {"tree_sitter": TREE_SITTER,
                          "languages": dict(sorted(parsers_seen.items()))},
            "stats": stats,
            "tree": self._tree(walked, files),
            "files": files_out,
            "edges": edges,
            "externals": dict(sorted(externals.items())),
            "types": type_index,
            "targets": [t.to_dict() for t in sorted(targets, key=lambda t: (t.platform, t.root))],
            "filter": {"applied": False, "criteria": {},
                       "matched_files": len(files_out), "matched_symbols": stats["symbols"]},
            "entrypoints": eps,
            "cycles": cycle_list,
            "coverage": coverage,
        }
        if langs:
            bundle["filter"]["criteria"]["langs"] = list(langs)
        if self.map_filter:
            bundle = filter_map(bundle, self.map_filter)
        return bundle

    # ------------------------------------------------------------------
    def _file_target_bundle(self, path: Path) -> dict:
        suffix = path.suffix.lower()
        platform = ("android-app" if suffix in {".apk", ".xapk", ".apks", ".aab"}
                    else "ios-app" if suffix == ".ipa"
                    else "windows-app" if suffix in {".exe", ".dll", ".sys", ".node"}
                    else "repository")
        target = Target(platform=platform, root=path.name, confidence=0.9,
                        evidence=[suffix], binary_only=True,
                        applicability="not_applicable",
                        applicability_reason="binary-only target")
        return {
            "schema_version": 1,
            "root": path.name,
            "toolchain": {"tree_sitter": TREE_SITTER, "languages": {}},
            "stats": {"files": 0, "dirs": 0, "source_files": 0, "symbols": 0,
                      "edges": 0, "unresolved": 0, "truncated": False},
            "tree": [],
            "files": {},
            "edges": [],
            "externals": {},
            "types": {},
            "targets": [target.to_dict()],
            "filter": {"applied": False, "criteria": {}, "matched_files": 0,
                       "matched_symbols": 0},
            "entrypoints": [],
            "cycles": [],
            "coverage": {"files_scanned": 0, "files_parsed": 0,
                         "applicability": "not_applicable",
                         "skipped": [{"path": path.name, "reason": "binary-only target"}],
                         "limitations": [], "archives": []},
        }

    def _walk(self, fs: FileSystem, caps: Caps) -> Tuple[List[str], int, bool]:
        found: List[str] = []
        dirs_count = 0
        stack = [""]
        truncated = False
        while stack:
            current = stack.pop()
            try:
                children = fs.list(current)
            except (OSError, ValueError):
                continue
            for child in children:
                if fs.is_dir(child):
                    name = child.rsplit("/", 1)[-1]
                    if name in SKIP_DIRS or name.startswith("."):
                        continue
                    stack.append(child)
                    dirs_count += 1
                else:
                    found.append(child)
                    if len(found) >= caps.files:
                        truncated = True
                        stack.clear()
                        break
        return sorted(found), dirs_count, truncated

    def _skip_reason(self, fs: FileSystem, path: str, caps: Caps,
                     langs: Optional[Tuple[str, ...]]) -> Optional[str]:
        name = posixpath.basename(path)
        if path.endswith(".asar"):
            return f"archive container: contents mapped under {name}!/"
        if is_lockfile(path):
            return "lockfile"
        if is_binary_name(path):
            return f"binary: {name.rsplit('.', 1)[-1] if '.' in name else name}"
        if GENERATED_PATH.search(path):
            return "generated: R/BuildConfig/databinding"
        if name.endswith((".min.js", ".min.css")):
            return "generated: minified"
        try:
            size = fs.stat(path)
        except (OSError, ValueError, FileNotFoundError):
            size = 0
        if size > caps.file_bytes:
            kb = max(1, caps.file_bytes // 1024)
            return f"size: large: over {kb}KB"
        if langs:
            spec = detect(path)
            if spec is None or spec.name not in langs:
                return "language: excluded by filter"
        return None

    def _disambiguate_header(self, fs: FileSystem, path: str,
                             targets: List[Target]) -> Optional[str]:
        for target in targets:
            if target.platform in ("macos-app", "ios-app") and _contains(target.root, path.split("!/", 1)[0]):
                return "objc"
        try:
            raw = fs.read(path)
        except (OSError, ValueError):
            return None
        if objc.looks_like_objc(raw.decode("utf-8", errors="replace")):
            return "objc"
        return None

    def _mount_archives(self, fs: FileSystem, caps: Caps,
                        limitations: List[str]) -> Tuple[FileSystem, List[dict]]:
        archives: List[dict] = []
        layers: List[FileSystem] = []
        stack = [""]
        asar_paths: List[str] = []
        while stack:
            current = stack.pop()
            try:
                children = fs.list(current)
            except (OSError, ValueError):
                continue
            for child in children:
                if fs.is_dir(child):
                    if child.rsplit("/", 1)[-1] in SKIP_DIRS:
                        continue
                    stack.append(child)
                elif child.endswith(".asar"):
                    asar_paths.append(child)
        for asar_path in sorted(asar_paths):
            try:
                data = fs.read(asar_path)
            except (OSError, ValueError) as exc:
                limitations.append(f"asar: unreadable {asar_path} ({exc.__class__.__name__})")
                continue
            if len(data) > caps.asar_bytes:
                limitations.append(f"asar: {asar_path} over {caps.asar_bytes} bytes, not mounted")
                continue
            try:
                _, data_base, packed, unpacked, notes = asar_module.load_asar(
                    data, max_entries=caps.asar_entries, max_bytes=caps.asar_bytes)
            except asar_module.AsarError as exc:
                limitations.append(f"asar: {asar_path}: {exc}")
                continue
            limitations.extend(f"{asar_path}: {note}" for note in notes)
            layer = ArchiveFS(fs, asar_path, data, packed, data_base, unpacked)
            layers.append(layer)
            archives.append({"archive": asar_path, "prefix": asar_path + "!/",
                             "packed": len(packed), "unpacked": len(unpacked)})
        if not layers:
            return fs, archives
        return OverlayFS(layers + [fs]), archives

    def _resolve_storyboards(self, files: Dict[str, FileMap], type_index: dict) -> None:
        for path in sorted(files):
            fm = files[path]
            if fm.lang != "storyboard":
                continue
            for ref in fm.imports:
                if ref.reason != "storyboard" or not ref.names:
                    continue
                candidates = type_index.get(ref.names[0], [])
                hit = next((c for c in candidates if c["lang"] in ("swift", "objc")), None)
                if hit:
                    ref.resolved, ref.external, ref.reason = hit["file"], False, "storyboard"
                else:
                    ref.resolved, ref.external, ref.reason = None, False, "missing"

    def _apply_applicability(self, targets: List[Target], files: Dict[str, FileMap],
                             skipped: List[dict], archive_notes: List[dict]) -> None:
        for target in targets:
            parsed = archive_files = source_files = source_skips = 0
            for path, fm in files.items():
                disk_path = path.split("!/", 1)[0]
                if _contains(target.root, disk_path):
                    if "!/" in path:
                        archive_files += 1
                    parsed += 1
                    if _is_source_lang(fm.lang):
                        source_files += 1
            for entry in skipped:
                if _contains(target.root, entry["path"].split("!/", 1)[0]) and \
                   entry["reason"].startswith(SOURCE_SKIP_PREFIXES):
                    source_skips += 1
            if parsed == 0:
                if archive_files or any(_contains(target.root, note["archive"]) for note in archive_notes):
                    target.applicability = "partial"
                    target.applicability_reason = "archive subset: no parseable source"
                elif target.binary_only:
                    target.applicability = "not_applicable"
                    target.applicability_reason = "binary-only: no parseable source"
                else:
                    target.applicability = "not_applicable"
                    target.applicability_reason = "no parseable source"
            elif source_files == 0:
                if archive_files or source_skips:
                    # e.g. an asar whose only parseable content is package.json
                    target.applicability = "partial"
                    target.applicability_reason = "archive subset: no parseable source"
                elif target.binary_only or any("binary bundle" in e for e in target.evidence):
                    target.applicability = "not_applicable"
                    target.applicability_reason = "binary-only: no parseable source"
                else:
                    target.applicability = "partial"
                    target.applicability_reason = "subset: config-only content"
            elif source_skips:
                target.applicability = "partial"
                target.applicability_reason = f"subset: {source_skips} skipped sources"
            else:
                target.applicability = "full"
                target.applicability_reason = ""

    def _map_applicability(self, targets: List[Target], skipped: List[dict]) -> str:
        states = [t.applicability for t in targets] or ["not_applicable"]
        if all(s == "not_applicable" for s in states):
            return "not_applicable"
        if any(s == "partial" for s in states) or \
           any(e["reason"].startswith(SOURCE_SKIP_PREFIXES) for e in skipped):
            return "partial"
        return "full"

    def _tree(self, paths: List[str], files: Dict[str, FileMap]) -> List[dict]:
        dirs: Dict[str, int] = {}
        for rel in paths:
            parent = posixpath.dirname(rel)
            while parent not in {"", "."}:
                dirs[parent] = dirs.get(parent, 0) + 1
                parent = posixpath.dirname(parent)
        out = [{"path": d, "type": "dir", "files": n} for d, n in sorted(dirs.items())]
        for rel in sorted(paths):
            fm = files.get(rel)
            spec = detect(rel) if fm is None else None
            out.append({
                "path": rel, "type": "file",
                "lang": fm.lang if fm else (spec.name if spec else None),
                "role": fm.role.kind if fm else "unknown",
                "loc": fm.loc if fm else 0,
            })
        return out

    @staticmethod
    def _dir_count(paths: List[str]) -> int:
        dirs = set()
        for rel in paths:
            parent = posixpath.dirname(rel)
            while parent not in {"", "."}:
                dirs.add(parent)
                parent = posixpath.dirname(parent)
        return len(dirs)

    @staticmethod
    def _in_targets(rel: str, targets: List[Target]) -> bool:
        if any(t.platform == "repository" and t.root == "." for t in targets):
            return True
        return any(t.platform != "repository"
                   and (t.root == "." or rel == t.root or rel.startswith(t.root + "/"))
                   for t in targets)

    @staticmethod
    def _package_name(specifier: str) -> str:
        parts = specifier.split("/")
        return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]

    # ------------------------------------------------------------------
    @staticmethod
    def filter_map(map_dict: dict, spec: MapFilter) -> dict:
        return filter_map(map_dict, spec)


def _read_json_fs(fs: FileSystem, path: str) -> Optional[dict]:
    try:
        raw = fs.read(path)
    except (OSError, ValueError):
        return None
    import json
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, dict) else None
