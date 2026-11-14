"""Electron ASAR archive reader: the JSON header and the byte range of every file."""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

MAX_ENTRIES = 20000
MAX_HEADER = 32 * 1024 * 1024


@dataclass
class AsarEntry:
    path: str
    size: int
    offset: int  # absolute offset in the archive, or -1 for files stored outside it ("unpacked")
    unpacked: bool = False


@dataclass
class AsarArchive:
    entries: List[AsarEntry]
    data_start: int
    integrity: bool  # the header carries per-file integrity hashes


def _walk(node: Dict[str, Any], prefix: str, base: int, out: List[AsarEntry]) -> None:
    for name, child in (node.get("files") or {}).items():
        if len(out) >= MAX_ENTRIES:
            return
        path = f"{prefix}{name}"
        if isinstance(child, dict) and "files" in child:
            _walk(child, f"{path}/", base, out)
        elif isinstance(child, dict):
            unpacked = bool(child.get("unpacked"))
            offset = -1 if unpacked else base + int(child.get("offset", 0))
            out.append(AsarEntry(path=path, size=int(child.get("size", 0)), offset=offset, unpacked=unpacked))


def parse_asar(data: bytes) -> Optional[AsarArchive]:
    """Parses an ASAR archive held in memory; None when `data` is not one."""
    try:
        if len(data) < 16:
            return None
        pickle_size, header_size, _payload, str_len = struct.unpack_from("<IIII", data, 0)
        if pickle_size != 4 or header_size < 8 or header_size > MAX_HEADER or 16 + str_len > len(data):
            return None
        header = json.loads(data[16 : 16 + str_len].decode("utf-8", errors="replace"))
        if not isinstance(header, dict) or "files" not in header:
            return None
        base = 8 + header_size
        entries: List[AsarEntry] = []
        _walk(header, "", base, entries)
        has_integrity = any("integrity" in str(v)[:400] for v in list((header.get("files") or {}).values())[:3])
        return AsarArchive(entries=entries, data_start=base, integrity=has_integrity)
    except (struct.error, ValueError, TypeError):
        return None


def read_entry(data: bytes, entry: AsarEntry, limit: int = 2 * 1024 * 1024) -> Optional[bytes]:
    """The bytes of one packed entry, truncated to `limit`; None for unpacked or out-of-range entries."""
    if entry.unpacked or entry.offset < 0 or entry.offset + entry.size > len(data):
        return None
    return data[entry.offset : entry.offset + min(entry.size, limit)]


def iter_text_entries(data: bytes, archive: AsarArchive, suffixes=(".js", ".cjs", ".mjs", ".json", ".html")) -> Iterator[tuple]:
    """(path, text) for packed source-like entries, skipping node_modules."""
    for entry in archive.entries:
        if "node_modules/" in entry.path or not entry.path.lower().endswith(suffixes):
            continue
        raw = read_entry(data, entry)
        if raw is not None:
            yield entry.path, raw.decode("utf-8", errors="ignore")
