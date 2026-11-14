#!/usr/bin/env python3
"""
ext_merger.py - merge many analyzed browser extensions into ONE MV3 extension.

How it works
------------
1. PLAN    Read ext-analysis/<slug>/manifest-analysis.json and decide, from the
           manifest alone, which extensions can be merged (no cloning needed).
2. ACQUIRE Re-use cloned-repos/<slug> or `git clone --depth 1` it.
3. BUILD   For every mergeable extension:
             * copy its tree to  ext/<slug>/          (no filename clashes)
             * wrap background + content scripts in a per-extension function
               scope (no top-level `const x` clashes) and give them a shimmed
               `chrome`/`browser` that namespaces storage, i18n, commands and
               runtime.getURL
             * convert MV2 -> MV3 where possible
             * fold permissions / host permissions / content scripts /
               web_accessible_resources / commands / DNR rulesets / locales
               into one manifest
           plus a "hub" popup + options page that lists every merged extension
           and opens each one's own popup / options page.
4. OUTPUT  ext-merged/<name>/ (load unpacked), ext-merged/<name>.zip and
           ext-merged/<name>.report.json

Extensions that cannot be merged safely are excluded WITH a reason (see
`plan_extension`/`build_extension`); nothing is silently dropped.

Known limits (also written to the report): extensions share one service
worker / one message bus, so runtime.sendMessage is not namespaced; bundled
webextension-polyfill copies read globalThis.chrome and bypass the shim;
single-slot manifest features (new-tab override, side panel, omnibox,
devtools page) go to the first extension that claims them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SKIP_DIRS = {".git", "node_modules", ".github", "__tests__", "__mocks__", "__snapshots__", "__MACOSX"}
FIREFOX_ONLY_PERMS = {
    "browserSettings", "captivePortal", "contextualIdentities", "find", "dns", "pkcs11",
    "mozillaAddons", "normandyAddonStudy", "networkStatus", "theme", "trialML", "urlbar",
    "webRequestFilterResponse", "webRequestFilterResponse.serviceWorkerScript", "menus.overrideContext",
}
DOM_API_RE = re.compile(r"\b(?:window|document)\s*[.\[]|\blocalStorage\b|\bXMLHttpRequest\b|\bnew\s+Audio\b")
MARKER = ".qx-merged"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(tag: str, slug: str, msg: str) -> None:
    print(f"[{tag}] [{slug}] {msg}", flush=True)


def safe_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "ext"


def rel(path: str) -> str:
    """Manifest-relative path -> clean relative path (no leading ./ or /)."""
    p = path.split("?")[0].split("#")[0]
    while p.startswith("./") or p.startswith("/"):
        p = p[2:] if p.startswith("./") else p[1:]
    return p


def is_host_pattern(p: str) -> bool:
    return p == "<all_urls>" or "://" in p or p.startswith("*")


def read_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # tolerate // line comments, which some manifests/messages files carry
        return json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M))


# ----------------------------------------------------------------------------
# 1. PLAN (manifest-only checks)
# ----------------------------------------------------------------------------


def load_candidates(analysis_dir: Path) -> List[Dict[str, Any]]:
    out = []
    for d in sorted(analysis_dir.iterdir()):
        mf = d / "manifest-analysis.json"
        if d.is_dir() and not d.name.startswith(".") and mf.is_file():
            try:
                data = read_json(mf)
            except Exception:
                continue
            data["_dir"] = d.name
            out.append(data)
    return out


# @lat: [[source-lab#Pipeline]]
def plan_extension(a: Dict[str, Any], include_flagged: bool) -> Tuple[List[str], List[str]]:
    """Returns (blocking_reasons, warnings) using only analysis data."""
    reasons: List[str] = []
    warns: List[str] = []
    m = a.get("raw_manifest")
    if not isinstance(m, dict):
        return ["no manifest data in analysis"], warns
    if m.get("manifest_version") not in (2, 3):
        reasons.append(f"unsupported manifest_version {m.get('manifest_version')}")
    if a.get("threat_indicators") and not include_flagged:
        reasons.append(f"flagged by threat scan ({len(a['threat_indicators'])} indicator(s)); enable 'include flagged' to override")
    if "chrome_settings_overrides" in m:
        reasons.append("overrides browser search/homepage settings")
    if "oauth2" in m:
        reasons.append("oauth2 client is bound to the original extension ID")
    bg = m.get("background") or {}
    if isinstance(bg, dict):
        if bg.get("page"):
            reasons.append("uses a background HTML page (cannot run inside a shared service worker)")
        if bg.get("type") == "module":
            reasons.append("ES-module background script (needs bundling)")
    perms = [p for p in m.get("permissions", []) if isinstance(p, str)]
    if "webRequestBlocking" in perms:
        reasons.append("blocking webRequest is not available in MV3")
    csp = m.get("content_security_policy")
    csp_text = csp if isinstance(csp, str) else json.dumps(csp or {})
    if "unsafe-eval" in csp_text.replace("wasm-unsafe-eval", ""):
        reasons.append("requires 'unsafe-eval' (not allowed in MV3)")
    if "sandbox" in m:
        warns.append("sandbox pages are not carried over")
    if m.get("manifest_version") == 2:
        warns.append("converted from MV2 to MV3")
    return reasons, warns


# ----------------------------------------------------------------------------
# 2. ACQUIRE
# ----------------------------------------------------------------------------


def acquire(a: Dict[str, Any], workspace: Path, allow_clone: bool, timeout: int) -> Optional[Path]:
    dest = workspace / a["_dir"]
    if dest.is_dir():
        return dest
    if not allow_clone:
        return None
    repo = a.get("repo") or a["_dir"].replace("__", "/")
    url = f"https://github.com/{repo}.git"
    workspace.mkdir(parents=True, exist_ok=True)
    log("+", a["_dir"], f"cloning {url}")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--single-branch", url, str(dest)],
                       check=True, capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as exc:  # noqa: BLE001 - report any clone failure as exclusion
        shutil.rmtree(dest, ignore_errors=True)
        log("-", a["_dir"], f"clone failed: {str(exc)[:160]}")
        return None
    return dest


def locate_extension_root(repo_dir: Path, raw: Dict[str, Any]) -> Optional[Path]:
    """Directory holding the manifest.json that matches the analyzed manifest."""
    found: List[Path] = []
    base_depth = len(repo_dir.parts)
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if len(Path(root).parts) - base_depth > 6:
            dirs[:] = []
        if "manifest.json" in files:
            found.append(Path(root))
    for d in found:
        try:
            m = read_json(d / "manifest.json")
        except Exception:
            continue
        if m.get("name") == raw.get("name") and m.get("version") == raw.get("version"):
            return d
    return found[0] if found else None


# ----------------------------------------------------------------------------
# 3. BUILD
# ----------------------------------------------------------------------------


class Exclude(Exception):
    pass


def node_check(path: Path) -> Optional[str]:
    try:
        r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None  # node unavailable: skip the syntax gate
    return None if r.returncode == 0 else (r.stderr.strip().splitlines() or ["syntax error"])[-1][:200]


def wrap_group(slug: str, files: List[Tuple[str, str]], shim: bool, base: str) -> str:
    head = '(function(chrome, browser, importScripts){\n' if shim else '(function(){\n'
    parts = [head]
    for i, (name, code) in enumerate(files):
        code = code.lstrip("﻿")
        if i == 0:
            code = re.sub(r"^\s*(['\"])use strict\1;?", "", code)
        parts.append(f"/* ---- {name} ---- */\n{code}\n")
    if shim:
        parts.append(f'}}).call(globalThis, __qx.api({json.dumps(slug)}), __qx.api({json.dumps(slug)}), '
                     f'__qx.imp({json.dumps(slug)}, {json.dumps(base)}));\n')
    else:
        parts.append('}).call(globalThis);\n')
    return "".join(parts)


def write_group(out_root: Path, rel_path: str, slug: str, files: List[Tuple[str, str]], allow_shim: bool,
                warnings: List[str], base: str = "") -> None:
    target = out_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    variants = [True, False] if allow_shim else [False]
    last_err = ""
    for shim in variants:
        target.write_text(wrap_group(slug, files, shim, base), encoding="utf-8")
        err = node_check(target)
        if err is None:
            if allow_shim and not shim:
                warnings.append(f"{rel_path}: could not apply the API shim (identifier clash); storage/i18n/getURL are NOT namespaced")
            return
        last_err = err
    raise Exclude(f"script group {rel_path} has a syntax problem when isolated: {last_err}")


HTML_HEAD_RE = re.compile(r"<head[^>]*>", re.I)
ABS_ATTR_RE = re.compile(r'(\b(?:src|href)\s*=\s*)(["\'])/(?!/)')
MSG_RE = re.compile(r"__MSG_([A-Za-z0-9_@]+)__")


def copy_tree(src: Path, dst: Path, slug: str, out_root: Path) -> None:
    for root, dirs, files in os.walk(src):
        r = Path(root)
        rel_root = r.relative_to(src)
        keep = []
        for d in dirs:
            if d in SKIP_DIRS or (d == "_locales" and rel_root == Path(".")):
                continue
            if d.startswith("_"):
                raise Exclude(f"contains reserved directory name '{d}' (Chrome rejects names starting with '_')")
            keep.append(d)
        dirs[:] = keep
        (dst / rel_root).mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.endswith(".map") or f in {".DS_Store"}:
                continue
            if f.startswith("_"):
                raise Exclude(f"contains reserved file name '{f}' (Chrome rejects names starting with '_')")
            s, t = r / f, dst / rel_root / f
            ext = f.lower().rsplit(".", 1)[-1]
            if ext in {"html", "htm"}:
                html = s.read_text(encoding="utf-8", errors="replace")
                html = ABS_ATTR_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}/ext/{slug}/", html)
                tags = f'<script src="/qx/shim.js"></script><script src="/qx/page-{slug}.js"></script>'
                if HTML_HEAD_RE.search(html):
                    html = HTML_HEAD_RE.sub(lambda m: m.group(0) + tags, html, count=1)
                else:
                    html = tags + html
                t.write_text(html, encoding="utf-8")
            elif ext == "css":
                css = s.read_text(encoding="utf-8", errors="replace")
                t.write_text(MSG_RE.sub(lambda m: f"__MSG_{slug}__{m.group(1)}__", css), encoding="utf-8")
            else:
                shutil.copy2(s, t)


def merge_locales(src: Path, slug: str, default_locale: Optional[str], store: Dict[str, Dict[str, Any]],
                  hub_default: str) -> None:
    loc = src / "_locales"
    if not loc.is_dir():
        return
    per_lang: Dict[str, Dict[str, Any]] = {}
    for lang_dir in loc.iterdir():
        mf = lang_dir / "messages.json"
        if not mf.is_file():
            continue
        try:
            msgs = read_json(mf)
        except Exception:
            continue
        per_lang[lang_dir.name] = {f"{slug}__{k}": v for k, v in msgs.items() if isinstance(v, dict)}
    for lang, msgs in per_lang.items():
        store.setdefault(lang, {}).update(msgs)
    if default_locale and default_locale in per_lang and default_locale != hub_default:
        for k, v in per_lang[default_locale].items():
            store.setdefault(hub_default, {}).setdefault(k, v)


def resolve_msg(value: Any, src: Path, default_locale: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    m = re.fullmatch(r"__MSG_(.+)__", value)
    if not m or not default_locale:
        return value
    try:
        msgs = read_json(src / "_locales" / default_locale / "messages.json")
        for k, v in msgs.items():
            if k.lower() == m.group(1).lower():
                return v.get("message", value)
    except Exception:
        pass
    return value


def to_host_split(perms: List[Any], host_perms: List[Any]) -> Tuple[List[str], List[str]]:
    p_out: List[str] = []
    h_out = [h for h in host_perms if isinstance(h, str)]
    for p in perms:
        if not isinstance(p, str):
            continue
        if is_host_pattern(p):
            h_out.append(p)
        elif p == "menus":
            p_out.append("contextMenus")
        elif p not in FIREFOX_ONLY_PERMS and p != "webRequestBlocking":
            p_out.append(p)
    return p_out, h_out


class Merged:
    """Accumulates the hub manifest while extensions are folded in."""

    def __init__(self) -> None:
        self.permissions: set = set()
        self.optional_permissions: set = set()
        self.host_permissions: set = set()
        self.optional_host_permissions: set = set()
        self.content_scripts: List[Dict[str, Any]] = []
        self.war: List[Dict[str, Any]] = []
        self.commands: Dict[str, Any] = {}
        self.suggested_keys = 0
        self.dnr: List[Dict[str, Any]] = []
        self.bg_files: List[str] = []
        self.overrides: Dict[str, str] = {}
        self.single: Dict[str, Tuple[str, Any]] = {}  # side_panel / omnibox / devtools_page
        self.wasm_eval = False
        self.min_chrome = 0
        self.locales: Dict[str, Dict[str, Any]] = {}
        self.hub_default_locale = "en"
        self.has_locales = False
        self.extensions: List[Dict[str, Any]] = []
        self.dropped: List[Dict[str, str]] = []

    def drop(self, slug: str, feature: str, why: str) -> None:
        self.dropped.append({"slug": slug, "feature": feature, "reason": why})


def build_extension(a: Dict[str, Any], src_repo: Path, out_root: Path, acc: Merged) -> Dict[str, Any]:
    """Fold one extension into `acc`/`out_root`. Raises Exclude on failure."""
    slug = safe_id(a["_dir"])
    raw = a["raw_manifest"]
    root = locate_extension_root(src_repo, raw)
    if root is None:
        raise Exclude("manifest.json not found in cloned source")
    m = read_json(root / "manifest.json")
    warnings: List[str] = []
    prefix = f"ext/{slug}/"

    def P(p: str) -> str:
        return prefix + rel(p)

    def exists(p: str) -> bool:
        return (root / rel(p)).is_file()

    mv = m.get("manifest_version", 3)
    default_locale = m.get("default_locale")

    # --- background -----------------------------------------------------
    bg = m.get("background") or {}
    bg_files: List[str] = []
    if isinstance(bg, dict):
        if bg.get("service_worker"):
            bg_files = [bg["service_worker"]]
        elif isinstance(bg.get("scripts"), list):
            bg_files = list(bg["scripts"])
    missing = [f for f in bg_files if not exists(f)]
    if missing:
        raise Exclude(f"background file(s) missing from source (needs a build step?): {', '.join(missing[:3])}")
    bg_group = None
    if bg_files:
        chunks = [(f, (root / rel(f)).read_text(encoding="utf-8", errors="replace")) for f in bg_files]
        if mv == 2 and any(DOM_API_RE.search(c) for _, c in chunks):
            raise Exclude("MV2 background uses window/document/localStorage/XHR, unavailable in a service worker")
        if any(re.search(r"^\s*(import|export)\s[^;]*?\bfrom\b|^\s*export\s", c, re.M) for _, c in chunks):
            raise Exclude("background uses ES module syntax (needs bundling)")
        bg_group = f"bg/{slug}.js"
        write_group(out_root, bg_group, slug, chunks, True, warnings, os.path.dirname(rel(bg_files[0])))
        if any(re.search(r"\bimportScripts\s*\(", c) for _, c in chunks):
            warnings.append("nested importScripts() are redirected into the extension folder but run in the shared global scope")

    # --- content scripts --------------------------------------------------
    content: List[Dict[str, Any]] = []
    for i, cs in enumerate(m.get("content_scripts") or []):
        entry = {k: v for k, v in cs.items() if k not in {"js", "css"}}
        js, css = cs.get("js") or [], cs.get("css") or []
        bad = [f for f in js + css if not exists(f)]
        if bad:
            raise Exclude(f"content script file(s) missing from source (needs a build step?): {', '.join(bad[:3])}")
        if js:
            chunks = [(f, (root / rel(f)).read_text(encoding="utf-8", errors="replace")) for f in js]
            main_world = cs.get("world") == "MAIN"
            grp = f"cs/{slug}-{i}.js"
            write_group(out_root, grp, slug, chunks, not main_world, warnings)
            entry["js"] = [grp] if main_world else ["qx/shim.js", grp]
        if css:
            entry["css"] = [P(f) for f in css]
        content.append(entry)

    # --- pages ------------------------------------------------------------
    action = m.get("action") or m.get("browser_action") or m.get("page_action") or {}
    popup = action.get("default_popup") if isinstance(action, dict) else None
    opts = (m.get("options_ui") or {}).get("page") or m.get("options_page")
    for label, val in (("popup", popup), ("options", opts)):
        if val and not exists(val):
            warnings.append(f"{label} page '{val}' missing from source; not linked")
            if label == "popup":
                popup = None
            else:
                opts = None
    if not (bg_group or content or popup or opts):
        raise Exclude("nothing mergeable (no background, content scripts, popup or options page)")

    # --- copy tree (after checks so excluded extensions leave nothing behind)
    copy_tree(root, out_root / "ext" / slug, slug, out_root)
    (out_root / "qx").mkdir(exist_ok=True)
    (out_root / "qx" / f"page-{slug}.js").write_text(f'__qx.patchPage({json.dumps(slug)});\n', encoding="utf-8")

    # --- commit to accumulator (nothing below may raise) --------------------
    perms, hosts = to_host_split(m.get("permissions") or [], m.get("host_permissions") or [])
    acc.permissions.update(perms)
    acc.host_permissions.update(hosts)
    operms, ohosts = to_host_split(m.get("optional_permissions") or [], m.get("optional_host_permissions") or [])
    acc.optional_permissions.update(operms)
    acc.optional_host_permissions.update(ohosts)
    if bg_group:
        acc.bg_files.append(bg_group)
    acc.content_scripts.extend(content)

    war = m.get("web_accessible_resources") or []
    if war and isinstance(war[0], str):
        acc.war.append({"resources": [P(r) for r in war], "matches": ["<all_urls>"]})
    else:
        for w in war:
            if isinstance(w, dict) and w.get("resources"):
                entry = {k: v for k, v in w.items() if k != "resources"}
                entry["resources"] = [P(r) for r in w["resources"]]
                acc.war.append(entry)

    for cname, c in (m.get("commands") or {}).items():
        if cname.startswith("_execute_"):
            acc.drop(slug, f"command {cname}", "action/page-action shortcuts cannot be shared in a merged extension")
            continue
        c = dict(c)
        desc = c.get("description", cname)
        c["description"] = MSG_RE.sub(lambda mm: f"__MSG_{slug}__{mm.group(1)}__", desc) if "__MSG_" in desc else f"[{slug}] {desc}"
        if "suggested_key" in c:
            if acc.suggested_keys >= 4:
                c.pop("suggested_key")
                acc.drop(slug, f"shortcut for {cname}", "Chrome allows 4 suggested shortcuts per extension; assign it manually")
            else:
                acc.suggested_keys += 1
        acc.commands[f"{slug}__{cname}"] = c

    for rs in (m.get("declarative_net_request") or {}).get("rule_resources", []):
        if exists(rs.get("path", "")):
            acc.dnr.append({"id": f"{slug}_{rs['id']}", "enabled": rs.get("enabled", True), "path": P(rs["path"])})
            warnings.append("declarativeNetRequest ruleset ids are prefixed; code that toggles rulesets by id will not find them")

    for key, val in (m.get("chrome_url_overrides") or {}).items():
        if key in acc.overrides:
            acc.drop(slug, f"chrome_url_overrides.{key}", f"already claimed by {acc.overrides[key].split('/')[1]}")
        elif exists(val):
            acc.overrides[key] = P(val)
    if m.get("side_panel", {}).get("default_path"):
        acc.single.setdefault("side_panel", (slug, {"default_path": P(m["side_panel"]["default_path"])}))
        if acc.single["side_panel"][0] != slug:
            acc.drop(slug, "side_panel", f"already claimed by {acc.single['side_panel'][0]}")
    if m.get("omnibox"):
        if "omnibox" in acc.single:
            acc.drop(slug, "omnibox", f"already claimed by {acc.single['omnibox'][0]}")
        else:
            acc.single["omnibox"] = (slug, m["omnibox"])
    if m.get("devtools_page"):
        if "devtools_page" in acc.single or not exists(m["devtools_page"]):
            acc.drop(slug, "devtools_page", "only one devtools page is allowed per extension")
        else:
            acc.single["devtools_page"] = (slug, P(m["devtools_page"]))
    for feature in ("externally_connectable", "incognito", "key", "update_url", "sidebar_action", "applications",
                    "browser_specific_settings", "storage"):
        if feature in m:
            acc.drop(slug, feature, "not applicable to a merged extension")

    csp = m.get("content_security_policy")
    if "wasm-unsafe-eval" in (csp if isinstance(csp, str) else json.dumps(csp or {})):
        acc.wasm_eval = True
    mc = str(m.get("minimum_chrome_version", "")).split(".")[0]
    if mc.isdigit():
        acc.min_chrome = max(acc.min_chrome, int(mc))

    if acc.has_locales is False and default_locale:
        acc.hub_default_locale = default_locale
    if (root / "_locales").is_dir():
        acc.has_locales = True
        merge_locales(root, slug, default_locale, acc.locales, acc.hub_default_locale)

    info = {
        "slug": slug,
        "repo": a.get("repo"),
        "name": resolve_msg(m.get("name"), root, default_locale) or a.get("name") or slug,
        "version": m.get("version", ""),
        "description": resolve_msg(m.get("description"), root, default_locale),
        "originalManifestVersion": mv,
        "popup": P(popup) if popup else None,
        "options": P(opts) if opts else None,
        "hasBackground": bool(bg_group),
        "contentScriptGroups": len(content),
        "permissions": len(perms) + len(hosts),
        "warnings": warnings,
    }
    if mv == 2 and not popup and (m.get("browser_action") or m.get("page_action")):
        warnings.append("relied on a toolbar click handler without a popup; that click is now taken by the hub popup")
    acc.extensions.append(info)
    return info


# ----------------------------------------------------------------------------
# hub UI + shim + icons
# ----------------------------------------------------------------------------

SHIM_JS = r"""// Generated by ext_merger.py - per-extension API namespacing for merged extensions.
(function (g) {
  if (g.__qx) return;
  var real = g.chrome || g.browser;
  var cb = function (args) { return typeof args[args.length - 1] === 'function' ? args.pop() : null; };
  function respond(p, f) { if (f) { p.then(f, function () { f(); }); return undefined; } return p; }

  function area(r, slug) {
    var pfx = slug + '::';
    var strip = function (o) { var x = {}; for (var k in (o || {})) if (k.indexOf(pfx) === 0) x[k.slice(pfx.length)] = o[k]; return x; };
    var keyify = function (k) {
      if (k == null) return null;
      if (typeof k === 'string') return pfx + k;
      if (Array.isArray(k)) return k.map(function (x) { return pfx + x; });
      var o = {}; Object.keys(k).forEach(function (n) { o[pfx + n] = k[n]; }); return o;
    };
    var api = {
      get: function () { var a = [].slice.call(arguments), f = cb(a), k = a[0];
        return respond(r.get(k == null ? null : keyify(k)).then(strip), f); },
      set: function (items) { var a = [].slice.call(arguments), f = cb(a);
        var o = {}; Object.keys(items || {}).forEach(function (n) { o[pfx + n] = items[n]; });
        return respond(r.set(o), f); },
      remove: function (keys) { var a = [].slice.call(arguments), f = cb(a);
        var list = [].concat(keys).map(function (x) { return pfx + x; });
        return respond(r.remove(list), f); },
      clear: function () { var a = [].slice.call(arguments), f = cb(a);
        return respond(r.get(null).then(function (all) {
          return r.remove(Object.keys(all).filter(function (k) { return k.indexOf(pfx) === 0; }));
        }), f); },
      onChanged: wrapEvent(r.onChanged, function (fn) {
        return function (changes, name) { var s = strip(changes); if (Object.keys(s).length) fn(s, name); };
      })
    };
    return new Proxy(r, { get: function (t, p) { return p in api ? api[p] : t[p]; } });
  }

  function wrapEvent(ev, mk) {
    if (!ev) return ev;
    var map = new Map();
    return {
      addListener: function (fn) { var w = mk(fn); map.set(fn, w); ev.addListener(w); },
      removeListener: function (fn) { var w = map.get(fn); if (w) { ev.removeListener(w); map.delete(fn); } },
      hasListener: function (fn) { return map.has(fn); }
    };
  }

  function overrides(slug) {
    var url = function (p) { return real.runtime.getURL('ext/' + slug + '/' + String(p || '').replace(/^\/+/, '')); };
    var o = {
      runtime: { getURL: url },
      extension: { getURL: url },
      i18n: { getMessage: function (n) { var a = [].slice.call(arguments);
        if (String(n).charAt(0) !== '@') a[0] = slug + '__' + n; return real.i18n.getMessage.apply(real.i18n, a); } }
    };
    if (real.storage) {
      var st = { onChanged: wrapEvent(real.storage.onChanged, function (fn) {
        var pfx = slug + '::';
        return function (changes, name) { var s = {}; for (var k in changes) if (k.indexOf(pfx) === 0) s[k.slice(pfx.length)] = changes[k];
          if (Object.keys(s).length) fn(s, name); };
      }) };
      ['local', 'sync', 'session', 'managed'].forEach(function (n) { if (real.storage[n]) st[n] = area(real.storage[n], slug); });
      o.storage = st;
    }
    if (real.commands) {
      o.commands = { onCommand: wrapEvent(real.commands.onCommand, function (fn) {
        return function (c, tab) { if (c.indexOf(slug + '__') === 0) fn(c.slice(slug.length + 2), tab); };
      }) };
    }
    return o;
  }

  function imp(slug, base) {
    return function () {
      var urls = [].map.call(arguments, function (u) {
        u = String(u);
        if (/^[a-z][a-z0-9+.-]*:/i.test(u)) return u;
        var p = u.charAt(0) === '/' ? u.slice(1) : (base ? base + '/' : '') + u.replace(/^\.\//, '');
        return 'ext/' + slug + '/' + p;
      });
      return g.importScripts.apply(g, urls);
    };
  }

  function api(slug) {
    var over = overrides(slug);
    if (!real.menus && real.contextMenus) over.menus = real.contextMenus;
    var sub = {};
    return new Proxy(real, {
      get: function (t, p) {
        if (!(p in over)) return t[p];
        if (p === 'menus') return over.menus;
        if (!sub[p]) { var mine = over[p]; sub[p] = new Proxy(t[p] || {}, { get: function (tt, q) { return q in mine ? mine[q] : tt[q]; } }); }
        return sub[p];
      }
    });
  }

  // Extension pages are separate documents, so patch the real object in place.
  function patchPage(slug) {
    var over = overrides(slug);
    Object.keys(over).forEach(function (ns) {
      Object.keys(over[ns]).forEach(function (k) { try { real[ns][k] = over[ns][k]; } catch (e) { /* read-only */ } });
    });
  }
  g.__qx = { api: api, imp: imp, patchPage: patchPage };
})(globalThis);
"""

HUB_JS = r"""(async function () {
  var data = await (await fetch('/hub/extensions.json')).json();
  var mode = document.body.dataset.mode;
  var root = document.getElementById('list');
  var q = document.getElementById('q');
  function open(path) { chrome.tabs.create({ url: chrome.runtime.getURL(path) }); }
  function el(tag, props, kids) {
    var e = document.createElement(tag); Object.assign(e, props || {});
    (kids || []).forEach(function (k) { e.append(k); }); return e;
  }
  function render() {
    var term = (q && q.value || '').toLowerCase();
    root.textContent = '';
    data.extensions.filter(function (x) { return (x.name + ' ' + x.description).toLowerCase().indexOf(term) >= 0; })
      .forEach(function (x) {
        var row = el('div', { className: 'ext' }, [
          el('div', { className: 'name', textContent: x.name + ' ' + x.version }),
          el('div', { className: 'desc', textContent: x.description || x.repo || '' })
        ]);
        var bar = el('div', { className: 'bar' });
        if (x.popup) bar.append(el('button', { textContent: 'Open', onclick: function () { open(x.popup); } }));
        if (x.options) bar.append(el('button', { textContent: 'Options', onclick: function () { open(x.options); } }));
        row.append(bar);
        if (mode === 'options') {
          (x.warnings || []).forEach(function (w) { row.append(el('div', { className: 'warn', textContent: '! ' + w })); });
        }
        root.append(row);
      });
  }
  document.getElementById('count').textContent = data.extensions.length + ' extensions merged';
  if (q) q.addEventListener('input', render);
  render();
  if (mode === 'options') {
    var ex = document.getElementById('excluded');
    data.excluded.forEach(function (x) { ex.append(el('li', { textContent: x.name + ' - ' + x.reasons.join('; ') })); });
    var dr = document.getElementById('dropped');
    data.dropped.forEach(function (x) { dr.append(el('li', { textContent: x.slug + ': ' + x.feature + ' - ' + x.reason })); });
  }
})();
"""

HUB_CSS = """body{font:13px system-ui,sans-serif;margin:0;padding:12px;min-width:340px;color:#e2e8f0;background:#0f172a}
h1{font-size:15px;margin:0 0 4px}#count{color:#94a3b8;margin-bottom:8px}
input{width:100%;box-sizing:border-box;padding:6px;margin-bottom:8px;border-radius:6px;border:1px solid #334155;background:#1e293b;color:inherit}
.ext{border:1px solid #334155;border-radius:8px;padding:8px;margin-bottom:6px;background:#111c33}
.name{font-weight:600}.desc{color:#94a3b8;font-size:12px;margin:2px 0 6px}
.bar button{margin-right:6px;padding:3px 10px;border-radius:5px;border:0;background:#0891b2;color:#fff;cursor:pointer}
.warn{color:#fbbf24;font-size:11px}ul{padding-left:18px;color:#94a3b8}
.popup #list{max-height:480px;overflow:auto}"""


def hub_html(mode: str, title: str) -> str:
    extra = ('<h2>Excluded</h2><ul id="excluded"></ul><h2>Dropped features</h2><ul id="dropped"></ul>'
             if mode == "options" else "")
    cls = "popup" if mode == "popup" else ""
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
            f'<link rel="stylesheet" href="/hub/hub.css"></head><body class="{cls}" data-mode="{mode}">'
            f'<h1>{title}</h1><div id="count"></div><input id="q" placeholder="Filter extensions">'
            f'<div id="list"></div>{extra}<script src="/hub/hub.js"></script></body></html>')


def make_png(size: int, rgb: Tuple[int, int, int]) -> bytes:
    rows = b""
    for y in range(size):
        row = b"\x00"
        for x in range(size):
            t = (x + y) / (2 * size)
            row += bytes(int(c * (0.65 + 0.35 * (1 - t))) for c in rgb) + b"\xff"
        rows += row

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def finalize(acc: Merged, out_root: Path, name: str, excluded: List[Dict[str, Any]]) -> Dict[str, Any]:
    (out_root / "qx").mkdir(exist_ok=True)
    (out_root / "qx" / "shim.js").write_text(SHIM_JS, encoding="utf-8")
    hub = out_root / "hub"
    hub.mkdir(exist_ok=True)
    (hub / "popup.html").write_text(hub_html("popup", name), encoding="utf-8")
    (hub / "options.html").write_text(hub_html("options", f"{name} - overview"), encoding="utf-8")
    (hub / "hub.js").write_text(HUB_JS, encoding="utf-8")
    (hub / "hub.css").write_text(HUB_CSS, encoding="utf-8")
    (hub / "extensions.json").write_text(json.dumps(
        {"extensions": acc.extensions, "excluded": excluded, "dropped": acc.dropped}, indent=2), encoding="utf-8")
    for size in (16, 48, 128):
        (hub / f"icon{size}.png").write_bytes(make_png(size, (8, 145, 178)))

    (out_root / "background.js").write_text(
        "// Generated by ext_merger.py\nimportScripts('qx/shim.js');\n"
        f"var MERGED_BACKGROUNDS = {json.dumps(acc.bg_files, indent=2)};\n"
        "MERGED_BACKGROUNDS.forEach(function (f) {\n"
        "  try { importScripts(f); } catch (e) { console.error('[merged] ' + f + ' failed', e); }\n"
        "});\n", encoding="utf-8")

    war = acc.war
    manifest: Dict[str, Any] = {
        "manifest_version": 3,
        "name": name,
        "version": "1.0.0",
        "description": f"{len(acc.extensions)} extensions merged into one by iExtensionCrawler.",
        "icons": {str(s): f"hub/icon{s}.png" for s in (16, 48, 128)},
        "action": {"default_popup": "hub/popup.html", "default_icon": {str(s): f"hub/icon{s}.png" for s in (16, 48, 128)}},
        "options_ui": {"page": "hub/options.html", "open_in_tab": True},
        "background": {"service_worker": "background.js"},
    }
    if acc.permissions:
        manifest["permissions"] = sorted(acc.permissions)
    if acc.host_permissions:
        manifest["host_permissions"] = sorted(acc.host_permissions)
    if acc.optional_permissions:
        manifest["optional_permissions"] = sorted(acc.optional_permissions)
    if acc.optional_host_permissions:
        manifest["optional_host_permissions"] = sorted(acc.optional_host_permissions)
    if acc.content_scripts:
        manifest["content_scripts"] = acc.content_scripts
    if war:
        manifest["web_accessible_resources"] = war
    if acc.commands:
        manifest["commands"] = acc.commands
    if acc.dnr:
        manifest["declarative_net_request"] = {"rule_resources": acc.dnr}
    if acc.overrides:
        manifest["chrome_url_overrides"] = acc.overrides
    if "side_panel" in acc.single:
        manifest["side_panel"] = acc.single["side_panel"][1]
        manifest["permissions"] = sorted(set(manifest.get("permissions", [])) | {"sidePanel"})
    if "omnibox" in acc.single:
        manifest["omnibox"] = acc.single["omnibox"][1]
    if "devtools_page" in acc.single:
        manifest["devtools_page"] = acc.single["devtools_page"][1]
    if acc.wasm_eval:
        manifest["content_security_policy"] = {"extension_pages": "script-src 'self' 'wasm-unsafe-eval'; object-src 'self'"}
    if acc.min_chrome:
        manifest["minimum_chrome_version"] = str(acc.min_chrome)
    if acc.has_locales:
        manifest["default_locale"] = acc.hub_default_locale
        for lang, msgs in acc.locales.items():
            d = out_root / "_locales" / lang
            d.mkdir(parents=True, exist_ok=True)
            (d / "messages.json").write_text(json.dumps(msgs, indent=1, ensure_ascii=False), encoding="utf-8")
        if acc.hub_default_locale not in acc.locales:
            acc.has_locales = False
            manifest.pop("default_locale")
            shutil.rmtree(out_root / "_locales", ignore_errors=True)
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


# ----------------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis-dir", default="ext-analysis")
    ap.add_argument("--workspace", default="cloned-repos")
    ap.add_argument("--out", default="ext-merged")
    ap.add_argument("--name", default="Merged Extension")
    ap.add_argument("--slugs", default="all", help="comma-separated ext-analysis dir names, or 'all'")
    ap.add_argument("--include-flagged", action="store_true", help="also merge extensions flagged by the threat scan")
    ap.add_argument("--no-clone", action="store_true", help="only use sources already in the workspace")
    ap.add_argument("--clone-timeout", type=int, default=240)
    ap.add_argument("--mv", type=int, choices=(2, 3), help="only merge extensions whose original manifest_version matches")
    ap.add_argument("--plan", action="store_true", help="manifest-only mergeability check; prints JSON and exits")
    args = ap.parse_args()

    analysis_dir, workspace, out_base = Path(args.analysis_dir), Path(args.workspace), Path(args.out)
    wanted = None if args.slugs == "all" else {s.strip() for s in args.slugs.split(",") if s.strip()}
    cands = [c for c in load_candidates(analysis_dir) if wanted is None or c["_dir"] in wanted]
    if args.mv:
        cands = [c for c in cands if (c.get("raw_manifest") or {}).get("manifest_version") == args.mv]

    planned, excluded = [], []
    for a in cands:
        reasons, warns = plan_extension(a, args.include_flagged)
        entry = {"slug": a["_dir"], "name": a.get("name") or a["_dir"], "repo": a.get("repo"), "reasons": reasons, "warnings": warns}
        (excluded if reasons else planned).append(entry)

    if args.plan:
        print(json.dumps({"mergeable": planned, "excluded": excluded}))
        return 0
    if not planned:
        print("[!] nothing mergeable in the selection", flush=True)
        return 2

    folder = safe_id(args.name)
    out_root = out_base / folder
    if out_root.exists():
        if not (out_root / MARKER).exists():
            print(f"[!] refusing to overwrite {out_root}: not created by ext_merger", flush=True)
            return 3
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    (out_root / MARKER).write_text(now(), encoding="utf-8")

    for e in excluded:
        log("-", e["slug"], "EXCLUDED " + "; ".join(e["reasons"]))

    acc = Merged()
    by_dir = {c["_dir"]: c for c in cands}
    for e in planned:
        a = by_dir[e["slug"]]
        slug = e["slug"]
        src = acquire(a, workspace, not args.no_clone, args.clone_timeout)
        try:
            if src is None:
                raise Exclude("source not available (clone failed or --no-clone)")
            info = build_extension(a, src, out_root, acc)
            info["planWarnings"] = e["warnings"]
            info["warnings"] = e["warnings"] + info["warnings"]
            log("+", slug, f"MERGED {info['name']} {info['version']}")
        except Exclude as exc:
            sid = safe_id(slug)
            shutil.rmtree(out_root / "ext" / sid, ignore_errors=True)
            (out_root / "bg" / f"{sid}.js").unlink(missing_ok=True)
            for f in (out_root / "cs").glob(f"{sid}-*.js"):
                f.unlink()
            (out_root / "qx" / f"page-{sid}.js").unlink(missing_ok=True)
            excluded.append({"slug": slug, "name": e["name"], "repo": e["repo"], "reasons": [str(exc)], "warnings": []})
            log("-", slug, f"EXCLUDED {exc}")

    if not acc.extensions:
        print("[!] every candidate was excluded; nothing to build", flush=True)
        return 2

    manifest = finalize(acc, out_root, args.name, excluded)
    zip_path = out_base / f"{folder}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out_root.rglob("*")):
            if f.is_file() and f.name != MARKER:
                z.write(f, f.relative_to(out_root).as_posix())

    report = {
        "name": args.name, "folder": folder, "outDir": str(out_root), "zip": str(zip_path),
        "generatedAt": now(), "manifest": manifest, "merged": acc.extensions, "excluded": excluded,
        "droppedFeatures": acc.dropped,
        "stats": {
            "merged": len(acc.extensions), "excluded": len(excluded),
            "permissions": len(manifest.get("permissions", [])), "hostPermissions": len(manifest.get("host_permissions", [])),
            "contentScriptEntries": len(acc.content_scripts), "backgrounds": len(acc.bg_files),
            "commands": len(acc.commands), "zipBytes": zip_path.stat().st_size,
        },
        "limits": [
            "runtime.sendMessage is one shared bus: merged extensions can receive each other's messages",
            "bundled webextension-polyfill reads globalThis.chrome and bypasses storage/i18n namespacing",
            "single-slot features (new tab override, side panel, omnibox, devtools) go to the first claimant",
            "not loaded in a real browser by this tool; verify in chrome://extensions before relying on it",
        ],
    }
    (out_base / f"{folder}.report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[+] [merge] DONE {len(acc.extensions)} merged, {len(excluded)} excluded -> {out_root}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
