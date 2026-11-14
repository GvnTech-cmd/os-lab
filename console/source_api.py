"""Namespaced Source Lab HTTP contracts, bounded file readers and job adapters."""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import urllib.parse

from source_artifacts import SourceArtifacts, ArtifactError, MAX_JSON, SLUG, _reject_constant
import source_control as control
import oslab


class Download:
    def __init__(self, content: bytes, mime: str, name: str):
        self.content, self.mime, self.name = content, mime, name


def redact(root: str, value):
    """Scrub secret fields and known process/config keys before serialization."""
    values = oslab.secret_values(root)
    def scrub(item):
        if isinstance(item, dict):
            return {key: "[redacted]" if oslab.is_secret(str(key)) else scrub(v) for key, v in item.items()}
        if isinstance(item, list):
            return [scrub(v) for v in item]
        return oslab.redact_text(root, item, values) if isinstance(item, str) else item
    return scrub(value)


def zip_download(root, content, name):
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 1000 or sum(e.file_size for e in entries) > 16 * 1024 * 1024:
                raise ArtifactError(413, "Merged archive exceeds the inspection limit")
            secrets = oslab.secret_values(root)
            for entry in entries:
                parts = entry.filename.split("/")
                if any(part in (".", "..") or part.startswith(".") or oslab.is_secret(part) or part.lower().endswith((".key", ".pem", ".p12")) for part in parts if part):
                    raise ArtifactError(403, "Merged archive contains a private or invalid file")
                data = archive.read(entry)
                if any(value.encode() in data for value in secrets if value):
                    raise ArtifactError(403, "Merged archive contains a configured credential")
                if b"\0" not in data:
                    text = data.decode("utf-8", errors="replace")
                    if oslab.redact_text(root, text, secrets) != text:
                        raise ArtifactError(403, "Merged archive requires credential review before downloading")
    except ArtifactError:
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, ValueError):
        raise ArtifactError(400, "Invalid merged archive") from None
    return Download(content, "application/zip", name)


