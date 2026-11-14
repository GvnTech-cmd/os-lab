"""Language registry.

A language is a registry entry; the walker and the engine never branch on a
language name.  ``parser`` records what the extractor actually uses (``ast``,
``regex``, ``block``, ``html``, ``css``, ``xml``, ``plist``, ``json`` or
``tree-sitter`` when the optional grammar extra is installed), never what was
requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

Grammar = Optional[Union[Tuple[str, str], str]]


@dataclass(frozen=True)
class LanguageSpec:
    name: str
    extensions: Tuple[str, ...]
    extractor: str
    parser: str
    grammar: Grammar = None  # tuple for the legacy tree-sitter path

    @property
    def kind(self) -> str:
        """Legacy classification used by older callers."""
        if self.name in {"astro", "svelte", "html", "xml", "storyboard"}:
            return "markup"
        if self.name in {"css"}:
            return "style"
        if self.name in {"plist", "json"}:
            return "config"
        return "code"


LANGUAGES: Tuple[LanguageSpec, ...] = (
    LanguageSpec("python", (".py",), "python_ast", "ast"),
    LanguageSpec("tsx", (".tsx",), "ts", "regex",
                 ("tree_sitter_typescript", "language_tsx")),
    LanguageSpec("ts", (".ts",), "ts", "regex",
                 ("tree_sitter_typescript", "language_typescript")),
    LanguageSpec("jsx", (".jsx",), "ts", "regex",
                 ("tree_sitter_javascript", "language")),
    LanguageSpec("js", (".js", ".mjs", ".cjs"), "ts", "regex",
                 ("tree_sitter_javascript", "language")),
    LanguageSpec("php", (".php",), "php", "regex",
                 ("tree_sitter_php", "language_php")),
    LanguageSpec("rust", (".rs",), "rust", "regex",
                 ("tree_sitter_rust", "language")),
    LanguageSpec("astro", (".astro",), "markup", "block"),
    LanguageSpec("svelte", (".svelte",), "markup", "block"),
    LanguageSpec("html", (".html", ".htm"), "markup", "html"),
    LanguageSpec("css", (".css", ".scss", ".sass", ".less"), "markup", "css"),
    # The new adapters are line-aware regex scanners in this release; the
    # optional tree-sitter bridges currently exist for TS/JS, PHP and Rust.
    LanguageSpec("swift", (".swift",), "swift", "regex"),
    LanguageSpec("objc", (".m", ".mm"), "objc", "regex"),
    LanguageSpec("h", (".h",), "objc", "regex"),  # ambiguous: ObjC / C / C++
    LanguageSpec("kotlin", (".kt", ".kts"), "kotlin", "regex"),
    LanguageSpec("java", (".java",), "java", "regex"),
    LanguageSpec("xml", (".xml",), "android_xml", "xml"),
    LanguageSpec("storyboard", (".storyboard", ".xib"), "android_xml", "xml"),
    LanguageSpec("plist", (".plist", ".entitlements"), "plist", "plist"),
    LanguageSpec("json", (".json",), "plist", "json"),
)

_BY_EXT = {ext: spec for spec in LANGUAGES for ext in spec.extensions}
ALL_EXTENSIONS = tuple(sorted(_BY_EXT))
CODE_EXTENSIONS = tuple(ext for ext, spec in _BY_EXT.items() if spec.kind == "code")
MARKUP_EXTENSIONS = tuple(ext for ext, spec in _BY_EXT.items() if spec.kind == "markup")
STYLE_EXTENSIONS = tuple(ext for ext, spec in _BY_EXT.items() if spec.kind == "style")

BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".webp", ".bmp", ".svgz",
    ".pdf", ".zip", ".gz", ".tgz", ".tar", ".rar", ".7z", ".bz2", ".xz",
    ".apk", ".aab", ".ipa", ".jar", ".aar", ".war", ".class", ".pyc", ".pyo",
    ".exe", ".dll", ".so", ".dylib", ".node", ".bin", ".dat", ".o", ".obj",
    ".der", ".p12", ".pem", ".crt", ".mobileprovision", ".provisionprofile",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".mp3", ".mp4", ".mov", ".avi", ".wav", ".ogg", ".webm", ".flac",
    ".db", ".sqlite", ".sqlite3", ".asar",
)

LOCKFILE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "composer.lock", "Gemfile.lock",
    "Podfile.lock", "Packages.resolved", "gradle.lockfile",
}


def detect(path: Union[str, Path]) -> Optional[LanguageSpec]:
    """Detect the language from the (possibly virtual) path."""
    lowered = str(path).lower()
    for ext in sorted(_BY_EXT, key=len, reverse=True):
        if lowered.endswith(ext):
            return _BY_EXT[ext]
    return None


def is_binary_name(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(ext) for ext in BINARY_SUFFIXES)


def is_lockfile(path: str) -> bool:
    return path.rsplit("/", 1)[-1] in LOCKFILE_NAMES
