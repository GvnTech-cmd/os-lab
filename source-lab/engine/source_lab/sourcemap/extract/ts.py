"""TypeScript / TSX / JS adapter (line-aware regex; tree-sitter optional and
not packaged).  Records classes, functions, arrow functions, components,
hooks, type parameters, return annotations, re-exports and multi-line
imports with a specifier."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from ..model import ImportRef, Param, ReturnShape, Symbol
from .common import Extracted, find_block_end, infer_object_return, param_list, strip_comment

_IMPORT = re.compile(r"^\s*import\s+(?:type\s+)?(.+?)\s+from\s*['\"]([^'\"]+)['\"]\s*;?\s*$")
_IMPORT_BARE = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]\s*;?\s*$")
_IMPORT_OPEN = re.compile(r"^\s*import\s+(?:type\s+)?(.*)$")
_REEXPORT = re.compile(r"^\s*export\s+(?:type\s+)?\{(.+?)\}\s*(?:from\s*['\"]([^'\"]+)['\"])?\s*;?\s*$")
_REEXPORT_ALL = re.compile(r"^\s*export\s+\*\s*(?:as\s+(\w+)\s+)?from\s*['\"]([^'\"]+)['\"]\s*;?\s*$")
_CLASS = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)")
_FUNC = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)")
_ARROW = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?const\s+(\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::\s*[^=]+?)?=>")
_CONST = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)")
_INTERFACE = re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)")
_TYPEALIAS = re.compile(r"^\s*(?:export\s+)?type\s+(\w+)\s*[=<]")
_ENUM = re.compile(r"^\s*(?:export\s+)?(?:const\s+)?enum\s+(\w+)")
_RETURN_ANNOT = re.compile(r"\)\s*:\s*([A-Za-z_$][\w$.<>[\] |,]*)\s*(?:=>)?\s*\{?\s*$")
_REQUIRE = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
_REQUIRE_NAMES = re.compile(r"(?:const|let|var)\s+(?:\{([^}]*)\}|(\w+))\s*=\s*(?:async\s*)?require\s*\(")
_DEFAULT = re.compile(r"^\s*export\s+default\s+")


def _params_from_line(line: str) -> List[Param]:
    """Extract the parenthesised parameter list from a declaration line."""
    start = line.find("(")
    if start < 0:
        return []
    depth = 0
    for index in range(start, len(line)):
        if line[index] == "(":
            depth += 1
        elif line[index] == ")":
            depth -= 1
            if depth == 0:
                return param_list(line[start + 1:index], style="name_first")
    return []


def _names(clause: str) -> List[str]:
    """Legacy helper used by the tree-sitter path: import clause -> names."""
    clause = clause.strip().rstrip(";")
    if not clause:
        return []
    if clause.startswith("*"):
        return [clause.lstrip("* ").split(" as ")[-1].strip()]
    if "{" in clause and "}" in clause:
        body = clause[clause.index("{") + 1:clause.rindex("}")]
        names = []
        for item in body.split(","):
            item = item.strip()
            if not item:
                continue
            names.append(item.split(" as ")[-1].strip())
        return names
    return [part for part in clause.replace(",", " ").split() if part]


def _is_component(name: str, lang: str) -> bool:
    return lang in ("tsx", "jsx") and name[:1].isupper()


def extract(text: str, lang: str = "ts") -> Extracted:
    out = Extracted()
    lines = text.splitlines()
    pending: Optional[Tuple[int, str]] = None  # (line_no, buffered) for multi-line imports
    exports: List[str] = []
    default_exported = False

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = strip_comment(raw)
        stripped = line.strip()

        # continue a multi-line import
        if pending is not None:
            buffered = pending[1] + " " + stripped
            if "from" in buffered and ("'" in buffered or '"' in buffered):
                match = re.search(r"(.+?)\s+from\s*['\"]([^'\"]+)['\"]", buffered)
                if match:
                    out.imports.append(ImportRef(specifier=match.group(2), line=pending[0],
                                                 kind="static",
                                                 names=[n.strip().split(" as ")[-1] for n in match.group(1).strip("{}").split(",") if n.strip()],
                                                 reason="unresolved"))
                pending = None
            elif len(stripped) > 0:
                pending = (pending[0], buffered)
            i += 1
            continue

        # CommonJS require(): electron mains and preload scripts use it
        req_names = _REQUIRE_NAMES.search(line)
        req = _REQUIRE.search(line)
        if req and (req_names or not stripped.startswith("const")):
            names = []
            if req_names:
                if req_names.group(1):
                    names = [n.strip().split(":")[0].strip() for n in req_names.group(1).split(",") if n.strip()]
                elif req_names.group(2):
                    names = [req_names.group(2)]
            out.imports.append(ImportRef(specifier=req.group(1), line=i + 1,
                                         kind="require", names=names, reason="unresolved"))
            i += 1
            continue

        match = _IMPORT.match(line)
        if match:
            names_part, specifier = match.group(1), match.group(2)
            names = [n.strip() for n in names_part.strip("{}").split(",") if n.strip()]
            out.imports.append(ImportRef(specifier=specifier, line=i + 1, kind="static",
                                         names=[n.split(" as ")[-1] for n in names],
                                         reason="unresolved"))
            i += 1
            continue
        if _IMPORT_BARE.match(line):
            out.imports.append(ImportRef(specifier=_IMPORT_BARE.match(line).group(1),
                                         line=i + 1, kind="static-side-effect",
                                         names=[], reason="unresolved"))
            i += 1
            continue
        open_match = _IMPORT_OPEN.match(line)
        if open_match and ";" not in open_match.group(1) and "{" in open_match.group(1):
            pending = (i + 1, open_match.group(1))
            i += 1
            continue

        reexp = _REEXPORT.match(line)
        if reexp:
            names = [n.strip().split(" as ")[-1] for n in reexp.group(1).split(",") if n.strip()]
            exports.extend(names)
            if reexp.group(2):
                out.imports.append(ImportRef(specifier=reexp.group(2), line=i + 1,
                                             kind="reexport", names=names, reason="unresolved"))
            i += 1
            continue
        all_match = _REEXPORT_ALL.match(line)
        if all_match:
            out.imports.append(ImportRef(specifier=all_match.group(2), line=i + 1,
                                         kind="reexport", names=[], reason="unresolved"))
            i += 1
            continue

        is_export_line = stripped.startswith("export ")
        if _DEFAULT.match(line):
            default_exported = True

        class_match = _CLASS.match(line)
        if class_match:
            name = class_match.group(1)
            end = find_block_end(lines, i)
            out.symbols.append(Symbol(kind="class", name=name, line=i + 1, end_line=end + 1,
                                      exported=is_export_line or default_exported))
            i = end + 1
            continue

        interface_match = _INTERFACE.match(line)
        if interface_match:
            name = interface_match.group(1)
            end = find_block_end(lines, i)
            out.symbols.append(Symbol(kind="interface", name=name, line=i + 1, end_line=end + 1,
                                      exported=is_export_line))
            exports.append(name) if is_export_line else None
            i = end + 1
            continue

        enum_match = _ENUM.match(line)
        if enum_match:
            name = enum_match.group(1)
            end = find_block_end(lines, i)
            out.symbols.append(Symbol(kind="enum", name=name, line=i + 1, end_line=end + 1,
                                      exported=is_export_line))
            if is_export_line:
                exports.append(name)
            i = end + 1
            continue

        type_match = _TYPEALIAS.match(line)
        if type_match:
            name = type_match.group(1)
            end = i
            while end < len(lines) and not lines[end].rstrip().endswith(";"):
                end += 1
            out.symbols.append(Symbol(kind="type", name=name, line=i + 1, end_line=end + 1,
                                      exported=is_export_line))
            if is_export_line:
                exports.append(name)
            i = end + 1
            continue

        func_match = _FUNC.match(line)
        arrow_match = _ARROW.match(line)
        if func_match or arrow_match:
            name = (func_match or arrow_match).group(1)
            end = find_block_end(lines, i)
            kind = "hook" if re.match(r"^use[A-Z0-9]", name) else (
                "component" if _is_component(name, lang) else "function")
            returns = ReturnShape()
            annot = _RETURN_ANNOT.search(line.rstrip())
            if annot:
                returns = ReturnShape(type=annot.group(1).strip(), source="annotation")
            else:
                returns = infer_object_return(lines[i:end + 1])
            out.symbols.append(Symbol(kind=kind, name=name, line=i + 1, end_line=end + 1,
                                      exported=is_export_line or default_exported,
                                      params=_params_from_line(line),
                                      returns=returns))
            if is_export_line:
                exports.append(name)
            i = end + 1
            continue

        const_match = _CONST.match(line)
        if const_match and ("=> " in line or "=>" in line or "require(" in line):
            name = const_match.group(1)
            end = find_block_end(lines, i)
            kind = "hook" if re.match(r"^use[A-Z0-9]", name) else (
                "component" if _is_component(name, lang) else "const")
            out.symbols.append(Symbol(kind=kind, name=name, line=i + 1, end_line=end + 1,
                                      exported=is_export_line or default_exported,
                                      params=_params_from_line(line)))
            if is_export_line:
                exports.append(name)
            i = end + 1
            continue

        i += 1

    out.exports = list(dict.fromkeys(exports))
    if default_exported:
        out.exports.insert(0, "default")
    return out
