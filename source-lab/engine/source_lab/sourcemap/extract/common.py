"""Shared helpers for line-aware extractors.

Extractors are regex- or scanner-based on purpose: the tree-sitter grammars
are optional extras and are not packaged here.  Whatever parser actually ran
is recorded in ``toolchain`` and per-file ``parser``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..model import Param, ReturnShape, Symbol, ImportRef


@dataclass
class Extracted:
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[ImportRef] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    package: Optional[str] = None          # kotlin/java package declaration
    annotations: List[str] = field(default_factory=list)  # file-level notes


def strip_comment(line: str) -> str:
    """Remove // comments and block-comment markers; good enough for signatures."""
    out = []
    in_str = None
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str:
            out.append(ch)
            if ch == in_str and (i == 0 or line[i - 1] != "\\"):
                in_str = None
            i += 1
            continue
        if ch in "\"'`":
            in_str = ch
            out.append(ch)
        elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def find_block_end(lines: List[str], start: int) -> int:
    """Return the index of the line closing the brace opened at/after ``start``."""
    depth = 0
    started = False
    for idx in range(start, len(lines)):
        for ch in lines[idx]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth <= 0:
                    return idx
    return len(lines) - 1


def find_tag_end(lines: List[str], start: int, tag: str) -> int:
    """Find the line index of ``@end``/closing tag starting after ``start``."""
    for idx in range(start, len(lines)):
        if lines[idx].strip() == tag:
            return idx
    return len(lines) - 1


def split_top_level(text: str, sep: str = ",") -> List[str]:
    parts: List[str] = []
    depth = 0
    cur: List[str] = []
    for ch in text:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    last = "".join(cur).strip()
    if last:
        parts.append(last)
    return parts


def param_list(signature: str, style: str = "name_first") -> List[Param]:
    """Parse a parameter list from a signature body (inside the parens)."""
    params: List[Param] = []
    for raw in split_top_level(signature):
        if not raw or raw in ("self", "cls", "_"):
            continue
        if style == "name_first":  # name: Type
            if ":" in raw:
                name, _, typ = raw.partition(":")
                params.append(Param(name.strip().lstrip("_").split(": ")[-1], typ.strip() or None))
            else:
                params.append(Param(raw.strip(), None))
        elif style == "type_first":  # Type name  or  Type *name
            tokens = raw.replace("*", " ").split()
            if len(tokens) >= 2:
                params.append(Param(tokens[-1].lstrip("*_"), " ".join(tokens[:-1])))
            elif tokens:
                params.append(Param(tokens[0].lstrip("*_"), None))
        elif style == "swift":  # [external_label ]name: Type
            if ":" in raw:
                left, _, typ = _partition_top(raw, ":")
                tokens = left.split()
                name = tokens[0] if tokens else left.strip()
                params.append(Param(name, typ.strip() or None))
            else:
                tokens = raw.split()
                params.append(Param(tokens[-1].strip() if tokens else raw.strip(), None))
    return params


def _partition_top(text: str, sep: str) -> Tuple[str, str, str]:
    """Split on the first top-level separator; returns (left, sep, right)."""
    depth = 0
    for i, ch in enumerate(text):
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        elif ch == sep and depth == 0:
            return text[:i], sep, text[i + 1:]
    return text, "", ""


def infer_object_return(body: List[str]) -> ReturnShape:
    """A single-line ``return { ... }`` becomes an inferred sorted key shape."""
    for line in body:
        stripped = line.strip()
        if stripped.startswith("return") and "{" in stripped and "}" in stripped:
            inner = stripped[stripped.index("{") + 1:stripped.rindex("}")]
            keys = sorted({k.strip().strip("'\"") for k in split_top_level(inner) if k})
            keys = [k.split(":")[0].strip().strip("'\"") for k in keys if k]
            return ReturnShape(type="object", source="inferred", shape={k: None for k in sorted(keys)})
    return ReturnShape()


def merge_meta(target: Dict, extra: Dict) -> Dict:
    out = dict(target)
    for key, value in extra.items():
        if value is not None and value != [] and value != {}:
            out[key] = value
    return out
