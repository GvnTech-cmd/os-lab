"""Swift adapter.

Primary parser is ``tree-sitter-swift`` when the optional extra is
installed; otherwise the line-aware regex fallback below runs and ``parser``
records ``regex``.  Swift modules are never file-resolved: local files
belong to a target, not an import path, so every ``import Module`` (and
``@testable import``) is external.
"""

from __future__ import annotations

import re
from typing import List

from ..model import ImportRef, ReturnShape, Symbol

try:  # pragma: no cover - exercised only when the extra is installed
    from . import _ts_swift as _ts  # type: ignore
except Exception:  # noqa: BLE001
    _ts = None

from .common import Extracted, find_block_end, param_list, strip_comment

_ATTR = re.compile(r"@\w+(?:\([^)]*\))?")
_ACCESS = re.compile(r"\b(public|open|internal|private|fileprivate)\b")
_CLASSLIKE = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|open\s+|internal\s+|private\s+|fileprivate\s+|final\s+|static\s+|abstract\s+)*)"
    r"(class|struct|enum|protocol|extension)\s+(\w+)"
    r"(?:\s*<[^>]*>)?"
    r"(?:\s*:\s*[^{]+)?")
_TYPEALIAS = re.compile(r"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+)?typealias\s+(\w+)\s*(=|:)")
_FUNC = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|open\s+|internal\s+|private\s+|fileprivate\s+|static\s+|class\s+|final\s+|override\s+|mutating\s+|required\s+|convenience\s+|lazy\s+|weak\s+)*)"
    r"(?:func\s+(\w+|`[^`]+`)|init\s*[?(]|deinit\b)")
_PROPLIKE = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?\s+|public\s+|open\s+|internal\s+|private\s+|fileprivate\s+|static\s+|class\s+|final\s+|override\s+|lazy\s+|weak\s+|mutating\s+)*)"
    r"(let|var)\s+(\w+)\s*(?::\s*([^={\n]+))?\s*[={=\n]")
_IMPORT = re.compile(r"^\s*(?:@testable\s+|@_exported\s+)?import\s+([\w.]+)")
_RET = re.compile(r"\)\s*(?:async\s+)?(?:throws\s+)?->\s*([^\s{]+)")


def looks_like_swift(text: str) -> bool:  # kept for symmetry with objc
    return bool(re.search(r"\b(func|struct|protocol|extension)\b", text))


def _extract_members(lines, start: int, end: int) -> List[Symbol]:
    """Scan a type/extension body for funcs, inits and properties.

    Deliberately flat: nested types are rare in app code and their members
    are captured with the same rules; a nested ``func`` inside another
    function is not a declaration we care about but is tolerated.
    """
    members: List[Symbol] = []
    i = start
    pending: List[str] = []
    while i < end:
        raw = lines[i]
        line = strip_comment(raw)
        stripped = line.strip()
        if stripped.startswith("import "):
            i += 1
            continue
        attrs = _attributes(line)
        if stripped.startswith("@") and "(" not in stripped.split("@")[-1].split(" ")[0]:
            # a bare attribute line carries to the next declaration
            if not any(k in stripped for k in ("func ", "init", "deinit", "var ", "let ")):
                pending.extend(attrs)
                i += 1
                continue
        access = _ACCESS.search(line)
        access_name = access.group(1) if access else "internal"
        func = _FUNC.match(line)
        if func:
            member_end = find_block_end(lines, i)
            head_end = line.index("(") if "(" in line else len(line)
            params_text = line[head_end + 1:line.rindex(")", head_end)] if ")" in line else ""
            params = param_list(params_text, style="swift")
            returns = ReturnShape()
            ret = _RET.search(line.rstrip())
            if ret:
                returns = ReturnShape(type=ret.group(1).strip(), source="annotation")
            if func.group(1):
                name = func.group(1).strip("`")
                kind = "method"
            elif stripped.startswith("init"):
                name, kind = "init", "method"
            else:
                name, kind = "deinit", "method"
            members.append(Symbol(
                kind=kind, name=name, line=i + 1, end_line=member_end + 1,
                exported=access_name in ("public", "open"),
                access=access_name, params=params, returns=returns,
                decorators=list(dict.fromkeys(pending + attrs))))
            pending = []
            i = member_end + 1
            continue
        prop = _PROPLIKE.match(line)
        if prop:
            members.append(Symbol(
                kind="property", name=prop.group(2), line=i + 1,
                exported=access_name in ("public", "open"),
                access=access_name,
                returns=ReturnShape(type=(prop.group(3) or "").strip() or None,
                                    source="annotation" if prop.group(3) else "unknown"),
                decorators=list(dict.fromkeys(pending + attrs))))
            pending = []
            i += 1
            continue
        if not stripped.startswith(("@", "//", "/*", "*")):
            pending = []
        i += 1
    return members


