"""Mach-O parser: load commands, sections, undefined symbols and the embedded code signature with its entitlements."""

from __future__ import annotations

import plistlib
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

MAX_COMMANDS = 2000
MAX_SYMBOLS = 20000
MAX_SLICES = 8

_MH_MAGICS = {0xFEEDFACE: ("<", False), 0xFEEDFACF: ("<", True), 0xCEFAEDFE: (">", False), 0xCFFAEDFE: (">", True)}
_FAT_MAGICS = {0xCAFEBABE: ">", 0xCAFEBABF: ">"}
_CPU = {7: "x86", 0x01000007: "x86_64", 12: "arm", 0x0100000C: "arm64", 0x0200000C: "arm64_32"}
_FILETYPE = {1: "object", 2: "executable", 6: "dylib", 7: "dylinker", 8: "bundle", 9: "dsym", 10: "kext"}

LC_SEGMENT, LC_SYMTAB, LC_SEGMENT_64, LC_CODE_SIGNATURE = 0x1, 0x2, 0x19, 0x1D
LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB = 0xC, 0x80000018, 0x8000001F
LC_LAZY_LOAD_DYLIB, LC_LOAD_UPWARD_DYLIB = 0x20, 0x80000023
LC_RPATH, LC_DYLD_ENVIRONMENT = 0x8000001C, 0x27

_DYLIB_COMMANDS = {
    LC_LOAD_DYLIB: "LC_LOAD_DYLIB",
    LC_LOAD_WEAK_DYLIB: "LC_LOAD_WEAK_DYLIB",
    LC_REEXPORT_DYLIB: "LC_REEXPORT_DYLIB",
    LC_LAZY_LOAD_DYLIB: "LC_LAZY_LOAD_DYLIB",
    LC_LOAD_UPWARD_DYLIB: "LC_LOAD_UPWARD_DYLIB",
}

CS_ADHOC = 0x2
CS_RUNTIME = 0x10000
CS_LINKER_SIGNED = 0x20000


@dataclass
class CodeSignatureInfo:
    flags: int = 0
    identifier: Optional[str] = None
    team_id: Optional[str] = None
    entitlements: Dict[str, Any] = field(default_factory=dict)

    @property
    def adhoc(self) -> bool:
        return bool(self.flags & CS_ADHOC)

    @property
    def hardened_runtime(self) -> bool:
        return bool(self.flags & CS_RUNTIME)


@dataclass
class MachOInfo:
    cpu: str
    filetype: str
    is_64: bool
    #: (load command name, install name)
    dylibs: List[Tuple[str, str]] = field(default_factory=list)
    rpaths: List[str] = field(default_factory=list)
    #: (segment, section)
    sections: List[Tuple[str, str]] = field(default_factory=list)
    undefined_symbols: List[str] = field(default_factory=list)
    dyld_environment: List[str] = field(default_factory=list)
    signature: Optional[CodeSignatureInfo] = None

    def has_section(self, section: str) -> bool:
        return any(s == section for _seg, s in self.sections)


