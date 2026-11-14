"""CLN-05 profile enumeration and privacy fixtures in disposable homes."""
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import catalog, safety  # noqa: E402

ROOT = str(pathlib.Path(__file__).resolve().parents[3])


class BrowserDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cln-browser-")
        self.home = pathlib.Path(self.temp.name) / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home)}
        self.entries = {entry["id"]: entry for entry in catalog.load(ROOT, self.env)}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 2048)
        return path

    def test_chrome_enumerates_every_profile_and_keeps_history_private(self):
        for profile in ("Default", "Profile 1", "Guest Profile"):
            self.write(f"Library/Caches/Google/Chrome/{profile}/Cache/data.bin")
            self.write(f"Library/Application Support/Google/Chrome/{profile}/History")
            self.write(f"Library/Application Support/Google/Chrome/{profile}/Extension State/state.bin")
        caches = catalog.resolve(self.entries["browser.chrome.cache"], "macos", self.env)
        histories = catalog.resolve(self.entries["browser.chrome.history"], "macos", self.env)
        traces = catalog.resolve(self.entries["browser.chrome.extension-traces"], "macos", self.env)
        self.assertEqual(len([item for item in caches if item["path"].endswith("/Cache")]), 3)
        self.assertEqual(len(histories), 3)
        self.assertEqual(len(traces), 3)
        for item in (self.entries["browser.chrome.history"], self.entries["browser.chrome.extension-traces"]):
            self.assertEqual(item["risk"], "privacy")
            self.assertFalse(item["defaultSelected"])

    def test_firefox_profiles_and_running_process_lock(self):
        self.write("Library/Caches/Firefox/Profiles/ada.default/cache2/entries")
        self.write("Library/Caches/Firefox/Profiles/work.default-release/cache2/entries")
        entry = self.entries["browser.firefox.cache"]
        paths = [item["path"] for item in catalog.resolve(entry, "macos", self.env)]
        self.assertEqual(len(paths), 2)
        self.assertIn("firefox", entry["owningProcesses"])
        verdict = safety.check_target(paths[0], entry, env=self.env, platform="macos", names=["firefox"])
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, "app-running")

    def test_profile_symlink_cannot_escape_catalog_root(self):
        root = self.home / "Library/Caches/Firefox/Profiles"
        root.mkdir(parents=True)
        outside = self.home / "outside"
        outside.mkdir()
        (root / "evil.default").symlink_to(outside, target_is_directory=True)
        (outside / "cache2").mkdir()
        entry = self.entries["browser.firefox.cache"]
        candidate = catalog.resolve(entry, "macos", self.env)[0]["path"]
        verdict = safety.check_target(candidate, entry, env=self.env, platform="macos", names=[])
        self.assertFalse(verdict.ok)
        self.assertEqual(verdict.code, "outside-root")

    def test_each_browser_has_a_process_and_correct_os_templates(self):
        env = dict(self.env, LOCALAPPDATA="C:\\Users\\Ada\\AppData\\Local",
                   APPDATA="C:\\Users\\Ada\\AppData\\Roaming")
        for key in ("chrome", "edge", "brave", "opera", "vivaldi", "firefox"):
            entry = self.entries[f"browser.{key}.cache"]
            self.assertTrue(entry["owningProcesses"])
            for platform in ("macos", "linux", "windows"):
                self.assertTrue(entry["paths"][platform])
                for template in entry["paths"][platform]:
                    path, reason = catalog.expand(template, platform, env)
                    self.assertTrue(path, (key, platform, reason))
        self.assertEqual(set(self.entries["browser.safari.cache"]["paths"]), {"macos"})


if __name__ == "__main__":
    unittest.main()
