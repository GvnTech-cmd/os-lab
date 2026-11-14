"""Xcode project support.

Decision (documented): ``project.pbxproj`` is parsed with a minimal,
line-oriented regex reader rather than a full object-graph parser.  It
extracts exactly what target detection and the resolver need:

- ``SDKROOT`` / ``TARGETED_DEVICE_FAMILY`` build settings -> macos vs ios,
- ``INFOPLIST_FILE`` and ``PRODUCT_BUNDLE_IDENTIFIER`` per configuration,
- source directories derived from ``lastKnownFileType`` file references and
  ``PBXFileSystemSynchronizedRootGroup`` paths (a documented file-tree
  heuristic, not full per-target membership).

Everything else (build phases, dependency graphs, signing) is out of scope;
a malformed project file yields an empty result, never an error.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

_SOURCE_TYPES = re.compile(
    r"lastKnownFileType\s*=\s*(?:sourcecode\.(?:swift|c\.objc|c\.objcpp|c|cpp\.objc|cpp|c\+plus)|text\.script\.pch)\b")
_OBJC_TYPES = re.compile(r"lastKnownFileType\s*=\s*sourcecode\.c\.objc(?:pp)?\b")
_PATH = re.compile(r"\bpath\s*=\s*\"?([^\";]+)\"?\s*;")
_SYNC_GROUP = re.compile(r"isa\s*=\s*PBXFileSystemSynchronizedRootGroup\b")
_SDKROOT = re.compile(r"\bSDKROOT\s*=\s*\"?([\w.]+)\"?\s*;")
_DEVICE_FAMILY = re.compile(r"\bTARGETED_DEVICE_FAMILY\s*=\s*\"?([\d,]+)\"?\s*;")
_INFOPLIST = re.compile(r"\bINFOPLIST_FILE\s*=\s*\"?([^\";]+)\"?\s*;")
_BUNDLE_ID = re.compile(r"\bPRODUCT_BUNDLE_IDENTIFIER\s*=\s*\"?([^\";]+)\"?\s*;")
_SECTION = re.compile(r"/\*\s*(\w+)\s*\*/\s*=\s*\{")


@dataclass
class PbxInfo:
    platforms: Set[str] = field(default_factory=set)          # {"macos"} / {"ios"}
    device_families: Set[str] = field(default_factory=set)    # {"1","2","6"}
    bundle_ids: Set[str] = field(default_factory=set)
    info_plists: List[str] = field(default_factory=list)
    source_dirs: List[str] = field(default_factory=list)
    objc_dirs: List[str] = field(default_factory=list)
    targets: List[str] = field(default_factory=list)


def _clean_dir(path: str) -> Optional[str]:
    path = path.strip().strip('"')
    directory = posixpath.dirname(path).strip("/")
    if directory in ("", "."):
        return None
    return directory


def parse_pbxproj(text: str) -> PbxInfo:
    info = PbxInfo()
    current_section = ""
    in_sync_group = False
    for raw in text.splitlines():
        line = raw.strip()
        section = _SECTION.search(raw)
        if section:
            current_section = section.group(1)
            in_sync_group = False
        if "isa = PBXNativeTarget" in line:
            name = re.search(r"name\s*=\s*\"?([^\";]+)", line)
            if name:
                info.targets.append(name.group(1))
        if _SYNC_GROUP.search(line):
            in_sync_group = True
            group_path = _PATH.search(line)
            if group_path:
                # the sync-group path is itself a source directory
                directory = group_path.group(1).strip().strip('"').strip("/")
                if directory and directory != "." and directory not in info.source_dirs:
                    info.source_dirs.append(directory)
            continue
        sdk = _SDKROOT.search(line)
        if sdk:
            value = sdk.group(1)
            if "macosx" in value:
                info.platforms.add("macos")
            elif "iphone" in value:
                info.platforms.add("ios")
            continue
        family = _DEVICE_FAMILY.search(line)
        if family:
            info.device_families.update(family.group(1).split(","))
            continue
        plist = _INFOPLIST.search(line)
        if plist:
            info.info_plists.append(plist.group(1).strip('"'))
            continue
        bundle = _BUNDLE_ID.search(line)
        if bundle:
            info.bundle_ids.add(bundle.group(1))
            continue
        if _SOURCE_TYPES.search(line) or (in_sync_group and "path =" in line) or \
           (current_section == "PBXFileReference" and ".swift" in line):
            path_match = _PATH.search(line)
            if path_match:
                source_path = path_match.group(1)
                if source_path.endswith((".swift", ".m", ".mm", ".h", ".c", ".cpp")):
                    directory = _clean_dir(source_path)
                    if directory and directory not in info.source_dirs:
                        info.source_dirs.append(directory)
                    if _OBJC_TYPES.search(line) or source_path.endswith((".m", ".mm")):
                        if directory and directory not in info.objc_dirs:
                            info.objc_dirs.append(directory)
    info.info_plists = sorted(set(info.info_plists))
    info.source_dirs = sorted(set(info.source_dirs))
    # documented heuristic: INFOPLIST_FILE sits inside the app source folder,
    # so its directory is a source root even without explicit file references
    for plist_path in info.info_plists:
        plist_dir = posixpath.dirname(plist_path.strip().strip('"')).strip("/")
        if plist_dir and plist_dir != "." and plist_dir not in info.source_dirs:
            info.source_dirs.append(plist_dir)
    info.source_dirs = sorted(set(info.source_dirs))
    info.objc_dirs = sorted(set(info.objc_dirs))
    info.targets = sorted(set(info.targets))
    if info.device_families & {"1", "2", "6"}:
        info.platforms.add("ios")
    return info


def platform_of(info: PbxInfo) -> Optional[str]:
    """macos vs ios from build settings; ios wins when families are present."""
    if "ios" in info.platforms or info.device_families & {"1", "2", "6"}:
        return "ios"
    if "macos" in info.platforms:
        return "macos"
    return None
