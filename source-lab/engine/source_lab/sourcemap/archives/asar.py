"""Electron ``app.asar`` archive support.

Disk layout (Chromium pickle format, all integers little-endian uint32):

    [0:4]   4                       -- size of the size pickle payload
    [4:8]   header_size             -- bytes of the header pickle that follows
    [8:12]  4 + padded(json_len)    -- header pickle payload length
    [12:16] json_len                -- byte length of the UTF-8 JSON header
    [16:16+json_len]                -- the JSON directory (zero-padded to 4)

File content offsets inside the JSON are relative to the end of the header,
i.e. absolute offset = ``8 + header_size + offset``.

The JSON directory is ``{"files": {name: node}}`` where a directory node has
its own ``files`` key and a file node carries ``size``, a string ``offset``
(a string on purpose: asar keeps JS number ordering safe), and optionally
``"unpacked": true`` when the bytes live beside the archive under
``<name>.asar.unpacked/``.

Caps on entry count and uncompressed size are enforced by the caller via
``read_directory``; member paths that traverse (``..``, absolute, backslash
segments, ``.`` components, symlinks) are rejected and reported, never
mounted.
"""

from __future__ import annotations

import json
import struct
from typing import Dict, List, Tuple

HEADER_SIZE = 16


class AsarError(ValueError):
    pass


def read_header(data: bytes) -> Tuple[dict, int]:
    """Parse the pickle header; return ``(header_json_dict, data_base)``."""
    if len(data) < HEADER_SIZE:
        raise AsarError("asar too small for a header")
    magic, header_size, payload_size, json_len = struct.unpack_from("<IIII", data, 0)
    if magic != 4:
        raise AsarError(f"asar magic mismatch: {magic}")
    if header_size < 8 or 8 + header_size > len(data):
        raise AsarError("asar header size out of bounds")
    if json_len <= 0 or HEADER_SIZE + json_len > len(data):
        raise AsarError("asar json length out of bounds")
    try:
        header = json.loads(data[HEADER_SIZE:HEADER_SIZE + json_len].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AsarError(f"asar header json invalid: {exc}") from exc
    if not isinstance(header, dict) or "files" not in header:
        raise AsarError("asar header json has no files entry")
    return header, 8 + header_size


def _reject(member: str) -> bool:
    if not member or member in (".", ".."):
        return True
    if member.startswith("/") or "\\" in member:
        return True
    parts = member.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return True
    return False


def read_directory(header: dict, *, max_entries: int = 20000,
                   max_bytes: int = 64 * 1024 * 1024) -> Tuple[Dict[str, Tuple[int, int]], set, List[str]]:
    """Flatten the JSON directory.

    Returns ``(packed_members, unpacked_members, limitations)`` where
    ``packed_members`` maps member path -> ``(offset, size)`` and
    ``unpacked_members`` is the set of members stored outside the archive.
    Traversal paths are dropped and reported in ``limitations``.
    """
    packed: Dict[str, Tuple[int, int]] = {}
    unpacked: set = set()
    limitations: List[str] = []
    total = 0
    stack = [("", header.get("files", {}))]
    while stack:
        base, files = stack.pop()
        for name in sorted(files):
            node = files[name]
            if not isinstance(node, dict):
                continue
            member = f"{base}/{name}" if base else name
            if "files" in node:
                stack.append((member, node.get("files", {})))
                continue
            if "link" in node:
                limitations.append(f"asar: symlink member not mounted: {member}")
                continue
            if _reject(member):
                limitations.append(f"asar: path traversal rejected: {member}")
                continue
            size = int(node.get("size", 0) or 0)
            offset = int(node.get("offset", 0) or 0)
            if len(packed) + len(unpacked) >= max_entries:
                limitations.append(f"asar: entry cap {max_entries} reached, remaining members not mounted")
                return packed, unpacked, limitations
            total += size
            if total > max_bytes:
                limitations.append(f"asar: uncompressed cap {max_bytes} bytes reached, remaining members not mounted")
                return packed, unpacked, limitations
            if node.get("unpacked"):
                unpacked.add(member)
            else:
                packed[member] = (offset, size)
    return packed, unpacked, limitations


def load_asar(data: bytes, *, max_entries: int = 20000,
              max_bytes: int = 64 * 1024 * 1024) -> Tuple[dict, int, Dict[str, Tuple[int, int]], set, List[str]]:
    """Convenience: header + directory in one call."""
    header, data_base = read_header(data)
    packed, unpacked, limitations = read_directory(
        header, max_entries=max_entries, max_bytes=max_bytes)
    return header, data_base, packed, unpacked, limitations
