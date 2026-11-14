"""Markup adapters: Astro frontmatter, Svelte ``<script>`` blocks, HTML ids,
classes, scripts and linked assets, CSS selectors, custom properties and
``@import``."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from ..model import ImportRef, Symbol
from .common import Extracted
from . import ts as ts_adapter


class _HTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list = []
        self.classes: list = []
        self.scripts: list = []
        self.assets: list = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if "id" in data and data["id"]:
            self.ids.append(data["id"])
        if data.get("class"):
            self.classes.extend(part for part in data["class"].split() if part)
        if tag == "script" and data.get("src"):
            self.scripts.append(data["src"])
        if tag == "link" and data.get("href"):
            self.assets.append(data["href"])
        if tag in ("img", "source", "video") and data.get("src"):
            self.assets.append(data["src"])


def extract_html(text: str) -> Extracted:
    out = Extracted()
    parser = _HTML()
    try:
        parser.feed(text)
    except Exception:
        pass  # tolerant: a broken html file still yields what we saw
    for name in sorted(set(parser.ids)):
        out.symbols.append(Symbol(kind="asset", name=name, line=0))
    for name in sorted(set(parser.classes)):
        out.symbols.append(Symbol(kind="asset", name=name, line=0))
    for src in parser.scripts:
        out.imports.append(ImportRef(specifier=src, line=0, kind="script", names=[], reason="asset"))
    for href in parser.assets:
        out.imports.append(ImportRef(specifier=href, line=0, kind="link", names=[], reason="asset"))
    return out


_CSS_SELECTOR = re.compile(r"^\s*([.#][\w-][\w\->:, .#\[\]=\"'()]*?)\s*\{")
_CSS_PROP = re.compile(r"^\s*(--[\w-]+)\s*:")
_CSS_IMPORT = re.compile(r"^\s*@import\s+(?:url\()?['\"]([^'\"]+)['\"]")


def extract_css(text: str) -> Extracted:
    out = Extracted()
    seen_props = set()
    for match in re.finditer(r"(--[\w-]+)\s*:", text):
        name = match.group(1)
        if name not in seen_props:
            seen_props.add(name)
            out.symbols.append(Symbol(kind="const", name=name, line=0))
    for line in text.splitlines():
        imp = _CSS_IMPORT.match(line)
        if imp:
            out.imports.append(ImportRef(specifier=imp.group(1), line=0, kind="css-import",
                                         names=[], reason="css"))
            continue
        sel = _CSS_SELECTOR.match(line)
        if sel:
            for part in sel.group(1).split(","):
                part = part.strip()
                if part:
                    out.symbols.append(Symbol(kind="selector", name=part, line=0))
    return out


def extract_astro(text: str) -> Extracted:
    out = Extracted()
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].strip() == "---":
        end = None
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end = idx
                break
        if end is not None:
            front = "\n".join(lines[1:end])
            inner = ts_adapter.extract(front, "ts")
            out.symbols.extend(inner.symbols)
            out.imports.extend(inner.imports)
            out.exports.extend(inner.exports)
    return out


def extract_svelte(text: str) -> Extracted:
    out = Extracted()
    match = re.search(r"<script[^>]*>(.*?)</script>", text, re.DOTALL | re.IGNORECASE)
    if match:
        inner = ts_adapter.extract(match.group(1), "js")
        out.symbols.extend(inner.symbols)
        out.imports.extend(inner.imports)
        out.exports.extend(inner.exports)
    return out


def extract(text: str, lang: str = "html") -> Extracted:
    if lang == "astro":
        return extract_astro(text)
    if lang == "svelte":
        return extract_svelte(text)
    if lang == "css":
        return extract_css(text)
    return extract_html(text)
