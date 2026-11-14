"""CLN-28: the volume inventory.

Fake mount tables and fake disks only — the tests never touch a real volume
(cleanup-lab/README.md rule 8). The collector seams (``mountinfo_text``,
``mount_output``, ``drive_query``, ``diskutil_query``) and the aggregation seams
(``rows``, ``usage_fn``) carry every platform difference, so these tests pass on
any host.
"""
import io
import json
import os
import plistlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import cli, volumes  # noqa: E402


LINUX_MOUNTINFO = "\n".join([
    "22 1 0:21 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p4 rw,errors=remount-ro",
    "24 22 0:24 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sysfs rw",
    "25 22 0:25 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw",
    "26 22 0:26 / /dev rw,nosuid - devtmpfs udev rw",
    "27 22 0:27 / /run rw,nosuid - tmpfs tmpfs rw",
    "36 22 0:36 / /sys/fs/cgroup rw - cgroup2 cgroup2 rw",
    "32 22 0:32 /var/lib/docker/x/merged /var/lib/docker rw - overlay overlay rw",
    "33 22 0:33 / /snap/core20 ro - squashfs /dev/loop3 ro",
    "28 22 0:28 / /home rw,relatime - ext4 /dev/nvme0n1p4 rw",
    "31 22 0:31 /sub /mnt/bind rw - ext4 /dev/nvme0n1p4 rw",
    "29 22 0:29 /mnt/data /mnt/data rw - ext4 /dev/sdb1 rw",
    "30 22 0:30 /export /mnt/nas rw - nfs4 192.168.1.10:/export rw",
    "37 22 0:37 /share /mnt/remote rw - cifs //server/share rw",
    "38 22 0:38 / /mnt/my\\040docs rw - ext4 /dev/nvme0n1p5 rw",
    "35 22 0:35 / /mnt/secure rw - ext4 /dev/mapper/secure rw",
]) + "\n"

MACOS_MOUNT = "\n".join([
    "/dev/disk3s1s1 on / (apfs, local, journaled)",
    "devfs on /dev (devfs, local, nobrowse)",
    "map auto_home on /System/Volumes/Data/home (autofs, automounted, nobrowse)",
    "/dev/disk3s4 on /Volumes/Preboot (apfs, local, journaled)",
    "/dev/disk4s1 on /Volumes/Backup\\040Disk (apfs, local, journaled)",
    "/dev/disk5s1 on /Volumes/Unknown (apfs, local)",
    "server:/export on /mnt/nas (nfs)",
]) + "\n"


class LinuxRowsTest(unittest.TestCase):
    def test_pseudo_network_and_loop_types_are_filtered(self):
        rows, error = volumes.linux_rows(mountinfo_text=LINUX_MOUNTINFO, removable_reader=lambda disk: "0")
        self.assertEqual(error, "")
        self.assertEqual(
            sorted(row["mountPoint"] for row in rows),
            ["/", "/mnt/data", "/mnt/my docs", "/mnt/secure"],
        )

    def test_one_device_is_listed_once_at_its_shortest_mount_point(self):
        rows, _ = volumes.linux_rows(mountinfo_text=LINUX_MOUNTINFO, removable_reader=lambda disk: "0")
        roots = [row for row in rows if row["device"] == "/dev/nvme0n1p4"]
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["mountPoint"], "/")

    def test_kind_classification_uses_sys_block(self):
        seen = []
        def reader(disk):
            seen.append(disk)
            return {"nvme0n1": "0", "sdb": "1"}.get(disk)
        rows, _ = volumes.linux_rows(mountinfo_text=LINUX_MOUNTINFO, removable_reader=reader)
        kinds = {row["mountPoint"]: row["kind"] for row in rows}
        self.assertEqual(kinds["/"], "root")
        self.assertEqual(kinds["/mnt/my docs"], "internal")
        self.assertEqual(kinds["/mnt/data"], "removable")
        self.assertEqual(kinds["/mnt/secure"], "internal")  # device mapper, no reader call
        self.assertNotIn("mmcblk", seen)

    def test_unknown_sys_block_state_is_reported_honestly(self):
        rows, _ = volumes.linux_rows(mountinfo_text=LINUX_MOUNTINFO, removable_reader=lambda disk: None)
        kinds = {row["mountPoint"]: row["kind"] for row in rows}
        self.assertEqual(kinds["/mnt/data"], "unknown")

    def test_a_missing_mount_table_is_an_error_not_a_crash(self):
        def broken():
            raise OSError("permission denied")
        rows, error = volumes.linux_rows(mountinfo_text=None, mountinfo_reader=broken)
        self.assertEqual(rows, [])
        self.assertIn("Could not read the Linux mount table", error)
        self.assertIn("permission denied", error)


