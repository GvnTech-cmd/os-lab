"""PHP adapter (regex).  Namespace, ``use``, class/trait/interface/enum,
methods with visibility and return type, ``require``/``include`` literals."""

from __future__ import annotations

import re

from ..model import ImportRef, ReturnShape, Symbol
from .common import Extracted, find_block_end, strip_comment

_NAMESPACE = re.compile(r"^\s*namespace\s+([\w\\\\]+)\s*;",)
_USE = re.compile(r"^\s*use\s+([\w\\\\]+)(?:\s+as\s+(\w+))?\s*;",)
_CLASSLIKE = re.compile(
    r"^\s*(?:abstract\s+|final\s+)?(class|interface|trait|enum)\s+(\w+)"
    r"(?:\s+extends\s+([\w\\\\]+))?(?:\s+implements\s+([\w\\\\,\s]+))?")
_METHOD = re.compile(
    r"^\s*(?:public|protected|private)?\s*(?:static\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*(?:\:\s*([\w?\\\\\[\]|]+))?")
_REQUIRE = re.compile(r"(?:require|include)(?:_once)?\s*\(?\s*['\"]([^'\"]+)['\"]")
_VISIBILITY = re.compile(r"^\s*(public|protected|private)")


def extract(text: str) -> Extracted:
    out = Extracted()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = strip_comment(lines[i])
        ns = _NAMESPACE.match(line)
        if ns:
            out.package = ns.group(1).replace("\\", ".")
            i += 1
            continue
        use = _USE.match(line)
        if use:
            name = use.group(2) or use.group(1).split("\\")[-1]
            out.imports.append(ImportRef(specifier=use.group(1), line=i + 1,
                                         kind="static", names=[name], reason="psr4"))
            i += 1
            continue
        req = _REQUIRE.search(line)
        if req:
            out.imports.append(ImportRef(specifier=req.group(1), line=i + 1,
                                         kind="require", names=[], reason="require"))
            i += 1
            continue
        cls = _CLASSLIKE.match(line)
        if cls:
            kind = {"class": "class", "interface": "interface",
                    "trait": "trait", "enum": "enum"}[cls.group(1)]
            end = find_block_end(lines, i)
            sym = Symbol(kind=kind, name=cls.group(2), line=i + 1, end_line=end + 1,
                         meta={"extends": cls.group(3)} if cls.group(3) else {})
            out.symbols.append(sym)
            i = end + 1
            continue
        method = _METHOD.match(line)
        if method:
            visibility = _VISIBILITY.match(line)
            returns = ReturnShape(type=method.group(3), source="annotation") if method.group(3) else ReturnShape()
            out.symbols.append(Symbol(kind="method", name=method.group(1), line=i + 1,
                                      exported=bool(visibility and visibility.group(1) == "public"),
                                      returns=returns))
            i += 1
            continue
        i += 1
    return out
