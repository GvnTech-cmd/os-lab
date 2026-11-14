#!/usr/bin/env python3
"""
ext-repo-analyzer.py — clone, analyze, and store browser-extension repositories.

Production pipeline (per repository), per the refined flow diagram:

  1. Acquire source        git clone --depth 1 (GitHub) OR local directory
  2. Locate manifest.json  root + known sub-paths, then pruned recursive search
  3. Parse manifest        MV2 / MV3, permissions, host_permissions, background,
                           content_scripts, action, architecture dirs
  4. Signature matching    append signature/rule checklist (H1-H5 heuristics,
                           HIGH/MEDIUM/LOW permission buckets, wildcards,
                           LLM-targeting, module architecture) -> risk level
                           + target priority
  5. Threat scan           regex indicators (WebSocket, Telegram API, native
                           messaging, cookies, beacons, crypto, clipboard...)
  6. Dependencies          package.json, requirements.txt, go.mod, Cargo.toml, ...
  7. File tree             pruned recursive listing (.git, node_modules skipped)
  8. Metadata              GitHub API: stars, forks, watchers, language, license
  9. AST per source file   tree-sitter if available, regex fallback
 10. Persist bundle        manifest-analysis.json, dependencies.json,
                           file-tree.json, metadata.json, ast/, ast-index.json
 11. Cleanup               delete clone unless --keep-workspace

Reliability / UX features:
  * live progress bar (repos/sec, ETA, current repo + stage) — TTY aware
  * per-stage timing and error capture (one failing stage never kills the repo)
  * retries with exponential backoff + jitter (clone, GitHub API)
  * GitHub rate-limit aware (waits for reset within --api-max-wait, else skips)
  * atomic JSON/CSV writes (never leaves half-written files)
  * checkpoint/resume (--resume skips repos already OK in a previous run)
  * concurrent workers (--workers N) with thread-safe progress reporting
  * graceful SIGINT/SIGTERM: finishes current work, still writes summary.csv
                          + report.json, exits 130
  * rotating log file (out_dir/analyzer.log) + colored console

Exit codes: 0 = all processed, 1 = one or more repo failures, 2 = fatal input
error, 130 = interrupted.

Usage:
  python3 ext-repo-analyzer.py owner/repo1 owner/repo2 -o ./ext-analysis
  python3 ext-repo-analyzer.py -i repos.csv -o ./ext-analysis --workers 4
  python3 ext-repo-analyzer.py --scan-dir /path/to/cloned/extensions -o ./out
  python3 ext-repo-analyzer.py -i repos.csv -o out --resume --keep-workspace
  python3 ext-repo-analyzer.py -i repos.csv -o out --no-ast --no-metadata
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import platform
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type

APP = "ext-repo-analyzer"
VERSION = "1.0.0"
UTC = timezone.utc

# ============================================================================
# SIGNATURES & RULES — from the COMPREHENSIVE SIGNATURES document
# ============================================================================

HIGH_RISK_PERMISSIONS = {
    "<all_urls>", "webNavigation", "nativeMessaging",
    "webRequest", "webRequestBlocking",
}
MEDIUM_RISK_PERMISSIONS = {
    "tabs", "storage", "downloads", "activeTab", "scripting", "sidePanel",
    "alarms", "cookies", "history", "clipboardWrite", "clipboardRead",
    "pageCapture", "desktopCapture", "tabCapture", "proxy",
    "declarativeNetRequest", "declarativeNetRequestWithHostAccess",
}
LOW_RISK_PERMISSIONS = {
    "notifications", "identity", "contextMenus", "idle",
}
# Any permission that looks like a host match pattern (contains "://" and/or
# trailing wildcard) is treated as HIGH risk — covers "https://*/", "*://*/*",
# "http://*/*", "<all_urls>" style entries (e.g. binance_profit "https/*").
_HOST_PATTERN_RE = re.compile(r"^(\*|https?|wss?|ftp)://|^<all_urls>$|^https?\*?$")

WILDCARD_MATCHES = {"<all_urls>", "http://*/*", "https://*/*", "*://*/*", "file://*/*"}

# Known LLM/AI platform domains — "LLM-targeted content injection" indicator.
LLM_DOMAINS = (
    "chatgpt.com", "openai.com", "claude.ai", "gemini.google.com",
    "bard.google.com", "perplexity.ai", "copilot.microsoft.com",
    "poe.com", "character.ai", "you.com", "chat.deepseek.com",
)

# Browser-extension manifest lookup paths (tried in order).
MANIFEST_CANDIDATES: Tuple[str, ...] = (
    "manifest.json",
    "src/manifest.json",
    "extension/manifest.json",
    "extensions/manifest.json",
    "webextension/manifest.json",
    "src/drivers/webextension/manifest.json",
    "packages/extension/manifest.json",
    "browser-extension/manifest.json",
    "app/manifest.json",
    "q_extension/manifest.json",
)

DEPENDENCY_MANIFESTS: Tuple[str, ...] = (
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "composer.json", "Gemfile", "pubspec.yaml",
)

SOURCE_EXTENSIONS: Dict[str, str] = {
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".py": "python",
}

SCAN_TEXT_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".html", ".htm"}
SCAN_SKIP_DIRS = {".git", "node_modules", "dist", "build", "vendor", ".venv", "__pycache__"}

# Manifest keys that mark a real browser extension (MV2/MV3 parity).
EXTENSION_KEYS = {
    "browser_action", "action", "content_scripts", "background",
    "permissions", "optional_permissions", "host_permissions",
    "optional_host_permissions", "web_accessible_resources",
    "options_ui", "options_page", "side_panel", "devtools_page", "commands",
}

# Threat-model indicators (regex over source text) — heuristics for review,
# mapped to the signature doc's APT / FINANCIAL / PRIVACY threat models.
THREAT_SIGNATURES: Tuple[Tuple[str, str, "re.Pattern[str]"], ...] = (
    ("websocket",        "APT: agent/connectivity",
     re.compile(r"\bnew\s+WebSocket\s*\(")),
    ("native_messaging", "APT: native app messaging",
     re.compile(r"chrome\.runtime\.connectNative|chrome\.runtime\.sendNativeMessage")),
    ("remote_code_exec", "APT: dynamic code eval",
     re.compile(r"\beval\s*\(\s*['\"]|new\s+Function\s*\(")),
    ("telegram_api",     "FINANCIAL: Telegram API access",
     re.compile(r"api\.telegram\.org")),
    ("crypto_refs",      "FINANCIAL: crypto wallet/exchange refs",
     re.compile(r"\b(?:metamask|phantom[_ ]?wallet|trustwallet|ledgerlive|coinbase|binance\.com/api|ethereum[_ ]?provider)\b", re.I)),
    ("cookie_access",    "PRIVACY: cookie/session manipulation",
     re.compile(r"document\.cookie\s*=|chrome\.cookies\.")),
    ("beacon_exfil",     "PRIVACY: sendBeacon exfiltration",
     re.compile(r"navigator\.sendBeacon\s*\(")),
    ("clipboard_read",   "PRIVACY: clipboard reading",
     re.compile(r"navigator\.clipboard\.read(?:Text|)\s*\(")),
    ("credential_sniff", "PRIVACY: credential/keystroke capture",
     re.compile(r"addEventListener\(\s*['\"](?:keydown|keypress|keyup)['\"].{0,120}(?:password|passwd|credential)", re.I | re.S)),
)

GITHUB_URL_RE = re.compile(r"github\.com[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}/[A-Za-z0-9_.-]{1,80}$")

# ============================================================================
# DATA MODEL
# ============================================================================


@dataclass
class StageInfo:
    ok: bool
    ms: int = 0
    detail: str = ""


@dataclass
class RepoResult:
    repo: str
    index: int
    source: str  # "github" | "local"
    status: str = "PENDING"
    risk_level: Optional[str] = None
    target_priority: Optional[str] = None
    heuristic_score: int = 0
    manifest_found: bool = False
    manifest_path: Optional[str] = None
    files: int = 0
    dirs: int = 0
    ast_files: int = 0
    threats: int = 0
    stars: Optional[int] = None
    duration_ms: int = 0
    out_dir: Optional[str] = None
    error: Optional[str] = None
    resumed: bool = False
    stages: Dict[str, StageInfo] = field(default_factory=dict)

    def csv_row(self) -> Dict[str, Any]:
        return {
            "repo": self.repo, "source": self.source, "status": self.status,
            "risk_level": self.risk_level or "",
            "target_priority": self.target_priority or "",
            "heuristic_score": self.heuristic_score,
            "manifest_found": self.manifest_found,
            "manifest_path": self.manifest_path or "",
            "files": self.files, "dirs": self.dirs, "ast_files": self.ast_files,
            "threats": self.threats,
            "stars": "" if self.stars is None else self.stars,
            "duration_ms": self.duration_ms,
            "out_dir": self.out_dir or "",
            "error": self.error or "",
        }


@dataclass
class Target:
    index: int
    spec: str
    source: str  # "github" | "local"


# ============================================================================
# EXCEPTIONS
# ============================================================================


class AnalyzerError(Exception):
    """Base class for expected, well-reported failures."""


class InvalidSlugError(AnalyzerError):
    pass


class CloneError(AnalyzerError):
    pass


class ManifestNotExtensionError(AnalyzerError):
    pass


class MetadataError(AnalyzerError):
    pass


class StopRequested(AnalyzerError):
    pass


# ============================================================================
# SMALL UTILITIES
# ============================================================================


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def atomic_write_text(path: Path, text: str) -> None:
    """Write text atomically: temp file in same dir, fsync, rename."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def iter_repo_files(root: Path,
                    skip_dirs: Iterable[str] = SCAN_SKIP_DIRS,
                    max_files: int = 200_000) -> Iterable[Path]:
    """Yield file paths under root, pruning VCS/build/dependency dirs.

    Unlike Path.rglob, this never descends into pruned directories and is
    safe against symlink cycles (dir symlinks are not followed).
    """
    skip = set(skip_dirs)
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.endswith(".git"))
        for name in sorted(filenames):
            yield Path(dirpath) / name
            count += 1
            if count >= max_files:
                return