class MacOSRowsTest(unittest.TestCase):
    def test_pseudo_and_network_mounts_are_filtered(self):
        rows, error = volumes.macos_rows(mount_output=MACOS_MOUNT, diskutil_query=lambda device: None)
        self.assertEqual(error, "")
        self.assertEqual(
            sorted(row["mountPoint"] for row in rows),
            ["/", "/Volumes/Backup Disk", "/Volumes/Preboot", "/Volumes/Unknown"],
        )

    def test_diskutil_answers_decide_the_kind(self):
        answers = {
            "/dev/disk3s4": {"Internal": True},
            "/dev/disk4s1": {"Internal": False},
        }
        rows, _ = volumes.macos_rows(mount_output=MACOS_MOUNT, diskutil_query=answers.get)
        kinds = {row["mountPoint"]: row["kind"] for row in rows}
        self.assertEqual(kinds["/"], "root")
        self.assertEqual(kinds["/Volumes/Preboot"], "internal")
        self.assertEqual(kinds["/Volumes/Backup Disk"], "removable")
        self.assertEqual(kinds["/Volumes/Unknown"], "unknown")

    def test_escaped_mount_points_are_decoded(self):
        rows, _ = volumes.macos_rows(mount_output=MACOS_MOUNT, diskutil_query=lambda device: None)
        self.assertIn("/Volumes/Backup Disk", [row["mountPoint"] for row in rows])

    def test_a_failed_mount_probe_is_an_error_not_a_crash(self):
        class Boom(Exception):
            pass
        def broken(argv, **kwargs):
            raise OSError("disk arbitration is busy")
        rows, error = volumes.macos_rows(mount_output=None, runner=broken)
        self.assertEqual(rows, [])
        self.assertIn("mount probe failed", error)
        self.assertIn("disk arbitration is busy", error)

    def test_diskutil_probe_through_the_real_runner_path(self):
        output = plistlib.dumps({"Internal": True})
        class Result:
            returncode = 0
            stdout = output
        calls = []
        def runner(argv, **kwargs):
            calls.append(list(argv))
            return Result()
        rows, _ = volumes.macos_rows(mount_output=MACOS_MOUNT, runner=runner)
        self.assertTrue(all(argv[0] == "diskutil" and argv[1:3] == ["info", "-plist"] for argv in calls))
        self.assertEqual({row["mountPoint"]: row["kind"] for row in rows}["/Volumes/Preboot"], "internal")


class WindowsRowsTest(unittest.TestCase):
    DRIVES = [
        {"letter": "C", "type": volumes.DRIVE_FIXED, "label": "Windows", "filesystem": "NTFS"},
        {"letter": "D", "type": volumes.DRIVE_REMOVABLE, "label": "USB", "filesystem": "exFAT"},
        {"letter": "E", "type": volumes.DRIVE_REMOTE, "label": "NAS", "filesystem": "NTFS"},
        {"letter": "F", "type": volumes.DRIVE_CDROM, "label": "", "filesystem": "CDFS"},
        {"letter": "G", "type": volumes.DRIVE_RAMDISK, "label": "", "filesystem": "NTFS"},
        {"letter": "H", "type": volumes.DRIVE_UNKNOWN, "label": "", "filesystem": ""},
    ]

    def test_only_fixed_and_removable_drives_survive(self):
        rows, error = volumes.windows_rows(drive_query=lambda env: self.DRIVES)
        self.assertEqual(error, "")
        self.assertEqual([row["mountPoint"] for row in rows], ["C:\\", "D:\\"])
        self.assertEqual(rows[0]["filesystem"], "NTFS")
        self.assertEqual(rows[0]["name"], "Windows")

    def test_the_system_root_drive_is_the_root_volume(self):
        rows, _ = volumes.windows_rows(
            env={"SystemRoot": "D:\\Windows"}, drive_query=lambda env: self.DRIVES
        )
        kinds = {row["mountPoint"]: row["kind"] for row in rows}
        self.assertEqual(kinds["D:\\"], "root")
        self.assertEqual(kinds["C:\\"], "internal")

    def test_a_failed_enumeration_is_an_error_not_a_crash(self):
        rows, error = volumes.windows_rows(drive_query=lambda env: None)
        self.assertEqual(rows, [])
        self.assertIn("Windows drive enumeration is not available", error)


