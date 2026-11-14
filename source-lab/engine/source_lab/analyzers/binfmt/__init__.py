"""Stdlib parsers for the binary formats the analyzers read: PE, Mach-O, ASAR and the APK signing block.

Each parser is defensive: bounds are checked, loops are capped and a malformed input returns None or a partial result
instead of raising, so a hostile file cannot stall or crash a run.
"""

from .apk import ApkSigningInfo, parse_apk_signing
from .asar import AsarEntry, parse_asar
from .macho import CodeSignatureInfo, MachOInfo, parse_macho
from .pe import PEInfo, parse_pe

__all__ = [
    "ApkSigningInfo",
    "AsarEntry",
    "CodeSignatureInfo",
    "MachOInfo",
    "PEInfo",
    "parse_apk_signing",
    "parse_asar",
    "parse_macho",
    "parse_pe",
]
