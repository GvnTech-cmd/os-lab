"""Read-only, bounded Source Lab artifacts. No engine imports or subprocesses."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import stat

MAX_JSON = 5 * 1024 * 1024
MAX_REPORT = 10 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_TARGETS = 100
MAX_SESSIONS = 100
MAX_EVENTS = 500
REPORTS = {
    "analysis-v2.json": "application/json", "findings.json": "application/json",
    "coverage.json": "application/json", "summary.md": "text/markdown; charset=utf-8",
    "report.sarif": "application/sarif+json",
}
SLUG = re.compile(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+\Z", re.ASCII)
SESSION = re.compile(r"ses_[A-Za-z0-9_.-]+\Z", re.ASCII)


def redirected(path: Path, info=None) -> bool:
    """Reject POSIX links and Windows reparse points, including directory junctions."""
    try:
        info = path.lstat() if info is None else info
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _reject_constant(_value):
    raise ValueError("Non-finite number")


class ArtifactError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class SourceArtifacts:
    """Create per request: the aggregate read budget is never shared between threads."""

    def __init__(self, root: str | Path):
        self.storage = Path(os.environ.get("SOURCE_LAB_STORAGE", str(Path(root) / "source-lab/storage"))).expanduser().resolve()
        self.remaining = MAX_TOTAL

    def _path(self, parts: tuple[str, ...]) -> Path:
        path = self.storage
        for part in parts:
            if not part or part in (".", "..") or any(c in part for c in ("/", "\\", "\0")):
                raise ArtifactError(400, "Invalid artifact path")
            path /= part
            if redirected(path):
                raise ArtifactError(404, "Artifact not found")
        return path

    def _fd(self, parts: tuple[str, ...], directory: bool = False) -> int:
        """Use descriptor-relative no-follow traversal where the OS supports it."""
        self._path(parts)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            fd = os.open(self.storage, flags | os.O_DIRECTORY)
            try:
                for index, part in enumerate(parts):
                    is_dir = directory or index < len(parts) - 1
                    child = os.open(part, flags | (os.O_DIRECTORY if is_dir else 0), dir_fd=fd)
                    os.close(fd)
                    fd = child
                return fd
            except BaseException:
                os.close(fd)
                raise
        return os.open(self._path(parts), flags)

    def _read(self, parts: tuple[str, ...], limit: int, optional: bool = False) -> bytes | None:
        try:
            fd = self._fd(parts)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ArtifactError(404, "Artifact not found")
                bound = min(limit, self.remaining)
                if info.st_size > bound:
                    raise ArtifactError(413, "Artifact or aggregate response exceeds the read limit")
                content = stream.read(bound + 1)
                if len(content) > bound:
                    raise ArtifactError(413, "Artifact or aggregate response exceeds the read limit")
                self.remaining -= len(content)
                return content
        except FileNotFoundError:
            if optional:
                return None
            raise ArtifactError(404, "Artifact not found") from None
        except OSError:
            raise ArtifactError(404, "Artifact not found") from None

    def _json(self, parts: tuple[str, ...], optional: bool = False):
        content = self._read(parts, MAX_JSON, optional)
        if content is None:
            return None
        try:
            return json.loads(content, parse_constant=_reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise ArtifactError(400, "Artifact contains invalid JSON") from None

    def _directories(self, parts: tuple[str, ...], limit: int, pattern) -> tuple[list[str], bool]:
        fd = None
        try:
            if os.scandir in os.supports_fd and os.open in os.supports_dir_fd:
                fd = self._fd(parts, directory=True)
                target = fd
            else:
                target = self._path(parts)
            names, truncated = [], False
            with os.scandir(target) as entries:
                for index, entry in enumerate(entries):
                    if index >= 1000:
                        truncated = True
                        break
                    if entry.is_dir(follow_symlinks=False) and pattern.fullmatch(entry.name):
                        if len(names) >= limit:
                            truncated = True
                            break
                        names.append(entry.name)
            return sorted(names), truncated
        except FileNotFoundError:
            return [], False
        except OSError:
            raise ArtifactError(404, "Artifact directory not found") from None
        finally:
            if fd is not None:
                os.close(fd)

    @staticmethod
    def _slug(slug: str) -> None:
        if len(slug) > 200 or not SLUG.fullmatch(slug):
            raise ArtifactError(400, "Invalid target slug")

    def _detail(self, slug: str) -> dict:
        self._slug(slug)
        parts = ("analysis", slug)
        # Directory existence is mandatory; missing individual formats are normal.
        try:
            if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
                os.close(self._fd(parts, directory=True))
            elif not self._path(parts).is_dir():
                raise ArtifactError(404, "Target not found")
        except OSError:
            raise ArtifactError(404, "Target not found") from None
        analysis = self._json((*parts, "analysis-v2.json"), optional=True)
        findings = self._json((*parts, "findings.json"), optional=True)
        findings_present = findings is not None
        coverage = self._json((*parts, "coverage.json"), optional=True)
        legacy = self._json((*parts, "manifest-analysis.json"), optional=True)
        for value in (analysis, coverage, legacy):
            if value is not None and not isinstance(value, dict):
                raise ArtifactError(400, "Artifact has an invalid object shape")
        analysis = analysis or {}
        coverage = coverage if coverage is not None else analysis.get("coverage")
        findings = findings if findings is not None else analysis.get("findings", [])
        if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
            raise ArtifactError(400, "Findings must be an array of objects")
        if coverage is not None and not isinstance(coverage, dict):
            raise ArtifactError(400, "Coverage must be an object")
        for artifact in (analysis, coverage or {}, *findings):
            if artifact and artifact.get("schema_version") != 2:
                raise ArtifactError(400, "Unsupported evidence schema version")
        identity = analysis.get("target") or (coverage or {}).get("target") or {}
        if not isinstance(identity, dict):
            raise ArtifactError(400, "Target identity must be an object")
        session_names, sessions_truncated = self._directories((*parts, "runtime-sessions"), MAX_SESSIONS, SESSION)
        sessions = []
        for name in session_names:
            metadata = self._json((*parts, "runtime-sessions", name, "session.json"))
            if not isinstance(metadata, dict):
                raise ArtifactError(400, "Session metadata must be an object")
            sessions.append({**metadata, "integrity": "not-verified"})
        # List report names without loading their contents or trusting symlinks.
        reports = []
        for filename in REPORTS:
            path = self._path((*parts, filename))
            if path.is_file():
                reports.append(filename)
        return {
            "slug": slug, "repo": identity.get("repo") or (legacy or {}).get("repo") or slug.replace("__", "/"),
            "platform": (coverage or {}).get("platform") or (findings[0].get("platform") if findings else None),
            "hasLegacyAnalysis": legacy is not None, "hasV2Analysis": bool(analysis) or coverage is not None or findings_present,
            "target": identity or None, "coverage": coverage, "scorecard": analysis.get("scorecard"),
            "findings": findings, "sessions": sessions, "sessionsTruncated": sessions_truncated,
            "reports": reports, "generatedAt": analysis.get("generated_at"),
        }

    def evidence(self, slug: str | None = None, session: str | None = None) -> dict:
        self.remaining = MAX_TOTAL
        if session is not None and slug is None:
            raise ArtifactError(400, "A session requires a target slug")
        if slug is None:
            names, truncated = self._directories(("analysis",), MAX_TARGETS, SLUG)
            targets = []
            for name in names:
                try:
                    detail = self._detail(name)
                    targets.append({key: detail[key] for key in ("slug", "repo", "platform", "hasLegacyAnalysis", "hasV2Analysis", "coverage")} |
                                   {"findingCount": len(detail["findings"]), "sessionCount": len(detail["sessions"])})
                except ArtifactError as exc:
                    if exc.status == 413:
                        raise
                    targets.append({"slug": name, "error": str(exc)})
            return {"targets": targets, "truncated": truncated}
        self._slug(slug)
        if session is None:
            return self._detail(slug)
        if len(session) > 200 or not SESSION.fullmatch(session):
            raise ArtifactError(400, "Invalid session ID")
        content = self._read(("analysis", slug, "runtime-sessions", session, "events.jsonl"), MAX_JSON)
        events, truncated = [], False
        try:
            for line in (line for line in io.BytesIO(content) if line.strip()):
                if len(events) >= MAX_EVENTS:
                    truncated = True
                    break
                item = json.loads(line, parse_constant=_reject_constant)
                if not isinstance(item, dict):
                    raise ValueError()
                events.append(item)
        except (ValueError, UnicodeError, RecursionError):
            raise ArtifactError(400, "Session contains invalid events") from None
        return {"session": session, "events": events, "truncated": truncated,
                "integrity": "not-verified"}

    def report(self, slug: str, filename: str) -> tuple[bytes, str, str]:
        self.remaining = MAX_REPORT
        self._slug(slug)
        if filename not in REPORTS:
            raise ArtifactError(400, "Invalid report name")
        return self._read(("analysis", slug, filename), MAX_REPORT), REPORTS[filename], f"{slug}-{filename}"
