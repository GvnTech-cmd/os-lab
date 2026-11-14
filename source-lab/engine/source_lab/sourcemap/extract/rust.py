"""Rust adapter (regex).  ``fn``, ``struct``, ``enum``, ``trait``, ``impl``,
``mod``, ``use``, ``-> T`` and attributes."""

from __future__ import annotations

import re

from ..model import ImportRef, ReturnShape, Symbol
from .common import Extracted, find_block_end, strip_comment

_FN = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)")
_STRUCT = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)")
_ENUM = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)")
_TRAIT = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)")
_IMPL = re.compile(r"^\s*impl(?:<[^>]*>)?\s+(?:([\w:<>]+)\s+for\s+)?([\w:<>]+)")
_MOD = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*[;{]")
_TYPE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?type\s+(\w+)")
_USE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+([^;]+);")
_RET = re.compile(r"\)\s*(?:->|:)\s*([\w<>\[\]:, ]+?)\s*\{?\s*$")
_ATTR = re.compile(r"^\s*#!?\[[^\]]*\]\s*$")
_PUB = re.compile(r"^\s*pub\b")


def extract(text: str) -> Extracted:
    out = Extracted()
    lines = text.splitlines()
    pending_attrs: list = []
    i = 0
    while i < len(lines):
        line = strip_comment(lines[i])
        if _ATTR.match(line):
            pending_attrs.append(line.strip())
            i += 1
            continue
        use = _USE.match(line)
        if use:
            out.imports.append(ImportRef(specifier=use.group(1).strip(), line=i + 1,
                                         kind="rust-use", names=[], reason="rust"))
            pending_attrs = []
            i += 1
            continue
        for pattern, kind in ((_STRUCT, "struct"), (_ENUM, "enum"), (_TRAIT, "trait"), (_TYPE, "type")):
            match = pattern.match(line)
            if match:
                out.symbols.append(Symbol(kind=kind, name=match.group(1), line=i + 1,
                                          exported=bool(_PUB.match(line)),
                                          decorators=list(pending_attrs)))
                pending_attrs = []
                if kind == "type":
                    end = i
                    while end < len(lines) and not lines[end].rstrip().endswith(";"):
                        end += 1
                    i = end + 1
                else:
                    end = find_block_end(lines, i)
                    i = end + 1
                break
        else:
            impl = _IMPL.match(line)
            if impl:
                end = find_block_end(lines, i)
                name = f"impl {impl.group(2)}" if not impl.group(1) else f"impl {impl.group(1)} for {impl.group(2)}"
                out.symbols.append(Symbol(kind="impl", name=name, line=i + 1, end_line=end + 1))
                i = end + 1
                continue
            mod = _MOD.match(line)
            if mod:
                if line.rstrip().endswith("{"):
                    end = find_block_end(lines, i)
                    out.symbols.append(Symbol(kind="module", name=mod.group(1), line=i + 1,
                                              end_line=end + 1, exported=bool(_PUB.match(line))))
                    i = end + 1
                else:
                    out.symbols.append(Symbol(kind="module", name=mod.group(1), line=i + 1,
                                              exported=bool(_PUB.match(line))))
                    out.imports.append(ImportRef(specifier=mod.group(1), line=i + 1,
                                                 kind="mod", names=[mod.group(1)],
                                                 reason="rust"))
                    i += 1
                continue
            fn = _FN.match(line)
            if fn:
                end = find_block_end(lines, i)
                returns = ReturnShape()
                ret = _RET.search(line.rstrip())
                if ret:
                    returns = ReturnShape(type=ret.group(1).strip(), source="annotation")
                out.symbols.append(Symbol(kind="function", name=fn.group(1), line=i + 1,
                                          end_line=end + 1, exported=bool(_PUB.match(line)),
                                          returns=returns, decorators=list(pending_attrs)))
                pending_attrs = []
                i = end + 1
                continue
            pending_attrs = []
            i += 1
    return out
