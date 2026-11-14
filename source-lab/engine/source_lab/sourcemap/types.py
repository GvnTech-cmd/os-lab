"""Cross-language type-definition index and reference counting.

Two same-named definitions stay separate entries; ``references`` counts
resolved imports whose names mention the type; caps: 20 sites per name,
2000 names, with overflow recorded in ``coverage.limitations``.
"""

from __future__ import annotations

from typing import Dict, List

from .model import FileMap

TYPE_KINDS = {"class", "interface", "type", "enum", "struct", "trait",
              "protocol", "annotation"}

SITE_CAP = 20
NAME_CAP = 2000


def build_type_index(files: Dict[str, FileMap], limitations: List[str]) -> Dict[str, list]:
    index: Dict[str, list] = {}
    imports_by_resolved: Dict[str, List[object]] = {}
    for path in sorted(files):
        fm = files[path]
        for imp in fm.imports:
            if imp.resolved and not imp.external:
                imports_by_resolved.setdefault(imp.resolved, []).append(imp)
    sites = 0
    for path in sorted(files):
        fm = files[path]
        for sym in fm.symbols:
            if sym.kind not in TYPE_KINDS:
                continue
            sites += 1
            if sites > NAME_CAP:
                limitations.append(f"type index: {NAME_CAP} definition cap")
                return _sorted(index)
            refs = sum(
                1 for imp in imports_by_resolved.get(path, [])
                if sym.name in imp.names or not imp.names
            )
            entry = {"file": path, "line": sym.line, "kind": sym.kind,
                     "lang": fm.lang, "exported": sym.exported, "references": refs}
            bucket = index.setdefault(sym.name, [])
            if len(bucket) < SITE_CAP:
                bucket.append(entry)
            else:
                limitations.append(f"type index: {sym.name} site cap {SITE_CAP}")
    return _sorted(index)


def _sorted(index: Dict[str, list]) -> Dict[str, list]:
    return {
        name: sorted(items, key=lambda e: (e["file"], e["line"]))
        for name, items in sorted(index.items())
    }