# ============================================================================
# PROGRESS REPORTING (thread-safe, TTY-aware)
# ============================================================================


class ProgressReporter:
    """Renders a single live status line on a TTY; degrades to log-only mode."""

    def __init__(self, total: int, stream: Any, use_ansi: bool) -> None:
        self.total = max(1, total)
        self.stream = stream
        self.use_ansi = use_ansi
        self.lock = threading.Lock()
        self.done = 0
        self.ok_count = 0
        self.fail_count = 0
        self.skipped = 0
        self._start = time.monotonic()
        self._current = ""
        self._last_len = 0
        self._live = bool(use_ansi and stream is not None
                          and getattr(stream, "isatty", lambda: False)())

    # -- line control -----------------------------------------------------
    def clear(self) -> None:
        if self._live and self._last_len:
            self.stream.write("\r" + " " * self._last_len + "\r")
            self._last_len = 0

    def redraw(self) -> None:
        if not self._live:
            return
        line = self._render()
        self.stream.write(line)
        self.stream.flush()
        self._last_len = len(line)

    def _render(self) -> str:
        elapsed = time.monotonic() - self._start
        pct = self.done / self.total * 100.0
        eta = (elapsed / self.done * (self.total - self.done)) if self.done else 0.0
        rate = self.done / elapsed if elapsed > 1 else 0.0
        bar_w = 22
        filled = int(round(bar_w * self.done / self.total))
        bar = "#" * filled + "-" * (bar_w - filled)
        return (f"\r[{bar}] {self.done}/{self.total} ({pct:3.0f}%) "
                f"eta {fmt_duration(eta)} ({rate:.1f} repo/s) | {self._current}")

    # -- public API --------------------------------------------------------
    def start_repo(self, slug: str, stage: str = "starting") -> None:
        with self.lock:
            self._current = f"{slug} · {stage}"
            self.clear()
            self.redraw()

    def update_stage(self, slug: str, stage: str) -> None:
        with self.lock:
            self._current = f"{slug} · {stage}"
            self.clear()
            self.redraw()

    def finish_repo(self, slug: str, status: str) -> None:
        with self.lock:
            self.done += 1
            if status in ("OK", "NOT_EXTENSION", "SKIPPED_RESUMED"):
                self.ok_count += 1
            elif status == "STOPPED":
                self.skipped += 1
            else:
                self.fail_count += 1
            self._current = ""
            self.clear()
            self.redraw()

    def close(self) -> None:
        with self.lock:
            self.clear()

    def summary_line(self) -> str:
        elapsed = time.monotonic() - self._start
        return (f"done={self.done} ok={self.ok_count} "
                f"failed={self.fail_count} stopped={self.skipped} "
                f"in {fmt_duration(elapsed)}")


class ProgressAwareLogHandler(logging.Handler):
    """Console log handler that coexists with the live progress line."""

    def __init__(self, reporter: Optional[ProgressReporter], stream: Any) -> None:
        super().__init__()
        self.reporter = reporter
        self.stream = stream
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            lock = self.reporter.lock if self.reporter else threading.Lock()
            with lock:
                if self.reporter:
                    self.reporter.clear()
                self.stream.write(msg + "\n")
                self.stream.flush()
                if self.reporter:
                    self.reporter.redraw()
        except Exception:  # pragma: no cover — never let logging crash the run
            pass


class _Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"

    @classmethod
    def wrap(cls, text: str, *codes: str, enabled: bool = True) -> str:
        if not enabled or not codes:
            return text
        return "".join(codes) + text + cls.RESET


STATUS_COLOR = {
    "OK": _Ansi.GREEN,
    "NOT_EXTENSION": _Ansi.CYAN,
    "SKIPPED_RESUMED": _Ansi.CYAN,
    "PARTIAL": _Ansi.YELLOW,
    "STOPPED": _Ansi.YELLOW,
    "CLONE_FAILED": _Ansi.RED,
    "INVALID_SLUG": _Ansi.RED,
    "EXCEPTION": _Ansi.RED,
}


def color_status(status: str, enabled: bool) -> str:
    return _Ansi.wrap(status, STATUS_COLOR.get(status, ""), enabled=enabled)


# ============================================================================
# RETRY ENGINE
# ============================================================================


def retry_call(
    fn: Callable[[], Any],
    *,
    what: str,
    attempts: int,
    base_delay: float,
    max_delay: float,
    logger: logging.Logger,
    stop_event: threading.Event,
    retry_on: Tuple[Type[BaseException], ...],
) -> Any:
    """Run fn() with exponential backoff + jitter; re-raise after last attempt."""
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        if stop_event.is_set():
            raise StopRequested(what)
        try:
            return fn()
        except StopRequested:
            raise
        except retry_on as exc:
            last_exc = exc
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay *= 0.5 + random.random()  # jitter
            logger.warning("  [retry] %s failed (attempt %d/%d): %s — retrying in %.1fs",
                           what, attempt, attempts, exc, delay)
            if stop_event.wait(delay):
                raise StopRequested(what)
    assert last_exc is not None
    raise last_exc


# ============================================================================
# GITHUB API CLIENT (urllib only, rate-limit aware)
# ============================================================================


