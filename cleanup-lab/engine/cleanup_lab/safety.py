"""The one guard every destructive call goes through (CLN-12).

Qleaner had two substring tests here. Both are replaced:

* ``contains("..")`` rejected valid names such as ``a..b`` and never resolved the
  path, so a symlink inside a cache folder could point anywhere;
* ``contains("system")`` blocked ``~/.cache/systemd`` while protecting nothing it
  did not literally name, and the running-app lock only looked at Chrome and
  Firefox by substring.

Here a target must resolve (symlinks included) inside one of **its catalog entry's**
resolved roots, must not be a protected root or a system directory, must exist, must
be owned by the current user, and must not have its owning application running.
Every refusal returns a reason the page shows next to the item, and
:func:`assert_safe_target` raises the same reason as a :class:`SafetyError`.

The path half is ported from ``cleanup-lab/reference/python/cleanup_ref/path_policy.py``
(same fixes: resolved containment, component comparison, no root-itself purges);
``validate_scan_root`` stays for the Disk Explorer (CLN-23) and ``validate_copy`` for
relocation (CLN-27).
"""
from __future__ import annotations

import csv
import io
import os
import glob
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .catalog import expand
from .paths import platform_id

PROCESS_TIMEOUT = 5.0
#: Never a cleanup target, on top of the roots in :func:`protected_roots`.
SYSTEM_ROOTS = {
    "macos": ("/System", "/usr", "/bin", "/sbin", "/etc", "/Applications", "/Library"),
    "linux": ("/usr", "/bin", "/sbin", "/etc", "/boot", "/lib", "/lib64", "/opt"),
    "windows": (
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
        "C:\\ProgramData",
    ),
}


class PathPolicyError(ValueError):
    """A path was rejected. ``code`` is stable; the message is safe to show."""

    def __init__(self, message, code="path-invalid"):
        super().__init__(message)
        self.code = code


