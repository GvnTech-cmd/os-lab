import os
import tempfile
import unittest

from cleanup_ref import path_policy as pp


class PathPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self._tmp.name)
        self.cache = os.path.join(self.home, "Library", "Caches")
        os.makedirs(os.path.join(self.cache, "app"))
        os.makedirs(os.path.join(self.home, "Documents"))

    def tearDown(self):
        self._tmp.cleanup()

    def test_canonical_expands_tilde_and_refuses_relative_and_empty(self):
        self.assertEqual(pp.canonical("~/Library/./Caches/", home=self.home), self.cache)
        for bad in ("", "   ", "relative/path", "a\x00b"):
            with self.assertRaises(pp.PathPolicyError):
                pp.canonical(bad, home=self.home)

    def test_home_and_root_are_protected(self):
        for raw in ("~", "/", self.home + "/"):
            with self.assertRaises(pp.PathPolicyError):
                pp.validate_managed_path(raw, home=self.home)

    def test_containment_uses_components_not_string_prefix(self):
        os.makedirs(os.path.join(self.home, "cache-old"))
        self.assertFalse(pp.is_contained(os.path.join(self.home, "cache-old"), os.path.join(self.home, "cache")))
        self.assertTrue(pp.is_contained(os.path.join(self.cache, "app"), self.cache))

    def test_symlink_escaping_an_allowed_root_is_rejected(self):
        link = os.path.join(self.cache, "escape")
        os.symlink(os.path.join(self.home, "Documents"), link)
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_target(link, ["~/Library/Caches"], home=self.home)

    def test_target_must_be_inside_and_not_the_root_itself(self):
        self.assertEqual(
            pp.validate_target("~/Library/Caches/app", ["~/Library/Caches"], home=self.home),
            os.path.join(self.cache, "app"),
        )
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_target("~/Library/Caches", ["~/Library/Caches"], home=self.home)
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_target("~/Documents", ["~/Library/Caches"], home=self.home)
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_target("~/Library/Caches/gone", ["~/Library/Caches"], home=self.home)

    def test_scan_root_must_be_an_existing_directory(self):
        self.assertEqual(pp.validate_scan_root("~/Documents", home=self.home), os.path.join(self.home, "Documents"))
        open(os.path.join(self.home, "file.txt"), "w").close()
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_scan_root("~/file.txt", home=self.home)
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_scan_root("~/missing", home=self.home)

    def test_copy_refuses_nesting_and_outside_destination(self):
        store = os.path.join(self.home, "Store")
        os.makedirs(store)
        src, dst = pp.validate_copy("~/Library/Caches/app", "~/Store/app", "~/Store", home=self.home)
        self.assertEqual(dst, os.path.join(store, "app"))
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_copy("~/Library/Caches", "~/Library/Caches/app/inner", "~/Library", home=self.home)
        with self.assertRaises(pp.PathPolicyError):
            pp.validate_copy("~/Library/Caches/app", "~/Documents/app", "~/Store", home=self.home)


if __name__ == "__main__":
    unittest.main()
