"""Kotlin adapter (regex; ``tree-sitter-kotlin`` optional extra).

Records classes (data/sealed/object/enum), interfaces, functions incl.
extension functions, properties, typealiases, annotations, ``package`` and
``import`` declarations."""

from __future__ import annotations

import re

from ..model import ImportRef, ReturnShape, Symbol
from .common import Extracted, find_block_end, param_list, strip_comment

_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)")
_IMPORT = re.compile(r"^\s*import\s+([\w.*]+)")
_CLASSLIKE = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|private\s+|internal\s+|protected\s+|open\s+|abstract\s+|final\s+|sealed\s+|data\s+|inner\s+|value\s+|enum\s+)*)"
    r"(class|interface|object)\s+(\w+)"
    r"(?:\s*<[^>]*>)?"
    r"(?:\s*\(([^)]*)\))?"
    r"(?:\s*:\s*([^{]+))?")
_FUN = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|private\s+|internal\s+|protected\s+|open\s+|override\s+|abstract\s+|final\s+|suspend\s+|inline\s+|operator\s+|external\s+)*)"
    r"fun\s+(?:<[^>]*>\s*)?(?:([\w.]+)\.)?(\w+)\s*\(([^)]*)\)\s*(?::\s*([^{=\n]+))?")
_VAL = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|private\s+|internal\s+|protected\s+|open\s+|override\s+|const\s+|lateinit\s+|companion\s+)*)"
    r"(val|var)\s+(\w+)\s*(?::\s*([^{=\n]+))?")
_TYPEALIAS = re.compile(r"^\s*(?:public\s+|internal\s+|private\s+)?typealias\s+(\w+)\s*=")
_ANNOT = re.compile(r"^\s*@(\w+)")
_ACCESS = re.compile(r"\b(public|private|internal|protected)\b")
_ENUM_KW = re.compile(r"\benum\s+class\b")
_DATA_KW = re.compile(r"\bdata\s+class\b")
_SEALED_KW = re.compile(r"\bsealed\s+(?:class|interface)\b")


def extract(text: str) -> Extracted:
    out = Extracted()
    lines = text.splitlines()
    pending_ann: list = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = strip_comment(raw)
        pkg = _PACKAGE.match(line)
        if pkg:
            out.package = pkg.group(1)
            i += 1
            continue
        imp = _IMPORT.match(line)
        if imp:
            out.imports.append(ImportRef(specifier=imp.group(1), line=i + 1,
                                         kind="kotlin-import", names=[], reason="package"))
            pending_ann = []
            i += 1
            continue
        ann = _ANNOT.match(line)
        if ann:
            pending_ann.append("@" + ann.group(1))
            i += 1
            continue
        access = _ACCESS.search(line)
        access_name = access.group(1) if access else "public"

        cls = _CLASSLIKE.match(line)
        if cls:
            kind = cls.group(1)
            name = cls.group(2)
            end = find_block_end(lines, i)
            meta = {}
            if _DATA_KW.match(line):
                meta["modifiers"] = "data"
            elif _SEALED_KW.match(line):
                meta["modifiers"] = "sealed"
            elif _ENUM_KW.match(line):
                kind, meta = "enum", {"modifiers": "enum"}
            if cls.group(3):
                meta["primary_constructor"] = cls.group(3).strip()
            if cls.group(4):
                meta["inherits"] = " ".join(cls.group(4).split())
            out.symbols.append(Symbol(kind=kind if kind != "object" else "class", name=name,
                                      line=i + 1, end_line=end + 1,
                                      exported=access_name == "public",
                                      access=access_name,
                                      params=param_list(cls.group(3)) if cls.group(3) else [],
                                      decorators=list(pending_ann), meta=meta))
            out.symbols.extend(_extract_members(lines, i + 1, end))
            pending_ann = []
            i = end + 1
            continue
        fun = _FUN.match(line)
        if fun:
            end = find_block_end(lines, i)
            returns = ReturnShape()
            if fun.group(4):
                returns = ReturnShape(type=fun.group(4).strip(), source="annotation")
            meta = {}
            if fun.group(1):
                meta["receiver"] = fun.group(1)
            out.symbols.append(Symbol(kind="function", name=fun.group(2), line=i + 1,
                                      end_line=end + 1,
                                      exported=access_name == "public",
                                      access=access_name,
                                      params=param_list(fun.group(4)) if fun.group(4) else [],
                                      returns=returns,
                                      decorators=list(pending_ann), meta=meta))
            pending_ann = []
            i = end + 1
            continue
        val = _VAL.match(line)
        if val:
            out.symbols.append(Symbol(kind="property", name=val.group(2), line=i + 1,
                                      exported=access_name == "public",
                                      access=access_name,
                                      returns=ReturnShape(type=(val.group(3) or "").strip() or None,
                                                          source="annotation" if val.group(3) else "unknown"),
                                      decorators=list(pending_ann)))
            pending_ann = []
            i += 1
            continue
        alias = _TYPEALIAS.match(line)
        if alias:
            out.symbols.append(Symbol(kind="type", name=alias.group(1), line=i + 1,
                                      exported=access_name == "public",
                                      access=access_name, decorators=list(pending_ann)))
            pending_ann = []
            i += 1
            continue
        if not stripped_comment(raw):
            pending_ann = []
        i += 1
    return out


def _extract_members(lines, start: int, end: int) -> list:
    """Scan a class/object body for funcs and properties (flat scan; nested
    types' members are captured with the same rules)."""
    members: list = []
    i = start
    pending: list = []
    while i < end:
        raw = lines[i]
        line = strip_comment(raw)
        stripped = line.strip()
        ann = _ANNOT.match(line)
        if ann and not any(k in stripped for k in ("fun ", "val ", "var ", "class ")):
            pending.append("@" + ann.group(1))
            i += 1
            continue
        access = _ACCESS.search(line)
        access_name = access.group(1) if access else "public"
        fun = _FUN.match(line)
        if fun:
            member_end = find_block_end(lines, i)
            returns = ReturnShape()
            if fun.group(4):
                returns = ReturnShape(type=fun.group(4).strip(), source="annotation")
            meta = {"receiver": fun.group(1)} if fun.group(1) else {}
            members.append(Symbol(kind="function", name=fun.group(2), line=i + 1,
                                  end_line=member_end + 1,
                                  exported=access_name == "public",
                                  access=access_name,
                                  params=param_list(fun.group(4)) if fun.group(4) else [],
                                  returns=returns,
                                  decorators=list(pending), meta=meta))
            pending = []
            i = member_end + 1
            continue
        val = _VAL.match(line)
        if val:
            members.append(Symbol(kind="property", name=val.group(2), line=i + 1,
                                  exported=access_name == "public",
                                  access=access_name,
                                  returns=ReturnShape(type=(val.group(3) or "").strip() or None,
                                                      source="annotation" if val.group(3) else "unknown"),
                                  decorators=list(pending)))
            pending = []
            i += 1
            continue
        if not stripped.startswith(("@", "//", "/*", "*")):
            pending = []
        i += 1
    return members


def stripped_comment(raw: str) -> bool:
    return raw.strip().startswith(("@", "//", "/*", "*"))
