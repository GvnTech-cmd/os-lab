"""CLN-28: a read-only inventory of the local mounted volumes.

Standard library only. The inventory answers the three questions the cleanup
workflow needs — which local volumes exist, how full each one is, and which one
holds the home folder — and never writes anything: the only filesystem access is
a capacity query (:func:`shutil.disk_usage`).

Network and pseudo filesystems are filtered out before any capacity call, so a
dead network mount cannot stall the probe. Each surviving volume reports its
mount point, filesystem, capacity, a ``root`` / ``internal`` / ``removable`` /
``unknown`` kind, and — above :data:`PRESSURE_THRESHOLD` usage — a pressure
warning. The engine also marks the volume that holds the home folder.

Every platform difference sits behind an injected seam, so tests pass fake
mount tables and never touch a real disk:

* Windows — ``ctypes`` calls ``kernel32`` (``GetLogicalDrives``,
  ``GetDriveTypeW``, ``GetVolumeInformationW``): local calls, no shell.
* Linux — ``/proc/self/mountinfo`` is read as data.
* macOS — the fixed-argv ``mount`` probe, plus an optional fixed-argv
  ``diskutil info -plist`` probe per device (same pattern as the CLN-25
  tool probes: five-second timeout, output validated, failure is not fatal).

A drive whose Windows type is unknown is hidden, like a container action whose
engine does not answer: the inventory reports what it can prove.
"""
from __future__ import annotations

import ctypes
import ntpath
import os
import plistlib
import posixpath
import shutil
import subprocess
import time

from . import paths

#: A volume above this used fraction carries a pressure warning.
PRESSURE_THRESHOLD = 0.90
#: Every fixed-argv probe answers within this many seconds or counts as absent.
PROBE_TIMEOUT = 5

#: Filesystem types that hold no user-cleanable data and are never reported.
PSEUDO_FILESYSTEMS = {
    "autofs", "binfmt_misc", "bpf", "cgroup", "cgroup2", "cgroupfs", "configfs",
    "cramfs", "debugfs", "devpts", "devtmpfs", "efivarfs", "efivars", "fusectl",
    "hugetlbfs", "iso9660", "mqueue", "nsfs", "overlay", "proc", "pstore", "ramfs",
    "romfs", "rpc_pipefs", "securityfs", "selinuxfs", "squashfs", "sysfs",
    "tmpfs", "tracefs", "udf",
}

#: Network filesystems: a dead server must never stall the probe, so these
#: volumes are filtered before any capacity query.
NETWORK_FILESYSTEMS = {
    "9p", "9p2000", "9p2000.L", "afs", "afp", "afpfs", "ceph", "cifs", "coda",
    "davfs", "davfs2", "gfs", "gfs2", "glusterfs", "lustre", "mfs", "ncpfs",
    "nfs", "nfs4", "nfsd", "ocfs2", "openafs", "smb", "smb2", "smbfs", "sshfs",
    "virtiofs", "webdav",
}

# Windows drive types from GetDriveTypeW; only the first two are reported.
DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6


def _unescape(value):
    """Decode ``\\040``-style octal escapes used by kernel mount tables."""
    result = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 4 <= len(value):
            digits = value[index + 1:index + 4]
            if len(digits) == 3 and all(digit in "01234567" for digit in digits):
                result.append(chr(int(digits, 8)))
                index += 4
                continue
        result.append(value[index])
        index += 1
    return "".join(result)


def _format_bytes(value):
    """A short human-readable byte count for the pressure warnings."""
    if value is None:
        return "an unknown amount"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            return "{0:.0f} {1}".format(size, unit) if unit == "B" else "{0:.1f} {1}".format(size, unit)
        size /= 1024
    return "{0:.1f} PB".format(size)


def _read_proc_mountinfo():
    with open("/proc/self/mountinfo", encoding="utf-8") as handle:
        return handle.read()


def _sys_block_removable(disk):
    """/sys says whether the parent disk holds ejectable media; None = unknown."""
    try:
        with open("/sys/block/{0}/removable".format(disk), encoding="ascii") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _linux_parent(device):
    """/dev/nvme0n1p4 → nvme0n1, /dev/sda1 → sda, /dev/mmcblk0p2 → mmcblk0."""
    name = device.rsplit("/", 1)[-1]
    if (name.startswith("nvme") or name.startswith("mmcblk")) and "p" in name:
        return name.rsplit("p", 1)[0]
    return name.rstrip("0123456789")


