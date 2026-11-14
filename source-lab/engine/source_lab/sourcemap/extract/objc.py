"""Objective-C adapter (``.m``, ``.mm`` and, for Apple targets or files with
Objective-C tokens, ``.h``).

Extracts ``@interface`` (incl. categories), ``@implementation``, ``@protocol``,
``@property``, methods and C functions.  ``#import "Local.h"`` resolves to a
file; ``#import <Framework/Header.h>`` and ``@import Module;`` stay external.
Primary parser is ``tree-sitter-objc`` when the optional extra is installed,
otherwise the regex fallback below (macros and conditional compilation are
syntax-only either way).
"""

from __future__ import annotations

import re

from ..model import ImportRef, ReturnShape, Symbol
from .common import Extracted, find_tag_end, param_list, strip_comment

try:  # pragma: no cover - exercised only when the extra is installed
    from . import _ts_objc as _ts  # type: ignore
except Exception:  # noqa: BLE001
    _ts = None

_INTERFACE = re.compile(
    r"^\s*@interface\s+(\w+)\s*(?::\s*([\w<>,\s]+?))?\s*(?:\((\w*)\))?\s*(?:<[^>]*>)?\s*$")
_IMPLEMENTATION = re.compile(r"^\s*@implementation\s+(\w+)\s*(?:\((\w*)\))?\s*$")
_PROTOCOL = re.compile(r"^\s*@protocol\s+(\w+)\s*(?:<[^>]*>)?\s*$")
_PROPERTY = re.compile(
    r"^\s*@property\s*(?:\(([^)]*)\))?\s*(.*?)\s*(\w+)\s*;")
_METHOD = re.compile(
    r"^\s*([-+])\s*\(\s*([^)]+?)\s*\)\s*(\w+)(?:\s*:\s*\(([^)]*)\)\s*(\w+))?")
_CFUNC = re.compile(
    r"^\s*(?:static\s+|inline\s+|extern\s+|const\s+)*[\w\*\s]+?\b(\w+)\s*\(([^;{]*)\)\s*\{")
_IMPORT_QUOTED = re.compile(r'^\s*#(?:import|include)\s*"([^"]+)"')
_IMPORT_ANGLE = re.compile(r"^\s*#(?:import|include)\s*<([^>]+)>")
_MODULE = re.compile(r"^\s*@import\s+([\w.]+)\s*;")

_OBJC_TOKENS = re.compile(
    r"@interface|@implementation|@protocol|@property|@end|@import|@autoreleasepool|"
    r"#import\s+[<\"]|\bid\s*<|IBAction|IBOutlet|\bnil\b")


def looks_like_objc(text: str) -> bool:
    """Header disambiguation: plain C/C++ headers lack every token below."""
    return bool(_OBJC_TOKENS.search(text))


def extract(text: str) -> Extracted:
    if _ts is not None:  # pragma: no cover - requires the optional extra
        try:
            return _ts.extract(text)
        except Exception:  # noqa: BLE001
            pass
    out = Extracted()
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        line = strip_comment(lines[i])
        stripped = line.strip()

        if stripped.startswith("@interface"):
            match = _INTERFACE.match(line)
            if match:
                name, super_name, category = match.group(1), match.group(2), match.group(3)
                end = find_tag_end(lines, i, "@end")
                kind = "category" if category is not None else "interface"
                meta = {}
                if category:
                    meta["category"] = category
                if super_name:
                    meta["inherits"] = super_name.strip()
                out.symbols.append(Symbol(kind=kind, name=name, line=i + 1, end_line=end + 1,
                                          meta=meta))
                # methods and properties inside the interface block
                inner = _extract_block(lines, i + 1, end, interface=True)
                out.symbols.extend(inner.symbols)
                i = end + 1
                continue
        if stripped.startswith("@implementation"):
            match = _IMPLEMENTATION.match(line)
            if match:
                name, category = match.group(1), match.group(2)
                end = find_tag_end(lines, i, "@end")
                kind = "implementation-category" if category else "implementation"
                meta = {"category": category} if category else {}
                out.symbols.append(Symbol(kind=kind, name=name, line=i + 1, end_line=end + 1,
                                          meta=meta))
                inner = _extract_block(lines, i + 1, end, interface=False)
                out.symbols.extend(inner.symbols)
                i = end + 1
                continue
        if stripped.startswith("@protocol"):
            match = _PROTOCOL.match(line)
            if match:
                end = find_tag_end(lines, i, "@end")
                out.symbols.append(Symbol(kind="protocol", name=match.group(1),
                                          line=i + 1, end_line=end + 1))
                i = end + 1
                continue
        module = _MODULE.match(line)
        if module:
            out.imports.append(ImportRef(specifier=module.group(1), line=i + 1,
                                         kind="objc-module", names=[], reason="module"))
            i += 1
            continue
        quoted = _IMPORT_QUOTED.match(line)
        if quoted:
            out.imports.append(ImportRef(specifier=quoted.group(1), line=i + 1,
                                         kind="objc-import", names=[], reason="quoted-header"))
            i += 1
            continue
        angle = _IMPORT_ANGLE.match(line)
        if angle:
            out.imports.append(ImportRef(specifier=angle.group(1), line=i + 1,
                                         kind="objc-import", names=[], reason="framework"))
            i += 1
            continue
        cfunc = _CFUNC.match(line)
        if cfunc and "(" in line and not stripped.startswith(("return", "if", "for", "while", "switch")):
            end_i = i
            depth = line.count("{") - line.count("}")
            while depth > 0 and end_i + 1 < n:
                end_i += 1
                depth += lines[end_i].count("{") - lines[end_i].count("}")
            out.symbols.append(Symbol(kind="function", name=cfunc.group(1), line=i + 1,
                                      end_line=end_i + 1,
                                      params=param_list(cfunc.group(2), style="type_first")))
            i = end_i + 1
            continue
        i += 1
    return out


def _extract_block(lines, start: int, end: int, *, interface: bool) -> Extracted:
    out = Extracted()
    i = start
    while i < end:
        line = strip_comment(lines[i])
        prop = _PROPERTY.match(line)
        if prop:
            attrs = [a.strip() for a in (prop.group(1) or "").split(",") if a.strip()]
            type_text = prop.group(2).strip()
            out.symbols.append(Symbol(kind="property", name=prop.group(3), line=i + 1,
                                      decorators=[f"{a}" for a in attrs],
                                      returns=ReturnShape(type=type_text or None,
                                                          source="annotation" if type_text else "unknown")))
            i += 1
            continue
        method = _METHOD.match(line)
        if method:
            sign, ret_type, name = method.group(1), method.group(2), method.group(3)
            params = []
            if method.group(4) is not None and method.group(4).strip():
                params.extend(param_list(method.group(4), style="type_first"))
            # collect the rest of the selector: label:(Type)name ... up to ; or {
            j = i
            while j < end and not (lines[j].rstrip().endswith(";") or lines[j].rstrip().endswith("{")):
                j += 1
            statement = " ".join(part.strip() for part in lines[i:j + 1])
            tail = statement.split(name, 1)[-1] if name in statement else ""
            for pair in re.finditer(r":\s*\(\s*([^)]*?)\s*\)\s*\w+", tail):
                params.extend(param_list(pair.group(1), style="type_first"))
            out.symbols.append(Symbol(kind="method", name=name, line=i + 1,
                                      exported=sign == "+",
                                      params=params,
                                      returns=ReturnShape(type=ret_type.strip(), source="annotation")))
            i = j + 1
            continue
        i += 1
    return out
