"""APK signing block reader: which signature schemes are present and the SHA-256 of the signing certificate."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import List, Optional

_MAGIC = b"APK Sig Block 42"
_SCHEMES = {0x7109871A: "v2", 0xF05368C0: "v3", 0x1B93AD61: "v3.1", 0x6DFF800D: "source-stamp"}


@dataclass
class ApkSigningInfo:
    schemes: List[str] = field(default_factory=list)
    #: SHA-256 (hex) of each signer's first certificate, from the v2/v3 block
    certificate_sha256: List[str] = field(default_factory=list)
    has_signing_block: bool = False


def _u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]


def _first_certificate(value: bytes, v3: bool) -> Optional[bytes]:
    """The first signer's first X.509 DER certificate out of a v2/v3 scheme value."""
    try:
        signers_len = _u32(value, 0)
        pos = 4
        if signers_len == 0 or pos + 4 > len(value):
            return None
        signer_len = _u32(value, pos)
        pos += 4
        signed_len = _u32(value, pos)
        sd = value[pos + 4 : pos + 4 + signed_len]
        digests_len = _u32(sd, 0)
        certs_off = 4 + digests_len
        certs_len = _u32(sd, certs_off)
        cert_len = _u32(sd, certs_off + 4)
        if certs_len == 0 or cert_len == 0:
            return None
        return sd[certs_off + 8 : certs_off + 8 + cert_len]
    except (struct.error, IndexError):
        return None


def parse_apk_signing(data: bytes) -> ApkSigningInfo:
    """Reads the APK signing block of an APK held in memory (empty result when there is none)."""
    info = ApkSigningInfo()
    try:
        eocd = data.rfind(b"PK\x05\x06")
        if eocd == -1 or eocd + 20 > len(data):
            return info
        cd_offset = _u32(data, eocd + 16)
        if cd_offset < 32 or cd_offset > len(data) or data[cd_offset - 16 : cd_offset] != _MAGIC:
            return info
        block_size = struct.unpack_from("<Q", data, cd_offset - 24)[0]
        start = cd_offset - block_size - 8
        if start < 0 or block_size < 24:
            return info
        info.has_signing_block = True
        pos, end = start + 8, cd_offset - 24
        while pos + 12 <= end:
            (pair_len,) = struct.unpack_from("<Q", data, pos)
            (pair_id,) = struct.unpack_from("<I", data, pos + 8)
            value = data[pos + 12 : pos + 8 + pair_len]
            if pair_id in _SCHEMES:
                info.schemes.append(_SCHEMES[pair_id])
                if pair_id in (0x7109871A, 0xF05368C0, 0x1B93AD61):
                    cert = _first_certificate(value, pair_id != 0x7109871A)
                    if cert:
                        digest = hashlib.sha256(cert).hexdigest()
                        if digest not in info.certificate_sha256:
                            info.certificate_sha256.append(digest)
            if pair_len < 4 or pos + 8 + pair_len > end:
                break
            pos += 8 + pair_len
    except (struct.error, IndexError):
        pass
    return info
