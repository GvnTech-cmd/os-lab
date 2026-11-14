"""File-backed Overview presentation of the pinned first-party crawler formats."""
import json
from pathlib import Path

SPECS = json.loads((Path(__file__).with_name("source_manifest_specs.json")).read_text())


def dependency_category(name):
    name = name.lower()
    families = [
        ("Bundler / Tooling", ("webpack", "vite", "rollup", "esbuild", "parcel", "tsup", "babel", "typescript", "@types/")),
        ("UI / Framework", ("react", "vue", "svelte", "solid", "preact", "tailwind", "postcss", "lucide", "radix")),
        ("Extension Polyfills", ("webextension", "crx", "plasmo", "wxt", "chrome", "firefox")),
        ("Network & API", ("axios", "fetch", "socket", "octokit", "graphql", "trpc")),
        ("State & Utilities", ("lodash", "zustand", "redux", "rxjs", "dayjs", "date-fns", "immer")),
        ("Security & Parsers", ("purify", "cheerio", "crypto", "yaml", "marked", "sanitize")),
        ("Testing & Quality", ("jest", "vitest", "playwright", "puppeteer", "eslint", "prettier", "lint")),
    ]
    return next((category for category, tokens in families if any(token in name for token in tokens)), "General Ecosystem")


def overview(extensions, truncated=False):
    matrices = {"propsMatrix": {}, "depsMatrix": {}, "permsMatrix": {}}
    groups = {"serviceWorker": [], "persistentScript": [], "backgroundPage": [], "none": []}
    versions = {}
    def add(kind, name, slug, **extra):
        row = matrices[kind].setdefault(name, {"name": name, "slugs": [], "count": 0, **extra})
        if slug not in row["slugs"]:
            row["slugs"].append(slug)
            row["count"] += 1
        return row
    for ext in extensions:
        analysis = ext.get("manifestAnalysis")
        analysis = analysis if isinstance(analysis, dict) else {}
        manifest = analysis.get("manifest", analysis.get("raw_manifest"))
        manifest = manifest if isinstance(manifest, dict) else analysis
        slug = ext["slug"]
        mv = str(manifest.get("manifest_version", "unknown"))
        versions[slug] = mv
        keys = manifest.keys() if manifest is not analysis else analysis.get("manifest_keys", [])
        for key in keys:
            if not isinstance(key, str):
                continue
            add("propsMatrix", key, slug, **SPECS.get(key, {"category": "Platform", "mvStatus": "Review required",
                "specNote": "Operator-defined or vendor-specific manifest property.", "migrationNote": "Review vendor documentation for compatibility."}))
        permissions = [p for key in ("permissions", "host_permissions") for p in (manifest.get(key, []) if isinstance(manifest.get(key), list) else []) if isinstance(p, str)]
        for permission in set(permissions):
            risk = "high" if permission in {"<all_urls>", "webNavigation", "nativeMessaging", "webRequest", "webRequestBlocking"} or "://" in permission else "medium" if permission in {"tabs", "storage", "downloads", "activeTab", "scripting", "sidePanel", "alarms", "cookies", "history", "clipboardWrite", "clipboardRead", "declarativeNetRequest", "declarativeNetRequestWithHostAccess"} else "low" if permission in {"notifications", "identity", "contextMenus", "idle"} else "other"
            add("permsMatrix", permission, slug, risk=risk)
        deps = ext.get("dependencies") or {}
        dep_files = deps.values() if isinstance(deps, dict) else []
        sections = [(k, v) for k, v in deps.items() if k in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")] if isinstance(deps, dict) else []
        for file in dep_files:
            if isinstance(file, dict) and isinstance(file.get("deps"), dict):
                sections.extend(file["deps"].items())
        dep_names = set()
        for section, packages in sections:
            if not isinstance(packages, dict):
                continue
            for package in packages:
                row = add("depsMatrix", package, slug, category=dependency_category(package), sections=[])
                if section not in row["sections"]:
                    row["sections"].append(section)
                dep_names.add(package)
        bg = manifest.get("background") or analysis.get("background") or {}
        if isinstance(bg, dict):
            group = "serviceWorker" if bg.get("service_worker") else "backgroundPage" if bg.get("page") else "persistentScript" if bg.get("scripts") else "none"
        else:
            group = "serviceWorker" if str(bg).startswith("service_worker:") else "persistentScript" if str(bg).startswith("scripts:") else "backgroundPage" if str(bg).startswith("page:") else "none"
        groups[group].append(slug)
        ext.update({"name": manifest.get("name", ext["repo"]), "version": manifest.get("version", ""), "manifestVersion": mv,
                    "description": manifest.get("description", ""), "backgroundType": group,
                    "permissions": permissions, "riskLevel": analysis.get("risk_level", "unknown"),
                    "heuristicScore": analysis.get("heuristic_score"), "dependenciesCount": len(dep_names)})
    for row in matrices["propsMatrix"].values():
        row.update({"mv2": sum(versions[s] == "2" for s in row["slugs"]), "mv3": sum(versions[s] == "3" for s in row["slugs"])})
    stats = {"totalAnalyzed": len(extensions), "mv2Count": sum(v == "2" for v in versions.values()), "mv3Count": sum(v == "3" for v in versions.values()),
             "uniquePropsCount": len(matrices["propsMatrix"]), "uniqueDepsCount": len(matrices["depsMatrix"]), "uniquePermsCount": len(matrices["permsMatrix"]),
             **{key + "Count": len(value) for key, value in groups.items()}}
    return {"success": True, "extensions": extensions, "swGroups": groups, "truncated": truncated, "stats": stats,
            **{key: sorted(matrix.values(), key=lambda r: (-r["count"], r["name"])) for key, matrix in matrices.items()}}