class GitHubClient:
    """GitHub REST client with explicit, bounded retry/rate-limit handling.

    Retry policy (all bounded, no recursion):
      * hard quota errors (403/429 with X-RateLimit-Remaining: 0) are
        deterministic — wait for reset ONLY if the reset is within
        `max_wait` seconds, otherwise fail fast with an actionable message;
        at most one such wait per repo.
      * other 403/429 (secondary limits) and 5xx/network errors retry with
        exponential backoff + jitter, up to `retries` attempts.
      * 4xx others (404 etc.) are permanent — no retry.
    """

    RETRYABLE_NET = (urllib.error.URLError, TimeoutError, OSError)

    def __init__(self, token: Optional[str], logger: logging.Logger,
                 stop_event: threading.Event, retries: int = 3,
                 max_wait: float = 90.0) -> None:
        self.token = token
        self.logger = logger
        self.stop_event = stop_event
        self.retries = max(1, retries)
        self.max_wait = max(0.0, max_wait)

    def _backoff(self, attempt: int, what: str) -> bool:
        """Sleep with exponential backoff + jitter. Returns False if stopped."""
        delay = min(15.0, 1.0 * (2 ** max(0, attempt - 1))) * (0.5 + random.random())
        self.logger.warning("  [retry] %s failed — retrying in %.1fs", what, delay)
        return not self.stop_event.wait(delay)

    def repo_metadata(self, slug: str) -> Dict[str, Any]:
        url = f"https://api.github.com/repos/{slug}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP}/{VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        what = f"metadata:{slug}"
        attempts_left = self.retries
        quota_wait_used = False
        while True:
            if self.stop_event.is_set():
                raise StopRequested(what)
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8", "ignore"))
                return {
                    "full_name": data.get("full_name"),
                    "html_url": data.get("html_url"),
                    "description": data.get("description"),
                    "stars": data.get("stargazers_count"),
                    "forks": data.get("forks_count"),
                    "watchers": data.get("subscribers_count"),  # true watchers
                    "language": data.get("language"),
                    "license": (data.get("license") or {}).get("spdx_id"),
                    "default_branch": data.get("default_branch"),
                    "topics": data.get("topics", []),
                    "created_at": data.get("created_at"),
                    "pushed_at": data.get("pushed_at"),
                    "fetched_at": utcnow_iso(),
                }
            except urllib.error.HTTPError as exc:
                code = exc.code
                hdrs = exc.headers or {}
                if code == 404:
                    raise MetadataError("HTTP 404 (repository not found)")
                if code in (403, 429):
                    remaining = hdrs.get("X-RateLimit-Remaining")
                    reset = hdrs.get("X-RateLimit-Reset")
                    if remaining == "0":
                        # Hard quota — deterministic until reset. Wait once,
                        # and only if the reset is inside our wait horizon.
                        if not quota_wait_used and reset and self.max_wait > 0:
                            secs = float(reset) - time.time() + 1.0
                            if 0 < secs <= self.max_wait:
                                quota_wait_used = True
                                self.logger.warning(
                                    "  [rate-limit] quota exhausted for %s — "
                                    "waiting %.0fs for reset", slug, secs)
                                if self.stop_event.wait(secs):
                                    raise StopRequested(what)
                                continue
                        raise MetadataError(
                            f"HTTP {code} (rate limit exhausted; resets in "
                            f"{fmt_duration(float(reset) - time.time() if reset else 0)}"
                            " — set GITHUB_TOKEN for 5000 req/h)")
                    # Non-quota 403/429 (secondary/abuse limits) — retryable.
                    if attempts_left > 1:
                        attempts_left -= 1
                        if self._backoff(attempts_left, what):
                            continue
                    raise MetadataError(f"HTTP {code} (forbidden)")
                if 500 <= code < 600 and attempts_left > 1:
                    attempts_left -= 1
                    if self._backoff(attempts_left, what):
                        continue
                raise MetadataError(f"HTTP {code}")
            except self.RETRYABLE_NET as exc:
                if attempts_left > 1:
                    attempts_left -= 1
                    if self._backoff(attempts_left, f"{what}: {exc}"):
                        continue
                raise MetadataError(f"network error: {exc}")
            except json.JSONDecodeError as exc:
                raise MetadataError(f"invalid API response: {exc}")


# ============================================================================
# CLONE
# ============================================================================


def normalize_slug(text: str) -> str:
    """GitHub URL or 'owner/name' -> 'owner/name'."""
    text = text.strip()
    m = GITHUB_URL_RE.search(text)
    if m:
        return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"
    return text.removesuffix(".git").strip("/")


def validate_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise InvalidSlugError(
            f"invalid repo identifier: {slug!r} (expected 'owner/name' or GitHub URL)")


def clone_repo(url: str, dest: Path, depth: int, timeout: float,
               logger: logging.Logger, stop_event: threading.Event,
               retries: int) -> int:
    """Shallow-clone url into dest. Returns elapsed ms. Raises CloneError.

    The git subprocess is watched while it runs; a stop request terminates it
    promptly instead of waiting out the full clone timeout.
    """
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--quiet", "--depth", str(depth),
           "--single-branch", url, str(dest)]

    start = time.monotonic()

    def _once() -> None:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
        except OSError as exc:
            raise CloneError(f"git not runnable: {exc}") from exc
        try:
            # Poll in short intervals so stop requests and the timeout both
            # interrupt the clone even while git is still running.
            stderr = ""
            while True:
                try:
                    _, stderr = proc.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if stop_event.is_set():
                    proc.terminate()
                    try:
                        proc.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise StopRequested(f"clone:{url}")
                if time.monotonic() - start > timeout:
                    proc.kill()
                    raise CloneError(f"clone timed out after {timeout:.0f}s")
            if stop_event.is_set():
                raise StopRequested(f"clone:{url}")
            if proc.returncode != 0:
                err = (stderr or "").strip().splitlines()
                raise CloneError(err[-1] if err else f"git exit {proc.returncode}")
        finally:
            if proc.poll() is None:
                proc.kill()

    retry_call(_once, what=f"clone:{url}", attempts=retries,
               base_delay=1.0, max_delay=20.0, logger=logger,
               stop_event=stop_event,
               retry_on=(CloneError,))
    return int((time.monotonic() - start) * 1000)


# ============================================================================
# MANIFEST ANALYSIS — signature + rule matching (HEURISTIC 1-5)
# ============================================================================


def is_browser_extension(manifest: Any) -> bool:
    if not isinstance(manifest, dict):
        return False
    if manifest.get("manifest_version") not in (2, 3, "2", "3"):
        return False
    return bool(EXTENSION_KEYS & set(manifest.keys()))


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, dict):
        value = list(value.keys())
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int, float))]


def _perm_bucket(perms: List[str]) -> Dict[str, List[str]]:
    high, med, low, other = [], [], [], []
    for p in perms:
        if p in HIGH_RISK_PERMISSIONS or _HOST_PATTERN_RE.match(p):
            high.append(p)
        elif p in MEDIUM_RISK_PERMISSIONS:
            med.append(p)
        elif p in LOW_RISK_PERMISSIONS:
            low.append(p)
        else:
            other.append(p)
    return {"high": high, "medium": med, "low": low, "other": other}


def _llm_targets(matches: List[str]) -> List[str]:
    hits = []
    for m in matches:
        for domain in LLM_DOMAINS:
            if domain in m and domain not in hits:
                hits.append(domain)
    return hits


def _background_desc(bg: Any) -> str:
    if isinstance(bg, dict):
        if "service_worker" in bg:
            return f"service_worker: {bg['service_worker']}"
        if "scripts" in bg:
            scripts = bg.get("scripts")
            if isinstance(scripts, list):
                return "scripts: " + ",".join(str(s) for s in scripts)
            return f"scripts: {scripts}"
        if "page" in bg:
            return f"page: {bg['page']}"
        return ""
    if isinstance(bg, str):
        return bg
    return ""


def analyze_manifest(manifest: dict, manifest_dir: Path) -> Dict[str, Any]:
    """Full signature/rule analysis -> manifest-analysis.json payload."""
    perms = _as_str_list(manifest.get("permissions"))
    opt = _as_str_list(manifest.get("optional_permissions"))
    host_perms = (_as_str_list(manifest.get("host_permissions"))
                  + _as_str_list(manifest.get("optional_host_permissions")))
    all_perms = perms + opt
    risk = _perm_bucket(all_perms + host_perms)

    bg_desc = _background_desc(manifest.get("background"))

    cs_list = manifest.get("content_scripts") or []
    if not isinstance(cs_list, list):
        cs_list = []
    cs_matches: List[str] = []
    cs_files: List[str] = []
    all_frames: List[bool] = []
    run_ats: List[str] = []
    for cs in cs_list:
        if not isinstance(cs, dict):
            continue
        cs_matches.extend(_as_str_list(cs.get("matches")))
        cs_files.extend(_as_str_list(cs.get("js")))
        if "all_frames" in cs:
            all_frames.append(bool(cs["all_frames"]))
        if "run_at" in cs:
            run_ats.append(str(cs["run_at"]))

    if "action" in manifest:
        action_type = "MV3 action"
    elif "browser_action" in manifest:
        action_type = "MV2 browser_action"
    elif "side_panel" in manifest:
        action_type = "side_panel"
    else:
        action_type = ""

    # Architecture dirs — relative to the manifest's directory (correct logic:
    # extensions commonly live in src/, extension/, ... so background.js,
    # popup/, modules/ sit next to manifest.json, not at the repo root).
    arch_names = ("background.js", "content.js", "popup", "assets", "modules", "_locales")
    arch_hits = [d for d in arch_names if (manifest_dir / d).exists()]
    modules_js = 0
    if "modules" in arch_hits:
        modules_dir = manifest_dir / "modules"
        modules_js = sum(
            1 for p in iter_repo_files(modules_dir, max_files=2000)
            if p.suffix.lower() in (".js", ".mjs", ".cjs")
        )

    # @lat: [[source-lab#Pipeline]]
    # ---- Heuristic scoring (signature doc, Detection Algorithms H1-H5) ----
    score = 0
    reasons: List[str] = []
    checklist: List[Dict[str, Any]] = []

    def add_rule(rule: str, matched: bool, weight: int, evidence: str = "") -> None:
        nonlocal score
        entry: Dict[str, Any] = {"rule": rule, "matched": matched, "weight": weight}
        if evidence:
            entry["evidence"] = evidence
        checklist.append(entry)
        if matched:
            score += weight
            reasons.append(f"{rule} (+{weight})")

    add_rule("H1 manifest_version present (MV2/MV3)", True, 2,
             f"manifest_version={manifest.get('manifest_version')}")
    add_rule("H2a HIGH-risk permission (<all_urls>/webNavigation/host-pattern)",
             bool(risk["high"]), 3, ",".join(risk["high"]))
    add_rule("H2b nativeMessaging/webRequest",
             any(p in {"nativeMessaging", "webRequest", "webRequestBlocking"}
                 for p in all_perms + host_perms), 2)
    add_rule("H3 content_scripts.matches present", bool(cs_matches), 1,
             f"{len(cs_matches)} match pattern(s)")
    add_rule("H4 background section or assets//popup/ dirs",
             bool(bg_desc) or bool({"assets", "popup"} & set(arch_hits)), 2,
             f"bg={bool(bg_desc)} dirs={[d for d in ('assets', 'popup') if d in arch_hits]}")
    add_rule("H5 modules/ architecture (>=2 js files)",
             modules_js >= 2, 3, f"{modules_js} js files in modules/")

    universal = bool(risk["high"])
    has_native_or_webrequest = any(
        p in {"nativeMessaging", "webRequest", "webRequestBlocking"}
        for p in all_perms + host_perms)
    if universal and has_native_or_webrequest:
        risk_level = "VERY_HIGH"
    elif score >= 5 or len(risk["high"]) >= 2:
        risk_level = "HIGH"
    elif score >= 3:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "name": manifest.get("name", ""),
        "version": str(manifest.get("version", "")),
        "manifest_version": manifest.get("manifest_version"),
        "description": " ".join(str(manifest.get("description") or "").split()),
        "author": manifest.get("author", "") if not isinstance(manifest.get("author"), dict) else "",
        "action_type": action_type,
        "background": bg_desc,
        "permissions": all_perms,
        "host_permissions": host_perms,
        "permission_risk": risk,
        "content_scripts": {
            "count": len(cs_list),
            "matches": sorted(set(cs_matches)),
            "files": sorted(set(cs_files)),
            "wildcard_matches": sorted(set(cs_matches) & WILDCARD_MATCHES),
            "llm_targets": _llm_targets(cs_matches),
            "all_frames": all_frames,
            "run_at": run_ats,
        },
        "architecture": {"dirs": arch_hits, "modules_js_count": modules_js},
        "signature_checklist": checklist,
        "heuristic_score": score,
        "heuristic_reasons": reasons,
        "risk_level": risk_level,
        "raw_manifest": manifest,
        "manifest_keys": sorted(list(manifest.keys())),
        "generated_at": utcnow_iso(),
    }


