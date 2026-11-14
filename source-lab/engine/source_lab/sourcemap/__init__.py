"""Structural repository map: symbols, resolved imports, roles and targets.

Public surface: :class:`~sourcemap.engine.RepoMap`,
:class:`~sourcemap.filter.MapFilter`, :func:`~sourcemap.filter.filter_map`
and the optional parse-tree / archive backends.
"""

from .engine import Caps, RepoMap
from .filter import MapFilter, filter_map
from .model import FileMap, ImportRef, Role, Symbol
from .vfs import ArchiveFS, DiskFS, FileSystem, OverlayFS

__all__ = [
    "ArchiveFS", "Caps", "DiskFS", "FileMap", "FileSystem", "ImportRef",
    "MapFilter", "OverlayFS", "RepoMap", "Role", "Symbol", "filter_map",
]
