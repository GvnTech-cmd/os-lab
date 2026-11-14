"""CLN-06 developer catalog fixtures use a fake home and fake binaries."""
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cleanup_lab import catalog, clean  # noqa: E402

ROOT = str(pathlib.Path(__file__).resolve().parents[3])


class DeveloperDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cln-dev-")
        self.base = pathlib.Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.env = {"HOME": str(self.home), "PATH": str(self.bin),
                    "XDG_CACHE_HOME": str(self.home / "xdg-cache"),
                    "LOCALAPPDATA": "C:\\Users\\Ada\\AppData\\Local",
                    "APPDATA": "C:\\Users\\Ada\\AppData\\Roaming",
                    "USERPROFILE": "C:\\Users\\Ada"}
        self.entries = {item["id"]: item for item in catalog.load(ROOT, self.env)}

    def tearDown(self):
        self.temp.cleanup()

    def test_fake_path_detects_binary_without_running_shell(self):
        fake = self.bin / "npm"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
        result = catalog.report(ROOT, platform="linux", env=self.env)
        by_id = {item["id"]: item for item in result["entries"]}
        self.assertTrue(by_id["developers.npm"]["toolPresent"])
        self.assertFalse(by_id["developers.pnpm"]["toolPresent"])
        self.assertIsNone(by_id["developers.nvm"]["toolPresent"])

    def test_paths_follow_each_os_and_xdg_cache(self):
        self.assertEqual(catalog.resolve(self.entries["developers.pip"], "linux", self.env)[0]["path"],
                         str(self.home / "xdg-cache" / "pip"))
        self.assertEqual(catalog.resolve(self.entries["developers.pip"], "macos", self.env)[0]["path"],
                         str(self.home / "Library" / "Caches" / "pip"))
        self.assertEqual(catalog.resolve(self.entries["developers.pip"], "windows", self.env)[0]["path"],
                         "C:\\Users\\Ada\\AppData\\Local\\pip\\Cache")
        self.assertEqual(catalog.resolve(self.entries["developers.rustup"], "linux", self.env)[0]["path"],
                         str(self.home / ".rustup" / "toolchains"))

    def test_credentials_and_toolchains_are_not_default_cleanable(self):
        for key in ("gh", "aws", "gcloud", "azure", "k9s"):
            item = self.entries["developers." + key]
            self.assertEqual(item["risk"], "credentials")
            self.assertFalse(item["defaultSelected"])
        for key in ("nvm", "pyenv", "rbenv", "rustup", "virtualenvwrapper", "minikube"):
            item = self.entries["developers." + key]
            self.assertFalse(item["cleanable"])
            plan = clean.build_plan(ROOT, [item["id"]], env=self.env, platform="linux",
                                    catalog_entries=[item])
            self.assertEqual(plan.payload["items"][0]["code"], "not-cleanable")


if __name__ == "__main__":
    unittest.main()
