"""Map filtering.

``MapFilter`` is shared by the library, the CLI and the UI.  Dimensions are
ANDed; values inside a dimension are ORed.  A file survives when it matches
the file filters and either has a matching symbol or ``kinds`` is empty.
Edges, ``entrypoints`` and ``cycles`` always describe the full graph:
filtering prunes payload, not truth.

``targets`` carries platform names (``android-app``); they are mapped to the
target roots from ``map["targets"]`` before path filtering so a platform
filter narrows to the right subtrees.
"""

from __future__ import annotations

import fnmatch
from dataclasses import asdict, dataclass, field, fields
from typing import Tuple


@dataclass(frozen=True)
class MapFilter:
    roles: Tuple[str, ...] = ()
    kinds: Tuple[str, ...] = ()
    langs: Tuple[str, ...] = ()
    paths: Tuple[str, ...] = ()
    targets: Tuple[str, ...] = ()
    exported_only: bool = False
    min_role_confidence: float = 0.0

    def is_empty(self) -> bool:
        return not (self.roles or self.kinds or self.langs or self.paths
                    or self.targets or self.exported_only or self.min_role_confidence)

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v)
                for k, v in asdict(self).items()}


EMPTY_SENTINELS = ((), [], None, "", 0.0, False)


def _targets_to_roots(spec: MapFilter, map_dict: dict) -> Tuple[str, ...]:
    if not spec.targets:
        return ()
    roots = [t.get("root", ".") for t in map_dict.get("targets", [])
             if t.get("platform") in spec.targets]
    return tuple(roots) if roots else spec.targets


def filter_map(map_dict: dict, spec: MapFilter) -> dict:
    if spec.is_empty():
        out = dict(map_dict)
        out["filter"] = {"applied": False, "criteria": {}, "matched_files": len(map_dict.get("files", {}))}
        return out

    roots = _targets_to_roots(spec, map_dict)

    def under_root(path: str) -> bool:
        if not roots:
            return True
        return any(root == "." or path == root or path.startswith(root + "/")
                   for root in roots)

    files = map_dict.get("files", {})
    matched: dict = {}
    matched_symbols = 0
    for path in sorted(files):
        entry = files[path]
        role = entry.get("role", {})
        if spec.roles and role.get("kind") not in spec.roles:
            continue
        if spec.langs and entry.get("lang") not in spec.langs:
            continue
        if spec.paths and not any(fnmatch.fnmatch(path, p) or p in path
                                  for p in spec.paths):
            continue
        if roots and not under_root(path):
            continue
        if spec.min_role_confidence and float(role.get("confidence", 0.0)) < spec.min_role_confidence:
            continue
        symbols = entry.get("symbols") or []
        if spec.kinds or spec.exported_only:
            hits = [s for s in symbols
                    if (not spec.kinds or s.get("kind") in spec.kinds)
                    and (not spec.exported_only or s.get("exported"))]
            if not hits:
                continue
            kept = [s for s in symbols if s in hits] if symbols else symbols
            entry_out = dict(entry)
            if symbols:
                entry_out["symbols"] = kept
                matched_symbols += len(kept)
        else:
            entry_out = dict(entry)
            matched_symbols += len(symbols)
        matched[path] = entry_out

    out = dict(map_dict)
    out["files"] = matched
    criteria = {key: (list(value) if isinstance(value, tuple) else value)
                for key, value in spec.to_dict().items()
                if value not in EMPTY_SENTINELS}
    out["filter"] = {
        "applied": True,
        "criteria": criteria,
        "matched_files": len(matched),
        "matched_symbols": matched_symbols,
    }
    return out
