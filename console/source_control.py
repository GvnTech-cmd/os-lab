"""Source Lab console adapter; engine code runs only in child processes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def python() -> str:
    return os.environ.get("SOURCE_LAB_PYTHON") or sys.executable


def readiness(root: str) -> dict:
    try:
        result = subprocess.run([python(), str(Path(root) / "source-lab/run.py"), "status", "--json"],
                                capture_output=True, text=True, timeout=8)
        report = json.loads(result.stdout)
        if not isinstance(report, dict) or "storage" not in report:
            raise ValueError()
        return report
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"state": "unavailable", "python": {}, "storage": {}, "optional": {}, "capabilities": []}


def lab_status(root: str, os_name: str) -> dict:
    report = readiness(root) if os_name in ("linux", "macos", "windows") else {}
    installed = (Path(root) / "source-lab/run.py").is_file()
    version = str(report.get("python", {}).get("version", "")).split(".")
    supported = len(version) >= 2 and all(p.isdigit() for p in version[:2]) and tuple(map(int, version[:2])) >= (3, 11)
    runnable = supported and installed
    writable = report.get("storage", {}).get("writable", False)
    requirements = [
        {"id": "python", "label": "Python 3.11+", "found": runnable, "required": True,
         "hint": "Install Python 3.11+ and set SOURCE_LAB_PYTHON if needed."},
        {"id": "storage", "label": "Writable Source Lab storage", "found": writable, "required": True,
         "hint": "Set SOURCE_LAB_STORAGE to a writable private directory."},
    ]
    for tool in ("git", "node", "tree_sitter", "playwright"):
        requirements.append({"id": tool, "label": tool, "found": bool(report.get("optional", {}).get(tool)),
                             "required": False, "hint": "Optional; static detection does not need this tool."})
    state = "unavailable" if not runnable else "ready" if writable else "needs-setup"
    return {"id": "source", "label": "Source Lab", "summary": "Local source and package analysis across five platforms.",
            "provider": "native-python" if runnable else None, "state": state, "requirements": requirements,
            "reasons": [] if state == "ready" else [r["hint"] for r in requirements if r["required"] and not r["found"]],
            "notes": ["Static analysis needs no VM, KVM, Docker or network downloads."], "installed": installed,
            "capabilities": report.get("capabilities", []),
            "actions": [{"id": a, "label": a.capitalize(), "description": d, "privileged": False} for a, d in
                        (("status", "Read Source Lab readiness."), ("doctor", "Check core and optional tools."),
                         ("setup", "Create private storage directories; no downloads."))] if runnable else []}



# Request validation is repeated when the confirmed worker starts. Paths are
# never supplied as command strings. @lat: [[source-lab#Console operations]]
import re
import stat
import urllib.parse
from source_artifacts import SourceArtifacts, ArtifactError, SLUG, MAX_JSON, redirected

NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}\Z", re.ASCII)
REPO = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z", re.ASCII)
PLATFORMS = {"auto", "browser-extension", "windows-app", "macos-app", "android-app", "ios-app"}


def storage(root: str) -> Path:
    return SourceArtifacts(root).storage


def checked(base: Path, relative: str, *, exists: bool = False) -> Path:
    if not isinstance(relative, str) or len(relative) > 2048:
        raise ArtifactError(400, "Invalid relative path")
    parts = relative.split("/")
    if any(not NAME.fullmatch(part) or part in (".", "..") for part in parts):
        raise ArtifactError(400, "Invalid relative path")
    target = base
    for part in parts:
        target = target / part
        if redirected(target):
            raise ArtifactError(400, "Symlinks are not allowed")
        if target.exists() and not (target.is_dir() or target.is_file()):
            raise ArtifactError(400, "Only regular files and directories are allowed")
    if exists and not target.exists():
        raise ArtifactError(404, "Source path not found")
    return target


def safe_tree(path: Path) -> None:
    """Inputs and outputs must not contain redirecting links or special files."""
    count = 0
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            count += 1
            child = Path(parent) / name
            if count > 100000:
                raise ArtifactError(413, "Source tree exceeds the validation limit")
            info = child.lstat()
            mode = info.st_mode
            if redirected(child, info) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ArtifactError(400, "Source tree contains a link or special file")


def prepare(root: str) -> Path:
    base = storage(root)
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ("analysis", "cloned-repos", "targets", "merged", "catalogs", "control"):
        checked(base, name).mkdir(mode=0o700, exist_ok=True)
    return base


def candidates(root: str) -> list[dict]:
    base = storage(root)
    result = []
    for folder in ("cloned-repos", "targets"):
        path = checked(base, folder)
        if not path.exists():
            continue
        with os.scandir(path) as entries:
            for index, item in enumerate(entries):
                if index >= 1000:
                    break
                if not NAME.fullmatch(item.name) or item.is_symlink() or redirected(Path(item.path)):
                    continue
                if item.is_dir(follow_symlinks=False) or (item.is_file(follow_symlinks=False) and Path(item.name).suffix.lower() in
                        {".apk", ".xapk", ".apks", ".aab", ".ipa", ".exe", ".dll", ".sys", ".node"}):
                    slug = item.name if folder == "cloned-repos" and SLUG.fullmatch(item.name) else "local__" + item.name
                    if len(slug) > 200:
                        continue
                    result.append({"key": folder + "/" + item.name, "name": item.name, "slug": slug,
                                   "kind": "directory" if item.is_dir(follow_symlinks=False) else "package", "source": folder})
                if len(result) >= 100:
                    return result
    return sorted(result, key=lambda item: item["key"])


def source_lists(root: str) -> tuple[list[dict], bool]:
    base = storage(root)
    resources = Path(os.environ.get("SOURCE_LAB_RESOURCES", str(base / "resources"))).expanduser().resolve()
    directory = checked(resources, "sources")
    if not directory.exists():
        return [], False
    files, truncated = [], False
    with os.scandir(directory) as entries:
        for index, entry in enumerate(entries):
            if index >= 1000 or len(files) >= 100:
                truncated = True
                break
            suffix = Path(entry.name).suffix.lower()
            if NAME.fullmatch(entry.name) and entry.is_file(follow_symlinks=False) and not redirected(Path(entry.path)) and suffix in (".csv", ".txt", ".xlsx"):
                files.append({"name": entry.name, "format": suffix[1:].upper()})
    return sorted(files, key=lambda item: item["name"]), truncated


def list_targets(root: str, path: Path) -> list[str]:
    result = subprocess.run([python(), str(Path(root) / "source-lab/list_inputs.py"), str(path)],
                            capture_output=True, text=True, timeout=10)
    if result.returncode != 0 or len(result.stdout) > 65536:
        raise ArtifactError(400, "Invalid or oversized source list")
    try:
        values = json.loads(result.stdout)
    except ValueError:
        raise ArtifactError(400, "Invalid source list") from None
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ArtifactError(400, "Choose 1–100 source targets")
    base = storage(root)
    local = {}
    for item in candidates(root):
        if item["kind"] == "directory":
            candidate = checked(base, item["key"], exists=True)
            local[str(candidate)] = candidate
            local[item["key"]] = candidate
    normalized = []
    for value in values:
        if not isinstance(value, str):
            raise ArtifactError(400, "Invalid source target")
        if value in local:
            safe_tree(local[value])
            normalized.append(str(local[value]))
            continue
        if value.startswith("https://github.com/"):
            url = urllib.parse.urlsplit(value)
            if url.query or url.fragment or url.username or url.password:
                raise ArtifactError(400, "Credentials and URL parameters are not permitted")
            value = url.path.strip("/").removesuffix(".git")
        if not REPO.fullmatch(value) or any(p in (".", "..") for p in value.split("/")):
            raise ArtifactError(400, "Source lists may contain GitHub slugs or available private targets only")
        normalized.append(value)
    return list(dict.fromkeys(normalized))


def _integer(options: dict, key: str, default: int, maximum: int) -> int:
    value = options.get(key, default)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ArtifactError(400, f"Invalid {key}")
    return value


def _boolean(options: dict, key: str, default: bool = False) -> bool:
    value = options.get(key, default)
    if type(value) is not bool:
        raise ArtifactError(400, f"Invalid {key}")
    return value


def http_url(value) -> str:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise ArtifactError(400, "Invalid canary URL")
    url = urllib.parse.urlsplit(value)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ArtifactError(400, "Use an HTTP(S) canary URL without credentials, query or fragment")
    return value


def runtime(root: str) -> dict:
    base = storage(root)
    key = checked(base, "control/session-hmac.key")
    env_key, env_file = os.environ.get("IQ_SESSION_HMAC_KEY"), os.environ.get("IQ_SESSION_HMAC_KEY_FILE")
    source = "env" if env_key is not None else "env-file" if env_file else "managed-file" if key.exists() else "none"
    configured = False
    problem = None
    material = None
    try:
        file_material = None
        if env_file:
            fd = os.open(env_file, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError()
                file_material = stream.read(4097).rstrip(b"\r\n")
        if env_key is not None:
            material = env_key.encode()
            if file_material is not None and material != file_material:
                raise ValueError()
        elif env_file:
            material = file_material
        elif key.exists():
            material = SourceArtifacts(root)._read(("control", "session-hmac.key"), 4096).rstrip(b"\r\n")
        configured = material is not None and 32 <= len(material) <= 4096
    except (OSError, ValueError):
        problem = "Session key is unavailable, ambiguous or invalid"
    settings = SourceArtifacts(root)._json(("control", "runtime-settings.json"), optional=True) or {}
    test_url = http_url(settings.get("testUrl", "https://example.test"))
    return {"key": {"configured": configured, "source": source,
                    "problem": problem or (None if configured or source == "none" else "Session key is unavailable or too short")},
            "canary": {"testUrl": test_url}, "playwright": bool(readiness(root).get("optional", {}).get("playwright")),
            "rotationWarning": "Rotating the key prevents verification of earlier sessions."}


def build_plan(root: str, request: dict) -> dict:
    import oslab
    if not isinstance(request, dict) or set(request) - {"lab", "action", "options"} or request.get("lab") != "source":
        raise ArtifactError(400, "Invalid Source Lab request")
    if len(json.dumps(request, allow_nan=False).encode()) > 65536:
        raise ArtifactError(413, "Source request exceeds the size limit")
    action = request.get("action")
    options = request.get("options", {})
    if not isinstance(options, dict):
        raise ArtifactError(400, "Options must be an object")
    allowed = {
        "status": set(), "doctor": set(), "setup": set(),
        "detect": {"target", "platform", "runCanary", "testUrl", "session"},
        "crawl": {"target", "repos", "sourceFile", "workers", "depth", "noAst", "noMetadata", "resume", "keepWorkspace", "retries", "cloneTimeout", "apiMaxWait", "maxTreeEntries", "maxAstFiles", "noMap", "mapDetail", "mapMaxFiles", "mapBudgetMs"},
        "merge": {"slugs", "name", "includeFlagged", "allowClone", "mv", "plan"},
        "csv-merge": set(),
        "runtime": {"action", "rotate", "testUrl", "slug", "session"},
    }
    if not isinstance(action, str) or action not in allowed or set(options) - allowed[action]:
        raise ArtifactError(400, "Unsupported Source Lab action or options")
    base = storage(root)
    args = [str(Path(root) / "source-lab/run.py")]
    effects = ["Reads operator-supplied local inputs; generated output stays in private Source Lab storage."]
    timeout = 3600
    if action in ("status", "doctor", "setup"):
        args += [action]
        effects = ["Creates private storage, without downloads." if action == "setup" else "Reads readiness without changing state."]
        timeout = 30
    elif action == "detect":
        target = next((item for item in candidates(root) if item["key"] == options.get("target")), None)
        platform = options.get("platform", "auto")
        if target is None or not isinstance(platform, str) or platform not in PLATFORMS:
            raise ArtifactError(400, "Choose an available target and platform")
        path = checked(base, target["key"], exists=True)
        safe_tree(path)
        output = checked(base, "analysis/" + target["slug"])
        if output.exists():
            safe_tree(output)
        args += ["detect", str(path), "--output", str(output), "--format", "all"]
        if platform != "auto":
            args += ["--platform", platform]
        session = options.get("session")
        canary = _boolean(options, "runCanary")
        if canary or session:
            if not runtime(root)["key"]["configured"]:
                raise ArtifactError(409, "Runtime evidence needs a configured signing key")
        if session:
            if not isinstance(session, str) or not re.fullmatch(r"ses_[A-Za-z0-9_.-]+", session):
                raise ArtifactError(400, "Invalid session ID")
            session_path = checked(base, "analysis/" + target["slug"] + "/runtime-sessions/" + session, exists=True)
            safe_tree(session_path)
            args += ["--session", str(session_path)]
        if canary:
            if platform not in ("auto", "browser-extension"):
                raise ArtifactError(400, "Canary collection requires a browser-extension target")
            args += ["--run-canary", http_url(options.get("testUrl", runtime(root)["canary"]["testUrl"]))]
            effects.append("Starts optional browser tooling and contacts the chosen test URL. Synthetic sessions cannot confirm runtime findings.")
        elif "testUrl" in options:
            raise ArtifactError(400, "testUrl requires runCanary")
    elif action == "crawl":
        args += ["crawl"]
        repos = options.get("repos")
        source = options.get("sourceFile")
        candidate_key = options.get("target")
        if sum(bool(v) for v in (repos, source, candidate_key)) != 1:
            raise ArtifactError(400, "Choose repositories, a source list or an available private target")
        if candidate_key:
            target = next((item for item in candidates(root) if item["key"] == candidate_key and item["kind"] == "directory"), None)
            if target is None:
                raise ArtifactError(400, "Choose an available private directory")
            path = checked(base, target["key"], exists=True)
            safe_tree(path)
            args += [str(path)]
        elif repos:
            if not isinstance(repos, list) or not 1 <= len(repos) <= 100 or any(not isinstance(r, str) or not REPO.fullmatch(r) or any(p in (".", "..") for p in r.split("/")) for r in repos):
                raise ArtifactError(400, "Use GitHub owner/repo identifiers")
            args += repos
        else:
            resource = Path(os.environ.get("SOURCE_LAB_RESOURCES", str(base / "resources"))).expanduser().resolve()
            if not isinstance(source, str) or "/" in source or Path(source).suffix.lower() not in (".csv", ".txt", ".xlsx"):
                raise ArtifactError(400, "Choose an available source list")
            args += list_targets(root, checked(resource, "sources/" + source, exists=True))
        args += ["--workers", str(_integer(options, "workers", 1, 8)), "--depth", str(_integer(options, "depth", 1, 10))]
        for key, flag, default, cap in (("retries", "--retries", 3, 5), ("cloneTimeout", "--clone-timeout", 300, 600),
                ("apiMaxWait", "--api-max-wait", 90, 120), ("maxTreeEntries", "--max-tree-entries", 50000, 50000),
                ("maxAstFiles", "--max-ast-files", 200, 1000), ("mapMaxFiles", "--map-max-files", 4000, 10000),
                ("mapBudgetMs", "--map-budget-ms", 30000, 120000)):
            args += [flag, str(_integer(options, key, default, cap))]
        if _boolean(options, "noMap"):
            args.append("--no-map")
        if "mapDetail" in options:
            if options["mapDetail"] not in ("files", "symbols", "full"):
                raise ArtifactError(400, "Invalid map detail")
            args += ["--map-detail", options["mapDetail"]]
        for key, flag, default in (("noAst", "--no-ast", True), ("noMetadata", "--no-metadata", True),
                                   ("resume", "--resume", False), ("keepWorkspace", "--keep-workspace", True)):
            if _boolean(options, key, default):
                args.append(flag)
        effects.append("Reads the selected private directory; GitHub metadata is optional." if candidate_key else "Contacts GitHub for explicitly selected sources; may clone repositories. No credentials are accepted in requests or command arguments.")
        for folder in ("analysis", "cloned-repos"):
            path = checked(base, folder)
            if path.exists():
                safe_tree(path)
    elif action == "csv-merge":
        resources = Path(os.environ.get("SOURCE_LAB_RESOURCES", str(base / "resources"))).expanduser().resolve()
        source = checked(resources, "sources", exists=True)
        safe_tree(source)
        for name in ("browser-extensions.csv", "browser-extension-repos.csv"):
            file = checked(source, name, exists=True)
            if file.stat().st_size > MAX_JSON:
                raise ArtifactError(413, "Catalog exceeds the input limit")
        for folder in ("analysis", "catalogs"):
            path = checked(base, folder)
            if path.exists():
                safe_tree(path)
        args += ["merge-csvs", "--sources", str(source), "--analysis-dir", str(checked(base, "analysis")),
                 "--output-dir", str(checked(base, "catalogs"))]
        effects = ["Joins operator catalogs with private analysis metadata into private catalogs/. Resource inputs remain unchanged. No network access."]
    elif action == "merge":
        slugs = options.get("slugs")
        if not isinstance(slugs, list) or not 1 <= len(slugs) <= 100:
            raise ArtifactError(400, "Select target slugs explicitly")
        for slug in slugs:
            if not isinstance(slug, str):
                raise ArtifactError(400, "Invalid slug")
            SourceArtifacts._slug(slug)
            safe_tree(checked(base, "analysis/" + slug, exists=True))
            workspace = checked(base, "cloned-repos/" + slug)
            if workspace.exists():
                safe_tree(workspace)
        output = checked(base, "merged")
        if output.exists():
            safe_tree(output)
        name = options.get("name", "Merged Extension")
        if not isinstance(name, str) or not 1 <= len(name) <= 60 or any(ord(c) < 32 for c in name):
            raise ArtifactError(400, "Invalid extension name")
        args += ["merge", "--slugs", ",".join(slugs), "--name", name]
        if _boolean(options, "includeFlagged"):
            args += ["--include-flagged"]
        if not _boolean(options, "allowClone"):
            args += ["--no-clone"]
        else:
            effects.append("May clone selected repositories from GitHub.")
        if "mv" in options:
            if type(options["mv"]) is not int or options["mv"] not in (2, 3):
                raise ArtifactError(400, "Invalid manifest version")
            args += ["--mv", str(options["mv"])]
        if _boolean(options, "plan"):
            args += ["--plan"]
        effects.append("Builds only operator-authorized extensions for disposable lab browser profiles.")
    else:
        operation = options.get("action")
        if operation != "verify-session" and set(options) & {"slug", "session"}:
            raise ArtifactError(400, "Unexpected session selection")
        if operation == "verify-session":
            if set(options) != {"action", "slug", "session"}:
                raise ArtifactError(400, "Choose a target slug and session to verify")
            SourceArtifacts._slug(options["slug"])
            if not isinstance(options["session"], str) or not re.fullmatch(r"ses_[A-Za-z0-9_.-]+", options["session"]):
                raise ArtifactError(400, "Invalid session ID")
            session_path = checked(base, "analysis/" + options["slug"] + "/runtime-sessions/" + options["session"], exists=True)
            safe_tree(session_path)
            if not runtime(root)["key"]["configured"]:
                raise ArtifactError(409, "Session verification needs a configured signing key")
            effects = ["Verifies signed metadata, events and artifact hashes locally; no key is displayed or network request made."]
        elif operation == "generate-key":
            info = runtime(root)
            if info["key"]["source"] in ("env", "env-file"):
                raise ArtifactError(409, "The key is owned by the environment")
            rotate = _boolean(options, "rotate")
            if info["key"]["source"] != "none" and not rotate:
                raise ArtifactError(409, "A key exists; explicitly request rotation")
            if "testUrl" in options:
                raise ArtifactError(400, "Unexpected testUrl")
            effects = ["Creates a private signing key; its value never reaches the UI."]
            if rotate:
                effects.append("WARNING: previous sessions will no longer verify with the new key.")
        elif operation == "set-canary":
            http_url(options.get("testUrl"))
            if "rotate" in options:
                raise ArtifactError(400, "Unexpected rotate")
            effects = ["Stores the default test URL; no network request is made."]
        else:
            raise ArtifactError(400, "Unknown runtime settings action")
        args = [str(Path(root) / "console/source_worker.py"), json.dumps(request, sort_keys=True, separators=(",", ":"))]
        timeout = 30
    effects.append("Records the action in private local job history.")
    engine_args = args
    if action != "runtime":
        args = [str(Path(root) / "console/source_worker.py"), "--run", root,
                json.dumps(request, sort_keys=True, separators=(",", ":"))]
    return {"lab": "source", "action": action, "provider": "native-python", "workspace": root,
            "engineArgs": engine_args if action != "runtime" else None,
            "program": python(), "args": args, "effects": effects, "timeoutSec": timeout,
            "privileged": False, "runnable": True, "manualCommand": None, "setup": None,
            "display": " ".join(oslab._quote(p) for p in [python(), *args])}


# Keep oslab.plan's ordinary source previews and namespaced previews identical.
def plan(root: str, request: dict) -> dict:
    import oslab
    try:
        return build_plan(root, request)
    except ArtifactError as error:
        raise oslab.PlanError(str(error)) from None