class SafetyError(ValueError):
    """A destructive action was refused. ``code`` is stable, the message is shown."""

    def __init__(self, message, code="unsafe"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Verdict:
    """The guard's answer for one item, with the reason the page should show.

    ``code`` is what the page translates (all seven locale catalogs); ``reason`` is
    the English fallback used by the CLI, the audit log and the API payload.
    """

    ok: bool
    path: str | None
    reason: str = ""
    privileged: bool = False
    code: str = ""


def _home(home):
    return os.fspath(home) if home is not None else os.path.expanduser("~")


def canonical(raw, *, home=None):
    """Trim, expand a leading ``~`` and normalise. Does not touch the disk.

    Relative paths are refused: the catalog and the page must name a path
    absolutely (or relative to ``~``).
    """
    text = os.fspath(raw).strip()
    if not text:
        raise PathPolicyError("A filesystem path cannot be empty.", "empty")
    if "\x00" in text:
        raise PathPolicyError("A filesystem path cannot contain NUL bytes.", "nul")
    if text == "~" or text.startswith("~/") or text.startswith("~\\"):
        text = _home(home) + text[1:]
    if not os.path.isabs(text):
        raise PathPolicyError(
            "Filesystem paths must be absolute: {0}".format(raw), "relative"
        )
    return os.path.normpath(text)


def resolved(raw, *, home=None):
    """:func:`canonical`, then resolve every symlink on the way."""
    return os.path.realpath(canonical(raw, home=home))


def protected_roots(*, home=None):
    """Paths Cleanup Lab never operates on as a whole: the root(s) and the home folder."""
    roots = {os.path.realpath(os.path.abspath(os.sep)), os.path.realpath(_home(home))}
    if os.name == "nt":  # every drive root, e.g. C:\ and D:\
        roots.update("{0}:\\".format(letter) for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return roots


def system_roots(platform):
    """Directories a catalog entry must never point at, resolved for comparison."""
    return {os.path.realpath(item) for item in SYSTEM_ROOTS.get(platform, ())}


def is_contained(path, root):
    """True when the resolved ``path`` equals or lies under the resolved ``root``."""
    p, r = os.path.realpath(os.fspath(path)), os.path.realpath(os.fspath(root))
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:  # different drives on Windows, or mixed absolute/relative
        return False


def validate_managed_path(raw, *, home=None):
    """Resolved path that is not a protected root or a system directory."""
    path = resolved(raw, home=home)
    if path in protected_roots(home=home):
        raise PathPolicyError(
            "Refusing to operate on protected root {0}.".format(path), "protected"
        )
    for root in sorted(system_roots(_platform_of(path))):
        if path == root:
            raise PathPolicyError(
                "Refusing to operate on system directory {0}.".format(path), "system-root"
            )
    return path


def _platform_of(path):
    """Best-effort platform for a path (the host running the engine)."""
    import sys

    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return "linux"


def validate_scan_root(raw, *, home=None):
    """A folder the user chose to explore read-only (CLN-23).

    Must exist, be a directory, be readable and listable, and must not be the whole
    disk or the home root ("choose a specific folder").
    """
    path = validate_managed_path(raw, home=home)
    if not os.path.lexists(path):
        raise PathPolicyError("That folder doesn't exist: {0}".format(path), "missing")
    if not os.path.isdir(path):
        raise PathPolicyError("Choose a folder, not a file: {0}".format(path), "not-a-folder")
    if not os.access(path, os.R_OK | os.X_OK):
        raise PathPolicyError("That folder isn't readable: {0}".format(path), "unreadable")
    return path


def validate_target(raw, allowed_roots, *, home=None, allow_root_itself=False):
    """Resolved purge/relocation target that lies inside one of ``allowed_roots``.

    ``allowed_roots`` come from the catalog, never from the page. The target itself
    must exist; a vanished path is reported, not ignored.
    """
    path = validate_managed_path(raw, home=home)
    if not os.path.lexists(canonical(raw, home=home)):
        raise PathPolicyError("Path no longer exists: {0}".format(path), "missing")
    roots = [resolved(root, home=home) for root in allowed_roots]
    for root in roots:
        if is_contained(path, root) and (allow_root_itself or path != root):
            return path
    raise PathPolicyError(
        "Path is outside every allowed root: {0}".format(path), "outside-roots"
    )


def validate_copy(source, destination, destination_root, *, home=None):
    """Source/destination pair for a relocation (CLN-27).

    The destination must be inside its managed root, differ from the source, and
    neither path may contain the other (copying a folder into itself).
    """
    src = validate_managed_path(source, home=home)
    target = Path(canonical(destination, home=home))
    dst = os.path.join(os.path.realpath(target.parent), target.name)
    if dst in protected_roots(home=home):
        raise PathPolicyError(
            "Refusing to operate on protected root {0}.".format(dst), "protected"
        )
    root = validate_managed_path(destination_root, home=home)
    if src == dst:
        raise PathPolicyError(
            "Source and destination must be different paths: {0}".format(src), "same-path"
        )
    if is_contained(dst, src) or is_contained(src, dst):
        raise PathPolicyError(
            "Source and destination must not contain each other.", "nested"
        )
    if not is_contained(dst, root):
        raise PathPolicyError(
            "Destination is outside its managed root: {0}".format(dst), "destination-outside"
        )
    return src, dst


# ── Ownership and the running-app lock ──────────────────────────────────────


def owned_by_user(path, *, uid=None, lstat=None):
    """Whether the current user owns the path.

    Windows has no comparable POSIX owner check here; the catalog roots live under
    the user's own profile, and a privileged target is flagged separately.
    """
    import sys

    if sys.platform == "win32":
        return True
    lstat = lstat or os.lstat
    uid = os.getuid() if uid is None else uid
    try:
        return lstat(path).st_uid == uid
    except OSError:
        return False


def _run(args):
    try:
        completed = subprocess.run(
            args, capture_output=True, text=True, timeout=PROCESS_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 0, ""
    return completed.returncode, completed.stdout


def process_names(*, platform=None, runner=None):
    """Command names of the running processes, best effort.

    A failure to list processes yields an empty tuple: the lock then cannot prove an
    app is running, and the plan says so rather than blocking every clean.
    """
    runner = runner or _run
    if platform == "windows":
        code, out = runner(["tasklist", "/fo", "csv", "/nh"])
        if code != 0:
            return ()
        names = []
        for row in csv.reader(io.StringIO(out)):
            if row and row[0]:
                names.append(row[0])
        return tuple(names)
    code, out = runner(["ps", "-axo", "comm="])
    if code != 0:
        return ()
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def running_processes(wanted, *, names=None, platform=None, runner=None):
    """The subset of ``wanted`` that is running, matched on the whole name.

    Comparison is case-insensitive against the command name and against its
    basename, so ``Google Chrome`` matches
    ``/Applications/Google Chrome.app/Contents/MacOS/Google Chrome``. No substring
    test: ``Slack`` does not match ``slackd``.
    """
    if not wanted:
        return []
    if names is None:
        names = process_names(platform=platform, runner=runner)
    available = set()
    for name in names:
        available.add(name.casefold())
        available.add(os.path.basename(name.replace("\\", "/")).casefold())
    return [name for name in wanted if name.casefold() in available]


# ── The guard ───────────────────────────────────────────────────────────────


def entry_roots(entry, *, env=None, platform=None):
    """The resolved roots a catalog entry authorises, or ``[]`` when none resolve."""
    env = os.environ if env is None else env
    target = platform or platform_id()
    roots = []
    detector = entry.get("detector")
    if detector == "spotlight" or detector == "tool" and entry.get("cacheEnv"):
        from .catalog import resolve as catalog_resolve
        roots = [os.path.realpath(item["path"]) for item in catalog_resolve(entry, target, env) if item["path"]]
    else:
        for template in entry.get("paths", {}).get(target, []):
            path, _reason = expand(template, target, env)
            if path:
                if entry.get("detector") == "profile-glob":
                    prefix = path.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
                    root = prefix.rstrip(os.sep) if glob.has_magic(path) else os.path.dirname(path)
                    roots.append(os.path.realpath(root))
                else:
                    roots.append(os.path.realpath(path))
    return roots


def check_target(
    raw,
    entry,
    *,
    env=None,
    platform=None,
    home=None,
    uid=None,
    lstat=None,
    names=None,
    runner=None,
):
    """Every check one destructive action needs, as a :class:`Verdict`.

    Order matters for the reason shown to the user: a path that is both outside its
    root and owned by someone else reports the more specific "outside" reason.
    """
    privileged = bool(entry.get("needsPrivilege"))
    try:
        path = validate_managed_path(raw, home=home)
    except PathPolicyError as exc:
        return Verdict(False, None, str(exc), privileged, exc.code)
    if entry.get("detector") == "profile-glob":
        direct = False
        for template in entry.get("paths", {}).get(platform or platform_id(), []):
            expanded, _ = expand(template, platform or platform_id(), os.environ if env is None else env)
            if not expanded:
                continue
            prefix = expanded.split("*", 1)[0].split("?", 1)[0].split("[", 1)[0]
            prefix = prefix.rstrip(os.sep) if glob.has_magic(expanded) else os.path.dirname(expanded)
            try:
                relative = os.path.relpath(os.path.abspath(raw), os.path.abspath(prefix))
            except ValueError:
                continue
            if relative == os.pardir or relative.startswith(os.pardir + os.sep):
                continue
            expected = os.path.normcase(os.path.join(os.path.realpath(prefix), relative))
            if os.path.normcase(path) == expected:
                direct = True
                break
        if not direct:
            return Verdict(False, path, "Browser path traverses a symlink outside its catalog target.", privileged, "outside-root")
    if not os.path.lexists(canonical(raw, home=home)):
        return Verdict(False, path, "Path no longer exists.", privileged, "missing")
    roots = entry_roots(entry, env=env, platform=platform)
    if not roots:
        return Verdict(
            False, path, "This entry has no path for this system.", privileged, "no-path"
        )
    if not any(is_contained(path, root) for root in roots):
        return Verdict(
            False,
            path,
            "Path resolves outside its catalog root (symlink escape).",
            privileged,
            "outside-root",
        )
    if not owned_by_user(canonical(raw, home=home), uid=uid, lstat=lstat):
        return Verdict(
            False,
            path,
            "Owned by another user account; a privileged plan is required.",
            privileged,
            "foreign-owner",
        )
    busy = running_processes(
        entry.get("owningProcesses", ()), names=names, platform=platform, runner=runner
    )
    if busy:
        return Verdict(
            False,
            path,
            "The owning application is running: {0}.".format(", ".join(sorted(busy))),
            privileged,
            "app-running",
        )
    return Verdict(True, path, "", privileged, "")


def assert_safe_target(raw, entry, **kwargs):
    """Return the resolved path, or raise :class:`SafetyError` with the page's reason."""
    verdict = check_target(raw, entry, **kwargs)
    if not verdict.ok:
        raise SafetyError(verdict.reason, verdict.code)
    return verdict.path


def describe_refusal(verdict):
    """One line for the item row: the reason, plus the privilege note when relevant."""
    if verdict.ok:
        return ""
    return verdict.reason
