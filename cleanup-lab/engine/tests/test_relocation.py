"""CLN-27: relocation plans and the step executor.

Generated temp trees and a per-test fake catalog only (rule 8). The executor
tests run the real steps — copy, verify, rename aside, symlink, verify link,
remove — and prove that a failure at any step leaves the original or a verified
copy. Tests that need real symlinks skip honestly where the OS refuses to
create them (Windows without Developer Mode), and the refusal itself is tested
everywhere by simulating the failure.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import relocation as rl  # noqa: E402
from cleanup_lab.relocation import FolderStatus as S  # noqa: E402


def _symlinks_supported():
    try:
        holder = tempfile.mkdtemp()
        target = os.path.join(holder, "target")
        os.makedirs(target)
        link = os.path.join(holder, "link")
        os.symlink(target, link)
        os.unlink(link)
        return True
    except (OSError, NotImplementedError):
        return False
    finally:
        try:
            shutil.rmtree(holder)
        except Exception:
            pass


SYMLINKS_OK = _symlinks_supported()

NEEDS_SYMLINK = "this host cannot create symlinks (Windows needs Developer Mode or a privilege)"


class TreeBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = os.path.realpath(self._tmp.name)
        self.home = os.path.join(root, "home", ".npm")
        self.store = os.path.join(root, "store", "npm")
        os.makedirs(os.path.dirname(self.home))
        os.makedirs(os.path.dirname(self.store))

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, path, size):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"x" * size)


class ClassifyTest(TreeBase):
    def setUp(self):
        super().setUp()
        if not SYMLINKS_OK:
            self.skipTest(NEEDS_SYMLINK)

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


class PlanTest(TreeBase):
    def test_move_plan_verifies_before_anything_is_removed(self):
        os.makedirs(self.home)
        steps = rl.plan_move(self.home, self.store, size_bytes=10, free_bytes=10 ** 12)
        ops = [step.op for step in steps]
        self.assertEqual(
            ops, ["copy", "verify_copy", "rename", "symlink", "verify_link", "remove_tree"]
        )
        self.assertLess(ops.index("verify_copy"), ops.index("remove_tree"))
        self.assertEqual(steps[-1].src, self.home + rl.ASIDE_SUFFIX,
                         "only the set-aside original is removed")

    def test_move_is_refused_without_space_or_in_a_wrong_state(self):
        os.makedirs(self.home)
        with self.assertRaises(rl.RelocationError):
            rl.plan_move(self.home, self.store, size_bytes=10 ** 9, free_bytes=10 ** 9)
        os.makedirs(self.store)
        with self.assertRaises(rl.RelocationError):
            rl.plan_move(self.home, self.store, size_bytes=1, free_bytes=10 ** 12)

    def test_an_interrupted_move_blocks_a_new_one(self):
        os.makedirs(self.home)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)
        with self.assertRaises(rl.RelocationError):
            rl.plan_move(self.home, self.store, size_bytes=1, free_bytes=10 ** 12)

    def test_restore_and_relink_never_remove_a_real_folder(self):
        if not SYMLINKS_OK:
            self.skipTest(NEEDS_SYMLINK)
        os.makedirs(self.store)
        os.symlink(self.store, self.home)
        steps = rl.plan_restore(self.home, self.store)
        self.assertEqual([step.op for step in steps], ["copy", "verify_copy", "remove_link", "rename"])
        self.assertNotIn("remove_tree", [step.op for step in steps], "store copy kept by default")
        os.unlink(self.home)
        os.makedirs(self.home)
        with self.assertRaises(rl.RelocationError):
            rl.plan_relink(self.home, self.store)  # CONFLICT: the user decides

    def test_fingerprint_counts_files_and_links_without_following(self):
        os.makedirs(self.home)
        self.write(os.path.join(self.home, "sub", "a.bin"), 100)
        self.write(os.path.join(self.home, "b.bin"), 20)
        self.assertEqual(rl.tree_fingerprint(self.home), (2, 120))


class ResumeTest(TreeBase):
    def test_no_aside_is_nothing_to_resume(self):
        with self.assertRaises(rl.RelocationError):
            rl.plan_resume(self.home, self.store)

    def test_resume_before_the_rename_reverifies_and_continues(self):
        os.makedirs(self.home)
        os.makedirs(self.store)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)
        steps = rl.plan_resume(self.home, self.store)
        self.assertEqual([step.op for step in steps],
                         ["verify_copy", "rename", "symlink", "verify_link", "remove_tree"])

    def test_resume_after_the_rename_relinks_then_verifies_before_removing(self):
        os.makedirs(self.store)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)  # the home path itself is gone
        steps = rl.plan_resume(self.home, self.store)
        self.assertEqual([step.op for step in steps],
                         ["symlink", "verify_link", "verify_copy", "remove_tree"])

    def test_resume_with_the_link_already_in_place_only_removes_verified_aside(self):
        if not SYMLINKS_OK:
            self.skipTest(NEEDS_SYMLINK)
        os.makedirs(self.store)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)
        os.symlink(self.store, self.home)
        steps = rl.plan_resume(self.home, self.store)
        self.assertEqual([step.op for step in steps], ["verify_copy", "remove_tree"])


class ExecuteStepsTest(TreeBase):
    def test_a_full_move_leaves_a_working_link_and_no_aside(self):
        if not SYMLINKS_OK:
            self.skipTest(NEEDS_SYMLINK)
        os.makedirs(self.home)
        self.write(os.path.join(self.home, "cache.bin"), 300)
        steps = rl.plan_move(self.home, self.store, size_bytes=300, free_bytes=10 ** 9)
        outcome = rl.execute_steps(steps)
        self.assertFalse(outcome["cancelled"])
        self.assertTrue(os.path.islink(self.home))
        self.assertEqual(rl._link_target(self.home), os.path.normpath(self.store))
        self.assertEqual(rl.tree_fingerprint(self.store), (1, 300))
        self.assertFalse(os.path.lexists(self.home + rl.ASIDE_SUFFIX))

    def test_a_verify_failure_keeps_the_original(self):
        os.makedirs(self.home)
        self.write(os.path.join(self.home, "cache.bin"), 300)
        steps = rl.plan_move(self.home, self.store, size_bytes=300, free_bytes=10 ** 9)
        sneaky_original = rl.copy_tree

        def sneaky(src, dst):
            sneaky_original(src, dst)
            self.write(os.path.join(dst, "extra.bin"), 10)  # the copy went wrong

        with mock.patch.object(rl, "copy_tree", side_effect=sneaky):
            with self.assertRaises(rl.RelocationError) as raised:
                rl.execute_steps(steps)
        self.assertIn("does not match", str(raised.exception))
        self.assertTrue(os.path.isdir(self.home), "the original is still in place")
        self.assertFalse(os.path.islink(self.home))

    def test_a_cancel_between_steps_lists_what_remains_and_resumes(self):
        if not SYMLINKS_OK:
            self.skipTest(NEEDS_SYMLINK)
        os.makedirs(self.home)
        self.write(os.path.join(self.home, "cache.bin"), 100)
        steps = rl.plan_move(self.home, self.store, size_bytes=100, free_bytes=10 ** 9)
        cancel = threading.Event()

        def progress(payload):
            if payload["step"] == "verify_copy":
                cancel.set()

        outcome = rl.execute_steps(steps, progress_callback=progress, cancel=cancel)
        self.assertTrue(outcome["cancelled"])
        self.assertEqual(outcome["remaining"], ["rename", "symlink", "verify_link", "remove_tree"])
        resumed = rl.plan_resume(self.home, self.store)
        done = rl.execute_steps(resumed)
        self.assertFalse(done["cancelled"])
        self.assertTrue(os.path.islink(self.home))
        self.assertFalse(os.path.lexists(self.home + rl.ASIDE_SUFFIX))

    def test_remove_link_refuses_a_real_folder(self):
        os.makedirs(self.home)
        with self.assertRaises(rl.RelocationError) as raised:
            rl.execute_steps([rl.Step("remove_link", self.home)])
        self.assertIn("real folder", str(raised.exception))

    def test_a_failed_rename_stops_with_the_original_in_place(self):
        os.makedirs(self.home)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)  # the aside exists: rename must fail
        self.write(os.path.join(self.home, "keep.bin"), 5)
        with self.assertRaises(rl.RelocationError):
            rl.execute_steps([rl.Step("rename", self.home, self.home + rl.ASIDE_SUFFIX)])
        self.assertTrue(os.path.isdir(self.home))

    def test_a_symlink_failure_is_reported_honestly_everywhere(self):
        os.makedirs(self.home)
        os.makedirs(self.store)
        with mock.patch("os.symlink", side_effect=OSError(1314, "A required privilege is not held by the client")):
            with self.assertRaises(rl.RelocationError) as raised:
                rl.execute_steps([
                    rl.Step("symlink", self.home, self.store),
                ])
        self.assertIn("symlink", str(raised.exception).lower() + str(raised.exception))
        self.assertTrue(os.path.isdir(self.home), "nothing was removed when the link failed")


class FakeCatalogBase(TreeBase):
    """build_plan through a per-test catalog entry on the host's own path semantics."""

    ENTRY_ID = "test.cache"

    def setUp(self):
        super().setUp()
        self.dest = os.path.join(os.path.dirname(os.path.dirname(self.store)), "volume")
        self.env = {"LOCALAPPDATA": os.path.dirname(self.home), "PATH": ""}
        self.catalog_root = os.path.join(self._tmp.name, "fake-root")
        catdir = os.path.join(self.catalog_root, "cleanup-lab", "catalog")
        os.makedirs(catdir)
        entry = {
            "id": self.ENTRY_ID, "name": "Test cache", "category": "developer",
            "risk": "low", "hint": "h", "impact": "i", "defaultSelected": False,
            "needsPrivilege": False, "owningProcesses": ["gradle.exe"], "detector": "paths",
            "paths": {"windows": ["%LOCALAPPDATA%\\.npm"]},
        }
        with open(os.path.join(catdir, "one.json"), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "family": "test", "entries": [entry]}, handle)

    def plan(self, action="move", **kwargs):
        defaults = dict(
            fingerprint=lambda path: (1, 50), free_bytes=10 ** 9, process_list=[],
        )
        defaults.update(kwargs)
        return rl.build_plan(self.catalog_root, self.ENTRY_ID, self.dest, action,
                             platform="windows", env=self.env, **defaults)


