"""Extractor dispatch for every supported language.

The legacy ``extract`` signature returns the five-tuple the first engine used
(symbols, imports, exports, limitations, parser).  The adapter engine calls
``extract_structured`` for the richer :class:`~sourcemap.extract.common.Extracted`
record that also carries a package declaration.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..model import ImportRef, Symbol
from ..registry import LanguageSpec
from .common import Extracted


def _text(source) -> str:
    if isinstance(source, bytes):
        return source.decode("utf-8", errors="replace")
    return source


def extract_structured(spec: LanguageSpec, source, path: str
                       ) -> Tuple[Extracted, List[str], str]:
    """Return ``(record, limitations, parser)`` for one file."""
    text = _text(source)
    if isinstance(spec.grammar, tuple):
        from .treesitter import available, extract as run_ts
        if available():
            result = run_ts(spec, text.encode("utf-8"), path)
            if result is not None:
                symbols, imports, exports, limits = result
                return Extracted(symbols=symbols, imports=imports, exports=exports), limits, "tree-sitter"

    if spec.extractor == "python_ast":
        from .python_ast import extract as run
    elif spec.extractor == "ts":
        from .ts import extract as run
        record = run(text, spec.name)
        return record, [], spec.parser
    elif spec.extractor == "php":
        from .php import extract as run
    elif spec.extractor == "rust":
        from .rust import extract as run
    elif spec.extractor == "markup":
        from .markup import extract as run
        record = run(text, spec.name)
        return record, [], spec.parser
    elif spec.extractor == "android_xml":
        from .android_xml import extract as run
        return run(text, path), [], spec.parser
    elif spec.extractor in {"swift", "objc", "kotlin", "java"}:
        module = {"swift": "swift", "objc": "objc",
                  "kotlin": "kotlin", "java": "java"}[spec.extractor]
        from importlib import import_module
        run = import_module(f".{module}", __package__).extract
        return run(text), [], spec.parser
    elif spec.extractor in {"plist", "json"}:
        from .plist import extract as run
        return run(text, path), [], spec.parser
    else:
        raise ValueError(f"no extractor for {spec.extractor}")

    record = run(text)
    return record, [], spec.parser


def extract(spec: LanguageSpec, source, path: str
            ) -> Tuple[List[Symbol], List[ImportRef], List[str], List[str], str]:
    record, limits, parser = extract_structured(spec, source, path)
    return record.symbols, record.imports, record.exports, limits, parser
