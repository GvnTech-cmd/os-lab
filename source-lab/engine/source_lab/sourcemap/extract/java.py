"""Java adapter (regex; ``tree-sitter-java`` optional extra).

Records classes, interfaces, enums, records, annotations, methods with
visibility, ``package`` and ``import`` declarations (incl. static and
wildcard imports)."""

from __future__ import annotations

import re

from ..model import ImportRef, ReturnShape, Symbol
from .common import Extracted, find_block_end, param_list, strip_comment

_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;")
_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;")
_TYPE = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|protected\s+|private\s+|static\s+|final\s+|abstract\s+|sealed\s+|non-sealed\s+|strictfp\s+)*)"
    r"(class|interface|enum|record|@interface)\s+(\w+)"
    r"(?:\s*<[^>]*>)?"
    r"(?:\s+extends\s+([\w<>, .?]+?))?"
    r"(?:\s+implements\s+([\w<>, .?]+?))?"
    r"(?:\s*\([^)]*\))?"
    r"\s*(?:\{|\s|$)")
_METHOD = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|protected\s+|private\s+|static\s+|final\s+|abstract\s+|synchronized\s+|native\s+|default\s+|transient\s+|volatile\s+)*)"
    r"([\w<>\[\], .?]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w, .]+)?\s*\{")
_FIELD = re.compile(
    r"^\s*(?:(?:public\s+|protected\s+|private\s+|static\s+|final\s+|transient\s+|volatile\s+)*)"
    r"([\w<>\[\], .?]+)\s+(\w+)\s*(?:=[^;]*)?;")
_ANNOT = re.compile(r"^\s*@(\w+)(?:\([^)]*\))?\s*$")
_ACCESS = re.compile(r"\b(public|private|protected)\b")


def _extract_members(lines, start: int, end: int, class_name: str = "") -> list:
    """Scan a class/interface/enum body for methods and fields (flat scan)."""
    members: list = []
    i = start
    pending: list = []
    while i < end:
        raw = lines[i]
        line = strip_comment(raw)
        stripped = line.strip()
        ann = _ANNOT.match(line)
        if ann and "(" not in stripped.split(")")[-1]:
            pending.append("@" + ann.group(1))
            i += 1
            continue
        access = _ACCESS.search(line)
        access_name = access.group(1) if access else "package-private"
        method = _METHOD.match(line)
        if method and not stripped.startswith(("if", "for", "while", "switch", "catch", "return", "new")):
            member_end = find_block_end(lines, i)
            ret_type = (method.group(1) or "").strip()
            returns = ReturnShape(type=ret_type, source="annotation") if ret_type else ReturnShape()
            members.append(Symbol(kind="method", name=method.group(2), line=i + 1,
                                  end_line=member_end + 1,
                                  exported=access_name == "public",
                                  access=access_name,
                                  params=param_list(method.group(3)),
                                  returns=returns,
                                  decorators=list(pending)))
            pending = []
            i = member_end + 1
            continue
        field = _FIELD.match(line)
        if field and ";" in stripped and "(" not in stripped and not stripped.startswith(("return", "throw")):
            type_text = field.group(1).strip()
            if type_text not in ("else", "new", "return"):
                members.append(Symbol(kind="property", name=field.group(2), line=i + 1,
                                      exported=access_name == "public",
                                      access=access_name,
                                      returns=ReturnShape(type=type_text, source="annotation"),
                                      decorators=list(pending)))
            pending = []
            i += 1
            continue
        if not stripped.startswith(("@", "//", "/*", "*")):
            pending = []
        i += 1
    return members


def extract(text: str) -> Extracted:
    out = Extracted()
    lines = text.splitlines()
    pending_ann: list = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = strip_comment(raw)
        stripped = line.strip()
        pkg = _PACKAGE.match(line)
        if pkg:
            out.package = pkg.group(1)
            pending_ann = []
            i += 1
            continue
        imp = _IMPORT.match(line)
        if imp:
            out.imports.append(ImportRef(specifier=imp.group(1), line=i + 1,
                                         kind="java-import", names=[], reason="package"))
            pending_ann = []
            i += 1
            continue
        ann = _ANNOT.match(line)
        if ann:
            pending_ann.append("@" + ann.group(1))
            i += 1
            continue
        access = _ACCESS.search(line)
        access_name = access.group(1) if access else "package-private"

        type_match = _TYPE.match(line)
        if type_match:
            kind_word, name = type_match.group(1), type_match.group(2)
            kind = {"class": "class", "interface": "interface", "enum": "enum",
                    "record": "class", "@interface": "annotation"}[kind_word]
            end = find_block_end(lines, i)
            meta = {}
            if type_match.group(3):
                meta["extends"] = type_match.group(3).strip()
            if type_match.group(4):
                meta["implements"] = [p.strip() for p in type_match.group(4).split(",")]
            out.symbols.append(Symbol(kind=kind, name=name, line=i + 1, end_line=end + 1,
                                      exported=access_name == "public",
                                      access=access_name,
                                      decorators=list(pending_ann), meta=meta))
            out.symbols.extend(_extract_members(lines, i + 1, end, class_name=name))
            pending_ann = []
            i = end + 1
            continue
        method = _METHOD.match(line)
        if method and not stripped.startswith(("if", "for", "while", "switch", "catch", "return", "new")):
            end = find_block_end(lines, i)
            ret_type = (method.group(1) or "").strip()
            returns = ReturnShape(type=ret_type, source="annotation") if ret_type else ReturnShape()
            out.symbols.append(Symbol(kind="method", name=method.group(2), line=i + 1,
                                      end_line=end + 1,
                                      exported=access_name == "public",
                                      access=access_name,
                                      params=param_list(method.group(3)),
                                      returns=returns,
                                      decorators=list(pending_ann)))
            pending_ann = []
            i = end + 1
            continue
        field = _FIELD.match(line)
        if field and ";" in stripped and "(" not in stripped and not stripped.startswith(("return", "throw")):
            type_text = field.group(1).strip()
            if type_text not in ("else", "new", "return"):
                out.symbols.append(Symbol(kind="property", name=field.group(2), line=i + 1,
                                          exported=access_name == "public",
                                          access=access_name,
                                          returns=ReturnShape(type=type_text, source="annotation"),
                                          decorators=list(pending_ann)))
            pending_ann = []
            i += 1
            continue
        if not stripped.startswith(("@", "//", "/*", "*")):
            pending_ann = []
        i += 1
    return out
