"""Data model for the structural repository map.

Every artifact the map emits is a plain dict serialized from these
dataclasses.  Nothing here is allowed to carry a Finding, a severity or a
score: the map describes structure, never evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReturnShape:
    """What a function returns.  ``source`` is annotation, inferred or unknown."""

    type: Optional[str] = None
    source: str = "unknown"
    shape: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "source": self.source, "shape": self.shape}


@dataclass
class Param:
    name: str
    type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "type": self.type}


def _param_dict(param: Any) -> Dict[str, Any]:
    """Serialize a Param, or pass through the regex/tree-sitter dict form."""
    if isinstance(param, Param):
        return param.to_dict()
    if isinstance(param, dict):
        return dict(param)
    return {"name": str(param), "type": None}


@dataclass
class Symbol:
    kind: str
    name: str
    line: int
    end_line: int = 0
    exported: bool = False
    params: List[Any] = field(default_factory=list)
    returns: ReturnShape = field(default_factory=ReturnShape)
    decorators: List[str] = field(default_factory=list)
    members: List[str] = field(default_factory=list)
    access: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "line": self.line,
            "end_line": self.end_line,
            "exported": self.exported,
            "params": [_param_dict(p) for p in self.params],
            "returns": self.returns.to_dict(),
            "decorators": list(self.decorators),
            "members": list(self.members),
        }
        if self.access is not None:
            out["access"] = self.access
        if self.meta:
            out["meta"] = dict(self.meta)
        return out


@dataclass
class ImportRef:
    specifier: str
    line: int
    kind: str = "static"
    names: List[str] = field(default_factory=list)
    resolved: Optional[str] = None
    external: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "specifier": self.specifier,
            "line": self.line,
            "kind": self.kind,
            "names": list(self.names),
            "resolved": self.resolved,
            "external": self.external,
            "reason": self.reason,
        }


@dataclass
class Role:
    kind: str = "unknown"
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": round(float(self.confidence), 3),
            "evidence": list(self.evidence),
        }


@dataclass
class FileMap:
    path: str
    lang: str
    parser: str
    loc: int = 0
    sloc: int = 0
    role: Role = field(default_factory=Role)
    exports: List[str] = field(default_factory=list)
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[ImportRef] = field(default_factory=list)

    def to_dict(self, with_symbols: bool = True) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "lang": self.lang,
            "parser": self.parser,
            "loc": self.loc,
            "sloc": self.sloc,
            "role": self.role.to_dict(),
            "exports": list(self.exports),
            "symbols": [s.to_dict() for s in self.symbols] if with_symbols else [],
            # Imports are always present: resolution and links do not depend
            # on whether symbol detail was requested (the legacy contract).
            "imports": [i.to_dict() for i in self.imports],
        }
        return out


@dataclass(frozen=True)
class Resolved:
    path: str
    reason: str