class InventoryTest(unittest.TestCase):
    ROWS = [
        {"mountPoint": "/home", "name": "", "device": "/dev/nvme0n1p3", "filesystem": "ext4", "kind": "internal"},
        {"mountPoint": "/", "name": "", "device": "/dev/nvme0n1p4", "filesystem": "ext4", "kind": "root"},
        {"mountPoint": "/mnt/data", "name": "DATA", "device": "/dev/sdb1", "filesystem": "ext4", "kind": "removable"},
    ]

    def test_home_volume_is_the_longest_prefix(self):
        report = volumes.inventory(
            platform="linux", rows=self.ROWS, usage_fn=lambda mp: (1000, 500), home="/home/ada/x"
        )
        self.assertEqual(report["homeVolume"], "/home")
        homes = {row["mountPoint"]: row["isHome"] for row in report["volumes"]}
        self.assertTrue(homes["/home"])
        self.assertFalse(homes["/"])

    def test_checked_at_comes_from_the_clock(self):
        report = volumes.inventory(platform="linux", rows=self.ROWS, usage_fn=lambda mp: (1000, 500),
                                   clock=lambda: 123.5)
        self.assertEqual(report["checkedAt"], 123.5)

    def test_usage_math_and_pressure_warning(self):
        def usage_fn(mount_point):
            return (1000, 70) if mount_point == "/" else (1000, 500)
        report = volumes.inventory(
            platform="linux", rows=self.ROWS, usage_fn=usage_fn, home="/home"
        )
        self.assertEqual(report["threshold"], volumes.PRESSURE_THRESHOLD)
        by_mount = {row["mountPoint"]: row for row in report["volumes"]}
        self.assertEqual(by_mount["/"]["usedBytes"], 930)
        self.assertEqual(by_mount["/"]["usage"], 0.93)
        self.assertEqual(by_mount["/"]["pressure"], "warning")
        self.assertTrue(any("93% full" in text for text in report["warnings"]))
        self.assertEqual(by_mount["/mnt/data"]["pressure"], "ok")

    def test_an_unreadable_volume_carries_its_error_and_no_bytes(self):
        def usage_fn(mount_point):
            if mount_point == "/mnt/data":
                raise OSError("disk gone")
            return 1000, 500
        report = volumes.inventory(platform="linux", rows=self.ROWS, usage_fn=usage_fn, home="/home")
        data = {row["mountPoint"]: row for row in report["volumes"]}["/mnt/data"]
        self.assertIn("disk gone", data["error"])
        self.assertIsNone(data["totalBytes"])
        self.assertIsNone(data["usage"])
        self.assertEqual(data["pressure"], "ok")
        self.assertEqual(report["warnings"], [])

    def test_home_matching_is_case_insensitive_on_windows(self):
        rows = [
            {"mountPoint": "C:\\", "name": "Win", "device": "C:", "filesystem": "NTFS", "kind": "root"},
            {"mountPoint": "D:\\", "name": "Data", "device": "D:", "filesystem": "NTFS", "kind": "internal"},
        ]
        report = volumes.inventory(platform="windows", rows=rows, usage_fn=lambda mp: (100, 50),
                                   home="c:\\users\\ada")
        self.assertEqual(report["homeVolume"], "C:\\")
        self.assertTrue({row["mountPoint"]: row["isHome"] for row in report["volumes"]}["C:\\"])

    def test_no_home_volume_when_nothing_matches(self):
        report = volumes.inventory(platform="linux", rows=[self.ROWS[2]],
                                   usage_fn=lambda mp: (100, 50), home="/home/ada")
        self.assertIsNone(report["homeVolume"])
        self.assertTrue(all(not row["isHome"] for row in report["volumes"]))

    def test_an_unsupported_platform_is_reported(self):
        report = volumes.inventory(platform="freebsd", usage_fn=lambda mp: (100, 50))
        self.assertEqual(report["volumes"], [])
        self.assertIn("not a supported platform", report["error"])

    def test_volumes_are_sorted_by_mount_point(self):
        report = volumes.inventory(platform="linux", rows=self.ROWS, usage_fn=lambda mp: (100, 50))
        mounts = [row["mountPoint"] for row in report["volumes"]]
        self.assertEqual(mounts, sorted(mounts))


class CliTest(unittest.TestCase):
    REPORT = {
        "platform": "linux",
        "checkedAt": 1.0,
        "threshold": 0.9,
        "homeVolume": "/",
        "error": None,
        "volumes": [
            {"mountPoint": "/", "name": "", "device": "/dev/sda1", "filesystem": "ext4",
             "kind": "root", "totalBytes": 1000, "freeBytes": 100, "usedBytes": 900,
             "usage": 0.9, "isHome": True, "pressure": "ok", "error": None},
            {"mountPoint": "/mnt/full", "name": "", "device": "/dev/sdb1", "filesystem": "ext4",
             "kind": "removable", "totalBytes": 1000, "freeBytes": 10, "usedBytes": 990,
             "usage": 0.99, "isHome": False, "pressure": "warning", "error": None},
        ],
        "warnings": ["Volume /mnt/full is 99% full (10 B free)."],
    }

    def run_cli(self, argv):
        stream = io.StringIO()
        with mock.patch.object(cli, "volumes") as fake:
            fake.inventory.return_value = self.REPORT
            code = cli.main(argv, stream=stream)
        return code, stream.getvalue()

    def test_volumes_prints_mount_kinds_and_pressure(self):
        code, text = self.run_cli(["volumes"])
        self.assertEqual(code, 0)
        self.assertIn("2 volumes", text)
        self.assertIn("/", text)
        self.assertIn("root", text)
        self.assertIn("99% used", text)
        self.assertIn("· home", text)
        self.assertIn("99% full", text)

    def test_volumes_json_is_machine_readable(self):
        code, text = self.run_cli(["volumes", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["homeVolume"], "/")

    def test_a_collection_error_is_a_problem_exit(self):
        report = dict(self.REPORT, error="Could not read the Linux mount table: no /proc")
        stream = io.StringIO()
        with mock.patch.object(cli, "volumes") as fake:
            fake.inventory.return_value = report
            code = cli.main(["volumes"], stream=stream)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
