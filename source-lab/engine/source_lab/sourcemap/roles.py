"""Role classification.

Roles come from an ordered cascade; the first hit wins and every role keeps a
confidence and evidence.  A role describes structure, never behaviour, and
never becomes a Finding or scorecard entry.

Cascade: explicit evidence (package.json main/preload, manifest components),
framework path, convention path, symbol shape.  Taxonomy additions for the
new adapters: ``view_model`` and ``component`` join the existing names; the
UI Map tab already renders unknown role names as chips.
"""

from __future__ import annotations

import posixpath
import re
from typing import Dict, List, Optional, Tuple

from .model import Role, Symbol

TAXONOMY = (
    "entrypoint", "page", "route", "layout", "view", "component", "hook",
    "context", "store", "slice", "view_model", "service", "api", "helper",
    "lib", "model", "schema", "migration", "db", "middleware", "config",
    "test", "fixture", "story", "style", "asset", "docs", "generated",
    "vendor", "unknown",
)

_PATH_TIERS: List[Tuple[str, str, float, str]] = [
    # (regex on path, role, confidence, evidence tag)
    (r"(^|/)tests?/|(^|/)__tests__/|_test\.|\.test\.|\.spec\.", "test", 0.9, "path:tests"),
    (r"Tests?\.(swift|kt|java)$|(^|/)XCTestCase", "test", 0.9, "symbol:test suffix"),
    (r"(^|/)fixtures?/", "fixture", 0.9, "path:fixtures"),
    (r"(^|/)pages?/|(^|/)app/.+\.(tsx|jsx)$|_page\.", "page", 0.9, "path:pages"),
    (r"(^|/)routes?/", "route", 0.85, "path:routes"),
    (r"(^|/)layouts?/", "layout", 0.9, "path:layouts"),
    (r"(^|/)views?/|ViewController|(^|/)res/layout/", "view", 0.85, "path:views"),
    (r"(^|/)components?/", "component", 0.8, "path:components"),
    (r"(^|/)hooks?/|(^|/)composables?/", "hook", 0.85, "path:hooks"),
    (r"(^|/)contexts?/|(^|/)providers?/", "context", 0.85, "path:contexts"),
    (r"(^|/)store?s?/|(^|/)stores/", "store", 0.85, "path:stores"),
    (r"(^|/)ViewModel|ViewModel\.", "view_model", 0.85, "path:viewmodels"),
    (r"(^|/)slice", "slice", 0.8, "path:slices"),
    (r"(^|/)middleware/", "middleware", 0.9, "path:middleware"),
    (r"(^|/)migrations?/", "migration", 0.9, "path:migrations"),
    (r"(^|/)schemas?/", "schema", 0.85, "path:schemas"),
    (r"(^|/)repositor(y|ies)/|Repository\.(kt|java|swift|ts|py)$", "service", 0.8, "path:repositories"),
    (r"(^|/)services?/", "service", 0.8, "path:services"),
    (r"(^|/)models?/|(^|/)entities?/", "model", 0.8, "path:models"),
    (r"(^|/)data/", "model", 0.7, "path:data"),
    (r"(^|/)api/|(^|/)apis?/", "api", 0.8, "path:api"),
    (r"(^|/)helpers?/|(^|/)utils?/", "helper", 0.7, "path:helpers"),
    (r"(^|/)lib/|(^|/)core/", "lib", 0.7, "path:lib"),
    (r"(^|/)styles?/|\.css$|\.scss$|\.sass$|\.less$", "style", 0.9, "path:styles"),
    (r"(^|/)assets?/|(^|/)res/|\.storyboard$|\.xib$|\.xcassets", "asset", 0.8, "path:assets"),
    (r"(^|/)docs?/|\.md$", "docs", 0.8, "path:docs"),
]

_CONFIG_NAMES = {
    "package.json": 0.9, "tsconfig.json": 0.9, "composer.json": 0.9,
    "AndroidManifest.xml": 0.95, "Info.plist": 0.9, "build.gradle": 0.9,
    "build.gradle.kts": 0.9, "settings.gradle": 0.9, "settings.gradle.kts": 0.9,
    "Podfile": 0.9, "project.pbxproj": 0.95, "Cargo.toml": 0.9,
}

