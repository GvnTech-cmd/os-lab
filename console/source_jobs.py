"""Private Source job journal and cross-console conflict lock (stdlib only)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time

import source_control as control
from source_artifacts import ArtifactError, SourceArtifacts


def claim(root, *, existing=False):
    base = control.storage(root) if existing else control.prepare(root)
    path = control.checked(base, "control/jobs.lock")
    flags = os.O_RDWR | (0 if existing else os.O_CREAT) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            if not existing and os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        raise ArtifactError(409, "Another Source Lab operation is running") from None


def release(fd):
    if fd is None:
        return
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    os.close(fd)


def atomic(root, relative, content: bytes):
    base = control.prepare(root)
    target = control.checked(base, relative)
    fd, name = tempfile.mkstemp(prefix=".source-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(service):
    import source_api
    jobs = [j.to_dict(logs=True) for j in list(service.jobs.values()) if j.lab == "source"]
    body = json.dumps(source_api.redact(service.root, jobs[-50:]), allow_nan=False).encode()
    # A pathological log stream must not produce an unbounded restart artifact.
    while len(body) > 4 * 1024 * 1024 and jobs:
        jobs.pop(0)
        body = json.dumps(source_api.redact(service.root, jobs), allow_nan=False).encode()
    atomic(service.root, "control/jobs.json", body)


def recover(service):
    """No writes on startup/status. A released lock makes old running jobs interrupted."""
    import oslab
    local = [j for j in list(service.jobs.values()) if j.lab == "source" and not getattr(j, "external", False)]
    if any(j.state == "running" or j.proc is not None for j in local):
        return
    try:
        rows = SourceArtifacts(service.root)._json(("control", "jobs.json"), optional=True)
    except ArtifactError:
        return
    if not isinstance(rows, list):
        return
    # Probe a preexisting lock only. Read-only status must never create storage.
    locked = False
    base = control.storage(service.root)
    try:
        lock = control.checked(base, "control/jobs.lock")
    except ArtifactError:
        return
    if lock.exists():
        try:
            fd = claim(service.root, existing=True)
            release(fd)
        except (ArtifactError, OSError):
            locked = True
    local_ids = {j.id for j in local}
    import source_api
    rows = source_api.redact(service.root, rows)
    for row in rows[:50]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in local_ids:
            continue
        if (not isinstance(row.get("startedAt"), (int, float)) or not isinstance(row.get("logs", []), list)
                or any(not isinstance(row.get(key, ""), str) for key in ("label", "action", "command"))):
            continue
        if row.get("lab") != "source" or row.get("state") not in {"running", "succeeded", "failed", "cancelled", "timed-out", "interrupted"}:
            continue
        job = oslab.Job(str(row.get("label", "Source Lab")), "source", str(row.get("action", "")), {"display": str(row.get("command", ""))})
        job.id, job.state = row["id"], row["state"]
        job.started_at, job.finished_at = row.get("startedAt", 0), row.get("finishedAt")
        job.exit_code, job.error = row.get("exitCode"), row.get("error")
        job.lines = [str(v)[:8192] for v in row.get("logs", [])[-4000:]]
        job.truncated = bool(row.get("truncated"))
        job.external = True
        if job.state == "running" and not locked:
            job.state, job.error, job.finished_at = "interrupted", "Console stopped before this job completed; inspect partial outputs before retrying.", time.time()
        service.jobs[job.id] = job