def linux_rows(env=None, *, mountinfo_text=None, mountinfo_reader=_read_proc_mountinfo,
               removable_reader=_sys_block_removable):
    """Parse the Linux mount table into volume rows, filtering pseudo and network types.

    Bind mounts and btrfs subvolumes that share one device collapse into the
    shortest mount point, so one physical volume is listed once.
    """
    del env
    text = mountinfo_text
    if text is None:
        try:
            text = mountinfo_reader()
        except OSError as exc:
            return [], "Could not read the Linux mount table: {0}".format(exc)
    candidates = {}
    order = []
    for line in text.splitlines():
        if " - " not in line:
            continue
        prefix, suffix = line.split(" - ", 1)
        fields = suffix.split()
        parts = prefix.split()
        if len(fields) < 2 or len(parts) < 5:
            continue
        fstype, device = fields[0], fields[1]
        if fstype in PSEUDO_FILESYSTEMS or fstype in NETWORK_FILESYSTEMS:
            continue
        if fstype.startswith("fuse."):
            continue
        if device == "none" or device.startswith("loop") or device == "":
            continue
        mount_point = _unescape(parts[4])
        if not mount_point.startswith("/"):
            continue
        if device not in candidates:
            candidates[device] = []
            order.append(device)
        candidates[device].append((mount_point, fstype))
    rows = []
    for device in order:
        mount_point, fstype = min(
            candidates[device], key=lambda item: (item[0].count("/"), item[0])
        )
        if mount_point == "/":
            kind = "root"
        elif device.startswith("/dev/mapper/") or device.startswith("/dev/dm-"):
            kind = "internal"
        elif device.startswith("/dev/"):
            state = removable_reader(_linux_parent(device))
            if state == "1":
                kind = "removable"
            elif state == "0":
                kind = "internal"
            else:
                kind = "unknown"
        else:
            kind = "unknown"
        rows.append({
            "mountPoint": mount_point,
            "name": "",
            "device": device,
            "filesystem": fstype,
            "kind": kind,
        })
    return rows, ""


