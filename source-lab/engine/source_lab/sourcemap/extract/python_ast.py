"""Python adapter on the stdlib ``ast`` module.

Records classes, methods, decorators, async functions, annotations, alias
imports and ``__all__`` exports.  ``TypedDict``, ``NamedTuple`` and
``NewType`` assignments enter the type index as ``type`` definitions.
"""

from __future__ import annotations

import ast
from typing import List, Optional

from ..model import ImportRef, Param, ReturnShape, Symbol
from .common import Extracted

_TYPE_BASES = {"TypedDict", "NamedTuple"}


def _unparse(node) -> Optional[str]:
    try:
        return ast.unparse(node) if node is not None else None
    except Exception:  # pragma: no cover - unparse is best effort
        return None


def _params(args: ast.arguments) -> List[Param]:
    params: List[Param] = []
    pos = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for arg, default in zip(pos, defaults):
        params.append(Param(arg.arg, _unparse(arg.annotation)))
    if args.vararg is not None:
        params.append(Param("*" + args.vararg.arg, _unparse(args.vararg.annotation)))
    for arg in args.kwonlyargs:
        params.append(Param(arg.arg, _unparse(arg.annotation)))
    if args.kwarg is not None:
        params.append(Param("**" + args.kwarg.arg, _unparse(args.kwarg.annotation)))
    return params


def _decorators(node) -> List[str]:
    out = []
    for dec in getattr(node, "decorator_list", []):
        text = _unparse(dec) or ""
        out.append("@" + text.lstrip("@"))
    return out


def _function_symbol(node, *, kind: str, exported: bool, line_offset_end: int) -> Symbol:
    returns = ReturnShape()
    if node.returns is not None:
        returns = ReturnShape(type=_unparse(node.returns), source="annotation")
    else:
        returns = _inferred_return(node)
    name = node.name
    if kind == "function" and getattr(node, "is_async", False) and False:
        pass
    return Symbol(
        kind="function" if kind == "function" else kind,
        name=name,
        line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        exported=exported,
        params=_params(node.args),
        returns=returns,
        decorators=_decorators(node),
    )


def _inferred_return(node) -> ReturnShape:
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
            keys = []
            for key in child.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.append(key.value)
            if keys:
                return ReturnShape(type="object", source="inferred",
                                   shape={k: None for k in sorted(keys)})
    return ReturnShape()


def extract(text: str) -> Extracted:
    out = Extracted()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"python parse error: {exc}") from exc

    all_exports: List[str] = []

    def handle_import(node) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                ref = ImportRef(specifier=alias.name, line=node.lineno, kind="static",
                                names=[], reason="package")
                out.imports.append(ref)
        else:  # ImportFrom
            prefix = "." * (node.level or 0)
            specifier = prefix + (node.module or "")
            names = [alias.asname or alias.name for alias in node.names]
            out.imports.append(ImportRef(specifier=specifier, line=node.lineno, kind="static",
                                         names=names, reason="relative" if node.level else "package"))

    def handle_class(node, exported: bool, members: Optional[List[str]] = None) -> None:
        bases = [_unparse(base) for base in node.bases if _unparse(base)]
        kind = "class"
        meta = {}
        if bases:
            last = bases[-1]
            leaf = last.split(".")[-1].split("[")[0]
            if leaf in _TYPE_BASES:
                kind = "type"
                meta["base"] = last
        sym = Symbol(kind=kind, name=node.name, line=node.lineno,
                     end_line=node.end_lineno or node.lineno, exported=exported,
                     decorators=_decorators(node),
                     meta={"bases": bases} if bases else {})
        sym.meta = {**(sym.meta or {}), **({"members": members} if members else {})}
        out.symbols.append(sym)

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            handle_import(node)
        elif isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "__all__" in target_names:
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    all_exports = [elt.value for elt in node.value.elts
                                   if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
            # NewType assignment: Name = NewType("Name", int)
            call = node.value if isinstance(node.value, ast.Call) else None
            if call is not None and isinstance(call.func, ast.Name) and call.func.id == "NewType":
                if target_names:
                    out.symbols.append(Symbol(kind="type", name=target_names[0],
                                              line=node.lineno, end_line=node.end_lineno or node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            call = node.value if isinstance(node.value, ast.Call) else None
            if call is not None and isinstance(call.func, ast.Name) and call.func.id == "NewType":
                out.symbols.append(Symbol(kind="type", name=node.target.id,
                                          line=node.lineno, end_line=node.end_lineno or node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sym = _function_symbol(node, kind="function", exported=False,
                                   line_offset_end=node.end_lineno or node.lineno)
            out.symbols.append(sym)
        elif isinstance(node, ast.ClassDef):
            members = [item.name for item in node.body
                       if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
            handle_class(node, exported=False, members=members)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.symbols.append(_function_symbol(item, kind="method", exported=False,
                                                        line_offset_end=item.end_lineno or item.lineno))

    for name in all_exports:
        if name not in out.exports:
            out.exports.append(name)
    return out