class BuildPlanTest(FakeCatalogBase):
    def setUp(self):
        super().setUp()
        os.makedirs(self.home)
        self.write(os.path.join(self.home, "data.bin"), 50)

    def test_a_move_is_planned_for_the_catalog_entry(self):
        record = self.plan("move")
        self.assertEqual(record["action"], "move")
        self.assertEqual(record["entryId"], self.ENTRY_ID)
        self.assertEqual(os.path.normcase(record["homePath"]), os.path.normcase(self.home))
        self.assertTrue(record["storePath"].lower().startswith(self.dest.lower()))
        self.assertIn(rl.STORE_DIRNAME, record["storePath"])
        self.assertEqual(record["sizeBytes"], 50)
        self.assertEqual(
            [step["op"] for step in record["steps"]],
            ["copy", "verify_copy", "rename", "symlink", "verify_link", "remove_tree"],
        )

    def test_unknown_entry_and_action_and_busy_app_are_refused(self):
        with self.assertRaises(rl.RelocationError):
            rl.build_plan(self.catalog_root, "test.nope", self.dest, "move",
                          platform="windows", env=self.env)
        with self.assertRaises(rl.RelocationError):
            rl.build_plan(self.catalog_root, self.ENTRY_ID, self.dest, "destroy",
                          platform="windows", env=self.env)
        with self.assertRaises(rl.RelocationError) as raised:
            self.plan("move", process_list=["gradle.exe"])
        self.assertIn("owning application is running", str(raised.exception))

    def test_the_planned_move_executes_end_to_end(self):
        if not SYMLINKS_OK:
            self.skipTest(NEEDS_SYMLINK)
        record = self.plan("move", fingerprint=None)
        result = rl.execute(record)
        self.assertFalse(result["cancelled"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["bytesRelocated"], 50)
        self.assertIsNone(result["bytesRemoved"])
        self.assertTrue(os.path.islink(self.home))
        self.assertEqual(rl.tree_fingerprint(self.store), (1, 50))

    def test_a_changed_folder_refuses_to_execute(self):
        record = self.plan("move")
        self.write(os.path.join(self.home, "new.bin"), 9)
        with self.assertRaises(rl.RelocationError) as raised:
            rl.execute(record)
        self.assertIn("changed since the preview", str(raised.exception))


class StatusTest(FakeCatalogBase):
    def test_status_lists_relocatable_entries_and_destinations(self):
        os.makedirs(self.home)
        report = rl.status(self.catalog_root, platform="windows", env=self.env)
        ids = {entry["entryId"] for entry in report["entries"]}
        self.assertIn(self.ENTRY_ID, ids)
        row = next(entry for entry in report["entries"] if entry["entryId"] == self.ENTRY_ID)
        self.assertTrue(row["relocatable"])
        self.assertFalse(row["interrupted"])
        self.assertTrue(any(item["kind"] in ("root", "internal", "removable")
                            for item in report["destinations"]),
                        "the host has at least one usable volume")

    def test_an_interrupted_entry_is_flagged(self):
        os.makedirs(self.home)
        os.makedirs(self.home + rl.ASIDE_SUFFIX)
        report = rl.status(self.catalog_root, platform="windows", env=self.env)
        row = next(entry for entry in report["entries"] if entry["entryId"] == self.ENTRY_ID)
        self.assertTrue(row["interrupted"])
        self.assertTrue(row["relocatable"], "the real folder is still there; resume decides")

    def test_destinations_come_from_the_volume_inventory(self):
        rows = [
            {"mountPoint": "C:\\", "name": "", "device": "C:", "filesystem": "NTFS", "kind": "root"},
            {"mountPoint": "D:\\", "name": "", "device": "D:", "filesystem": "NTFS", "kind": "internal"},
            {"mountPoint": "E:\\", "name": "", "device": "E:", "filesystem": "NTFS", "kind": "unknown"},
        ]
        dests = rl.destinations(platform="windows", rows=rows,
                                usage_fn=lambda mount_point: (100, 50))
        self.assertEqual([item["mountPoint"] for item in dests], ["C:\\", "D:\\"])
        self.assertEqual([item["kind"] for item in dests], ["root", "internal"])


if __name__ == "__main__":
    unittest.main()
