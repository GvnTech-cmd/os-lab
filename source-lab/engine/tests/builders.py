"""Builders that assemble small, valid PE, Mach-O, ASAR and APK files in memory, so analyzer tests need no binary fixtures."""

from __future__ import annotations

import hashlib
import json
import plistlib
import struct
import zipfile
from io import BytesIO
from typing import Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------------------------------------------------
# PE
# ---------------------------------------------------------------------------------------------------------------------


def build_pe(
    imports: Optional[Dict[str, List[str]]] = None,
    exports: Optional[List[str]] = None,
    forwarders: Optional[Dict[str, str]] = None,
    signed: bool = False,
    managed: bool = False,
    dll: bool = False,
    extra: bytes = b"",
) -> bytes:
    """A PE32+ image with one section holding the import and export tables."""
    imports = imports or {}
    exports = list(exports or [])
    forwarders = forwarders or {}
    exports += [n for n in forwarders if n not in exports]
    section_rva, section_raw = 0x1000, 0x400
    blob = bytearray()

    def rva(off: int) -> int:
        return section_rva + off

    def cstr(text: str) -> int:
        off = len(blob)
        blob.extend(text.encode("ascii") + b"\x00")
        if len(blob) % 2:
            blob.append(0)
        return off

    imp_rva = imp_size = 0
    if imports:
        descriptors_off = len(blob)
        blob.extend(b"\x00" * (20 * (len(imports) + 1)))
        for i, (dll_name, funcs) in enumerate(imports.items()):
            name_off = cstr(dll_name)
            hint_offs = []
            for fn in funcs:
                hint_off = len(blob)
                blob.extend(b"\x00\x00")
                blob.extend(fn.encode("ascii") + b"\x00")
                if len(blob) % 2:
                    blob.append(0)
                hint_offs.append(hint_off)
            thunk_off = len(blob)
            for h in hint_offs:
                blob.extend(struct.pack("<Q", rva(h)))
            blob.extend(struct.pack("<Q", 0))
            struct.pack_into("<IIIII", blob, descriptors_off + i * 20, rva(thunk_off), 0, 0, rva(name_off), rva(thunk_off))
        imp_rva, imp_size = rva(descriptors_off), 20 * (len(imports) + 1)

    exp_rva = exp_size = 0
    if exports:
        exp_off = len(blob)
        blob.extend(b"\x00" * 40)
        funcs_off = len(blob)
        blob.extend(b"\x00" * (4 * len(exports)))
        names_off = len(blob)
        blob.extend(b"\x00" * (4 * len(exports)))
        ords_off = len(blob)
        blob.extend(b"\x00" * (2 * len(exports)))
        if len(blob) % 4:
            blob.extend(b"\x00" * (4 - len(blob) % 4))
        for i, name in enumerate(sorted(exports)):
            n_off = cstr(name)
            struct.pack_into("<I", blob, names_off + i * 4, rva(n_off))
            struct.pack_into("<H", blob, ords_off + i * 2, i)
            if name in forwarders:
                f_off = cstr(forwarders[name])
                struct.pack_into("<I", blob, funcs_off + i * 4, rva(f_off))
            else:
                struct.pack_into("<I", blob, funcs_off + i * 4, 0x2000)  # outside the export directory
        exp_size = len(blob) - exp_off
        struct.pack_into("<IIHHIIIIII", blob, exp_off, 0, 0, 0, 0, 0, 1, len(exports), len(exports), rva(funcs_off), rva(names_off))
        struct.pack_into("<I", blob, exp_off + 36, rva(ords_off))
        exp_rva = rva(exp_off)

    blob.extend(extra)
    while len(blob) % 16:
        blob.append(0)

    dos = bytearray(0x40)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 240, 0x2022 if dll else 0x22)
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 108, 16)
    dirs = [(0, 0)] * 16
    dirs[0] = (exp_rva, exp_size)
    dirs[1] = (imp_rva, imp_size)
    if managed:
        dirs[14] = (rva(0), 72)
    for i, (a, b) in enumerate(dirs):
        struct.pack_into("<II", opt, 112 + i * 8, a, b)
    section = bytearray(40)
    section[:6] = b".rdata"
    struct.pack_into("<IIII", section, 8, len(blob), section_rva, len(blob), section_raw)
    header = bytes(dos) + b"PE\x00\x00" + coff + bytes(opt) + bytes(section)
    image = bytearray(header.ljust(section_raw, b"\x00")) + blob
    if signed:
        sig_off = len(image)
        image.extend(b"\x30\x82" + b"\x00" * 14)
        struct.pack_into("<II", image, 0x40 + 24 + 112 + 4 * 8, sig_off, 16)
    return bytes(image)