class SourceAPI:
    # @lat: [[source-lab#Console operations]]
    def __init__(self, root, jobs, signer):
        self.root, self.jobs, self.signer = root, jobs, signer
        self.reader = SourceArtifacts(root)

    def _query(self, query: dict, allowed=()) -> dict:
        if set(query) - set(allowed) or any(len(v) != 1 for v in query.values()):
            raise ArtifactError(400, "Unexpected or duplicate query parameters")
        return {key: values[0] for key, values in query.items()}

    def runs(self, action=None):
        return [j for j in self.jobs.list() if j["lab"] == "source" and (action is None or j["action"] == action)]

    def _resource_reader(self):
        reader = SourceArtifacts(self.root)
        reader.storage = Path(os.environ.get("SOURCE_LAB_RESOURCES", str(self.reader.storage / "resources"))).expanduser().resolve()
        return reader

    def _repos(self):
        names, truncated = self.reader._directories(("analysis",), 100, SLUG)
        return names, truncated

    def _bundle(self, slug):
        SourceArtifacts._slug(slug)
        control.checked(self.reader.storage, "analysis/" + slug, exists=True)
        keys = {"manifestAnalysis": "manifest-analysis.json", "dependencies": "dependencies.json",
                "fileTree": "file-tree.json", "astIndex": "ast-index.json", "metadata": "metadata.json",
                "findings": "findings.json", "coverage": "coverage.json", "analysisV2": "analysis-v2.json", "repoMap": "repo-map.json"}
        result = {key: self.reader._json(("analysis", slug, file), optional=True) for key, file in keys.items()}
        workspace = control.checked(self.reader.storage, "cloned-repos/" + slug)
        return {"repo": slug.replace("__", "/", 1), "slug": slug, "isCloned": workspace.is_dir(),
                "clonedPath": "cloned-repos/" + slug if workspace.is_dir() else None, **result,
                "runtimeSessions": self.reader._detail(slug)["sessions"]}

    def get(self, path: str, query: dict):
        endpoint = path.removeprefix("/api/source/")
        if endpoint == "evidence":
            q = self._query(query, ("slug", "session"))
            return self.reader.evidence(q.get("slug"), q.get("session"))
        if endpoint == "evidence/report":
            q = self._query(query, ("slug", "file"))
            if set(q) != {"slug", "file"}:
                raise ArtifactError(400, "A target slug and report file are required")
            content, mime, name = self.reader.report(q["slug"], q["file"])
            if mime in ("application/json", "application/sarif+json"):
                parsed = json.loads(content, parse_constant=_reject_constant)
                content = json.dumps(redact(self.root, parsed), allow_nan=False).encode()
            else:
                content = redact(self.root, content.decode("utf-8")).encode()
            return Download(content, mime, name)
        if endpoint == "detection":
            self._query(query)
            health = control.readiness(self.root)
            runs = self.runs("detect")
            return {"targets": control.candidates(self.root), "runner": {"ready": health["state"] == "ready"}, "run": runs[0] if runs else None}
        if endpoint == "settings/runtime":
            self._query(query)
            return control.runtime(self.root)
        if endpoint == "analyzer":
            self._query(query)
            report = self.reader._json(("analysis", "report.json"), optional=True)
            raw = self.reader._read(("analysis", "summary.csv"), MAX_JSON, optional=True)
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8")))) if raw else []
            runs = self.runs("crawl")
            files, truncated = control.source_lists(self.root)
            return {"run": runs[0] if runs else None, "report": report, "summaryCount": len(rows), "summaryRows": rows[:50],
                    "sourceFiles": files, "sourceFilesTruncated": truncated}
        if endpoint == "sources":
            q = self._query(query, ("download", "origin"))
            if q.get("origin") not in (None, "resources", "generated"):
                raise ArtifactError(400, "Invalid catalog origin")
            generated = q.get("origin") == "generated"
            reader = self.reader if generated else self._resource_reader()
            folder = "catalogs" if generated else "sources"
            filenames = ("browser-extensions-merged.csv", "browser-extensions.csv", "browser-extension-repos.csv")
            if "download" in q:
                if q["download"] not in filenames:
                    raise ArtifactError(400, "Unknown catalog download")
                raw = reader._read((folder, q["download"]), MAX_JSON)
                return Download(redact(self.root, raw.decode("utf-8")).encode(), "text/csv; charset=utf-8", q["download"])
            lists, files = [], []
            for name in filenames:
                raw = reader._read((folder, name), MAX_JSON, optional=True)
                lists.append(list(csv.DictReader(io.StringIO(raw.decode("utf-8")))) if raw else [])
                if raw is not None:
                    files.append({"name": name, "type": "CSV", "size": len(raw)})
            merged, curated, monitored = lists
            return {"success": True, "mergedExtensions": merged, "curated": curated, "monitored": monitored,
                    "categories": sorted({r.get("category", "") for r in merged} - {""}), "files": files,
                    "stats": {"totalMerged": len(merged), "totalCurated": len(curated), "totalMonitored": len(monitored)}}
        if endpoint == "deep-analysis":
            q = self._query(query, ("repo", "file", "view"))
            if q.get("view") not in (None, "ast") or ("view" in q and "file" not in q):
                raise ArtifactError(400, "Invalid source view")
            if "file" in q and "repo" not in q:
                raise ArtifactError(400, "A file requires a repository")
            if "repo" in q:
                repo = q["repo"]
                slug = repo.replace("/", "__")
                SourceArtifacts._slug(slug)
                if "file" in q and q.get("view") == "ast":
                    if any(part.startswith(".") or oslab.is_secret(part) or part.lower().endswith((".key", ".pem", ".p12", ".db", ".sqlite")) for part in q["file"].split("/")):
                        raise ArtifactError(403, "Private file is not available")
                    index = self.reader._json(("analysis", slug, "ast-index.json"), optional=True) or []
                    if not isinstance(index, list):
                        raise ArtifactError(400, "Invalid AST index")
                    match = next((item for item in index if isinstance(item, dict) and item.get("path") == q["file"]), None)
                    if not match or not isinstance(match.get("file"), str) or not match["file"].startswith("ast/") or not match["file"].endswith(".json"):
                        raise ArtifactError(404, "AST artifact not available")
                    control.checked(self.reader.storage, "analysis/" + slug + "/" + match["file"], exists=True)
                    return {"repo": repo, "file": q["file"], "ast": self.reader._json(("analysis", slug, *match["file"].split("/")))}
                if "file" in q:
                    parts = q["file"].split("/")
                    if any(part.startswith(".") or oslab.is_secret(part) or part.lower().endswith((".key", ".pem", ".p12", ".db", ".sqlite")) for part in parts):
                        raise ArtifactError(403, "Private file is not available")
                    control.checked(self.reader.storage, "cloned-repos/" + slug + "/" + q["file"], exists=True)
                    raw = self.reader._read(("cloned-repos", slug, *parts), MAX_JSON)
                    if b"\0" in raw:
                        raise ArtifactError(400, "Binary source files are not displayed")
                    return {"repo": repo, "file": q["file"], "content": raw.decode("utf-8")}
                return self._bundle(slug)
            names, truncated = self._repos()
            return {"availableRepos": control.candidates(self.root), "analyzedRepos": [self._bundle(slug) for slug in names],
                    "truncated": truncated, "run": (self.runs("crawl") or [None])[0]}
        if endpoint == "analyzer/merged":
            q = self._query(query, ("export",))
            if q.get("export") not in (None, "json", "csv"):
                raise ArtifactError(400, "Unknown export format")
            names, truncated = self._repos()
            extensions = [self._bundle(slug) for slug in names]
            from source_overview import overview
            result = overview(extensions, truncated)
            if q.get("export") == "csv":
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["property", "category", "status", "count", "mv2", "mv3", "specification", "migration", "slugs"])
                def cell(value):
                    value = str(value)
                    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
                writer.writerows([cell(value) for value in [row["name"], row["category"], row["mvStatus"], row["count"], row["mv2"], row["mv3"],
                                 row["specNote"], row["migrationNote"], " ".join(row["slugs"])]] for row in result["propsMatrix"])
                return Download(redact(self.root, output.getvalue()).encode(), "text/csv; charset=utf-8", "extension-manifest-props-mapping.csv")
            return result
        if endpoint == "deep-analysis/merge":
            q = self._query(query, ("download", "plan", "slugs", "includeFlagged"))
            if "download" in q:
                if len(q) != 1 or not control.NAME.fullmatch(q["download"]):
                    raise ArtifactError(400, "Invalid merged download")
                return zip_download(self.root, self.reader._read(("merged", q["download"] + ".zip"), 10 * 1024 * 1024), q["download"] + ".zip")
            if "plan" in q:
                # GET remains read-only: preview the exact background manifest-plan job.
                return {"plan": control.build_plan(self.root, {"lab": "source", "action": "merge", "options": {
                    "slugs": q.get("slugs", "").split(","), "includeFlagged": q.get("includeFlagged") == "1", "plan": True}})}
            if q:
                raise ArtifactError(400, "Merge parameters require plan or download")
            folders, truncated = self.reader._directories(("merged",), 100, control.NAME)
            reports = [{"folder": name, "report": self.reader._json(("merged", name + ".report.json"), optional=True)} for name in folders]
            return {"runs": self.runs("merge"), "outputs": reports, "truncated": truncated}
        if endpoint == "brain" or endpoint.startswith("brain/files/"):
            self._query(query)
            if endpoint == "brain":
                manifest = self.reader._json(("brain-data", "manifest.json"))
                if not isinstance(manifest, dict) or not isinstance(manifest.get("tabs", []), list):
                    raise ArtifactError(400, "Invalid Brain manifest")
                providers = manifest.get("providers", {})
                if not isinstance(providers, dict) or len(manifest.get("tabs", [])) > 100:
                    raise ArtifactError(400, "Invalid Brain providers or tabs")
                for kind, file in providers.items():
                    if kind not in ("source", "history", "flow", "sequence", "aiRules") or not isinstance(file, str) or not file.endswith(".json"):
                        raise ArtifactError(400, "Invalid Brain provider")
                    control.checked(self.reader.storage, "brain-data/" + file)
                tabs = []
                ids = set()
                for tab in manifest.get("tabs", []):
                    if not isinstance(tab, dict) or not isinstance(tab.get("file"), str):
                        raise ArtifactError(400, "Invalid Brain tab")
                    if not isinstance(tab.get("id"), str) or not tab["id"] or tab["id"] in ids or not isinstance(tab.get("label"), str) or not tab["file"].endswith(".json"):
                        raise ArtifactError(400, "Invalid or duplicate Brain tab")
                    ids.add(tab["id"])
                    control.checked(self.reader.storage, "brain-data/" + tab["file"])
                    tabs.append({**tab, "graph": "/api/source/brain/files/" + tab["file"]})
                return {"data": {"manifest": manifest, "tabs": tabs}}
            relative = urllib.parse.unquote(endpoint.removeprefix("brain/files/"))
            if not relative.endswith(".json"):
                raise ArtifactError(400, "Brain files must be JSON")
            control.checked(self.reader.storage, "brain-data/" + relative, exists=True)
            return self.reader._json(("brain-data", *relative.split("/")))
        if endpoint == "pipeline":
            self._query(query)
            data = self.reader._json(("snapshots", "pipeline.json"), optional=True)
            if data is not None:
                if not isinstance(data, dict) or not isinstance(data.get("stages"), list):
                    raise ArtifactError(400, "Invalid Pipeline snapshot")
                for stage in data["stages"]:
                    if not isinstance(stage, dict) or any(not isinstance(stage.get(key), str) for key in ("id", "label", "phase", "description", "failure")) or type(stage.get("order")) is not int or any(not isinstance(stage.get(key), list) or any(not isinstance(item, str) for item in stage[key]) for key in ("reads", "writes", "network")):
                        raise ArtifactError(400, "Invalid Pipeline stage")
                return {"data": data, "available": True, "source": "operator-snapshot", "date": str(data.get("date", "unknown")),
                        "revision": str(data.get("revision", "unknown")), "message": "Operator-provided snapshot; not a live run."}
            reference = json.loads((Path(__file__).with_name("source_pipeline.json")).read_text())
            return {"data": reference["data"], "available": True, "source": "bundled-reference", "date": reference["date"],
                    "revision": reference["revision"], "message": "Pinned architecture reference; no run was performed."}
        if endpoint == "spotlight":
            q = self._query(query, ("q", "section", "limit"))
            text = q.get("q", "").strip().lower()
            if len(text) > 200 or q.get("section") not in (None, "evidence", "deep-analysis", "sources"):
                raise ArtifactError(400, "Invalid search")
            try:
                limit = int(q.get("limit", "4"))
            except ValueError:
                raise ArtifactError(400, "Invalid limit") from None
            if not 1 <= limit <= 25:
                raise ArtifactError(400, "Invalid limit")
            if not text and not q.get("section"):
                return {"data": []}
            names, truncated = self._repos()
            section = q.get("section", "evidence")
            if section == "sources":
                data = self.get("/api/source/sources", {})["mergedExtensions"]
                return {"data": [{"title": str(r.get("extension_name") or r.get("repo_name") or "Source"),
                                  "href": "/source/"} for r in data if text in json.dumps(r).lower()][:limit]}
            return {"data": [{"title": slug, "href": "/source/" + section + "/?" + urllib.parse.urlencode({"slug" if section == "evidence" else "repo": slug})}
                             for slug in names if text in slug.lower()][:limit], "truncated": truncated}
        raise ArtifactError(404, "Source Lab endpoint not found")

    def mutate(self, path: str, data: dict, method: str = "POST"):
        actions = {"/api/source/sources": "csv-merge", "/api/source/detection": "detect", "/api/source/analyzer": "crawl",
                   "/api/source/deep-analysis": "crawl", "/api/source/deep-analysis/merge": "merge",
                   "/api/source/settings/runtime": "runtime"}
        if path not in actions or (method == "DELETE" and path != "/api/source/detection"):
            raise ArtifactError(404, "Source Lab endpoint not found")
        if method == "DELETE" or data.get("action") in ("cancel", "stop"):
            if set(data) - {"action", "jobId"}:
                raise ArtifactError(400, "Unexpected cancel fields")
            job_id = data.get("jobId")
            job = self.jobs.get(job_id) if isinstance(job_id, str) else None
            if not job or job.lab != "source" or job.action != actions[path]:
                raise ArtifactError(404, "Source job not found for this operation")
            return 200, {"job": self.jobs.cancel(job_id).to_dict(logs=True)}
        if (set(data) - {"options", "token", "preview"} or not isinstance(data.get("options", {}), dict)
                or ("preview" in data and type(data["preview"]) is not bool)):
            raise ArtifactError(400, "Expected options and preview or token")
        request = {"lab": "source", "action": actions[path], "options": data.get("options", {})}
        plan = control.build_plan(self.root, request)
        signed = {"request": request, "plan": plan}
        if data.get("preview") is True:
            if "token" in data:
                raise ArtifactError(400, "A preview cannot carry a confirmation token")
            return 200, {"plan": plan, "token": self.signer.sign(signed)}
        if not self.signer.verify(signed, data.get("token")):
            raise ArtifactError(409, "Preview the exact options before running this action")
        job = self.jobs.start(plan)
        return 202, {"job": job.to_dict(logs=True)}