def find_manifest(root: Path) -> Optional[Path]:
    """Known sub-paths first, then a pruned recursive search."""
    for cand in MANIFEST_CANDIDATES:
        p = root / cand
        if p.is_file():
            return p
    for p in iter_repo_files(root, max_files=20_000):
        if p.name == "manifest.json":
            return p
    return None


# ============================================================================
# THREAT SCAN (signature doc: APT / FINANCIAL / PRIVACY indicators)
# ============================================================================


def scan_threats(root: Path, max_files: int = 400, max_kb: int = 512) -> Dict[str, Any]:
    hits: Dict[str, Dict[str, Any]] = {}
    scanned = 0
    skipped_minified = 0
    for path in iter_repo_files(root, max_files=max_files * 4):
        if scanned >= max_files:
            break
        if path.suffix.lower() not in SCAN_TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > max_kb * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        if ".min." in path.name or (text.count("\n") < 5 and len(text) > 20_000):
            skipped_minified += 1
            continue
        scanned += 1
        for name, model, pattern in THREAT_SIGNATURES:
            n = len(pattern.findall(text))
            if not n:
                continue
            entry = hits.setdefault(name, {"model": model, "match_count": 0, "files": []})
            entry["match_count"] += n
            if len(entry["files"]) < 5:
                entry["files"].append(rel)
    return {"indicators": hits, "files_scanned": scanned,
            "minified_skipped": skipped_minified}


# @lat: [[source-lab#Pipeline]]
def derive_target_priority(analysis: Dict[str, Any], threats: Dict[str, Any]) -> str:
    """Signature doc: Primary / Secondary / Tertiary target selection."""
    cs = analysis.get("content_scripts", {})
    perms = analysis.get("permissions", [])
    indicators = set((threats.get("indicators") or {}).keys())
    if (cs.get("wildcard_matches")
            or "webNavigation" in perms
            or "nativeMessaging" in perms
            or int(cs.get("count") or 0) >= 2
            or bool(cs.get("llm_targets"))):
        return "PRIMARY"
    financial = {"telegram_api", "crypto_refs"}
    apt = {"websocket", "native_messaging"}
    if (indicators & financial or indicators & apt
            or analysis.get("architecture", {}).get("modules_js_count", 0) >= 2
            or analysis.get("risk_level") in ("MEDIUM", "HIGH", "VERY_HIGH")):
        return "SECONDARY"
    return "TERTIARY"


# ============================================================================
# DEPENDENCIES
# ============================================================================