# ---------------------------------------------------------------------------------------------------------------------
# Mach-O
# ---------------------------------------------------------------------------------------------------------------------

_DYLIB = {"LC_LOAD_DYLIB": 0xC, "LC_LOAD_WEAK_DYLIB": 0x80000018, "LC_REEXPORT_DYLIB": 0x8000001F}


def _lc_string(cmd: int, text: str) -> bytes:
    raw = text.encode() + b"\x00"
    size = (12 + len(raw) + 7) & ~7
    return struct.pack("<III", cmd, size, 12) + raw.ljust(size - 12, b"\x00")


def build_code_signature(flags: int = 0, entitlements: Optional[dict] = None, identifier: str = "com.example.app", team_id: Optional[str] = None) -> bytes:
    ident = identifier.encode() + b"\x00"
    team = (team_id.encode() + b"\x00") if team_id else b""
    cd_header = 52
    ident_off = cd_header
    team_off = ident_off + len(ident) if team else 0
    cd_len = cd_header + len(ident) + len(team)
    code_dir = struct.pack(">IIIIIIIIIBBBBIII", 0xFADE0C02, cd_len, 0x20200, flags, 0, ident_off, 0, 0, 0, 0, 0, 0, 0, 0, 0, team_off)
    code_dir += ident + team
    code_dir = code_dir[:cd_len]
    blobs: List[Tuple[int, bytes]] = [(0, code_dir)]
    if entitlements is not None:
        xml = plistlib.dumps(entitlements)
        blobs.append((5, struct.pack(">II", 0xFADE7171, 8 + len(xml)) + xml))
    index_len = 12 + 8 * len(blobs)
    out = bytearray()
    offset = index_len
    entries = b""
    for slot, body in blobs:
        entries += struct.pack(">II", slot, offset)
        offset += len(body)
    out += struct.pack(">III", 0xFADE0CC0, offset, len(blobs)) + entries
    for _slot, body in blobs:
        out += body
    return bytes(out)


def build_macho(
    dylibs: Iterable[Tuple[str, str]] = (),
    rpaths: Iterable[str] = (),
    sections: Iterable[Tuple[str, str]] = (),
    undefined: Iterable[str] = (),
    signature: Optional[bytes] = None,
    dyld_env: Iterable[str] = (),
    cputype: int = 0x0100000C,
    filetype: int = 2,
) -> bytes:
    """A thin 64-bit Mach-O with the requested load commands, sections, undefined symbols and code signature."""
    cmds: List[bytes] = []
    for kind, path in dylibs:
        cmds.append(_lc_string(_DYLIB[kind], path))
    for path in rpaths:
        raw = path.encode() + b"\x00"
        size = (12 + len(raw) + 7) & ~7
        cmds.append(struct.pack("<III", 0x8000001C, size, 12) + raw.ljust(size - 12, b"\x00"))
    for env in dyld_env:
        raw = env.encode() + b"\x00"
        size = (12 + len(raw) + 7) & ~7
        cmds.append(struct.pack("<III", 0x27, size, 12) + raw.ljust(size - 12, b"\x00"))
    by_seg: Dict[str, List[str]] = {}
    for seg, sect in sections:
        by_seg.setdefault(seg, []).append(sect)
    for seg, sects in by_seg.items():
        size = 72 + 80 * len(sects)
        body = struct.pack("<II16sQQQQiiII", 0x19, size, seg.encode().ljust(16, b"\x00"), 0, 0, 0, 0, 7, 7, len(sects), 0)
        for sect in sects:
            body += sect.encode().ljust(16, b"\x00") + seg.encode().ljust(16, b"\x00") + b"\x00" * 48
        cmds.append(body)

    header_size = 32
    sizeofcmds_without_tail = sum(len(c) for c in cmds)
    undefined = list(undefined)
    tail = b""
    layout_cmds = list(cmds)
    symtab_cmd_len = 24 if undefined else 0
    sig_cmd_len = 16 if signature else 0
    base = header_size + sizeofcmds_without_tail + symtab_cmd_len + sig_cmd_len
    body_data = b""
    if undefined:
        strtab = b"\x00"
        nlists = b""
        for name in undefined:
            nlists += struct.pack("<IBBHQ", len(strtab), 0x01, 0, 0, 0)
            strtab += b"_" + name.encode() + b"\x00"
        symoff = base
        stroff = base + len(nlists)
        layout_cmds.append(struct.pack("<IIIIII", 0x2, 24, symoff, len(undefined), stroff, len(strtab)))
        body_data = nlists + strtab
    if signature:
        sig_off = base + len(body_data)
        layout_cmds.append(struct.pack("<IIII", 0x1D, 16, sig_off, len(signature)))
        body_data += signature
    sizeofcmds = sum(len(c) for c in layout_cmds)
    header = struct.pack("<IiiIIIII", 0xFEEDFACF, cputype, 0, filetype, len(layout_cmds), sizeofcmds, 0, 0)
    return header + b"".join(layout_cmds) + body_data + tail


