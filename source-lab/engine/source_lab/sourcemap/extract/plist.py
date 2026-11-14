"""Property list and JSON config adapters (``plistlib`` with size caps).

A malformed or oversized plist is not a parse error: the file simply yields
no symbols and the engine records the skip reason.  ``summarize_info_plist``
derives the platform hints used by target detection."""

from __future__ import annotations

import json
import plistlib
from typing import Dict, Optional, Tuple

from ..model import Symbol
from .common import Extracted

MAX_PLIST_BYTES = 4 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024


def read_plist(data: bytes, *, max_bytes: int = MAX_PLIST_BYTES) -> Tuple[Optional[dict], str]:
    """Safe plist reader: caps input size and never raises.  Returns
    ``(payload|None, reason)``."""
    if len(data) > max_bytes:
        return None, f"plist: {len(data)} bytes over cap {max_bytes}"
    try:
        payload = plistlib.loads(data)
    except Exception as exc:  # noqa: BLE001 - binary or malformed plists
        return None, f"plist: unreadable ({exc.__class__.__name__})"
    if not isinstance(payload, dict):
        return None, "plist: not a dictionary"
    return payload, ""


def summarize_info_plist(payload: dict) -> Dict:
    families = payload.get("UIDeviceFamily") or []
    supported = payload.get("CFBundleSupportedPlatforms") or []
    ios = bool(
        payload.get("LSRequiresIPhoneOS")
        or (isinstance(families, list) and families)
        or any("iPhoneOS" in str(p) for p in supported)
    )
    macos = bool(
        payload.get("LSUIElement") is not None
        or any("MacOSX" in str(p) for p in supported)
        or (payload.get("CFBundlePackageType") == "APPL" and not ios)
    )
    return {
        "bundle_id": payload.get("CFBundleIdentifier"),
        "executable": payload.get("CFBundleExecutable"),
        "package_type": payload.get("CFBundlePackageType"),
        "min_os": payload.get("MinimumOSVersion") or payload.get("LSMinimumSystemVersion"),
        "ios": ios,
        "macos": macos and not ios,
        "ui_element": payload.get("LSUIElement") is not None,
    }


def extract(text: str, path: str = "") -> Extracted:
    out = Extracted()
    base = path.rsplit("/", 1)[-1]
    if base.endswith((".json",)):
        return out  # json config carries no symbols
    return out
