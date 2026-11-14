"""Objective-C header/implementation pairing.

``#import "Local.h"`` resolves to a file and ``#import <Framework/Header.h>``
stays external (handled by the resolver).  This module adds what the import
graph cannot see: an ``@implementation Foo`` in ``Foo.m`` is paired with the
``@interface Foo`` in ``Foo.h`` by class name even when the import is
missing, and categories (``Foo (Ext)``) pair against their base class header.
Pairing records a deterministic implicit import so reference counting in the
type index stays honest.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .model import FileMap, ImportRef


def _declaration_files(files: Dict[str, FileMap]) -> Dict[str, str]:
    """class name -> header path that declares ``@interface``/``@protocol``."""
    decls: Dict[str, str] = {}
    for path in sorted(files):
        fm = files[path]
        if not path.endswith((".h", ".m", ".mm")):
            continue
        for sym in fm.symbols:
            if sym.kind in ("interface", "protocol") and sym.name not in decls:
                decls[sym.name] = path
    return decls


def pair_implementation(files: Dict[str, FileMap]) -> List[Tuple[str, str]]:
    """Add implicit implementation->header imports; returns the added pairs."""
    decls = _declaration_files(files)
    added: List[Tuple[str, str]] = []
    for path in sorted(files):
        fm = files[path]
        if not path.endswith((".m", ".mm")):
            continue
        for sym in fm.symbols:
            if sym.kind not in ("implementation", "implementation-category"):
                continue
            header = decls.get(sym.name)
            if header is None or header == path:
                continue
            already = any(imp.resolved == header for imp in fm.imports)
            if already:
                continue
            fm.imports.append(ImportRef(
                specifier=f"{sym.name}.h", line=sym.line, kind="objc-pair",
                names=[sym.name], resolved=header, external=False, reason="objc-pair"))
            added.append((path, header))
    return added