_GENERATED = re.compile(
    r"(^|/)R\.kt$|(^|/)R\.java$|R\$[\w]+\.java$|(^|/)BuildConfig\.(java|kt)$"
    r"|(^|/)databinding/|Binding\.(java|kt)$|(^|/)generated/")
_ENTRY_SYMBOL = re.compile(r"AppDelegate|SceneDelegate|Application@|@main|MainApplication")
_SWIFT_ENTRY = re.compile(r"^\s*(?:@main\b|(?:final\s+)?class\s+(AppDelegate|SceneDelegate)\b)")


class RoleContext:
    """Shared classification inputs for one generation run."""

    def __init__(self, *, manifest_components: Optional[Dict[str, dict]] = None,
                 explicit: Optional[Dict[str, Tuple[str, float, str]]] = None,
                 platform: str = "repository",
                 sources: Optional[Dict[str, str]] = None):
        # class full name -> {"type": activity|service|..., "launcher": bool}
        self.manifest_components = manifest_components or {}
        # path -> (role, confidence, evidence)
        self.explicit = explicit or {}
        self.platform = platform
        # path -> source text (a few legacy symbol rules read the text)
        self.sources = sources or {}


def classify(path: str, lang: str, symbols: List[Symbol], ctx: RoleContext) -> Role:
    explicit = ctx.explicit.get(path)
    if explicit:
        return Role(kind=explicit[0], confidence=explicit[1], evidence=[explicit[2]])

    base = path.split("!/", 1)[-1]
    name = posixpath.basename(base)

    if _GENERATED.search(path) or name in ("R.kt", "R.java", "BuildConfig.java"):
        return Role("generated", 0.95, ["generated: build or binding output"])

    # Legacy symbol rule: a database client is ``db`` even under lib/.
    source = ctx.sources.get(path, "")
    if re.search(r"\b(PrismaClient|drizzle\(|knex\(|sequelize\.define)", source):
        return Role("db", 0.75, ["symbol:database-client"])
    if re.search(r"models\.Model|@Entity\b", source):
        return Role("model", 0.75, ["symbol:orm-model"])

    lowered = base.lower()
    for pattern, role, confidence, tag in _PATH_TIERS:
        if re.search(pattern, base, re.IGNORECASE):
            return Role(role, confidence, [tag])

    config = _CONFIG_NAMES.get(name)
    if config:
        return Role("config", config, [f"config:{name}"])

    # manifest component match (android): symbols carry the expanded class name
    for sym in symbols:
        comp = ctx.manifest_components.get(sym.name)
        if comp:
            role = {"activity": "component", "service": "service", "receiver": "service",
                    "provider": "service"}.get(comp["type"], "component")
            tag = f"manifest:{comp['type']}"
            if comp.get("launcher"):
                return Role("entrypoint", 0.9, [tag, "manifest:launcher"])
            return Role(role, 0.85, [tag])

    for sym in symbols:
        if sym.kind in ("class", "struct") and sym.name in ("AppDelegate", "SceneDelegate"):
            return Role("entrypoint", 0.9, [f"symbol:{sym.name}"])
        meta_extends = " ".join([
            str(sym.meta.get("extends", "")), str(sym.meta.get("inherits", "")),
            " ".join(sym.meta.get("implements", []) if isinstance(sym.meta.get("implements"), list) else []),
        ])
        if re.search(r"\b(Activity|AppCompatActivity)\b", meta_extends):
            return Role("component", 0.7, [f"symbol:extends {meta_extends.strip()}"])
        if re.search(r"\b(Service|IntentService|JobService)\b", meta_extends):
            return Role("service", 0.7, [f"symbol:extends {meta_extends.strip()}"])
        if "ViewModel" in sym.name or "ViewModel" in meta_extends:
            return Role("view_model", 0.75, [f"symbol:{sym.name}"])

    for sym in symbols:
        if sym.kind == "component":
            return Role("component", 0.8, [f"symbol:{sym.kind}:{sym.name}"])
        if sym.kind == "hook":
            return Role("hook", 0.85, [f"symbol:{sym.name}"])

    if lang == "css":
        return Role("style", 0.8, ["lang:css"])
    if lang == "json":
        return Role("config", 0.6, ["lang:json"])
    if lang in ("objc", "swift") and name.endswith((".h",)):
        return Role("lib", 0.4, ["header"])

    return Role("unknown", 0.0, [])
