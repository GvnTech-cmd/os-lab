"""Target detection for monorepos and platform targets.

``detect_targets`` scans the VFS (never the disk directly) for markers and
records, per adapter: the platform, the target root, the source roots the
resolver should probe, the evidence that fired, the entrypoints read from
manifests, and whether the target is binary-only.  Every adapter's
``coverage.applicability`` stays honest: ``full`` for parsed source,
``partial`` for archive/source subsets, ``not_applicable`` for binary-only
targets (refined by the engine after generation).

Markers:

- ``package.json`` with an electron dependency, or ``resources/app.asar`` /
  ``app.asar.unpacked`` -> ``windows-app`` (Windows/Electron).
- ``AndroidManifest.xml``, ``build.gradle(.kts)``, ``settings.gradle(.kts)``
  -> ``android-app`` with Gradle module roots; ``*.apk`` -> binary-only.
- ``*.xcodeproj``, ``Info.plist`` (``LSRequiresIPhoneOS``, ``UIDeviceFamily``),
  ``*.mobileprovision`` / ``*.provisionprofile``, ``*.entitlements``,
  ``*.storyboard`` -> ``ios-app`` / ``macos-app`` (split by the pbxproj
  ``SDKROOT`` and the plist platform hints); ``*.ipa`` and binary ``*.app``
  bundles -> binary-only.
- ``manifest.json`` with ``manifest_version`` -> ``browser-extension``.
- A tree with no markers gets a single ``repository`` target so target
  filters are never a silent no-op.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .extract.plist import read_plist, summarize_info_plist
from .extract.android_xml import parse_manifest
from .vfs import FileSystem
from .xcode import parse_pbxproj, platform_of

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".gradle", "build", "dist", "out", "DerivedData", "Pods",
    ".build", ".swiftpm", "target", ".dart_tool", ".next", "coverage",
}

ENTRYPOINT_CAP = 50
TARGET_CAP = 50


@dataclass
class Target:
    platform: str
    root: str
    confidence: float
    evidence: List[str] = field(default_factory=list)
    source_roots: List[str] = field(default_factory=list)
    binary_only: bool = False
    entrypoints: Dict[str, str] = field(default_factory=dict)  # path -> reason
    applicability: str = "full"
    applicability_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "root": self.root,
            "confidence": round(float(self.confidence), 3),
            "evidence": sorted(set(self.evidence)),
            "source_roots": sorted(set(self.source_roots)),
            "binary_only": self.binary_only,
            "entrypoints": dict(sorted(self.entrypoints.items())),
            "applicability": self.applicability,
            "applicability_reason": self.applicability_reason,
        }


def _walk_dirs(fs: FileSystem, cap: int = TARGET_CAP * 4) -> List[str]:
    dirs: List[str] = []
    stack = [""]
    seen = 0
    while stack and seen < cap:
        current = stack.pop()
        seen += 1
        try:
            children = fs.list(current)
        except OSError:
            continue
        for child in children:
            if fs.is_dir(child):
                name = child.rsplit("/", 1)[-1]
                if name not in SKIP_DIRS and name != "!" and "!" not in child:
                    dirs.append(child)
                    stack.append(child)
    return sorted(set(dirs))[: cap]


def _read_json(fs: FileSystem, path: str, cap: int = 1024 * 1024) -> Optional[dict]:
    try:
        raw = fs.read(path)
    except (OSError, ValueError):
        return None
    if len(raw) > cap:
        return None
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    return payload if isinstance(payload, dict) else None


def detect_targets(fs: FileSystem) -> List[Target]:
    raw: List[Target] = []

    def add(platform: str, root: str, confidence: float, evidence: List[str],
            source_roots: Optional[List[str]] = None, binary_only: bool = False) -> None:
        root = root.strip("/") or "."
        for existing in raw:
            if existing.platform == platform and existing.root == root:
                existing.evidence.extend(evidence)
                existing.source_roots.extend(source_roots or [])
                existing.confidence = max(existing.confidence, confidence)
                return
        if len(raw) >= TARGET_CAP:
            return
        raw.append(Target(platform=platform, root=root, confidence=confidence,
                          evidence=list(evidence),
                          source_roots=list(source_roots or []),
                          binary_only=binary_only))

    dirs = _walk_dirs(fs)
    for directory in dirs:
        name = directory.rsplit("/", 1)[-1]
        if name.endswith(".xcodeproj"):
            pbx_path = posixpath.join(directory, "project.pbxproj")
            info = parse_pbxproj(_safe_text(fs, pbx_path))
            platform = platform_of(info)
            platform_name = {"ios": "ios-app", "macos": "macos-app"}.get(platform or "", "macos-app")
            confidence = 0.9 if platform else 0.6
            evidence = [directory]
            evidence.extend(f"{directory}: SDKROOT {value}" for value in sorted(info.platforms))
            if info.info_plists:
                evidence.append(f"{directory}: INFOPLIST_FILE {info.info_plists[0]}")
            # pbxproj paths are relative to the project directory (the
            # .xcodeproj's parent), which is the target root
            roots = [d for d in info.source_dirs
                     if d and not d.startswith("/") and ".xcodeproj" not in d] \
                or [name.removesuffix(".xcodeproj")]
            add(platform_name, posixpath.dirname(directory) or ".", confidence, evidence,
                source_roots=roots)
        elif name.endswith((".app",)):
            add("macos-app", posixpath.dirname(directory) or ".", 0.5,
                [f"binary bundle: {directory}"], binary_only=True)
        elif name == "AndroidManifest.xml":
            module_root = _android_module_root(directory)
            info = parse_manifest(_safe_text(fs, directory))
            roots = []
            for sub in ("src/main/java", "src/main/kotlin"):
                candidate = posixpath.join(module_root, sub)
                if fs.is_dir(candidate):
                    roots.append(candidate)
            add("android-app", module_root, 0.9, [directory], source_roots=roots)
            if info.get("package"):
                raw[-1].evidence.append(f"package {info['package']}")
        elif name.endswith((".apk",)):
            add("android-app", posixpath.dirname(directory) or ".", 0.6,
                [f"binary: {directory}"], binary_only=True)
        elif name.endswith((".ipa",)):
            add("ios-app", posixpath.dirname(directory) or ".", 0.6,
                [f"binary: {directory} (no extraction)"], binary_only=True)
        elif name.endswith(".exe"):
            add("windows-app", posixpath.dirname(directory) or ".", 0.6,
                [f"binary: {directory}"], binary_only=True)
        elif name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
            add("android-app", directory, 0.5, [directory])
        elif name.endswith((".mobileprovision",)):
            add("ios-app", posixpath.dirname(directory) or ".", 0.7,
                [f"provisioning: {directory}"], binary_only=False)
        elif name.endswith((".provisionprofile",)):
            add("macos-app", posixpath.dirname(directory) or ".", 0.7,
                [f"provisioning: {directory}"], binary_only=False)
        elif name.endswith(".entitlements"):
            add("ios-app", posixpath.dirname(directory) or ".", 0.5,
                [f"entitlements: {directory}"], binary_only=False)

    # files (not dirs)
    for child in _list_files(fs):
        name = child.rsplit("/", 1)[-1]
        parent = posixpath.dirname(child) or "."
        if name == "package.json":
            payload = _read_json(fs, child)
            if not payload:
                continue
            deps = {}
            deps.update(payload.get("dependencies") or {})
            deps.update(payload.get("devDependencies") or {})
            if "electron" in deps:
                add("windows-app", parent, 0.9,
                    [f"{child}: electron {deps['electron']}"])
        elif name == "manifest.json" and "!" not in child:
            payload = _read_json(fs, child, cap=256 * 1024)
            if payload and "manifest_version" in payload:
                add("browser-extension", parent, 0.9,
                    [f"{child}: manifest_version {payload.get('manifest_version')}"])
        elif name == "Info.plist":
            payload, reason = read_plist(_safe_bytes(fs, child))
            if not payload:
                continue
            summary = summarize_info_plist(payload)
            if summary["ios"]:
                add("ios-app", parent, 0.85, [f"{child}: UIDeviceFamily/LSRequiresIPhoneOS"])
            elif summary["macos"]:
                add("macos-app", parent, 0.8, [f"{child}: CFBundlePackageType APPL"])
        elif name == "app.asar" or name.endswith(".asar"):
            parent_asar = posixpath.dirname(posixpath.dirname(child)) or "."
            add("windows-app", parent_asar, 0.85, [child])
        elif name.endswith(".apk"):
            add("android-app", parent, 0.6, [f"binary: {child}"], binary_only=True)
        elif name.endswith(".ipa"):
            add("ios-app", parent, 0.6, [f"binary: {child} (no extraction)"], binary_only=True)
        elif name.endswith(".exe"):
            add("windows-app", parent, 0.6, [f"binary: {child}"], binary_only=True)
        elif name.endswith(".mobileprovision"):
            add("ios-app", parent, 0.7, [f"provisioning: {child}"])
        elif name.endswith(".provisionprofile"):
            add("macos-app", parent, 0.7, [f"provisioning: {child}"])
        elif name.endswith(".entitlements"):
            add("ios-app", parent, 0.5, [f"entitlements: {child}"])
        elif name == "AndroidManifest.xml":
            module_root = _android_module_root(parent)
            info = parse_manifest(_safe_text(fs, child))
            roots = []
            for sub in ("src/main/java", "src/main/kotlin"):
                candidate = posixpath.join(module_root, sub)
                if fs.is_dir(candidate):
                    roots.append(candidate)
            evidence = [child]
            if info.get("package"):
                evidence.append(f"package {info['package']}")
            add("android-app", module_root, 0.9, evidence, source_roots=roots)
        elif name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"):
            add("android-app", parent, 0.5, [child])

    if not raw:
        raw.append(Target(platform="repository", root=".", confidence=0.5, evidence=[]))
    # Gradle source-set discovery: any src/main/java|kotlin directory belongs
    # to an android-app target at its module root, even without a manifest.
    for directory in dirs:
        leaf = directory.rsplit("/", 1)[-1]
        if leaf in ("java", "kotlin") and directory.endswith(("src/main/java", "src/main/kotlin")):
            parts = directory.split("/")
            module_root = "/".join(parts[:-3]) or "."
            add("android-app", module_root, 0.7, [f"source set: {directory}"],
                source_roots=[directory])
    return _merge(sorted(raw, key=lambda t: (t.platform, t.root)))


def _merge(targets: List[Target]) -> List[Target]:
    """Fold binary-only markers into source targets that contain their root,
    fold weak evidence (provisioning, plists, entitlements) into strong
    same-platform targets that contain their root, drop duplicates, and keep
    deterministic order."""
    strong = [t for t in targets if any(
        marker in evidence for evidence in t.evidence
        for marker in (".xcodeproj", "AndroidManifest.xml", "package.json:",
                       "app.asar", "manifest.json", "build.gradle", "binary bundle"))]

    merged: List[Target] = []
    for target in targets:
        if target.binary_only and any(
            other.platform == target.platform and not other.binary_only
            and _contains(other.root, target.root)
            for other in targets
        ):
            continue
        if not any(marker in e for e in target.evidence
                   for marker in (".xcodeproj", "AndroidManifest.xml",
                                  "package.json:", "app.asar", "manifest.json",
                                  "build.gradle", "binary bundle")):
            host = next((s for s in strong if s.platform == target.platform
                         and s is not target and _contains(s.root, target.root)), None)
            if host is not None:
                host.evidence.extend(target.evidence)
                host.source_roots.extend(target.source_roots)
                host.confidence = max(host.confidence, target.confidence)
                continue
        merged.append(target)
    out: List[Target] = []
    for target in merged:
        same = [t for t in out if t.root == target.root]
        if same:
            strongest = max(same, key=lambda t: t.confidence)
            if target.confidence > strongest.confidence or \
               (target.confidence == strongest.confidence and not target.binary_only and strongest.binary_only):
                out.remove(strongest)
                out.append(target)
            elif not target.binary_only:
                strongest.evidence.extend(target.evidence)
                strongest.source_roots.extend(target.source_roots)
            continue
        out.append(target)
    return sorted(out, key=lambda t: (t.platform, t.root))[:TARGET_CAP]


def _contains(root: str, child: str) -> bool:
    root = (root or ".").rstrip("/")
    child = (child or ".").rstrip("/")
    if root == ".":
        return True
    return child == root or child.startswith(root + "/")


def _under_root(path: str, root: str) -> bool:
    return _contains(root, path)


def _android_module_root(manifest_dir: str) -> str:
    """"AndroidManifest.xml at 'app/src/main/AndroidManifest.xml' belongs to
    module root 'app'; a manifest at 'mobile/AndroidManifest.xml' belongs to
    module root 'mobile'."""
    parts = manifest_dir.split("/")
    for i, part in enumerate(parts):
        if part == "src" and i + 1 < len(parts) and parts[i + 1] == "main":
            return "/".join(parts[:i]) or "."
    return manifest_dir or "."


def _list_files(fs: FileSystem, cap: int = 2000) -> List[str]:
    """Bounded recursive file listing with the same directory pruning."""
    files: List[str] = []
    stack = [""]
    while stack and len(files) < cap:
        current = stack.pop()
        try:
            children = fs.list(current)
        except OSError:
            continue
        for child in children:
            if fs.is_dir(child):
                name = child.rsplit("/", 1)[-1]
                if name in SKIP_DIRS or "!" in child:
                    continue
                stack.append(child)
            else:
                files.append(child)
                if len(files) >= cap:
                    break
    return sorted(set(files))


def _safe_text(fs: FileSystem, path: str) -> str:
    try:
        return fs.read(path).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def _safe_bytes(fs: FileSystem, path: str) -> bytes:
    try:
        return fs.read(path)
    except (OSError, ValueError):
        return b""
