"""Portable Executable parser: sections, import table, export table with forwarders, security and CLR directories."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MAX_IMPORTS = 5000
MAX_EXPORTS = 5000
MAX_SECTIONS = 96
_DIR_EXPORT, _DIR_IMPORT, _DIR_SECURITY, _DIR_CLR = 0, 1, 4, 14


@dataclass
class PEInfo:
    is_64: bool
    machine: int
    is_dll: bool
    sections: List[str] = field(default_factory=list)
    #: lower-case DLL name -> imported function names (ordinal imports appear as "#<n>")
    imports: Dict[str, List[str]] = field(default_factory=dict)
    exports: List[str] = field(default_factory=list)
    #: (export name, forward target) for every exported function forwarded to another DLL
    forwarders: List[Tuple[str, str]] = field(default_factory=list)
    has_signature: bool = False
    is_managed: bool = False

    def imported(self, name: str) -> Optional[str]:
        """The DLL that imports `name`, matched case-insensitively, or None."""
        wanted = name.lower()
        for dll, funcs in self.imports.items():
            if any(f.lower() == wanted for f in funcs):
                return dll
        return None

    def all_imports(self) -> set:
        return {f.lower() for funcs in self.imports.values() for f in funcs}


def _cstr(data: bytes, offset: int, limit: int = 256) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end = data.find(b"\x00", offset, offset + limit)
    return data[offset : end if end != -1 else offset + limit].decode("ascii", errors="replace")


def parse_pe(data: bytes) -> Optional[PEInfo]:
    """Parses `data` as a PE image; None when it is not one."""
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    try:
        (e_lfanew,) = struct.unpack_from("<I", data, 0x3C)
        if e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
            return None
        machine, nsections, _ts, _sym, _nsym, opt_size, characteristics = struct.unpack_from("<HHIIIHH", data, e_lfanew + 4)
        opt = e_lfanew + 24
        if opt + 2 > len(data):
            return None
        (magic,) = struct.unpack_from("<H", data, opt)
        if magic not in (0x10B, 0x20B):
            return None
        is_64 = magic == 0x20B
        dir_base = opt + (112 if is_64 else 96)
        (ndirs,) = struct.unpack_from("<I", data, dir_base - 4)
        ndirs = min(ndirs, 16)

        def directory(index: int) -> Tuple[int, int]:
            if index >= ndirs or dir_base + index * 8 + 8 > len(data):
                return 0, 0
            return struct.unpack_from("<II", data, dir_base + index * 8)

        info = PEInfo(is_64=is_64, machine=machine, is_dll=bool(characteristics & 0x2000))

        sect_table = opt + opt_size
        sections: List[Tuple[int, int, int, int]] = []  # vaddr, vsize, rawptr, rawsize
        for i in range(min(nsections, MAX_SECTIONS)):
            off = sect_table + i * 40
            if off + 40 > len(data):
                break
            name = data[off : off + 8].rstrip(b"\x00").decode("ascii", errors="replace")
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, off + 8)
            info.sections.append(name)
            sections.append((vaddr, vsize, rawptr, rawsize))

        def rva_to_off(rva: int) -> Optional[int]:
            for vaddr, vsize, rawptr, rawsize in sections:
                if vaddr <= rva < vaddr + max(vsize, rawsize):
                    off = rawptr + (rva - vaddr)
                    return off if off < len(data) else None
            # headers are mapped 1:1
            return rva if rva < len(data) and not sections else None

        sec_off, sec_size = directory(_DIR_SECURITY)
        info.has_signature = sec_off > 0 and sec_size > 0
        clr_rva, clr_size = directory(_DIR_CLR)
        info.is_managed = clr_rva > 0 and clr_size > 0

        imp_rva, _ = directory(_DIR_IMPORT)
        imp_off = rva_to_off(imp_rva) if imp_rva else None
        if imp_off is not None:
            count = 0
            thunk_size = 8 if is_64 else 4
            ordinal_flag = 1 << (63 if is_64 else 31)
            while imp_off + 20 <= len(data) and count < MAX_IMPORTS:
                orig_first, _t, _f, name_rva, first_thunk = struct.unpack_from("<IIIII", data, imp_off)
                if name_rva == 0 and first_thunk == 0:
                    break
                dll_off = rva_to_off(name_rva)
                dll = _cstr(data, dll_off).lower() if dll_off is not None else ""
                thunk_off = rva_to_off(orig_first or first_thunk)
                funcs: List[str] = []
                while thunk_off is not None and thunk_off + thunk_size <= len(data) and count < MAX_IMPORTS:
                    (entry,) = struct.unpack_from("<Q" if is_64 else "<I", data, thunk_off)
                    if entry == 0:
                        break
                    if entry & ordinal_flag:
                        funcs.append(f"#{entry & 0xFFFF}")
                    else:
                        by_name = rva_to_off(entry & 0x7FFFFFFF)
                        if by_name is not None:
                            funcs.append(_cstr(data, by_name + 2))
                    thunk_off += thunk_size
                    count += 1
                if dll:
                    info.imports.setdefault(dll, []).extend(f for f in funcs if f)
                imp_off += 20

        exp_rva, exp_size = directory(_DIR_EXPORT)
        exp_off = rva_to_off(exp_rva) if exp_rva else None
        if exp_off is not None and exp_off + 40 <= len(data):
            n_funcs, n_names, funcs_rva, names_rva, ords_rva = struct.unpack_from("<IIIII", data, exp_off + 20)
            funcs_off, names_off, ords_off = rva_to_off(funcs_rva), rva_to_off(names_rva), rva_to_off(ords_rva)
            if funcs_off is not None and names_off is not None and ords_off is not None:
                for i in range(min(n_names, MAX_EXPORTS)):
                    if names_off + i * 4 + 4 > len(data) or ords_off + i * 2 + 2 > len(data):
                        break
                    (name_rva,) = struct.unpack_from("<I", data, names_off + i * 4)
                    (ordinal,) = struct.unpack_from("<H", data, ords_off + i * 2)
                    name_off = rva_to_off(name_rva)
                    name = _cstr(data, name_off) if name_off is not None else ""
                    if not name:
                        continue
                    info.exports.append(name)
                    if ordinal < n_funcs and funcs_off + ordinal * 4 + 4 <= len(data):
                        (func_rva,) = struct.unpack_from("<I", data, funcs_off + ordinal * 4)
                        # An export whose RVA points back inside the export directory is a forwarder string.
                        if exp_rva <= func_rva < exp_rva + exp_size:
                            fwd_off = rva_to_off(func_rva)
                            forward = _cstr(data, fwd_off) if fwd_off is not None else ""
                            if forward:
                                info.forwarders.append((name, forward))
        return info
    except (struct.error, IndexError, ValueError):
        return None
