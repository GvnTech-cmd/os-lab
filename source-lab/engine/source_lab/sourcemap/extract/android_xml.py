"""Android XML adapters: ``AndroidManifest.xml`` components and generic
storyboard/XIB class references.  Namespaced ``android:*`` attributes are
handled whether or not the prefix is literal."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from ..model import ImportRef, Symbol
from .common import Extracted

_ANDROID_NS = "http://schemas.android.com/apk/res/android"
_COMPONENT_TAGS = ("activity", "service", "receiver", "provider")
_CAP = 200


def _attr(node, name: str) -> Optional[str]:
    value = node.get(f"{{{_ANDROID_NS}}}{name}")
    if value is None:
        value = node.get(f"android:{name}")
    return value


def parse_manifest(text: str) -> Dict:
    """Parse an AndroidManifest into package, permissions and components.

    Each component records its full class name (relative ``.Name`` is expanded
    with the manifest package), ``exported`` flag and whether it carries the
    MAIN/LAUNCHER intent filter.
    """
    info: Dict = {"package": None, "permissions": [], "components": [], "application": None}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return info
    info["package"] = root.get("package")
    application = root.find("application")
    if application is None:
        return info
    info["application"] = _attr(application, "name")
    count = 0
    for perm in root.iter("uses-permission"):
        name = _attr(perm, "name")
        if name:
            info["permissions"].append(name)
            count += 1
            if count >= _CAP:
                return info
    for tag in _COMPONENT_TAGS:
        for node in application.iter(tag):
            name = _attr(node, "name")
            if not name:
                continue
            if name.startswith("."):
                name = f"{info['package'] or ''}{name}"
            exported = _attr(node, "exported")
            launcher = False
            for intent in node.findall("intent-filter"):
                actions = [a.get(f"{{{_ANDROID_NS}}}name") or a.get("android:name") or ""
                           for a in intent.findall("action")]
                categories = [c.get(f"{{{_ANDROID_NS}}}name") or c.get("android:name") or ""
                              for c in intent.findall("category")]
                if "android.intent.action.MAIN" in actions and "android.intent.category.LAUNCHER" in categories:
                    launcher = True
            info["components"].append({
                "type": tag,
                "name": name,
                "exported": None if exported is None else exported.lower() == "true",
                "launcher": launcher,
            })
            count += 1
            if count >= _CAP:
                return info
    return info


def extract(text: str, path: str = "") -> Extracted:
    """XML adapter.  Android manifests become component/permission symbols;
    storyboards and XIBs yield ``customClass`` references as import stubs;
    other XML files parse for validity only."""
    out = Extracted()
    base = path.rsplit("/", 1)[-1]
    if base == "AndroidManifest.xml":
        info = parse_manifest(text)
        if info["package"]:
            out.package = info["package"]
        for perm in info["permissions"]:
            out.symbols.append(Symbol(kind="permission", name=perm, line=0))
        for comp in info["components"]:
            out.symbols.append(Symbol(kind=comp["type"], name=comp["name"], line=0,
                                      meta={"exported": comp["exported"],
                                            "launcher": comp["launcher"]}))
        return out
    if base.endswith((".storyboard", ".xib")):
        for match in re.finditer(r'custom(?:Class|Module)="([^"]+)"', text):
            name = match.group(1)
            out.imports.append(ImportRef(specifier=f"customClass:{name}", line=0,
                                         kind="storyboard", names=[name], reason="storyboard"))
        return out
    # generic XML: validity only
    try:
        ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"xml parse error: {exc}") from exc
    return out
