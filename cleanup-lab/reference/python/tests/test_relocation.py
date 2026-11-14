import os
import tempfile
import unittest

from cleanup_ref import relocation as rl
from cleanup_ref.relocation import FolderStatus as S


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = os.path.realpath(self._tmp.name)
        self.home = os.path.join(root, "home", ".npm")
        self.store = os.path.join(root, "store", "npm")
        os.makedirs(os.path.dirname(self.home))
        os.makedirs(os.path.dirname(self.store))

    def tearDown(self):
        self._tmp.cleanup()

    def test_every_state_is_classified(self):
        self.assertIs(rl.classify(self.home, self.store), S.MISSING)
        os.makedirs(self.home)
        self.assertIs(rl.classify(self.home, self.store), S.LOCAL_ONLY)
        os.makedirs(self.store)
        self.assertIs(rl.classify(self.home, self.store), S.CONFLICT)
        os.rmdir(self.home)
        self.assertIs(rl.classify(self.home, self.store), S.MISSING_LINK)
        os.symlink(self.store, self.home)
        self.assertIs(rl.classify(self.home, self.store), S.LINKED_OK)
        os.rmdir(self.store)
        self.assertIs(rl.classify(self.home, self.store), S.BROKEN_LINK)
        other = os.path.join(os.path.dirname(self.store), "other")
        os.makedirs(other)
        os.unlink(self.home)
        os.symlink(other, self.home)
        self.assertIs(rl.classify(self.home, self.store), S.WRONG_TARGET)

    def test_relative_link_target_is_resolved_from_the_link_directory(self):
        os.makedirs(self.store)
        os.symlink(os.path.relpath(self.store, os.path.dirname(self.home)), self.home)
        self.assertIs(rl.classify(self.home, self.store), S.LINKED_OK)

    def test_move_plan_verifies_before_anything_is_removed(self):
        os.makedirs(self.home)
        steps = rl.plan_move(self.home, self.store, size_bytes=10, free_bytes=10**12)
        ops = [s.op for s in steps]
        self.assertEqual(ops, ["copy", "verify_copy", "rename", "symlink", "verify_link", "remove_tree"])
        self.assertLess(ops.index("verify_copy"), ops.index("remove_tree"))
        self.assertEqual(steps[-1].src, self.home + rl.ASIDE_SUFFIX, "only the set-aside original is removed")

    def test_move_is_refused_without_space_or_in_a_wrong_state(self):
        os.makedirs(self.home)
        with self.assertRaises(rl.RelocationError):
            rl.plan_move(self.home, self.store, size_bytes=10**9, free_bytes=10**9)
        os.makedirs(self.store)
        with self.assertRaises(rl.RelocationError):
            rl.plan_move(self.home, self.store, size_bytes=1, free_bytes=10**12)

    def test_interrupted_move_blocks_a_new_one(self):
        os.makedirs(self.home)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)
        with self.assertRaises(rl.RelocationError):
            rl.plan_move(self.home, self.store, size_bytes=1, free_bytes=10**12)

    def test_restore_and_relink_never_remove_a_real_folder(self):
        os.makedirs(self.store)
        os.symlink(self.store, self.home)
        steps = rl.plan_restore(self.home, self.store)
        self.assertEqual([s.op for s in steps], ["copy", "verify_copy", "remove_link", "rename"])
        self.assertNotIn("remove_tree", [s.op for s in steps], "store copy kept by default")
        os.unlink(self.home)
        os.makedirs(self.home)
        with self.assertRaises(rl.RelocationError):
            rl.plan_relink(self.home, self.store)  # CONFLICT: the user decides

    def test_fingerprint_counts_files_and_links_without_following(self):
        os.makedirs(os.path.join(self.home, "sub"))
        with open(os.path.join(self.home, "sub", "a.bin"), "wb") as fh:
            fh.write(b"x" * 100)
        os.symlink("/", os.path.join(self.home, "rootlink"))
        self.assertEqual(rl.tree_fingerprint(self.home), (2, 100))


if __name__ == "__main__":
    unittest.main()