def parse_dependencies(root: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    search_roots = [root] + [root / s for s in ("src", "extension", "webextension")
                             if (root / s).is_dir()]
    seen: set = set()
    for sr in search_roots:
        for name in DEPENDENCY_MANIFESTS:
            p = sr / name
            if not p.is_file():
                continue
            key = str(p.relative_to(root))
            if key in seen:
                continue
            seen.add(key)
            entry: Dict[str, Any] = {"type": name}
            try:
                if name == "package.json":
                    data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
                    if isinstance(data, dict):
                        entry["name"] = data.get("name", "")
                        entry["version"] = str(data.get("version", ""))
                        entry["deps"] = {
                            k: data[k] for k in
                            ("dependencies", "devDependencies",
                             "peerDependencies", "optionalDependencies")
                            if isinstance(data.get(k), dict)
                        }
                elif name in ("requirements.txt", "Pipfile"):
                    entry["deps"] = [
                        line.strip() for line in
                        p.read_text(encoding="utf-8", errors="ignore").splitlines()
                        if line.strip() and not line.lstrip().startswith("#")
                    ][:500]
                elif name == "go.mod":
                    m = re.search(r"^module\s+(\S+)",
                                  p.read_text(encoding="utf-8", errors="ignore"), re.M)
                    entry["module"] = m.group(1) if m else ""
                else:
                    entry["size_kb"] = round(p.stat().st_size / 1024, 1)
            except Exception as exc:  # a bad manifest must not break the scan
                entry["error"] = str(exc)
            out[key] = entry
    return out


# ============================================================================
# FILE TREE
# ============================================================================


def build_file_tree(root: Path, max_entries: int = 50_000) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    entries: List[Dict[str, Any]] = []
    stats = {"files": 0, "dirs": 0, "skipped_dirs": 0, "truncated": 0}
    base = str(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        pruned = [d for d in dirnames if d in SCAN_SKIP_DIRS or d.endswith(".git")]
        if pruned:
            stats["skipped_dirs"] += len(pruned)
        dirnames[:] = sorted(d for d in dirnames if d not in pruned)
        rel_dir = os.path.relpath(dirpath, base)
        for d in sorted(dirnames):
            entries.append({"path": os.path.normpath(os.path.join(rel_dir, d)),
                            "type": "tree", "size": ""})
            stats["dirs"] += 1
        for f in sorted(filenames):
            fp = Path(dirpath) / f
            try:
                size = fp.stat().st_size if not fp.is_symlink() else 0
            except OSError:
                size = 0
            entries.append({"path": os.path.normpath(os.path.join(rel_dir, f)),
                            "type": "blob", "size": size})
            stats["files"] += 1
        if len(entries) >= max_entries:
            stats["truncated"] = 1
            break
    return entries[:max_entries], stats


# ============================================================================
# AST (tree-sitter optional, regex fallback)
# ============================================================================


def _try_tree_sitter() -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
    try:
        import tree_sitter  # type: ignore
        from tree_sitter import Language, Parser  # type: ignore
        return tree_sitter, Language, Parser
    except Exception:
        return None, None, None


_TS_LANG_CACHE: Dict[str, Any] = {}


def _ts_parser(lang_name: str, Language: Any, Parser: Any) -> Optional[Any]:
    """Build a tree-sitter Parser for the language, if a grammar is installed."""
    if lang_name in _TS_LANG_CACHE:
        return _TS_LANG_CACHE[lang_name]
    pkg = {"javascript": "tree_sitter_javascript",
           "typescript": "tree_sitter_typescript",
           "tsx": "tree_sitter_typescript",
           "python": "tree_sitter_python"}.get(lang_name)
    parser = None
    if pkg:
        try:
            mod = __import__(pkg)
            ptr = getattr(mod, "language")()
            if lang_name == "tsx":
                ptr = getattr(mod, "language_tsx")()
            lang = Language(ptr)
            try:
                parser = Parser(lang)      # tree-sitter >= 0.22 style
            except TypeError:
                parser = Parser()          # tree-sitter < 0.22 style
                parser.set_language(lang)  # type: ignore[attr-defined]
        except Exception:
            parser = None
    _TS_LANG_CACHE[lang_name] = parser
    return parser


def _count_nodes_iterative(root: Any) -> int:
    n, stack = 0, [root]
    while stack:
        node = stack.pop()
        n += 1
        stack.extend(node.children)
    return n


def _regex_ast(source: str, lang: str) -> Dict[str, Any]:
    nodes: List[Dict[str, str]] = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r"^(?:import|from)\b", stripped):
            start, buf = i, stripped
            while (i + 1 < len(lines) and "from" not in buf
                   and not re.search(r"from\s*[\"']", buf)
                   and stripped.startswith("import")):
                i += 1
                buf += " " + lines[i].strip()
            nodes.append({"type": "import", "text": buf[:200]})
        i += 1
    for m in re.finditer(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
                         r"function\s+(\w+)", source, re.M):
        nodes.append({"type": "function", "name": m.group(1)})
    for m in re.finditer(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?"
                         r"class\s+(\w+)", source, re.M):
        nodes.append({"type": "class", "name": m.group(1)})
    for m in re.finditer(r"^\s*(?:async\s+)?def\s+(\w+)", source, re.M):
        nodes.append({"type": "function", "name": m.group(1)})
    return {"lang": lang, "parser": "regex", "node_count": len(nodes), "nodes": nodes[:200]}


def build_ast_file(path: Path, lang_name: str, ts_mod: Any, Language: Any,
                   Parser: Any, max_kb: int = 256) -> Dict[str, Any]:
    try:
        if path.stat().st_size > max_kb * 1024:
            return {"lang": lang_name, "parser": "none",
                    "skipped": f"file > {max_kb}KB"}
        source = path.read_bytes()
    except OSError as exc:
        return {"lang": lang_name, "error": str(exc)}

    if ts_mod and Language and Parser:
        parser = _ts_parser(lang_name, Language, Parser)
        if parser is not None:
            try:
                tree = parser.parse(source)
                return {
                    "lang": lang_name, "parser": "tree-sitter",
                    "root_type": tree.root_node.type,
                    "node_count": _count_nodes_iterative(tree.root_node),
                    "children": [c.type for c in tree.root_node.children][:50],
                }
            except Exception:
                pass  # fall through to regex
    try:
        return _regex_ast(source.decode("utf-8", "ignore"), lang_name)
    except Exception as exc:
        return {"lang": lang_name, "error": str(exc)}


# ============================================================================
# PER-REPO PIPELINE
# ============================================================================


class RepoProcessor:
    def __init__(self, cfg: "Config", logger: logging.Logger,
                 reporter: ProgressReporter, github: Optional[GitHubClient]) -> None:
        self.cfg = cfg
        self.logger = logger
        self.reporter = reporter
        self.github = github

    # -- helpers ------------------------------------------------------------
    def _stage(self, result: RepoResult, name: str, fn: Callable[[], Any]) -> Optional[Any]:
        """Run one pipeline stage with timing + error capture. Returns value."""
        if self.cfg.stop_event.is_set():
            raise StopRequested(result.repo)
        self.reporter.update_stage(result.repo, name)
        start = time.monotonic()
        try:
            value = fn()
        except StopRequested:
            raise
        except AnalyzerError as exc:
            result.stages[name] = StageInfo(ok=False,
                                            ms=int((time.monotonic() - start) * 1000),
                                            detail=str(exc))
            self.logger.warning("  [%s] %s failed: %s", result.repo, name, exc)
            return None
        except Exception as exc:  # unexpected — still captured, never fatal
            result.stages[name] = StageInfo(ok=False,
                                            ms=int((time.monotonic() - start) * 1000),
                                            detail=f"unexpected: {exc!r}")
            self.logger.exception("  [%s] %s unexpected error", result.repo, name)
            return None
        result.stages[name] = StageInfo(ok=True,
                                        ms=int((time.monotonic() - start) * 1000))
        return value

    def map_repo(self, src_dir: Path) -> Optional[dict]:
        """Build the structural repo map for one source tree."""
        from source_lab.sourcemap import MapFilter, RepoMap
        cfg = self.cfg
        spec = MapFilter(
            kinds=tuple(cfg.map_kind), roles=tuple(cfg.map_role),
            langs=tuple(x for x in cfg.map_langs.split(",") if x),
            paths=tuple(cfg.map_path), targets=tuple(cfg.map_target),
            exported_only=cfg.map_exported_only,
            min_role_confidence=cfg.map_min_role_confidence,
        )
        return RepoMap(
            max_files=cfg.map_max_files, max_kb=cfg.map_max_kb,
            max_symbols=cfg.map_symbols, detail=cfg.map_detail,
            langs=list(spec.langs) or None, filter=spec,
            target_classes=list(spec.targets) or None,
            budget_ms=cfg.map_budget_ms,
        ).generate(src_dir)

    # -- main entry ----------------------------------------------------------
    def process(self, target: Target) -> RepoResult:
        started = time.monotonic()
        result = RepoResult(repo=target.spec, index=target.index, source=target.source)
        cfg = self.cfg

        # Resolve source directory (local path or clone destination).
        if target.source == "local":
            src_dir = Path(target.spec).expanduser().resolve()
            out_name = "local__" + src_dir.name
            if not src_dir.is_dir():
                result.status = "CLONE_FAILED"
                result.error = f"local directory not found: {src_dir}"
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result
        else:
            out_name = target.spec.replace("/", "__")
            src_dir = cfg.workspace / out_name

        out_repo = cfg.out_dir / out_name
        result.out_dir = str(out_repo)

        # 1. Acquire source --------------------------------------------------
        if target.source == "github":
            try:
                validate_slug(target.spec)
            except InvalidSlugError as exc:
                result.status = "INVALID_SLUG"
                result.error = str(exc)
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result
            url = f"https://github.com/{target.spec}.git"
            ms = self._stage(result, "clone",
                             lambda: clone_repo(url, src_dir, cfg.depth,
                                                cfg.clone_timeout, self.logger,
                                                cfg.stop_event, cfg.retries))
            if not result.stages["clone"].ok:
                result.status = "CLONE_FAILED"
                result.error = result.stages["clone"].detail
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result
        else:
            self.reporter.update_stage(result.repo, "locate (local)")

        out_repo.mkdir(parents=True, exist_ok=True)

        # 2-3. Locate + parse manifest + signature matching -------------------
        manifest_payload: Optional[Dict[str, Any]] = None
        manifest_path = self._stage(result, "manifest", lambda: find_manifest(src_dir))
        if manifest_path:
            try:
                result.manifest_path = str(Path(manifest_path).relative_to(src_dir))
            except ValueError:
                result.manifest_path = str(manifest_path)
            raw = self._stage(
                result, "manifest",
                lambda: json.loads(
                    Path(manifest_path).read_text(encoding="utf-8", errors="ignore")))
            if isinstance(raw, dict):
                if is_browser_extension(raw):
                    result.manifest_found = True
                    manifest_payload = self._stage(
                        result, "signatures",
                        lambda: analyze_manifest(raw, Path(manifest_path).parent))
                    if manifest_payload is not None:
                        result.risk_level = manifest_payload["risk_level"]
                        result.heuristic_score = manifest_payload["heuristic_score"]
                else:
                    self.logger.info(
                        "  [%s] manifest.json present but not a browser extension "
                        "(no MV2/MV3 extension keys)", result.repo)
        elif result.stages.get("manifest", StageInfo(True)).ok:
            self.logger.info("  [%s] no manifest.json found", result.repo)

        # 4. Threat scan -------------------------------------------------------
        if manifest_payload is not None:
            threats = self._stage(result, "threat-scan", lambda: scan_threats(src_dir))
            if threats is not None:
                manifest_payload["threat_indicators"] = threats["indicators"]
                manifest_payload["threat_scan"] = {
                    "files_scanned": threats["files_scanned"],
                    "minified_skipped": threats["minified_skipped"],
                }
                result.threats = len(threats["indicators"])
                manifest_payload["target_priority"] = derive_target_priority(
                    manifest_payload, threats)
                result.target_priority = manifest_payload["target_priority"]

        # 5. Dependencies ------------------------------------------------------
        deps = self._stage(result, "dependencies", lambda: parse_dependencies(src_dir))
        if deps is not None:
            self._stage(result, "write",
                        lambda: atomic_write_json(out_repo / "dependencies.json", deps))

        # 6. File tree ---------------------------------------------------------
        tree = self._stage(result, "file-tree",
                           lambda: build_file_tree(src_dir, cfg.max_tree_entries))
        if tree is not None:
            entries, stats = tree
            self._stage(result, "write",
                        lambda: atomic_write_json(out_repo / "file-tree.json", entries))
            result.files, result.dirs = stats["files"], stats["dirs"]

        # 6b. Structural repo map ---------------------------------------------
        if cfg.do_map:
            bundle = self._stage(result, "map", lambda: self.map_repo(src_dir))
            if bundle is not None:
                self._stage(result, "write",
                            lambda: atomic_write_json(out_repo / "repo-map.json", bundle))

        # 7. Metadata ----------------------------------------------------------
        if cfg.do_metadata and self.github is not None and target.source == "github":
            meta = self._stage(result, "metadata",
                               lambda: self.github.repo_metadata(target.spec))
            if meta is None and not result.stages["metadata"].ok:
                # stage failed (rate limit / network) — record it for audit
                self._stage(result, "write",
                            lambda: atomic_write_json(
                                out_repo / "metadata.json",
                                {"error": result.stages["metadata"].detail}))
            elif meta is not None:
                self._stage(result, "write",
                            lambda: atomic_write_json(out_repo / "metadata.json", meta))
                result.stars = meta.get("stars")

        # 8. AST ---------------------------------------------------------------
        if cfg.do_ast and tree is not None:
            entries, _ = tree
            ts_mod, Language, Parser = _try_tree_sitter()
            parser_mode = "tree-sitter" if ts_mod else "regex"
            self.logger.debug("  [%s] AST mode: %s", result.repo, parser_mode)
            ast_out = out_repo / "ast"
            ast_out.mkdir(exist_ok=True)
            ast_index: List[Dict[str, Any]] = []
            src_entries = [e for e in entries
                           if e["type"] == "blob"
                           and Path(e["path"]).suffix.lower() in SOURCE_EXTENSIONS]
            src_entries = src_entries[: cfg.max_ast_files]
            for i, entry in enumerate(src_entries):
                if cfg.stop_event.is_set():
                    raise StopRequested(result.repo)
                if i % 25 == 0:
                    self.reporter.update_stage(
                        result.repo, f"ast {i + 1}/{len(src_entries)}")
                lang = SOURCE_EXTENSIONS[Path(entry["path"]).suffix.lower()]
                ast = build_ast_file(src_dir / entry["path"], lang,
                                     ts_mod, Language, Parser)
                ast["path"] = entry["path"]
                ast_out_name = entry["path"].replace("/", "__") + ".json"
                try:
                    atomic_write_json(ast_out / ast_out_name, ast)
                except OSError as exc:
                    self.logger.warning("  [%s] ast write failed for %s: %s",
                                        result.repo, entry["path"], exc)
                    continue
                ast_index.append({"path": entry["path"], "lang": ast.get("lang"),
                                  "parser": ast.get("parser", "regex"),
                                  "nodes": ast.get("node_count", 0),
                                  "file": f"ast/{ast_out_name}"})
            result.ast_files = len(ast_index)
            self._stage(result, "write",
                        lambda: atomic_write_json(out_repo / "ast-index.json", ast_index))

        # 9. Persist manifest analysis (signatures + rules APPENDED here) ------
        if manifest_payload is not None:
            manifest_payload["repo"] = target.spec
            manifest_payload["bundle_dir"] = str(out_repo)
            self._stage(result, "write",
                        lambda: atomic_write_json(
                            out_repo / "manifest-analysis.json", manifest_payload))

            # 9b. V2 Evidence contract (analysis-v2.json, findings.json, coverage.json)
            try:
                from source_lab.analyzers.browser import BrowserExtensionAnalyzer
                from source_lab.evidence.schema import TargetIdentity
                v2_target = TargetIdentity(
                    identifier=target.spec,
                    repo=target.spec if target.source == "github" else None,
                )
                v2_analyzer = BrowserExtensionAnalyzer(target_identity=v2_target)
                v2_findings, v2_coverage = v2_analyzer.analyze(src_dir)
                atomic_write_json(out_repo / "findings.json", [f.to_dict() for f in v2_findings])
                atomic_write_json(out_repo / "coverage.json", v2_coverage.to_dict())
                v2_bundle = {
                    "schema_version": 2,
                    "target": v2_target.to_dict(),
                    "coverage": v2_coverage.to_dict(),
                    "findings": [f.to_dict() for f in v2_findings],
                    "legacy_manifest": manifest_payload,
                }
                atomic_write_json(out_repo / "analysis-v2.json", v2_bundle)
            except Exception as v2_err:
                self.logger.warning("  [%s] v2 evidence analysis skipped: %s", result.repo, v2_err)

        # 10. Final status -------------------------------------------------------
        failed = [name for name, st in result.stages.items() if not st.ok]
        if failed:
            result.status = "PARTIAL"
            result.error = "failed stages: " + ",".join(sorted(failed))
        elif result.manifest_found:
            result.status = "OK"
        else:
            result.status = "NOT_EXTENSION"
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result


# ============================================================================
# TARGET LOADING
# ============================================================================


def dedupe_targets(entries: List[Tuple[str, str]], logger: logging.Logger) -> List[Target]:
    seen: set = set()
    targets: List[Target] = []
    for spec, source in entries:
        if source == "github":
            key = normalize_slug(spec).lower()
        else:
            key = "local:" + str(Path(spec).resolve()).lower()
        if key in seen:
            logger.debug("duplicate target dropped: %s", spec)
            continue
        seen.add(key)
        norm = normalize_slug(spec) if source == "github" else spec
        targets.append(Target(index=len(targets), spec=norm, source=source))
    return targets


def read_xlsx_records(path: Path) -> List[Dict[str, str]]:
    """Parse rows from the first worksheet of an .xlsx workbook without external dependencies."""
    import zipfile
    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(path) as z:
        strings: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in tree.findall(".//{*}si"):
                strings.append("".join(t.text or "" for t in si.findall(".//{*}t")))

        sheet_xml: Optional[bytes] = None
        for name in z.namelist():
            if name.startswith("xl/worksheets/sheet"):
                sheet_xml = z.read(name)
                break
        if not sheet_xml:
            return []

        tree = ET.fromstring(sheet_xml)
        raw_rows: List[List[str]] = []
        for r in tree.findall(".//{*}row"):
            row_vals: List[str] = []
            for c in r.findall("{*}c"):
                t = c.get("t")
                v = c.find("{*}v")
                is_tag = c.find("{*}is")
                val = ""
                if t == "s" and v is not None and v.text and v.text.isdigit():
                    idx = int(v.text)
                    val = strings[idx] if idx < len(strings) else ""
                elif is_tag is not None:
                    val = "".join(t_el.text or "" for t_el in is_tag.findall(".//{*}t"))
                elif v is not None and v.text:
                    val = v.text
                row_vals.append(val)
            if any(row_vals):
                raw_rows.append(row_vals)

        if not raw_rows:
            return []
        headers = [h.strip() for h in raw_rows[0]]
        records: List[Dict[str, str]] = []
        for row in raw_rows[1:]:
            rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
            records.append(rec)
        return records


def safe_expand_path(p: str | Path) -> Path:
    p_str = str(p)
    if p_str.startswith("~"):
        try:
            return Path(p_str).expanduser()
        except RuntimeError:
            home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or "/Users/Q"
            return Path(home) / p_str[2:].lstrip("/")
    return Path(p_str)


def is_local_dir(val: str) -> bool:
    if not val or val.startswith(("http://", "https://", "git@", "ssh://")):
        return False
    try:
        p = safe_expand_path(val)
        return p.is_dir()
    except Exception:
        return False


def load_targets(args: argparse.Namespace, logger: logging.Logger) -> List[Target]:
    entries: List[Tuple[str, str]] = []

    # --scan-dir: every non-hidden child directory is a local repo
    if args.scan_dir:
        scan_root = safe_expand_path(args.scan_dir).resolve()
        if not scan_root.is_dir():
            raise AnalyzerError(f"--scan-dir is not a directory: {scan_root}")
        children = sorted(p for p in scan_root.iterdir()
                          if p.is_dir() and not p.name.startswith("."))
        if not children:
            raise AnalyzerError(
                f"--scan-dir has no repository sub-directories: {scan_root}")
        for child in children:
            entries.append((str(child), "local"))
        logger.info("scan-dir: %d local repositories under %s", len(children), scan_root)

    # positional: slugs, GitHub URLs, or existing local directories
    for spec in args.repos:
        if is_local_dir(spec):
            entries.append((str(safe_expand_path(spec).resolve()), "local"))
        else:
            entries.append((spec, "github"))

    # -i/--input file: .csv, .xlsx, or plain text (one slug/URL/path per line)
    if args.input:
        path = safe_expand_path(args.input)
        if not path.is_file():
            raise AnalyzerError(f"input file not found: {path}")

        def _extract_val(row: Dict[str, Any]) -> str:
            norm = {
                str(k).strip().lower().replace("-", "_").replace(" ", "_"): str(v).strip()
                for k, v in row.items() if k is not None and v is not None
            }
            candidates = (
                "repo_url", "repo_link", "repolink", "repository", "repo",
                "full_name", "html_url", "url", "slug", "local_path", "path"
            )
            for c in candidates:
                val = norm.get(c)
                if val:
                    return val
            return ""

        suffix = path.suffix.lower()
        if suffix == ".csv":
            with open(path, encoding="utf-8", newline="") as f:
                for row_no, row in enumerate(csv.DictReader(f), start=2):
                    val = _extract_val(row)
                    if val:
                        if is_local_dir(val):
                            entries.append((str(safe_expand_path(val).resolve()), "local"))
                        else:
                            entries.append((val, "github"))
                    else:
                        logger.debug("input CSV row %d: no recognizable repo column", row_no)
        elif suffix == ".xlsx":
            records = read_xlsx_records(path)
            for row_no, row in enumerate(records, start=2):
                val = _extract_val(row)
                if val:
                    if is_local_dir(val):
                        entries.append((str(safe_expand_path(val).resolve()), "local"))
                    else:
                        entries.append((val, "github"))
                else:
                    logger.debug("input XLSX row %d: no recognizable repo column", row_no)
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    if is_local_dir(line):
                        entries.append((str(safe_expand_path(line).resolve()), "local"))
                    else:
                        entries.append((line, "github"))

    if not entries:
        raise AnalyzerError(
            "no repositories given. Use positional args, -i <file>, or --scan-dir.")

    return dedupe_targets(entries, logger)


# ============================================================================
# STATE (resume support)
# ============================================================================


def load_state(path: Path, logger: logging.Logger) -> Dict[str, Any]:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("state file unreadable, starting fresh", exc_info=True)
    return {}


def save_state(path: Path, state: Dict[str, Any], logger: logging.Logger) -> None:
    try:
        atomic_write_json(path, state)
    except OSError:
        logger.warning("could not persist state file: %s", path)


# ============================================================================
# CONFIG + CLI
# ============================================================================


@dataclass
class Config:
    out_dir: Path
    workspace: Path
    depth: int
    clone_timeout: float
    retries: int
    do_ast: bool
    do_metadata: bool
    do_map: bool
    map_detail: str
    map_max_files: int
    map_max_kb: int
    map_symbols: int
    map_budget_ms: int
    map_langs: str
    map_target: List[str]
    map_kind: List[str]
    map_role: List[str]
    map_path: List[str]
    map_exported_only: bool
    map_min_role_confidence: float
    keep_workspace: bool
    max_tree_entries: int
    max_ast_files: int
    stop_event: threading.Event


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=APP,
        description="Clone, analyze, and store browser-extension repositories.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("repos", nargs="*", metavar="repo",
                    help="owner/name slugs, GitHub URLs, or local directories")
    ap.add_argument("-i", "--input", help="CSV, XLSX, or plain-text file with repo list")
    ap.add_argument("--scan-dir", metavar="DIR",
                    help="treat each non-hidden sub-directory of DIR as a local "
                         "repo (no clone)")
    ap.add_argument("-o", "--out-dir", default="./ext-analysis",
                    help="output directory (default: ./ext-analysis)")
    ap.add_argument("--workspace", default=None,
                    help="clone workspace (default: fresh temp dir)")
    ap.add_argument("--keep-workspace", action="store_true",
                    help="preserve clones after processing")
    ap.add_argument("--token", default=None,
                    help="GitHub token (env: GITHUB_TOKEN / GH_TOKEN, or `gh auth token`)")
    ap.add_argument("-w", "--workers", type=int, default=1, metavar="N",
                    help="parallel workers (default: 1)")
    ap.add_argument("--retries", type=int, default=3, metavar="N",
                    help="retry attempts for clone/metadata (default: 3)")
    ap.add_argument("--depth", type=int, default=1, metavar="N",
                    help="git clone --depth (default: 1)")
    ap.add_argument("--clone-timeout", type=float, default=300.0, metavar="SEC",
                    help="per-clone timeout in seconds (default: 300)")
    ap.add_argument("--api-max-wait", type=float, default=90.0, metavar="SEC",
                    help="only wait for GitHub rate-limit reset if it is within "
                         "this many seconds, else fail fast (default: 90)")
    ap.add_argument("--max-tree-entries", type=int, default=50_000, metavar="N",
                    help="cap file-tree entries per repo (default: 50000)")
    ap.add_argument("--max-ast-files", type=int, default=200, metavar="N",
                    help="cap AST files per repo (default: 200)")
    ap.add_argument("--no-ast", action="store_true", help="skip AST building")
    ap.add_argument("--no-map", action="store_true", help="skip the structural repo map")
    ap.add_argument("--map-detail", choices=["files", "symbols", "full"], default="files",
                    help="repo-map detail (default: files)")
    ap.add_argument("--map-max-files", type=int, default=4000, metavar="N")
    ap.add_argument("--map-max-kb", type=int, default=512, metavar="N")
    ap.add_argument("--map-symbols", type=int, default=200, metavar="N")
    ap.add_argument("--map-budget-ms", type=int, default=30_000, metavar="N")
    ap.add_argument("--map-langs", default="", help="comma-separated languages")
    ap.add_argument("--map-target", action="append", default=[], metavar="PLATFORM")
    ap.add_argument("--map-kind", action="append", default=[], metavar="KIND")
    ap.add_argument("--map-role", action="append", default=[], metavar="ROLE")
    ap.add_argument("--map-path", action="append", default=[], metavar="GLOB")
    ap.add_argument("--map-exported-only", action="store_true")
    ap.add_argument("--map-min-role-confidence", type=float, default=0.0, metavar="F")
    ap.add_argument("--no-metadata", action="store_true",
                    help="skip GitHub API metadata")
    ap.add_argument("--resume", action="store_true",
                    help="skip repos already processed OK in a previous run")
    ap.add_argument("-v", "--verbose", action="store_true", help="debug console output")
    ap.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    ap.add_argument("--version", action="version", version=f"{APP} {VERSION}")
    return ap


