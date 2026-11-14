"""JSON, markdown and dot writers for a repo map."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def to_json(bundle: Dict[str, Any]) -> str:
    return json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def to_markdown(bundle: Dict[str, Any], limit: int = 50) -> str:
    entries = [item["path"] for item in bundle.get("entrypoints", [])]
    files = bundle.get("files", {})
    ordered = entries + [path for path in sorted(files) if path not in entries]
    lines = [f"# Repository map: {bundle.get('root', '')}", ""]
    stats = bundle.get("stats", {})
    lines.append(f"{stats.get('source_files', 0)} source files, "
                 f"{stats.get('symbols', 0)} symbols, {stats.get('edges', 0)} edges.")
    lines += ["", "| Role | File | Symbols |", "| --- | --- | --- |"]
    for path in ordered[:limit]:
        item = files[path]
        names = ", ".join(s.get("name", "") for s in item.get("symbols", [])[:6])
        lines.append(f"| {item.get('role', {}).get('kind', 'unknown')} | {path} | {names} |")
    return "\n".join(lines) + "\n"


def to_dot(bundle: Dict[str, Any]) -> str:
    lines = ["digraph repo_map {", "  rankdir=LR;"]
    for path in sorted(bundle.get("files", {})):
        lines.append(f'  "{path}";')
    for edge in bundle.get("edges", []):
        lines.append(f'  "{edge["from"]}" -> "{edge["to"]}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def write(path: Path, bundle: Dict[str, Any], fmt: str = "json") -> None:
    if fmt == "json":
        text = to_json(bundle)
    elif fmt == "md":
        text = to_markdown(bundle)
    elif fmt == "dot":
        text = to_dot(bundle)
    else:
        raise ValueError(f"unsupported format: {fmt}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
