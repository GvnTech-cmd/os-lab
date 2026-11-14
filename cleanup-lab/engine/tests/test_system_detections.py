"""CLN-04 system detector fixtures; no real user paths are scanned."""
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import catalog, scan, clean  # noqa: E402

ROOT = str(pathlib.Path(__file__).resolve().parents[3])


class SystemDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cln-system-")
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home), "TMPDIR": str(self.base / "temp"),
                    "XDG_CACHE_HOME": str(self.home / ".cache"),
                    "XDG_STATE_HOME": str(self.home / ".local" / "state")}
        self.entries = {entry["id"]: entry for entry in catalog.load(ROOT, self.env)}

    def tearDown(self):
        self.temp.cleanup()

    def test_temp_instances_skip_locks_sockets_small_files_and_symlinks(self):
        temporary = self.base / "temp"
        temporary.mkdir()
        (temporary / "large.bin").write_bytes(b"x" * 2048)
        (temporary / "small.bin").write_bytes(b"x" * 100)
        (temporary / "busy.lock").write_bytes(b"x" * 2048)
        (temporary / "service.pid").write_bytes(b"x" * 2048)
        (temporary / "cache-dir").mkdir()
        (temporary / "link").symlink_to(temporary / "large.bin")
        for platform in ("macos", "linux"):
            found = [row["path"] for row in catalog.resolve(self.entries["system.temp"], platform, self.env) if row["path"]]
            self.assertEqual(found, [str(temporary / "cache-dir"), str(temporary / "large.bin")])
            result = scan.scan_catalog(ROOT, ["system.temp"], env=self.env, platform=platform,
                                       catalog_entries=[self.entries["system.temp"]])
            self.assertEqual(result["totals"]["sizeBytes"], 2048)
            self.assertEqual(len([item for item in result["entries"][0]["paths"] if item["path"]]), 2)

    def test_system_paths_resolve_per_os(self):
        mac = {key: catalog.resolve(entry, "macos", self.env) for key, entry in self.entries.items()}
        linux = {key: catalog.resolve(entry, "linux", self.env) for key, entry in self.entries.items()}
        self.assertIn(str(self.home / "Library" / "Logs" / "DiagnosticReports"),
                      [row["path"] for row in mac["system.crash-reports"]])
        self.assertIn(str(self.home / ".cache" / "fontconfig"),
                      [row["path"] for row in linux["system.font-caches"]])
        self.assertEqual(linux["system.spotlight-index"], [])
        winenv = dict(self.env, LOCALAPPDATA="C:\\Users\\Ada\\AppData\\Local",
                      TEMP="C:\\Users\\Ada\\AppData\\Local\\Temp")
        for key in ("system.user-caches", "system.user-logs", "system.local-temp",
                    "system.crash-reports", "system.font-caches"):
            for template in self.entries[key]["paths"]["windows"]:
                path, reason = catalog.expand(template, "windows", winenv)
                self.assertTrue(path and path.startswith("C:"), (key, reason))
        self.assertNotIn("windows", self.entries["system.spotlight-index"]["paths"])

    def test_spotlight_finds_indexes_on_each_fixture_volume(self):
        volumes = self.base / "Volumes"
        for name in ("One", "Two"):
            (volumes / name / ".Spotlight-V100").mkdir(parents=True)
        (volumes / "NoIndex").mkdir()
        entry = dict(self.entries["system.spotlight-index"], paths={"macos": [str(volumes / "*" / ".Spotlight-V100")]})
        found = [row["path"] for row in catalog.resolve(entry, "macos", self.env)]
        self.assertEqual(found, [str(volumes / name / ".Spotlight-V100") for name in ("One", "Two")])
        self.assertTrue(entry["needsPrivilege"])
        self.assertFalse(entry["defaultSelected"])
        plan = clean.build_plan(ROOT, [entry["id"]], env=self.env, platform="macos",
                                catalog_entries=[entry])
        self.assertTrue(all(item["status"] == "skipped" and item["code"] == "privileged"
                            for item in plan.payload["items"]))


if __name__ == "__main__":
    unittest.main()
