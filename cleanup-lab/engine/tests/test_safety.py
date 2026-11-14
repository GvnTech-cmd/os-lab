import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import catalog, paths, safety  # noqa: E402

ROOT = str(Path(__file__).resolve().parents[3])


def entry(root, *, processes=(), privileged=False, platform=None):
    return {
        "id": "system.demo",
        "needsPrivilege": privileged,
        "owningProcesses": list(processes),
        "paths": {platform or paths.platform_id(): [root]},
    }


class Tree:
    """A generated folder tree: one allowed root, one sibling, one symlink escape."""

    def __enter__(self):
        self.base = tempfile.mkdtemp()
        self.root = os.path.join(self.base, "caches")
        self.inside = os.path.join(self.root, "app")
        self.outside = os.path.join(self.base, "outside")
        self.sibling = os.path.join(self.base, "caches-old")
        for folder in (self.inside, self.outside, self.sibling):
            os.makedirs(folder)
        self.escape = os.path.join(self.root, "escape")
        os.symlink(self.outside, self.escape)
        self.secret = os.path.join(self.outside, "secret")
        open(self.secret, "w").close()
        self.odd_name = os.path.join(self.root, "a..b")
        os.makedirs(self.odd_name)
        return self

    def __exit__(self, *_):
        import shutil

        shutil.rmtree(self.base, ignore_errors=True)


class TargetTest(unittest.TestCase):
    def check(self, tree, path, **kwargs):
        return safety.check_target(path, entry(tree.root, **kwargs.pop("entry", {})), **kwargs)

    def test_a_path_inside_the_catalog_root_is_allowed(self):
        with Tree() as tree:
            verdict = self.check(tree, tree.inside)
            self.assertTrue(verdict.ok, verdict.reason)
            self.assertEqual(verdict.path, os.path.realpath(tree.inside))
            self.assertEqual(verdict.reason, "")

    def test_the_catalog_root_itself_is_allowed(self):
        with Tree() as tree:
            self.assertTrue(self.check(tree, tree.root).ok)

    def test_a_sibling_with_the_same_prefix_is_outside(self):
        with Tree() as tree:
            verdict = self.check(tree, tree.sibling)
            self.assertFalse(verdict.ok)
            self.assertIn("outside its catalog root", verdict.reason)

    def test_a_dot_dot_name_is_a_valid_name(self):
        # Qleaner's `contains("..")` refused this path; it is inside the root.
        with Tree() as tree:
            verdict = self.check(tree, tree.odd_name)
            self.assertTrue(verdict.ok, verdict.reason)

    def test_a_symlink_that_escapes_the_root_is_refused(self):
        with Tree() as tree:
            verdict = self.check(tree, tree.escape)
            self.assertFalse(verdict.ok)
            self.assertIn("symlink escape", verdict.reason)

    def test_protected_roots_are_refused(self):
        with Tree() as tree:
            for path in ("/", os.path.expanduser("~")):
                with self.subTest(path=path):
                    verdict = safety.check_target(path, entry("/"))
                    self.assertFalse(verdict.ok)
                    self.assertIn("protected root", verdict.reason)
                    self.assertEqual(verdict.code, "protected")

    def test_a_missing_path_is_reported(self):
        with Tree() as tree:
            verdict = self.check(tree, os.path.join(tree.inside, "gone"))
            self.assertFalse(verdict.ok)
            self.assertEqual(verdict.reason, "Path no longer exists.")

    def test_another_users_file_is_refused(self):
        with Tree() as tree:
            foreign = SimpleNamespace(st_uid=os.getuid() + 1)
            verdict = self.check(tree, tree.inside, lstat=lambda _p: foreign)
            self.assertFalse(verdict.ok)
            self.assertIn("another user account", verdict.reason)

    def test_a_running_owning_application_is_refused(self):
        with Tree() as tree:
            verdict = self.check(
                tree, tree.inside, names=("Google Chrome",), entry={"processes": ["Google Chrome"]}
            )
            self.assertFalse(verdict.ok)
            self.assertIn("Google Chrome", verdict.reason)

    def test_a_quiet_owning_application_does_not_block(self):
        with Tree() as tree:
            verdict = self.check(
                tree, tree.inside, names=("firefox",), entry={"processes": ["Google Chrome"]}
            )
            self.assertTrue(verdict.ok, verdict.reason)

    def test_privileged_entries_are_flagged_but_allowed(self):
        with Tree() as tree:
            verdict = self.check(tree, tree.inside, entry={"privileged": True})
            self.assertTrue(verdict.ok, verdict.reason)
            self.assertTrue(verdict.privileged)

    def test_an_entry_without_this_platform_is_refused(self):
        with Tree() as tree:
            other = "macos" if paths.platform_id() != "macos" else "linux"
            item = entry(tree.root, platform=other)
            verdict = safety.check_target(tree.inside, item)
            self.assertFalse(verdict.ok)
            self.assertIn("no path for this system", verdict.reason)

    def test_refusal_codes_are_stable(self):
        # The page translates codes; the English reason is the fallback.
        with Tree() as tree:
            cases = [
                ("", {}, "empty"),
                ("relative/path", {}, "relative"),
                ("/", {}, "protected"),
                (tree.sibling, {}, "outside-root"),
                (tree.escape, {}, "outside-root"),
                (os.path.join(tree.inside, "gone"), {}, "missing"),
                (tree.inside, {"entry": {"processes": ["Google Chrome"]}}, "app-running"),
            ]
            for path, kwargs, code in cases:
                with self.subTest(path=path, code=code):
                    verdict = self.check(tree, path, **kwargs)
                    self.assertFalse(verdict.ok)
                    self.assertEqual(verdict.code, code)
            self.assertEqual(self.check(tree, tree.inside).code, "")

    def test_assert_safe_target_raises_the_same_reason(self):
        with Tree() as tree:
            with self.assertRaises(safety.SafetyError) as raised:
                safety.assert_safe_target(tree.sibling, entry(tree.root))
            self.assertIn("outside its catalog root", str(raised.exception))
            self.assertEqual(safety.assert_safe_target(tree.inside, entry(tree.root)),
                             os.path.realpath(tree.inside))


