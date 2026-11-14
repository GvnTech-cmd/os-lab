"""Opt-in, file-allowlisted legacy import with hashes, private backups and rollback."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from uuid import uuid4

from source_lab.contracts import validate
from source_lab.evidence.session import SessionBundleReader

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "console"))
import source_control as control
import source_jobs
from source_artifacts import SourceArtifacts, SLUG, SESSION

MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
REPORTS = {"analysis-v2.json", "findings.json", "coverage.json", "manifest-analysis.json", "dependencies.json", "file-tree.json", "ast-index.json", "repo-map.json", "metadata.json", "summary.md", "report.sarif", "report.stix.json"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path: Path, cap=MAX_FILE):
    if control.redirected(path):
        raise ValueError("Linked import files are not allowed")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Only regular import files are allowed")
        value = stream.read(cap + 1)
    if len(value) > cap:
        raise ValueError("Import file exceeds the size limit")
    return value


def strict_json(data):
    def invalid(_):
        raise ValueError("Nonfinite JSON is not supported")
    return json.loads(data, parse_constant=invalid)


def entries(path: Path):
    values = []
    with os.scandir(path) as items:
        for item in items:
            if len(values) >= 1000:
                raise ValueError("Directory exceeds the import entry limit")
            values.append(Path(item.path))
    return sorted(values)


def valid_destination(relative):
    if relative == "control/runtime-settings.json":
        return True
    parts = relative.split("/") if isinstance(relative, str) else []
    if len(parts) < 3 or parts[0] != "analysis" or not SLUG.fullmatch(parts[1]):
        return False
    tail = parts[2:]
    if len(tail) == 1:
        return tail[0] in REPORTS
    if len(tail) == 2 and tail[0] == "ast":
        return bool(control.NAME.fullmatch(tail[1])) and tail[1].endswith(".json")
    if len(tail) >= 3 and tail[0] == "runtime-sessions" and SESSION.fullmatch(tail[1]):
        rest = tail[2:]
        return (len(rest) == 1 and rest[0] in ("session.json", "events.jsonl", "manifest.json", "manifest.sig")) or (len(rest) == 2 and rest[0] == "artifacts" and bool(control.NAME.fullmatch(rest[1])) and Path(rest[1]).suffix in (".json", ".txt"))
    return False


def plan(source: Path, slugs: list[str], settings: Path | None = None):
    if control.redirected(source) or not source.is_dir():
        raise ValueError("Choose an explicit regular analysis directory")
    source = source.resolve()
    destination = control.storage(str(ROOT))
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Source and destination must be separate trees")
    files, excluded, sessions = [], [], []
    total = 0
    def add(path, relative):
        nonlocal total
        if not valid_destination(relative):
            raise ValueError("Excluded import destination")
        data = read(path)
        total += len(data)
        if len(files) >= 1000 or total > MAX_TOTAL:
            raise ValueError("Import exceeds aggregate limits")
        if path.suffix in (".json", ".sarif"):
            value = strict_json(data)
            kind = {"analysis-v2.json": "AnalysisV2", "coverage.json": "Coverage", "repo-map.json": "RepoMapV1"}.get(path.name)
            if kind and validate(value, kind):
                raise ValueError("Import artifact has an unsupported contract")
            if path.name == "findings.json" and (not isinstance(value, list) or any(validate(item, "Finding") for item in value)):
                raise ValueError("Invalid imported findings")
        elif path.name == "events.jsonl":
            if any(not isinstance(strict_json(line), dict) for line in data.splitlines() if line.strip()):
                raise ValueError("Imported events must be JSON objects")
        else:
            if b"\0" in data:
                raise ValueError("Binary imports are excluded")
            data.decode("utf-8")
        target = control.checked(destination, relative)
        before = digest(read(target)) if target.exists() else None
        files.append({"source": str(path), "destination": relative, "sha256": digest(data), "bytes": len(data), "before": before})
    for slug in dict.fromkeys(slugs):
        if not SLUG.fullmatch(slug) or len(slug) > 200:
            raise ValueError("Invalid selected analysis slug")
        folder = control.checked(source, slug, exists=True)
        for entry in entries(folder):
            if entry.name in REPORTS:
                add(entry, f"analysis/{slug}/{entry.name}")
            elif entry.name == "ast":
                if control.redirected(entry) or not entry.is_dir():
                    raise ValueError("Invalid AST directory")
                for ast in entries(entry):
                    if ast.suffix == ".json" and control.NAME.fullmatch(ast.name):
                        add(ast, f"analysis/{slug}/ast/{ast.name}")
                    else:
                        excluded.append(f"{slug}/ast/{ast.name}")
            elif entry.name == "runtime-sessions":
                if control.redirected(entry) or not entry.is_dir():
                    raise ValueError("Invalid session directory")
                for session in entries(entry):
                    if not SESSION.fullmatch(session.name) or control.redirected(session) or not session.is_dir():
                        raise ValueError("Invalid session directory")
                    control.safe_tree(session)
                    members = []
                    for p in session.rglob("*"):
                        if p.is_file():
                            if len(members) >= 1000:
                                raise ValueError("Session member limit exceeded")
                            members.append(p)
                    def permitted(p):
                        rel = p.relative_to(session).as_posix()
                        return rel in ("session.json", "events.jsonl", "manifest.json", "manifest.sig") or (rel.startswith("artifacts/") and p.suffix in (".json", ".txt"))
                    if any(not permitted(p) for p in members):
                        excluded.append(f"{slug}/runtime-sessions/{session.name}: private/binary members; whole bundle held out")
                        continue
                    key = None
                    if "IQ_SESSION_HMAC_KEY" not in os.environ and not os.environ.get("IQ_SESSION_HMAC_KEY_FILE"):
                        managed = control.checked(destination, "control/session-hmac.key")
                        if managed.exists():
                            key = read(managed, 4096).rstrip(b"\r\n")
                    try:
                        verification = SessionBundleReader(session, hmac_key=key).verify_integrity()
                    except RuntimeError:
                        raise ValueError("A valid signing key is required for imported sessions") from None
                    covered = strict_json(read(session / "manifest.json"))
                    sealed = {name.replace("\\", "/") for name in covered} if isinstance(covered, dict) else set()
                    actual = {p.relative_to(session).as_posix() for p in members if p.name not in ("manifest.json", "manifest.sig")}
                    if sealed != actual:
                        raise ValueError("Session has unsigned or missing members")
                    if not verification["valid"] or not verification["signature_verified"]:
                        raise ValueError("Imported session signature/integrity verification failed")
                    target_session = control.checked(destination, f"analysis/{slug}/runtime-sessions/{session.name}")
                    if target_session.exists():
                        raise ValueError("A destination session already exists; signed sessions cannot be overwritten")
                    sessions.append({"slug": slug, "id": session.name, "signature_verified": True})
                    for member in sorted(members):
                        add(member, f"analysis/{slug}/runtime-sessions/{session.name}/{member.relative_to(session).as_posix()}")
            else:
                excluded.append(f"{slug}/{entry.name}")
    if settings is not None:
        value = strict_json(read(settings))
        if not isinstance(value, dict) or set(value) != {"testUrl"}:
            raise ValueError("Only the default canary URL can be imported; keys/settings credentials are excluded")
        control.http_url(value["testUrl"])
        add(settings, "control/runtime-settings.json")
    result = {"files": files, "excluded": excluded, "sessions": sessions, "count": len(files), "bytes": total}
    result["fingerprint"] = digest(json.dumps(result, sort_keys=True).encode())
    return result


def write(relative, data):
    base = control.prepare(str(ROOT))
    parent = Path(relative).parent.as_posix()
    if parent != ".":
        control.checked(base, parent).mkdir(mode=0o700, parents=True, exist_ok=True)
    source_jobs.atomic(str(ROOT), relative, data)


def journal(id):
    if not re.fullmatch(r"[0-9a-f]{32}", id):
        raise ValueError("Invalid import journal ID")
    return f"control/imports/{id}.json"


def rollback(id, apply=False):
    relative = journal(id)
    base = control.storage(str(ROOT))
    value = strict_json(read(control.checked(base, relative, exists=True)))
    if not isinstance(value, dict) or value.get("id") != id or not isinstance(value.get("files"), list):
        raise ValueError("Invalid import journal")
    changes = []
    for item in reversed(value["files"]):
        if not isinstance(item, dict) or not valid_destination(item.get("destination")):
            raise ValueError("Excluded rollback destination")
        target = control.checked(base, item["destination"])
        current = digest(read(target)) if target.exists() else None
        if current == item["before"]:
            continue
        if current != item["sha256"]:
            raise ValueError("Rollback conflicts with a newer destination edit; nothing was changed")
        backup = None
        if item["before"] is not None:
            expected = f"control/import-backups/{id}/{item['destination']}"
            if item.get("backup") != expected:
                raise ValueError("Invalid backup path")
            backup = read(control.checked(base, expected, exists=True))
            if digest(backup) != item["before"]:
                raise ValueError("Backup hash does not match")
        changes.append((item["destination"], backup))
    result = {"id": id, "restoreCount": len(changes), "fingerprint": digest(json.dumps(value, sort_keys=True).encode())}
    if apply:
        for destination, backup in changes:
            if backup is None:
                control.checked(base, destination, exists=True).unlink()
            else:
                write(destination, backup)
        value["state"] = "rolled-back"
        write(relative, json.dumps(value, indent=2).encode())
    return result


def copy(plan_value, expected):
    if expected != plan_value["fingerprint"] or not plan_value["files"]:
        raise ValueError("Review the dry-run fingerprint before copying nonempty inputs")
    fd = source_jobs.claim(str(ROOT))
    id = uuid4().hex
    record = {"id": id, "state": "in-progress", "files": []}
    try:
        base = control.storage(str(ROOT))
        # Verify every source/destination before the first mutation.
        for item in plan_value["files"]:
            if not valid_destination(item.get("destination")):
                raise ValueError("Excluded import destination")
            target = control.checked(base, item["destination"])
            current = digest(read(target)) if target.exists() else None
            if digest(read(Path(item["source"]))) != item["sha256"] or current != item["before"]:
                raise ValueError("Import changed after preview")
        for item in plan_value["files"]:
            entry = {k: item[k] for k in ("destination", "sha256", "before")}
            target = control.checked(base, item["destination"])
            if (digest(read(target)) if target.exists() else None) != item["before"]:
                raise ValueError("Destination changed during import")
            if item["before"] is not None:
                entry["backup"] = f"control/import-backups/{id}/{item['destination']}"
                write(entry["backup"], read(control.checked(base, item["destination"], exists=True)))
            record["files"].append(entry)
            write(journal(id), json.dumps(record, indent=2).encode())
            data = read(Path(item["source"]))
            if digest(data) != item["sha256"]:
                raise ValueError("Source changed during import")
            write(item["destination"], data)
            if digest(read(control.checked(base, item["destination"], exists=True))) != item["sha256"]:
                raise ValueError("Imported hash mismatch")
        record["state"] = "complete"
        write(journal(id), json.dumps(record, indent=2).encode())
        return {"id": id, "count": len(record["files"]), "state": "complete"}
    except BaseException:
        if record["files"]:
            rollback(id, apply=True)
        raise
    finally:
        source_jobs.release(fd)


def main():
    parser = argparse.ArgumentParser(description="Dry-run/copy authorized first-party analysis artifacts; never recursive project copying")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--slug", action="append", default=[])
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--authorized", action="store_true", help="Attest selected artifacts are first-party or authorized for this local import")
    parser.add_argument("--expected-plan")
    parser.add_argument("--rollback")
    args = parser.parse_args()
    if args.copy and not args.authorized:
        parser.error("--copy requires --authorized")
    if args.rollback:
        if args.source or args.slug or args.settings:
            parser.error("Rollback cannot select new inputs")
        fd = source_jobs.claim(str(ROOT)) if args.copy else None
        try:
            preview = rollback(args.rollback)
            if args.copy:
                if args.expected_plan != preview["fingerprint"]:
                    parser.error("Review the rollback fingerprint first")
                preview = rollback(args.rollback, apply=True)
            print(json.dumps(preview, indent=2))
        finally:
            source_jobs.release(fd)
    else:
        if args.source is None or not args.slug:
            parser.error("Select --source and at least one --slug")
        preview = plan(args.source, args.slug, args.settings)
        print(json.dumps(copy(preview, args.expected_plan) if args.copy else preview, indent=2))


if __name__ == "__main__":
    main()