# ---------------------------------------------------------------------------------------------------------------------
# ASAR
# ---------------------------------------------------------------------------------------------------------------------


def build_asar(files: Dict[str, str], unpacked: Iterable[str] = ()) -> bytes:
    """An ASAR archive with the given text files (path -> content); `unpacked` paths are listed but stored outside."""
    unpacked = set(unpacked)
    tree: dict = {"files": {}}
    payload = b""
    for path, content in files.items():
        node = tree
        parts = path.split("/")
        for part in parts[:-1]:
            node = node["files"].setdefault(part, {"files": {}})
        raw = content.encode()
        if path in unpacked:
            node["files"][parts[-1]] = {"size": len(raw), "unpacked": True}
        else:
            node["files"][parts[-1]] = {"size": len(raw), "offset": str(len(payload))}
            payload += raw
    header = json.dumps(tree, separators=(",", ":")).encode()
    padded = header + b"\x00" * ((4 - len(header) % 4) % 4)
    pickle_payload = struct.pack("<I", len(header)) + padded
    header_size = 4 + len(pickle_payload)
    return struct.pack("<II", 4, header_size) + struct.pack("<I", len(pickle_payload)) + pickle_payload + payload


# ---------------------------------------------------------------------------------------------------------------------
# APK
# ---------------------------------------------------------------------------------------------------------------------


def _len_prefixed(b: bytes) -> bytes:
    return struct.pack("<I", len(b)) + b


def build_apk(files: Dict[str, bytes], certificate: Optional[bytes] = None, schemes: Tuple[str, ...] = ("v2",)) -> bytes:
    """A ZIP with an APK signing block carrying `certificate` under the requested schemes (no block when None)."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    raw = buf.getvalue()
    if certificate is None:
        return raw
    eocd = raw.rfind(b"PK\x05\x06")
    cd_offset = struct.unpack_from("<I", raw, eocd + 16)[0]
    ids = {"v2": 0x7109871A, "v3": 0xF05368C0}
    pairs = b""
    for scheme in schemes:
        signed = _len_prefixed(_len_prefixed(b"digests")) + _len_prefixed(_len_prefixed(certificate)) + _len_prefixed(b"")
        if scheme == "v3":
            signed = _len_prefixed(b"digests") + _len_prefixed(_len_prefixed(certificate)) + struct.pack("<II", 24, 0xFFFFFFFF) + _len_prefixed(b"")
        signer = _len_prefixed(signed) + _len_prefixed(b"") + _len_prefixed(b"")
        value = _len_prefixed(_len_prefixed(signer))
        pairs += struct.pack("<QI", 4 + len(value), ids[scheme]) + value
    block_size = len(pairs) + 24
    block = struct.pack("<Q", block_size) + pairs + struct.pack("<Q", block_size) + b"APK Sig Block 42"
    new_cd = raw[cd_offset:eocd]
    eocd_bytes = bytearray(raw[eocd:])
    struct.pack_into("<I", eocd_bytes, 16, cd_offset + len(block))
    return raw[:cd_offset] + block + new_cd + bytes(eocd_bytes)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