class ProcessTest(unittest.TestCase):
    def test_posix_process_list(self):
        names = safety.process_names(runner=lambda _args: (0, "Google Chrome\nfirefox\n\n"))
        self.assertEqual(names, ("Google Chrome", "firefox"))

    def test_windows_process_list(self):
        out = '"chrome.exe","4242","Console","1","100 MB"\r\n"Code.exe","7","Console","1","50 MB"\r\n'
        names = safety.process_names(platform="windows", runner=lambda _args: (0, out))
        self.assertEqual(names, ("chrome.exe", "Code.exe"))

    def test_a_failing_listing_yields_nothing(self):
        self.assertEqual(safety.process_names(runner=lambda _args: (1, "not supported")), ())

    def test_matching_is_exact_and_ignores_the_path(self):
        names = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "slackd")
        self.assertEqual(safety.running_processes(["Google Chrome"], names=names), ["Google Chrome"])
        self.assertEqual(safety.running_processes(["Slack"], names=names), [])
        self.assertEqual(safety.running_processes([], names=names), [])


class ScanRootAndCopyTest(unittest.TestCase):
    def test_scan_root_must_be_a_folder(self):
        with Tree() as tree:
            with self.assertRaises(safety.PathPolicyError):
                safety.validate_scan_root(os.path.join(tree.inside, "missing"))
            with tempfile.NamedTemporaryFile() as handle:
                with self.assertRaises(safety.PathPolicyError):
                    safety.validate_scan_root(handle.name)
            self.assertEqual(safety.validate_scan_root(tree.inside), os.path.realpath(tree.inside))

    def test_scan_root_refuses_the_home_folder(self):
        with self.assertRaises(safety.PathPolicyError):
            safety.validate_scan_root(os.path.expanduser("~"))

    def test_copy_pairs(self):
        with Tree() as tree:
            with tempfile.TemporaryDirectory() as destination:
                dst_root = os.path.join(destination, "vol")
                os.makedirs(dst_root)
                source, target = safety.validate_copy(
                    tree.inside, os.path.join(dst_root, "app"), dst_root
                )
                self.assertEqual(source, os.path.realpath(tree.inside))
                self.assertEqual(target, os.path.join(os.path.realpath(dst_root), "app"))
                with self.assertRaises(safety.PathPolicyError):
                    safety.validate_copy(tree.inside, tree.inside, tree.base)
                with self.assertRaises(safety.PathPolicyError):
                    safety.validate_copy(tree.inside, os.path.join(tree.inside, "x"), tree.base)
                with self.assertRaises(safety.PathPolicyError):
                    safety.validate_copy(tree.inside, os.path.join(destination, "elsewhere"), dst_root)


class CatalogGuardTest(unittest.TestCase):
    def test_shipped_entries_never_point_at_a_protected_root(self):
        platform = paths.platform_id()
        env = {"HOME": os.path.expanduser("~"), "PATH": ""}
        for item in catalog.load(ROOT, env):
            for template in item["paths"].get(platform, []):
                path, reason = catalog.expand(template, platform, env)
                if path is None:
                    self.assertTrue(reason, "an unresolved path carries a reason")
                    continue
                with self.subTest(entry=item["id"], path=path):
                    safety.validate_managed_path(path)


if __name__ == "__main__":
    unittest.main()
