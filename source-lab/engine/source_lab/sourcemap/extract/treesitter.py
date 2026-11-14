"""Optional tree-sitter extraction with the regex extractor as a fallback."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..model import ImportRef, ReturnShape, Symbol
from ..registry import LanguageSpec
from . import php as php_extract
from . import rust as rust_extract
from . import ts as ts_extract

DECLS = {
    "ts": {"function_declaration": "function", "class_declaration": "class",
           "interface_declaration": "interface", "type_alias_declaration": "type",
           "enum_declaration": "enum", "method_definition": "method"},
    "tsx": {"function_declaration": "function", "class_declaration": "class",
            "interface_declaration": "interface", "type_alias_declaration": "type",
            "enum_declaration": "enum", "method_definition": "method"},
    "js": {"function_declaration": "function", "class_declaration": "class",
           "method_definition": "method"},
    "jsx": {"function_declaration": "function", "class_declaration": "class",
            "method_definition": "method"},
    "php": {"function_definition": "function", "class_declaration": "class",
            "interface_declaration": "interface", "trait_declaration": "trait",
            "enum_declaration": "enum", "method_declaration": "method"},
    "rust": {"function_item": "function", "struct_item": "struct",
             "enum_item": "enum", "trait_item": "trait", "impl_item": "impl",
             "mod_item": "module", "type_item": "type"},
}

_TS_IMPORTS = {"import_statement", "export_statement"}
_PHP_IMPORTS = {"namespace_use_declaration"}
_RUST_IMPORTS = {"use_declaration", "mod_item"}


def _module() -> Optional[Any]:
    try:
        import tree_sitter  # type: ignore
        return tree_sitter
    except Exception:
        return None


def available() -> bool:
    return _module() is not None


def version() -> Optional[str]:
    module = _module()
    return getattr(module, "__version__", None) if module else None


def _parser(spec: LanguageSpec):
    if not spec.grammar:
        return None
    try:
        from tree_sitter import Language, Parser  # type: ignore
        package, factory = spec.grammar
        module = __import__(package)
        language = Language(getattr(module, factory)())
        return Parser(language)
    except Exception:
        return None


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", "ignore")


def _name(node: Any, source: bytes, kind: str) -> Optional[str]:
    child = node.child_by_field_name("name")
    if child is not None:
        return _text(child, source)
    if kind == "impl":
        match = re.search(r"impl(?:<[^>]*>)?\s+([A-Za-z_]\w*)", _text(node, source))
        return match.group(1) if match else None
    for child in node.named_children:
        if child.type in {"identifier", "type_identifier", "field_identifier", "name"}:
            return _text(child, source)
    return None


def _walk(node: Any):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def _lookup(symbols: List[Symbol], name: str, line: int) -> Optional[Symbol]:
    candidates = [s for s in symbols if s.name == name]
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs(s.line - line))


def _exported(node: Any, source: bytes, lang: str) -> bool:
    prefix = _text(node, source).lstrip()
    if prefix.startswith("export ") or " export " in prefix[:40]:
        return True
    if lang == "rust" and re.match(r"(?:pub(?:\([^)]*\))?\s+)", prefix):
        return True
    if lang == "php" and not prefix.startswith(("private ", "protected ")):
        return True
    parent = getattr(node, "parent", None)
    if parent is not None and parent.type in {"export_statement"}:
        return True
    return False


def _regex_symbols(spec: LanguageSpec, source: bytes, path: str) -> List[Symbol]:
    text = source.decode("utf-8", "replace")
    if spec.name in {"ts", "tsx", "js", "jsx"}:
        return ts_extract.extract(text, spec.name).symbols
    if spec.name == "php":
        return php_extract.extract(text).symbols
    if spec.name == "rust":
        return rust_extract.extract(text).symbols
    return []


def _regex_imports(spec: LanguageSpec, source: bytes, path: str) -> List[ImportRef]:
    text = source.decode("utf-8", "replace")
    if spec.name in {"ts", "tsx", "js", "jsx"}:
        return ts_extract.extract(text, spec.name).imports
    if spec.name == "php":
        return php_extract.extract(text).imports
    if spec.name == "rust":
        return rust_extract.extract(text).imports
    return []


def _imports(spec: LanguageSpec, root: Any, source: bytes) -> List[ImportRef]:
    out: List[ImportRef] = []
    for node in _walk(root):
        text = _text(node, source)
        line = node.start_point[0] + 1
        if spec.name in {"ts", "tsx", "js", "jsx"} and node.type in _TS_IMPORTS:
            source_node = node.child_by_field_name("source")
            if source_node is None:
                continue
            specifier = _text(source_node, source).strip("'\"")
            clause = text.split("from", 1)[0]
            names = ts_extract._names(clause.split(" ", 1)[-1] if " " in clause else "")
            kind = "reexport" if node.type == "export_statement" else "static"
            out.append(ImportRef(specifier, line, kind, names))
        elif spec.name == "php" and node.type in _PHP_IMPORTS:
            match = re.search(r"use\s+(.+?);", text, re.S)
            if match:
                specifier = match.group(1).strip().split(" as ")[0]
                out.append(ImportRef(specifier, line, "static",
                                     [specifier.split("\\")[-1]]))
        elif spec.name == "rust" and node.type in _RUST_IMPORTS:
            if node.type == "mod_item" and text.rstrip().endswith(";"):
                match = re.search(r"mod\s+([A-Za-z_]\w*)", text)
                if match:
                    out.append(ImportRef(match.group(1), line, "mod", [match.group(1)]))
            elif node.type == "use_declaration":
                match = re.search(r"use\s+(.+?);", text, re.S)
                if match:
                    specifier = match.group(1).strip().split(" as ")[0]
                    out.append(ImportRef(specifier, line, "static",
                                         [specifier.split("::")[-1]]))
    return out


def extract(spec: LanguageSpec, source: bytes, path: str
            ) -> Optional[Tuple[List[Symbol], List[ImportRef], List[str], List[str]]]:
    parser = _parser(spec)
    if parser is None:
        return None
    try:
        tree = parser.parse(source)
    except Exception:
        return None
    regex_syms = _regex_symbols(spec, source, path)
    regex_imports = _regex_imports(spec, source, path)
    mapping = DECLS.get(spec.name, {})
    symbols: List[Symbol] = []
    seen = set()
    for node in _walk(tree.root_node):
        if spec.name in {"ts", "tsx", "js", "jsx"} and node.type == "lexical_declaration":
            for child in node.named_children:
                if child.type != "variable_declarator":
                    continue
                value = child.child_by_field_name("value")
                if value is None or value.type not in {"arrow_function", "function_expression"}:
                    continue
                name = _name(child, source, "const")
                if not name:
                    continue
                kind = "component" if name[:1].isupper() else ("hook" if re.match(r"use[A-Z]", name) else "const")
                symbols.append(Symbol(kind, name, child.start_point[0] + 1,
                                      child.end_point[0] + 1, _exported(node, source, spec.name)))
            continue
        kind = mapping.get(node.type)
        if not kind:
            continue
        name = _name(node, source, kind)
        if not name:
            continue
        line, end = node.start_point[0] + 1, node.end_point[0] + 1
        detail = _lookup(regex_syms, name, line)
        exported = detail.exported if detail else _exported(node, source, spec.name)
        params = detail.params if detail else []
        returns = detail.returns if detail else ReturnShape()
        decorators = detail.decorators if detail else []
        members = detail.members if detail else []
        if kind == "function" and spec.name.startswith(("ts", "js")):
            if name[:1].isupper():
                kind = "component"
            elif re.match(r"use[A-Z]", name):
                kind = "hook"
        symbols.append(Symbol(kind, name, line, end, exported, params, returns,
                              decorators, members))
        seen.add(name)
    for detail in regex_syms:
        if detail.name not in seen:
            symbols.append(detail)
    imports = _imports(spec, tree.root_node, source)
    keys = {(i.specifier, i.line, i.kind) for i in imports}
    for item in regex_imports:
        if (item.specifier, item.line, item.kind) not in keys:
            imports.append(item)
    exports = sorted({s.name for s in symbols if s.exported})
    return symbols, imports, exports, []
