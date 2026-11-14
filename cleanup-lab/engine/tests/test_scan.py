"""CLN-03 scan tests: sizes from lstat only, symlinks never followed, hard links
counted once, unreadable paths reported, cancel honoured mid-walk.

Every test builds a generated tree under ``tempfile``; nothing reads a real
user folder (rule 8).
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from cleanup_lab import scan  # noqa: E402

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def make_entry(entry_id, paths, **overrides):
    entry = {
        "id": entry_id,
        "name": entry_id,
        "family": entry_id.split(".")[0],
        "category": "system",
        "risk": "low",
        "hint": "hint",
        "impact": "impact",
        "defaultSelected": True,
        "needsPrivilege": False,
        "owningProcesses": [],
        "detector": "paths",
        "paths": paths,
    }
    entry.update(overrides)
    return entry


class FlipAfter:
    """A cancel flag that flips to True after N polls — a deterministic mid-walk cancel."""

    def __init__(self, polls):
        self.polls = polls

    def is_set(self):
        self.polls -= 1
        return self.polls < 0


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cln-scan-")
        self.home = self.tmp.name
        self.env = {"HOME": self.home, "USERPROFILE": self.home}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, size):
        target = os.path.join(self.home, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(b"x" * size)
        return target

    def result_for(self, entry, **kwargs):
        return scan.scan_catalog(
            None,
            [entry["id"]],
            env=self.env,
            platform="macos",
            catalog_entries=[entry],
            **kwargs,
        )

    def test_sizes_and_counts_from_a_generated_tree(self):
        self.write("Library/Caches/app/one.bin", 100)
        self.write("Library/Caches/app/two.bin", 50)
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        result = self.result_for(entry)
        self.assertFalse(result["cancelled"])
        path_report = result["entries"][0]["paths"][0]
        self.assertTrue(path_report["measured"])
        self.assertEqual(path_report["sizeBytes"], 150)
        self.assertEqual(path_report["files"], 2)
        # the folder itself plus app/ are both counted
        self.assertEqual(path_report["folders"], 2)
        self.assertEqual(result["totals"]["sizeBytes"], 150)
        self.assertEqual(result["entries"][0]["sizeBytes"], 150)
        self.assertIsNotNone(path_report["sizeOnDiskBytes"])
        self.assertEqual(result["progress"]["phase"], "done")

    def test_symlink_inside_the_tree_is_never_followed_or_counted(self):
        real = self.write("Library/Caches/app/data.bin", 100)
        os.symlink(real, os.path.join(self.home, "Library/Caches/app/link.bin"))
        os.symlink(
            os.path.join(self.home, "Library/Caches/app"),
            os.path.join(self.home, "Library/Caches/link-dir"),
        )
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        result = self.result_for(entry)
        path_report = result["entries"][0]["paths"][0]
        self.assertEqual(path_report["sizeBytes"], 100)
        self.assertEqual(path_report["files"], 1)

    def test_symlink_loop_terminates(self):
        self.write("Library/Caches/app/data.bin", 10)
        # a loop: app/up -> Library/Caches, and Caches/root -> the home folder
        os.symlink(
            os.path.join(self.home, "Library/Caches"),
            os.path.join(self.home, "Library/Caches/app/up"),
        )
        os.symlink(self.home, os.path.join(self.home, "root"))
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        result = self.result_for(entry)
        self.assertFalse(result["cancelled"])
        self.assertEqual(result["entries"][0]["sizeBytes"], 10)

    def test_top_level_symlink_is_reported_not_walked(self):
        self.write("real/data.bin", 40)
        os.symlink(os.path.join(self.home, "real"), os.path.join(self.home, "link"))
        entry = make_entry("system.caches", {"macos": ["~/link"]})
        result = self.result_for(entry)
        path_report = result["entries"][0]["paths"][0]
        self.assertTrue(path_report["symlink"])
        self.assertFalse(path_report["measured"])
        self.assertIn("never followed", path_report["reason"])
        self.assertEqual(path_report["sizeBytes"], 0)

    def test_hard_links_count_once_across_paths(self):
        first = self.write("Library/Caches/a/data.bin", 100)
        os.makedirs(os.path.join(self.home, "Library/Logs"), exist_ok=True)
        os.link(first, os.path.join(self.home, "Library/Logs/data.bin"))
        entries = [
            make_entry("system.caches", {"macos": ["~/Library/Caches"]}),
            make_entry("system.logs", {"macos": ["~/Library/Logs"]}),
        ]
        result = scan.scan_catalog(
            None, None, env=self.env, platform="macos", catalog_entries=entries
        )
        by_id = {e["id"]: e["sizeBytes"] for e in result["entries"]}
        # Whichever worker sees it first owns the bytes; the scan counts it once.
        self.assertEqual(sum(by_id.values()), 100)
        self.assertEqual(result["totals"]["sizeBytes"], 100)

    @unittest.skipIf(sys.platform == "win32" or os.geteuid() == 0, "needs a non-root POSIX user")
    def test_permission_denied_directory_is_reported_not_fatal(self):
        self.write("Library/Caches/ok/data.bin", 30)
        blocked = os.path.join(self.home, "Library/Caches/blocked")
        os.makedirs(blocked)
        self.write("Library/Caches/blocked/hidden.bin", 500)
        os.chmod(blocked, 0o000)
        try:
            entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
            result = self.result_for(entry)
        finally:
            os.chmod(blocked, 0o755)
        path_report = result["entries"][0]["paths"][0]
        self.assertTrue(path_report["measured"])
        self.assertEqual(path_report["sizeBytes"], 30)
        self.assertIn(blocked, path_report["unreadable"])
        self.assertEqual(result["entries"][0]["unreadable"], [blocked])
        self.assertEqual(result["totals"]["unreadable"], 1)

    @unittest.skipIf(sys.platform == "win32", "POSIX permissions")
    def test_mode_zero_file_is_measured_because_lstat_never_opens_it(self):
        """The scan reads metadata only: a file nobody may read is still sized."""
        self.write("Library/Caches/ok/data.bin", 30)
        self.write("Library/Caches/ok/secret.bin", 900)
        secret = os.path.join(self.home, "Library/Caches/ok/secret.bin")
        os.chmod(secret, 0o000)
        try:
            entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
            result = self.result_for(entry)
        finally:
            os.chmod(secret, 0o644)
        path_report = result["entries"][0]["paths"][0]
        self.assertEqual(path_report["sizeBytes"], 930)
        self.assertEqual(path_report["unreadable"], [])

    def test_missing_path_reported_with_reason(self):
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        result = self.result_for(entry)
        path_report = result["entries"][0]["paths"][0]
        self.assertTrue(path_report["missing"])
        self.assertEqual(path_report["reason"], "The path does not exist.")
        self.assertEqual(path_report["sizeBytes"], 0)

    def test_unset_environment_variable_is_not_guessed(self):
        entry = make_entry("system.caches", {"macos": ["${CLN_UNSET_VAR}/cache"]})
        result = self.result_for(entry)
        path_report = result["entries"][0]["paths"][0]
        self.assertIsNone(path_report["path"])
        self.assertIn("CLN_UNSET_VAR", path_report["reason"])

    def test_entry_without_paths_for_platform(self):
        entry = make_entry("system.caches", {"linux": ["~/.cache"]})
        result = scan.scan_catalog(
            None, ["system.caches"], env=self.env, platform="macos", catalog_entries=[entry]
        )
        path_report = result["entries"][0]["paths"][0]
        self.assertIsNone(path_report["path"])
        self.assertEqual(path_report["reason"], "This entry has no path for this system.")

    def test_single_file_top_level_path(self):
        target = self.write("Library/Caches/one.bin", 77)
        entry = make_entry("system.caches", {"macos": [target]})
        result = self.result_for(entry)
        path_report = result["entries"][0]["paths"][0]
        self.assertTrue(path_report["measured"])
        self.assertEqual(path_report["sizeBytes"], 77)
        self.assertEqual(path_report["files"], 1)

    def test_unknown_entry_id_is_refused(self):
        with self.assertRaises(scan.ScanError):
            scan.scan_catalog(REPO_ROOT, ["nope.entry"], env=self.env, platform="macos")

    def test_workers_bounds_are_enforced(self):
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        for bad in (0, -1, scan.MAX_WORKERS + 1):
            with self.assertRaises(scan.ScanError):
                self.result_for(entry, workers=bad)

    def test_cancel_mid_walk_returns_partial_honest_result(self):
        for index in range(6):
            self.write("Library/Caches/d{0}/f.bin".format(index), 10)
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        cancel = FlipAfter(3)
        result = self.result_for(entry, cancel=cancel, workers=1)
        self.assertTrue(result["cancelled"])
        path_report = result["entries"][0]["paths"][0]
        self.assertFalse(path_report["measured"])
        self.assertIn("cancelled", path_report["reason"])
        # partial bytes are still reported, never invented
        self.assertLessEqual(path_report["sizeBytes"], 60)
        self.assertEqual(result["progress"]["phase"], "cancelled")

    def test_cancel_before_start_skips_everything(self):
        self.write("Library/Caches/data.bin", 10)
        entry = make_entry("system.caches", {"macos": ["~/Library/Caches"]})
        import threading

        cancel = threading.Event()
        cancel.set()
        result = self.result_for(entry, cancel=cancel, workers=1)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["entries"][0]["sizeBytes"], 0)

    def test_progress_reports_paths_and_never_blocks(self):
        self.write("Library/Caches/a.bin", 10)
        self.write("Library/Logs/b.log", 20)
        entries = [
            make_entry("system.caches", {"macos": ["~/Library/Caches"]}),
            make_entry("system.logs", {"macos": ["~/Library/Logs"]}),
        ]
        seen = []
        result = scan.scan_catalog(
            None,
            None,
            env=self.env,
            platform="macos",
            catalog_entries=entries,
            progress_callback=seen.append,
        )
        self.assertFalse(result["cancelled"])
        final = result["progress"]
        self.assertEqual(final["pathsDone"], 2)
        self.assertEqual(final["pathsTotal"], 2)
        for payload in seen:
            self.assertEqual(
                sorted(payload),
                ["bytesSeen", "currentPath", "filesSeen", "pathsDone", "pathsTotal", "phase"],
            )

    def test_parallel_workers_agree_with_one_worker(self):
        self.write("Library/Caches/d1/f.bin", 100)
        self.write("Library/Caches/d2/f.bin", 200)
        self.write("Library/Logs/g.log", 50)
        entries = [
            make_entry("system.caches", {"macos": ["~/Library/Caches"]}),
            make_entry("system.logs", {"macos": ["~/Library/Logs"]}),
        ]
        one = scan.scan_catalog(
            None, None, env=self.env, platform="macos", catalog_entries=entries, workers=1
        )
        many = scan.scan_catalog(
            None, None, env=self.env, platform="macos", catalog_entries=entries, workers=4
        )
        self.assertEqual(one["totals"]["sizeBytes"], many["totals"]["sizeBytes"])
        self.assertEqual(one["totals"]["files"], many["totals"]["files"])

    @unittest.skipIf(sys.platform == "win32", "POSIX FIFOs")
    def test_fifo_has_nothing_to_reclaim_and_is_not_measured(self):
        fifo = os.path.join(self.home, "Library/Caches/pipe")
        os.makedirs(os.path.dirname(fifo), exist_ok=True)
        os.mkfifo(fifo)
        entry = make_entry("system.caches", {"macos": [fifo]})
        result = self.result_for(entry)
        path_report = result["entries"][0]["paths"][0]
        self.assertFalse(path_report["measured"])
        self.assertIn("nothing was measured", path_report["reason"])
        self.assertEqual(path_report["files"], 0)

    def test_shipped_catalog_scans_against_a_fake_home(self):
        """End to end with the real catalog files: HOME is the generated tree."""
        os.makedirs(os.path.join(self.home, "Library/Caches/app"), exist_ok=True)
        with open(os.path.join(self.home, "Library/Caches/app/x.bin"), "wb") as handle:
            handle.write(b"y" * 25)
        result = scan.scan_catalog(
            REPO_ROOT, ["system.user-caches"], env=self.env, platform="macos"
        )
        self.assertEqual(result["entries"][0]["id"], "system.user-caches")
        self.assertEqual(result["entries"][0]["sizeBytes"], 25)
        self.assertGreaterEqual(result["totals"]["sizeBytes"], 25)


if __name__ == "__main__":
    unittest.main()
