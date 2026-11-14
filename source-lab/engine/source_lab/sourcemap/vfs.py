"""Virtual filesystem contract.

``RepoMap`` and ``Resolver`` take a :class:`FileSystem`, never a ``Path``, so
archives never need disk extraction.  Paths are POSIX-style and relative to
the FS root; absolute paths and ``..`` segments are rejected everywhere
(path-traversal defence).

Three implementations ship here:

- :class:`DiskFS` — the real tree on disk.
- :class:`ArchiveFS` — members of one archive (e.g. ``resources/app.asar``)
  presented under a virtual ``<archive>!/`` prefix, lazily sliced out of the
  archive bytes.  Entries the host stores outside the archive (asar's
  ``unpacked`` flag) are *not* served here; the unpacked overlay on disk is
  probed instead, which keeps the resolver's ordering honest
  (inside-asar, then unpacked overlay, then external).
- :class:`OverlayFS` — several filesystems tried in order, for mounting an
  archive over the disk tree without copying anything.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class FileSystem:
    """Minimal read-only contract: list, read, exists, stat."""

    label: str = "repository"

    def list(self, path: str = "") -> List[str]:
        """Immediate children of a directory (full relative paths, sorted)."""
        raise NotImplementedError

    def read(self, path: str) -> bytes:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        raise NotImplementedError

    def is_dir(self, path: str) -> bool:
        raise NotImplementedError

    def stat(self, path: str) -> int:
        """Size in bytes."""
        raise NotImplementedError

    # -- shared helpers -------------------------------------------------
    @staticmethod
    def normalize(path: str) -> str:
        """Normalize a relative POSIX path; reject traversal and absolute paths."""
        if not path:
            return ""
        cleaned = path.replace("\\", "/")
        if cleaned.startswith("/"):
            raise ValueError(f"path traversal rejected: absolute path {path!r}")
        normalized = posixpath.normpath(cleaned)
        if normalized == ".":
            return ""
        if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
            raise ValueError(f"path traversal rejected: {path!r}")
        return normalized


class DiskFS(FileSystem):
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"root does not exist: {self.root}")
        self.label = self.root.name

    def _resolve(self, path: str) -> Path:
        normalized = self.normalize(path)
        target = (self.root / normalized).resolve() if normalized else self.root
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"path traversal rejected: {path!r}")
        return target

    def list(self, path: str = "") -> List[str]:
        base = self._resolve(path)
        if not base.is_dir():
            return []
        children = []
        for child in sorted(base.iterdir(), key=lambda p: p.name):
            children.append(f"{path}/{child.name}" if path else child.name)
        return sorted(children)

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def exists(self, path: str) -> bool:
        try:
            return self._resolve(path).exists()
        except (ValueError, OSError):
            return False

    def is_dir(self, path: str) -> bool:
        try:
            return self._resolve(path).is_dir()
        except (ValueError, OSError):
            return False

    def stat(self, path: str) -> int:
        return self._resolve(path).stat().st_size


class ArchiveFS(FileSystem):
    """One archive mounted under ``<prefix>!/``.

    ``members`` maps member-relative paths to ``(offset, size)`` inside the
    archive ``data``; offsets are relative to ``data_base``.  ``unpacked``
    lists members whose bytes live outside the archive (asar's unpacked
    overlay); they are not readable here so callers fall through to disk.
    """

    def __init__(self, inner: FileSystem, prefix: str, data: bytes,
                 members: Dict[str, Tuple[int, int]], data_base: int,
                 unpacked: Optional[set] = None):
        self.inner = inner
        self.prefix = FileSystem.normalize(prefix)
        self.data = data
        self.members = dict(members)
        self.data_base = data_base
        self.unpacked = set(unpacked or ())
        self.label = inner.label

    # -- virtual path helpers -------------------------------------------
    def _split(self, path: str) -> Tuple[bool, str]:
        normalized = FileSystem.normalize(path)
        marker = self.prefix + "!/"
        if normalized.startswith(marker):
            return True, normalized[len(marker):]
        if normalized == self.prefix + "!":
            return True, ""
        return False, normalized

    def _member_paths(self, member: str) -> List[str]:
        """Sorted virtual member paths one level under the member dir."""
        marker = self.prefix + "!/"
        results = set()
        for name in self.members:
            virtual = marker + name
            results.add(virtual)
        return sorted(results)

    # -- FileSystem contract ---------------------------------------------
    def list(self, path: str = "") -> List[str]:
        inside, rel = self._split(path)
        if not inside:
            children = list(self.inner.list(path))
            # expose the virtual mount root as a sibling of the archive file
            if FileSystem.normalize(path).rstrip("/") == posixpath.dirname(self.prefix):
                children.append(self.prefix + "!")
            return sorted(set(children))
        marker = self.prefix + "!/"
        children = set()
        target = rel.rstrip("/")
        for name in self.members:
            if target and not name.startswith(target + "/"):
                continue
            rest = name[len(target) + 1:] if target else name
            if not rest:
                continue
            child = rest.split("/", 1)[0]
            full = marker + (target + "/" if target else "") + child
            children.add(full)
        return sorted(children)

    def read(self, path: str) -> bytes:
        inside, rel = self._split(path)
        if not inside:
            return self.inner.read(path)
        if rel in self.members:
            offset, size = self.members[rel]
            start = self.data_base + offset
            return self.data[start:start + size]
        raise FileNotFoundError(f"not a packed member: {path!r}")

    def exists(self, path: str) -> bool:
        inside, rel = self._split(path)
        if not inside:
            return self.inner.exists(path)
        if rel == "":
            return True  # the virtual mount root itself
        return rel in self.members

    def is_dir(self, path: str) -> bool:
        inside, rel = self._split(path)
        if not inside:
            return self.inner.is_dir(path)
        if rel == "":
            return bool(self.members) or bool(self.unpacked)
        target = rel.rstrip("/")
        for name in self.members:
            if name.startswith(target + "/"):
                return True
        return False

    def stat(self, path: str) -> int:
        inside, rel = self._split(path)
        if not inside:
            return self.inner.stat(path)
        if rel in self.members:
            return self.members[rel][1]
        raise FileNotFoundError(path)


class OverlayFS(FileSystem):
    """First filesystem that knows a path wins; ``list`` unions all layers."""

    def __init__(self, layers: List[FileSystem]):
        if not layers:
            raise ValueError("OverlayFS needs at least one layer")
        self.layers = layers
        self.label = layers[-1].label

    def list(self, path: str = "") -> List[str]:
        children: set = set()
        for layer in self.layers:
            try:
                children.update(layer.list(path))
            except (FileNotFoundError, NotADirectoryError, OSError):
                continue
        return sorted(children)

    def read(self, path: str) -> bytes:
        for layer in self.layers:
            if layer.exists(path):
                return layer.read(path)
        raise FileNotFoundError(path)

    def exists(self, path: str) -> bool:
        return any(layer.exists(path) for layer in self.layers)

    def is_dir(self, path: str) -> bool:
        return any(layer.is_dir(path) for layer in self.layers)

    def stat(self, path: str) -> int:
        for layer in self.layers:
            if layer.exists(path):
                return layer.stat(path)
        raise FileNotFoundError(path)