def _attributes(line: str) -> List[str]:
    found = _ATTR.findall(line.split(":")[0])
    return [a for a in found if a not in ("@end",)]


def extract(text: str) -> Extracted:
    if _ts is not None:  # pragma: no cover - requires the optional extra
        try:
            return _ts.extract(text)
        except Exception:  # noqa: BLE001 - fall back to regex
            pass
    out = Extracted()
    lines = text.splitlines()
    pending_attrs: List[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = strip_comment(raw)
        stripped = line.strip()

        import_match = _IMPORT.match(line)
        if import_match:
            out.imports.append(ImportRef(
                specifier=import_match.group(1), line=i + 1, kind="swift-import",
                names=[], reason="swift-module"))
            pending_attrs = []
            i += 1
            continue

        attrs = _attributes(line)
        access = _ACCESS.search(line)
        access_name = access.group(1) if access else "internal"

        classlike = _CLASSLIKE.match(line)
        if classlike:
            kind, name = classlike.group(1), classlike.group(2)
            end = find_block_end(lines, i)
            meta = {}
            inherits = line.split(":", 1)[1].strip() if ":" in line and kind != "extension" else ""
            if kind == "extension":
                meta["extends"] = name
            elif inherits:
                meta["inherits"] = inherits.rstrip("{").strip()
            out.symbols.append(Symbol(
                kind=kind, name=name, line=i + 1, end_line=end + 1,
                exported=access_name in ("public", "open"),
                access=access_name,
                decorators=list(dict.fromkeys(pending_attrs + attrs)),
                meta=meta))
            out.symbols.extend(_extract_members(lines, i + 1, end))
            pending_attrs = []
            i = end + 1
            continue

        typealias = _TYPEALIAS.match(line)
        if typealias:
            out.symbols.append(Symbol(kind="type", name=typealias.group(1), line=i + 1,
                                      exported=access_name in ("public", "open"),
                                      access=access_name,
                                      decorators=list(dict.fromkeys(pending_attrs))))
            pending_attrs = []
            i += 1
            continue

        func = _FUNC.match(line)
        if func:
            end = find_block_end(lines, i)
            head_end = line.index("(") if "(" in line else len(line)
            params_text = line[head_end + 1:line.rindex(")", head_end)] if ")" in line else ""
            params = param_list(params_text, style="swift")
            returns = ReturnShape()
            ret = _RET.search(line.rstrip())
            if ret:
                returns = ReturnShape(type=ret.group(1).strip(), source="annotation")
            if func.group(1):
                name = func.group(1).strip("`")
                # indented declarations sit inside a type or extension body
                kind = "method" if raw[:1] in (" ", "\t") else "function"
            elif line.strip().startswith("init"):
                name, kind = "init", "method"
            else:
                name, kind = "deinit", "method"
            out.symbols.append(Symbol(
                kind=kind, name=name, line=i + 1, end_line=end + 1,
                exported=access_name in ("public", "open"),
                access=access_name,
                params=params, returns=returns,
                decorators=list(dict.fromkeys(pending_attrs + attrs))))
            pending_attrs = []
            i = end + 1
            continue

        prop = _PROPLIKE.match(line)
        if prop and not stripped.startswith("//"):
            kind_word, name = prop.group(1), prop.group(2)
            type_text = (prop.group(3) or "").strip()
            out.symbols.append(Symbol(
                kind="property", name=name, line=i + 1,
                exported=access_name in ("public", "open"),
                access=access_name,
                returns=ReturnShape(type=type_text or None,
                                    source="annotation" if type_text else "unknown"),
                decorators=list(dict.fromkeys(pending_attrs + attrs))))
            pending_attrs = []
            i += 1
            continue

        if attrs and stripped.startswith("@"):
            pending_attrs.extend(attrs)
        elif stripped:
            pending_attrs = []
        i += 1
    return out