def resolve_token(args: argparse.Namespace, logger: logging.Logger) -> Optional[str]:
    token = args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        try:
            proc = subprocess.run(["gh", "auth", "token"], capture_output=True,
                                  text=True, timeout=5)
            if proc.returncode == 0 and proc.stdout.strip():
                token = proc.stdout.strip()
                logger.debug("using token from gh CLI")
        except Exception:
            pass
    return token


def setup_logging(args: argparse.Namespace, out_dir: Path,
                  reporter: Optional[ProgressReporter]) -> logging.Logger:
    logger = logging.getLogger(APP)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    stream = sys.stderr
    console = ProgressAwareLogHandler(reporter, stream)
    console.setLevel(logging.DEBUG if args.verbose else
                     logging.WARNING if args.quiet else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    file_handler = RotatingFileHandler(out_dir / "analyzer.log",
                                       maxBytes=1_000_000, backupCount=3,
                                       encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(threadName)s %(name)s: %(message)s"))
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def write_summary_csv(out_dir: Path, results: List[RepoResult]) -> Path:
    path = out_dir / "summary.csv"
    fields = ["repo", "source", "status", "risk_level", "target_priority",
              "heuristic_score", "manifest_found", "manifest_path",
              "files", "dirs", "ast_files", "threats", "stars",
              "duration_ms", "out_dir", "error"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in sorted(results, key=lambda x: x.index):
            writer.writerow(r.csv_row())
    return path


def print_final_report(results: List[RepoResult], use_color: bool) -> None:
    by_status: Dict[str, int] = {}
    by_risk: Dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        if r.risk_level:
            by_risk[r.risk_level] = by_risk.get(r.risk_level, 0) + 1
    print("\n" + _Ansi.wrap("════ RUN SUMMARY ════",
                            _Ansi.BOLD, _Ansi.CYAN, enabled=use_color))
    for status, n in sorted(by_status.items()):
        print(f"  {color_status(status.ljust(16), use_color)} {n:3d}")
    if by_risk:
        print(_Ansi.wrap("  risk levels:", _Ansi.DIM, enabled=use_color))
        for risk in ("VERY_HIGH", "HIGH", "MEDIUM", "LOW"):
            if by_risk.get(risk):
                print(f"    {risk.ljust(16)} {by_risk[risk]:3d}")
    failures = [r for r in results if r.status not in
                ("OK", "NOT_EXTENSION", "SKIPPED_RESUMED", "STOPPED")]
    if failures:
        print(_Ansi.wrap("  failures:", _Ansi.YELLOW, enabled=use_color))
        for r in failures:
            print(f"    {r.repo}: {r.error or r.status}")


def main() -> int:
    args = build_arg_parser().parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[!] cannot create output dir {out_dir}: {exc}", file=sys.stderr)
        return 2

    stop_event = threading.Event()
    reporter = ProgressReporter(total=1, stream=sys.stderr,
                                use_ansi=not args.no_color)
    logger = setup_logging(args, out_dir, reporter)

    def _on_signal(signum: int, _frame: Any) -> None:
        if not stop_event.is_set():
            stop_event.set()
            logger.warning(
                "signal %s received — finishing current work, then stopping "
                "(press Ctrl-C again to force)", signal.Signals(signum).name)
        else:
            logger.warning("second signal — aborting immediately")
            raise SystemExit(130)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    started = time.monotonic()
    try:
        targets = load_targets(args, logger)
    except AnalyzerError as exc:
        logger.error("[!] %s", exc)
        return 2
    reporter.total = len(targets)

    token = None if args.no_metadata else resolve_token(args, logger)
    if not token and not args.no_metadata:
        logger.warning("no GitHub token — metadata API limited to 60 req/h "
                       "(set GITHUB_TOKEN or --token)")

    workspace = (Path(args.workspace).expanduser().resolve()
                 if args.workspace else Path(tempfile.mkdtemp(prefix="ext-an-")))
    workspace.mkdir(parents=True, exist_ok=True)

    cfg = Config(
        out_dir=out_dir, workspace=workspace, depth=max(1, args.depth),
        clone_timeout=args.clone_timeout, retries=max(1, args.retries),
        do_ast=not args.no_ast, do_metadata=not args.no_metadata,
        do_map=not args.no_map, map_detail=args.map_detail,
        map_max_files=max(1, args.map_max_files), map_max_kb=max(1, args.map_max_kb),
        map_symbols=max(1, args.map_symbols), map_budget_ms=max(1, args.map_budget_ms),
        map_langs=args.map_langs, map_target=args.map_target, map_kind=args.map_kind,
        map_role=args.map_role, map_path=args.map_path,
        map_exported_only=args.map_exported_only,
        map_min_role_confidence=args.map_min_role_confidence,
        keep_workspace=args.keep_workspace,
        max_tree_entries=max(100, args.max_tree_entries),
        max_ast_files=max(1, args.max_ast_files),
        stop_event=stop_event,
    )
    github = (GitHubClient(token, logger, stop_event,
                           retries=cfg.retries, max_wait=args.api_max_wait)
              if not args.no_metadata else None)
    processor = RepoProcessor(cfg, logger, reporter, github)

    state_path = out_dir / ".state.json"
    state = load_state(state_path, logger) if args.resume else {}

    logger.info(_Ansi.wrap(
        f"{APP} {VERSION} — {len(targets)} repo(s) -> {out_dir}",
        _Ansi.BOLD, enabled=not args.no_color))
    logger.info("workspace: %s%s", workspace,
                " (kept)" if args.keep_workspace else " (temp)")
    if args.workers > 1:
        logger.info("workers: %d", args.workers)

    results: List[RepoResult] = []
    state_lock = threading.Lock()

    def _persist(result: RepoResult) -> None:
        with state_lock:
            results.append(result)
            state[result.repo] = {
                "status": result.status, "finished_at": utcnow_iso(),
                "out_dir": result.out_dir,
            }
            save_state(state_path, state, logger)

    def _run(target: Target) -> RepoResult:
        if stop_event.is_set():
            return RepoResult(repo=target.spec, index=target.index,
                              source=target.source, status="STOPPED")
        key = normalize_slug(target.spec) if target.source == "github" else target.spec
        prev = state.get(key) or state.get(target.spec)
        if args.resume and prev and prev.get("status") == "OK" \
                and prev.get("out_dir") and Path(prev["out_dir"]).is_dir():
            logger.info("[%d/%d] %s — already OK in previous run, skipping "
                        "(--resume)", target.index + 1, len(targets), target.spec)
            return RepoResult(repo=target.spec, index=target.index,
                              source=target.source, status="SKIPPED_RESUMED",
                              out_dir=prev["out_dir"], resumed=True)
        reporter.start_repo(target.spec)
        logger.info("[%d/%d] %s (%s)", target.index + 1, len(targets),
                    target.spec, target.source)
        try:
            result = processor.process(target)
        except StopRequested:
            return RepoResult(repo=target.spec, index=target.index,
                              source=target.source, status="STOPPED")
        except Exception as exc:  # absolute last resort — the loop must live
            logger.exception("[%s] crashed outside stage handling", target.spec)
            result = RepoResult(repo=target.spec, index=target.index,
                                source=target.source, status="EXCEPTION",
                                error=f"{type(exc).__name__}: {exc}")
        level = (logging.INFO if result.status in
                 ("OK", "NOT_EXTENSION", "SKIPPED_RESUMED") else logging.WARNING)
        logger.log(level,
                   "    → %s risk=%s score=%s files=%s ast=%s threats=%s (%dms)",
                   color_status(result.status, not args.no_color),
                   result.risk_level or "-", result.heuristic_score,
                   result.files, result.ast_files, result.threats,
                   result.duration_ms)
        return result

    workers = max(1, args.workers)
    try:
        if workers == 1:
            for target in targets:
                if stop_event.is_set():
                    results.append(RepoResult(repo=target.spec, index=target.index,
                                              source=target.source, status="STOPPED"))
                    continue
                result = _run(target)
                _persist(result)
                reporter.finish_repo(result.repo, result.status)
        else:
            with ThreadPoolExecutor(max_workers=workers,
                                    thread_name_prefix="worker") as pool:
                futures = {pool.submit(_run, t): t for t in targets}
                for fut in as_completed(futures):
                    target = futures[fut]
                    try:
                        result = fut.result()
                    except Exception as exc:  # pragma: no cover
                        logger.exception("[%s] worker crashed", target.spec)
                        result = RepoResult(repo=target.spec, index=target.index,
                                            source=target.source, status="EXCEPTION",
                                            error=str(exc))
                    _persist(result)
                    reporter.finish_repo(result.repo, result.status)
                    if stop_event.is_set():
                        for f in futures:
                            f.cancel()
                        break
    finally:
        reporter.close()
        # mark unprocessed targets as STOPPED so summary stays complete
        done_repos = {r.repo for r in results}
        for t in targets:
            if t.spec not in done_repos:
                results.append(RepoResult(repo=t.spec, index=t.index,
                                          source=t.source, status="STOPPED"))

    summary_csv = write_summary_csv(out_dir, results)

    failures = sum(1 for r in results if r.status not in
                   ("OK", "NOT_EXTENSION", "SKIPPED_RESUMED", "STOPPED"))
    report = {
        "app": APP, "version": VERSION,
        "started_at": datetime.fromtimestamp(
            started, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": utcnow_iso(),
        "duration_s": round(time.monotonic() - started, 2),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "args": {k: v for k, v in vars(args).items() if k != "token"},
        "totals": {
            "repos": len(results),
            "by_status": dict(sorted(
                {s: sum(1 for r in results if r.status == s)
                 for s in {r.status for r in results}}.items())),
            "by_risk": {risk: sum(1 for r in results if r.risk_level == risk)
                        for risk in ("VERY_HIGH", "HIGH", "MEDIUM", "LOW")
                        if any(r.risk_level == risk for r in results)},
            "total_files_seen": sum(r.files for r in results),
            "total_ast_files": sum(r.ast_files for r in results),
            "total_stars": sum(r.stars or 0 for r in results),
        },
        "results": [r.csv_row() for r in sorted(results, key=lambda x: x.index)],
    }
    atomic_write_json(out_dir / "report.json", report)

    print_final_report(results, use_color=not args.no_color)
    logger.info("summary: %s", summary_csv)
    logger.info("report : %s", out_dir / "report.json")
    logger.info("log    : %s", out_dir / "analyzer.log")

    if not cfg.keep_workspace and not args.workspace:
        shutil.rmtree(workspace, ignore_errors=True)

    if stop_event.is_set():
        return 130
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] interrupted", file=sys.stderr)
        sys.exit(130)