def _diskutil_info(device, runner=subprocess.run):
    """Fixed-argv ``diskutil info -plist`` probe; None when it does not answer."""
    try:
        result = runner(
            ["diskutil", "info", "-plist", device], shell=False, capture_output=True,
            timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = plistlib.loads(result.stdout)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def macos_rows(env=None, *, mount_output=None, diskutil_query=None, runner=subprocess.run):
    """Parse the ``mount`` probe output; classify disks through ``diskutil`` when it answers."""
    del env
    text = mount_output
    if text is None:
        try:
            result = runner(["mount"], shell=False, capture_output=True, text=True,
                            timeout=PROBE_TIMEOUT, stdin=subprocess.DEVNULL, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return [], "The macOS mount probe failed: {0}".format(exc)
        if result.returncode != 0:
            return [], "The macOS mount probe returned an error"
        text = result.stdout
    rows = []
    for line in text.splitlines():
        if " on " not in line or " (" not in line:
            continue
        device, rest = line.split(" on ", 1)
        mount_point_raw, tail = rest.rsplit(" (", 1)
        device = device.strip()
        mount_point = _unescape(mount_point_raw)
        flags = [flag.strip() for flag in tail.rstrip(")").split(",")]
        fstype = flags[0] if flags else ""
        if fstype in PSEUDO_FILESYSTEMS or fstype in NETWORK_FILESYSTEMS:
            continue
        if fstype.startswith("fuse."):
            continue
        if device in ("devfs", "map auto_home", "") or device.startswith("map "):
            continue
        if not mount_point.startswith("/"):
            continue
        if mount_point == "/":
            kind = "root"
        else:
            data = diskutil_query(device) if diskutil_query is not None else _diskutil_info(device, runner=runner)
            if data is None:
                kind = "unknown"
            elif data.get("Internal") is True:
                kind = "internal"
            elif data.get("Internal") is False:
                kind = "removable"
            else:
                kind = "unknown"
        rows.append({
            "mountPoint": mount_point,
            "name": "",
            "device": device,
            "filesystem": fstype,
            "kind": kind,
        })
    return rows, ""


def _windows_drive_query(env):
    """kernel32 enumeration: one row per drive letter, or None when unavailable."""
    del env
    try:
        kernel32 = ctypes.windll.kernel32
        bitmask = int(kernel32.GetLogicalDrives())
    except (AttributeError, OSError, ValueError):
        return None
    drives = []
    for index in range(26):
        if not (bitmask >> index) & 1:
            continue
        letter = chr(ord("A") + index)
        root = letter + ":\\"
        try:
            drive_type = int(kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
            label = ctypes.create_unicode_buffer(261)
            filesystem = ctypes.create_unicode_buffer(64)
            ok = bool(kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root), label, 261, None, None, None, filesystem, 64,
            ))
        except (AttributeError, OSError, ValueError):
            return None
        drives.append({
            "letter": letter,
            "type": drive_type,
            "label": label.value if ok else "",
            "filesystem": filesystem.value if ok else "",
        })
    return drives


def windows_rows(env=None, *, drive_query=None):
    """Enumerate fixed and removable drives; remote, optical, ram and unknown types hide."""
    env = os.environ if env is None else env
    query = drive_query if drive_query is not None else _windows_drive_query
    drives = query(env)
    if drives is None:
        return [], "Windows drive enumeration is not available on this host"
    root_prefix = ntpath.splitdrive(env.get("SystemRoot") or "C:\\Windows")[0].upper()
    rows = []
    for drive in drives:
        letter = str(drive.get("letter", "")).upper()
        if not letter:
            continue
        drive_type = drive.get("type")
        if drive_type in (DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOTE,
                          DRIVE_CDROM, DRIVE_RAMDISK):
            continue
        if drive_type == DRIVE_REMOVABLE:
            kind = "removable"
        elif drive_type == DRIVE_FIXED:
            kind = "internal"
        else:
            continue
        prefix = letter + ":"
        rows.append({
            "mountPoint": prefix + "\\",
            "name": drive.get("label") or "",
            "device": prefix,
            "filesystem": drive.get("filesystem") or "",
            "kind": "root" if prefix == root_prefix else kind,
        })
    return rows, ""


def _collect_rows(platform, env=None):
    if platform == "linux":
        return linux_rows(env)
    if platform == "macos":
        return macos_rows(env)
    if platform == "windows":
        return windows_rows(env)
    return [], "{0} is not a supported platform".format(platform)


def _home_volume_mount(volumes, home, platform):
    """The mount point of the volume that holds ``home`` (longest prefix wins)."""
    if not home:
        return None
    pathmod = ntpath if platform == "windows" else posixpath
    target = pathmod.normcase(pathmod.normpath(home))
    best = None
    best_length = -1
    for volume in volumes:
        prefix = pathmod.normcase(pathmod.normpath(volume["mountPoint"]))
        if not prefix:
            continue
        if prefix.endswith(pathmod.sep):
            matches = target.startswith(prefix)
        else:
            matches = target == prefix or target.startswith(prefix + pathmod.sep)
        if matches and len(prefix) > best_length:
            best, best_length = volume["mountPoint"], len(prefix)
    return best


def _capacity(mount_point):
    usage = shutil.disk_usage(mount_point)
    return usage.total, usage.free


def inventory(platform=None, env=None, *, rows=None, usage_fn=None, home=None,
              clock=time.time):
    """The typed payload behind ``GET /api/cleanup/volumes`` and ``labctl cleanup volumes``.

    Read-only: rows come from the platform's mount table and every capacity
    number from :func:`shutil.disk_usage`. ``rows`` and ``usage_fn`` are the
    test seams — fake mount tables, fake disks, never a real volume.
    """
    platform = platform or paths.platform_id()
    env = os.environ if env is None else env
    error = None
    if rows is None:
        rows, error = _collect_rows(platform, env=env)
    home = home or paths.home_dir(env)
    volumes = []
    warnings = []
    for row in sorted(rows, key=lambda item: item["mountPoint"].lower()):
        mount_point = row["mountPoint"]
        total = free = None
        measure_error = None
        try:
            measure = usage_fn(mount_point) if usage_fn is not None else _capacity(mount_point)
            total, free = int(measure[0]), int(measure[1])
        except OSError as exc:
            measure_error = str(exc)
        used = total - free if total is not None and free is not None else None
        usage = (used / total) if total else None
        pressure = "ok"
        if usage is not None and usage > PRESSURE_THRESHOLD:
            pressure = "warning"
            warnings.append("Volume {0} is {1:.0f}% full ({2} free).".format(
                mount_point, usage * 100, _format_bytes(free)))
        volumes.append({
            "mountPoint": mount_point,
            "name": row.get("name") or "",
            "device": row.get("device") or "",
            "filesystem": row.get("filesystem") or "",
            "kind": row.get("kind") or "unknown",
            "totalBytes": total,
            "freeBytes": free,
            "usedBytes": used,
            "usage": usage,
            "isHome": False,
            "pressure": pressure,
            "error": measure_error,
        })
    home_volume = _home_volume_mount(volumes, home, platform)
    if home_volume is not None:
        for volume in volumes:
            if volume["mountPoint"] == home_volume:
                volume["isHome"] = True
    return {
        "platform": platform,
        "checkedAt": clock(),
        "threshold": PRESSURE_THRESHOLD,
        "homeVolume": home_volume,
        "error": error,
        "volumes": volumes,
        "warnings": warnings,
    }