def _name(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def _parse_signature(blob: bytes) -> Optional[CodeSignatureInfo]:
    """Reads the SuperBlob of an LC_CODE_SIGNATURE: code directory flags, identifier, team id and entitlements."""
    try:
        if len(blob) < 12 or struct.unpack_from(">I", blob, 0)[0] != 0xFADE0CC0:
            return None
        count = struct.unpack_from(">I", blob, 8)[0]
        info = CodeSignatureInfo()
        for i in range(min(count, 32)):
            slot_type, offset = struct.unpack_from(">II", blob, 12 + i * 8)
            if offset + 8 > len(blob):
                continue
            magic, length = struct.unpack_from(">II", blob, offset)
            body = blob[offset : offset + length]
            if magic == 0xFADE0C02:  # CodeDirectory
                version, flags = struct.unpack_from(">II", body, 8)
                info.flags = flags
                ident_off = struct.unpack_from(">I", body, 20)[0]
                end = body.find(b"\x00", ident_off)
                info.identifier = body[ident_off : end if end != -1 else ident_off + 64].decode("utf-8", errors="replace")
                if version >= 0x20200 and len(body) >= 52:
                    team_off = struct.unpack_from(">I", body, 48)[0]
                    if team_off:
                        end = body.find(b"\x00", team_off)
                        info.team_id = body[team_off : end if end != -1 else team_off + 16].decode("utf-8", errors="replace")
            elif magic == 0xFADE7171:  # XML entitlements
                try:
                    parsed = plistlib.loads(body[8:])
                    if isinstance(parsed, dict):
                        info.entitlements.update(parsed)
                except Exception:
                    pass
        return info
    except (struct.error, IndexError):
        return None


def _parse_slice(data: bytes, base: int, order: str, is_64: bool) -> Optional[MachOInfo]:
    header = 32 if is_64 else 28
    if base + header > len(data):
        return None
    _magic, cputype, _sub, filetype, ncmds, _sizeofcmds, _flags = struct.unpack_from(f"{order}IiiIIII", data, base)
    info = MachOInfo(cpu=_CPU.get(cputype, f"cpu{cputype}"), filetype=_FILETYPE.get(filetype, str(filetype)), is_64=is_64)
    pos = base + header
    symtab: Optional[Tuple[int, int, int, int]] = None
    for _ in range(min(ncmds, MAX_COMMANDS)):
        if pos + 8 > len(data):
            break
        cmd, cmdsize = struct.unpack_from(f"{order}II", data, pos)
        if cmdsize < 8 or pos + cmdsize > len(data):
            break
        body = data[pos : pos + cmdsize]
        if cmd in (LC_SEGMENT_64, LC_SEGMENT):
            seg_hdr, sect_size = (72, 80) if cmd == LC_SEGMENT_64 else (56, 68)
            nsects = struct.unpack_from(f"{order}I", body, seg_hdr - 8)[0]
            for s in range(min(nsects, 256)):
                off = seg_hdr + s * sect_size
                if off + 32 > len(body):
                    break
                info.sections.append((_name(body[off + 16 : off + 32]), _name(body[off : off + 16])))
        elif cmd in _DYLIB_COMMANDS:
            (name_off,) = struct.unpack_from(f"{order}I", body, 8)
            info.dylibs.append((_DYLIB_COMMANDS[cmd], _name(body[name_off:])))
        elif cmd == LC_RPATH:
            (path_off,) = struct.unpack_from(f"{order}I", body, 8)
            info.rpaths.append(_name(body[path_off:]))
        elif cmd == LC_DYLD_ENVIRONMENT:
            (env_off,) = struct.unpack_from(f"{order}I", body, 8)
            info.dyld_environment.append(_name(body[env_off:]))
        elif cmd == LC_SYMTAB:
            symtab = struct.unpack_from(f"{order}IIII", body, 8)
        elif cmd == LC_CODE_SIGNATURE:
            dataoff, datasize = struct.unpack_from(f"{order}II", body, 8)
            if dataoff + datasize <= len(data) - base or base == 0:
                info.signature = _parse_signature(data[base + dataoff : base + dataoff + datasize])
        pos += cmdsize

    if symtab:
        symoff, nsyms, stroff, strsize = symtab
        entry = 16 if is_64 else 12
        strtab = data[base + stroff : base + stroff + strsize]
        for i in range(min(nsyms, MAX_SYMBOLS)):
            off = base + symoff + i * entry
            if off + entry > len(data):
                break
            n_strx, n_type = struct.unpack_from(f"{order}IB", data, off)
            if (n_type & 0x0E) == 0 and (n_type & 0x01) and 0 < n_strx < len(strtab):
                end = strtab.find(b"\x00", n_strx)
                sym = strtab[n_strx : end if end != -1 else n_strx + 128].decode("ascii", errors="replace")
                info.undefined_symbols.append(sym.lstrip("_"))
    return info


def parse_macho(data: bytes) -> List[MachOInfo]:
    """All Mach-O slices in `data` (one for a thin binary, several for a fat one); empty when it is not Mach-O."""
    if len(data) < 8:
        return []
    try:
        (magic_be,) = struct.unpack_from(">I", data, 0)
        (magic_le,) = struct.unpack_from("<I", data, 0)
        if magic_be in _FAT_MAGICS:
            (narch,) = struct.unpack_from(">I", data, 4)
            out: List[MachOInfo] = []
            for i in range(min(narch, MAX_SLICES)):
                cputype, _sub, offset, size, _align = struct.unpack_from(">iiIII", data, 8 + i * 20)
                if offset + 4 > len(data):
                    continue
                (slice_magic,) = struct.unpack_from("<I", data, offset)
                if slice_magic in _MH_MAGICS:
                    order, is_64 = _MH_MAGICS[slice_magic]
                    parsed = _parse_slice(data[offset : offset + size], 0, order, is_64)
                    if parsed:
                        out.append(parsed)
            return out
        if magic_le in _MH_MAGICS:
            order, is_64 = _MH_MAGICS[magic_le]
            parsed = _parse_slice(data, 0, order, is_64)
            return [parsed] if parsed else []
    except (struct.error, IndexError):
        pass
    return []
