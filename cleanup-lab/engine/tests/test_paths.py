import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import paths  # noqa: E402


class PlatformTest(unittest.TestCase):
    def test_maps_the_supported_platforms(self):
        self.assertEqual(paths.platform_id("darwin"), "macos")
        self.assertEqual(paths.platform_id("linux"), "linux")
        self.assertEqual(paths.platform_id("win32"), "windows")
        self.assertEqual(paths.platform_id("aix"), "unsupported")

    def test_home_prefers_home_then_userprofile(self):
        self.assertEqual(paths.home_dir({"HOME": "/home/ada"}), "/home/ada")
        self.assertEqual(paths.home_dir({"USERPROFILE": "C:/Users/ada"}), os.path.abspath("C:/Users/ada"))

    def test_state_folder_per_platform(self):
        env = {"HOME": "/home/ada"}
        self.assertEqual(
            paths.state_dir(dict(env, XDG_STATE_HOME="/state"), "linux"),
            "/state/os-lab/cleanup",
        )
        self.assertEqual(
            paths.state_dir(env, "linux"), "/home/ada/.local/state/os-lab/cleanup"
        )
        self.assertEqual(
            paths.state_dir(env, "macos"),
            "/home/ada/Library/Application Support/os-lab/cleanup",
        )
        self.assertEqual(
            paths.state_dir(dict(env, LOCALAPPDATA="C:/Local"), "windows"),
            os.path.join("C:/Local", "os-lab", "cleanup"),
        )

    def test_state_folder_override(self):
        env = {"HOME": "/home/ada", "OSLAB_CLEANUP_STATE": "/tmp/cleanup-state"}
        self.assertEqual(paths.state_dir(env, "macos"), "/tmp/cleanup-state")

    def test_trash_per_platform(self):
        env = {"HOME": "/home/ada"}
        self.assertEqual(paths.trash_dir(env, "macos"), "/home/ada/.Trash")
        self.assertEqual(paths.trash_dir(env, "linux"), "/home/ada/.local/share/Trash")
        self.assertEqual(
            paths.trash_dir(dict(env, XDG_DATA_HOME="/data"), "linux"), "/data/Trash"
        )
        self.assertIsNone(paths.trash_dir(env, "windows"))


class WritableTest(unittest.TestCase):
    def test_existing_folder_is_writable(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertTrue(paths.is_writable_dir(os.path.join(home, "a", "b")))

    def test_file_is_not_a_writable_folder(self):
        with tempfile.NamedTemporaryFile() as handle:
            self.assertFalse(paths.is_writable_dir(os.path.join(handle.name, "x")))

    def test_relative_xdg_values_are_ignored(self):
        env = {"HOME": "/home/ada", "XDG_STATE_HOME": "relative/state", "XDG_DATA_HOME": "relative/data"}
        self.assertEqual(paths.state_dir(env, "linux"), "/home/ada/.local/state/os-lab/cleanup")
        self.assertEqual(paths.trash_dir(env, "linux"), "/home/ada/.local/share/Trash")

    def test_dangling_symlink_is_the_existing_component(self):
        with tempfile.TemporaryDirectory() as base:
            link = os.path.join(base, "dangling")
            os.symlink(os.path.join(base, "missing"), link)
            self.assertEqual(paths.nearest_existing(os.path.join(link, "state")), link)
            self.assertFalse(paths.is_writable_dir(os.path.join(link, "state")))

    def test_private_folder_check(self):
        with tempfile.TemporaryDirectory() as base:
            private = os.path.join(base, "private")
            os.makedirs(private)
            os.chmod(private, 0o700)
            self.assertTrue(paths.is_private_dir(private))
            os.chmod(private, 0o755)
            self.assertFalse(paths.is_private_dir(private))
            self.assertTrue(paths.is_private_dir(os.path.join(base, "missing")))

    def test_missing_chain_climbs_to_the_existing_parent(self):
        with tempfile.TemporaryDirectory() as base:
            target = os.path.join(base, "a", "b", "c")
            self.assertEqual(paths.nearest_existing(target), base)


if __name__ == "__main__":
    unittest.main()
