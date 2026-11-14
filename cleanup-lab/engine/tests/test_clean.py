"""CLN-13 tests: plan → verify → clean with Trash by default and honest results.

The three behaviours the task calls out get dedicated tests: a failed Trash must
never become a permanent delete, a partial failure keeps the rest honest, and a
plan whose items changed is refused. Every test runs on a generated tree under
``tempfile`` — never a real user folder (rule 8).
"""
import errno
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from cleanup_lab import clean  # noqa: E402
from cleanup_lab import paths as paths_module  # noqa: E402


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
    """A cancel flag that flips to True after N calls — a deterministic mid-run cancel."""

    def __init__(self, calls):
        self.calls = calls

    def is_set(self):
        self.calls -= 1
        return self.calls < 0


class CleanTests(unittest.TestCase):
    platform = "macos"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cln-clean-")
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

    def caches_entry(self, template="~/Library/Caches", **overrides):
        return make_entry("system.caches", {"macos": [template], "linux": [template]}, **overrides)

    def trash_dir(self):
        return paths_module.trash_dir(self.env, self.platform)

    def build(self, entries, entry_ids=None, **kwargs):
        entry_ids = entry_ids or [entry["id"] for entry in entries]
        return clean.build_plan(
            None,
            entry_ids,
            env=self.env,
            platform=self.platform,
            catalog_entries=entries,
            **kwargs,
        )

    def run_plan(self, plan, **kwargs):
        """verify + execute, the way the console job runs a confirmed plan."""
        measures = clean.verify_plan(plan, **kwargs.pop("verify_kwargs", {}))
        return clean.execute_plan(plan, measures, env=self.env, platform=self.platform, **kwargs)

    def plan_and_run(self, entries, entry_ids=None, **kwargs):
        plan = self.build(entries, entry_ids, **kwargs.pop("plan_kwargs", {}))
        return plan, self.run_plan(plan, **kwargs)

    # ── the plan ─────────────────────────────────────────────────────────────

    def test_plan_lists_sizes_and_marks_ready_items(self):
        self.write("Library/Caches/app/one.bin", 100)
        self.write("Library/Caches/app/two.bin", 50)
        plan = self.build([self.caches_entry()])
        self.assertEqual(plan.mode, "trash")
        items = plan.payload["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "ready")
        self.assertEqual(items[0]["sizeBytes"], 150)
        self.assertEqual(items[0]["files"], 2)
        self.assertEqual(plan.payload["totals"]["ready"], 1)
        self.assertEqual(plan.payload["totals"]["bytes"], 150)
        self.assertEqual(plan.id, plan.payload["planId"])
        self.assertEqual(len(plan.fingerprints), 1)  # one fingerprint per ready item

    def test_the_guard_refuses_running_apps_and_privileged_entries(self):
        self.write("Library/Caches/app/data.bin", 10)
        busy = self.caches_entry(owningProcesses=["DemoApp"])
        plan = self.build([busy], names=["DemoApp"])
        self.assertEqual(plan.payload["items"][0]["code"], "app-running")
        plan = self.build([busy], names=["SomethingElse"])
        self.assertEqual(plan.payload["items"][0]["status"], "ready")

        privileged = self.caches_entry(id="system.spotlight", needsPrivilege=True)
        plan = self.build([privileged])
        self.assertEqual(plan.payload["items"][0]["code"], "privileged")
        self.assertEqual(plan.payload["totals"]["ready"], 0)
        self.assertEqual(plan.fingerprints, {})

    def test_duplicate_and_nested_paths_yield_to_the_first_item(self):
        self.write("Library/Caches/Foo/data.bin", 10)
        outer = self.caches_entry()
        inner = self.caches_entry("~/Library/Caches/Foo", id="system.caches-foo")
        plan = self.build([outer, inner])
        statuses = {item["template"]: item for item in plan.payload["items"]}
        self.assertEqual(statuses["~/Library/Caches"]["status"], "ready")
        self.assertEqual(statuses["~/Library/Caches/Foo"]["code"], "nested")

        same = self.caches_entry(id="system.caches-again")
        plan = self.build([outer, same])
        codes = [item["code"] for item in plan.payload["items"]]
        self.assertEqual(codes, ["", "duplicate"])

    def test_a_fifo_is_planned_as_not_cleanable(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("no mkfifo on this platform")
        os.makedirs(os.path.join(self.home, "Library", "Caches"), exist_ok=True)
        os.mkfifo(os.path.join(self.home, "Library", "Caches", "pipe"))
        pipe_entry = self.caches_entry("~/Library/Caches/pipe")
        plan = self.build([pipe_entry])
        self.assertEqual(plan.payload["items"][0]["code"], "not-cleanable")
        self.assertEqual(plan.payload["totals"]["ready"], 0)

    def test_a_cancelled_plan_build_makes_no_plan(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()], cancel=FlipAfter(1))
        self.assertIsNone(plan.payload)

    def test_the_trash_cannot_be_moved_into_itself(self):
        os.makedirs(self.trash_dir(), exist_ok=True)
        self.write(".Trash/inside.bin", 10)
        trash_entry = make_entry("system.trash", {"macos": ["~/.Trash"]})
        plan = self.build([trash_entry])
        self.assertEqual(plan.payload["items"][0]["code"], "trash-nesting")
        inner = make_entry("system.trash-inner", {"macos": ["~/.Trash/inside.bin"]})
        plan = self.build([inner])
        self.assertEqual(plan.payload["items"][0]["code"], "trash-nesting")

    def test_planning_is_read_only(self):
        self.write("Library/Caches/app/data.bin", 10)
        before = os.stat(os.path.join(self.home, "Library/Caches/app/data.bin")).st_mtime_ns
        self.build([self.caches_entry()])
        after = os.stat(os.path.join(self.home, "Library/Caches/app/data.bin")).st_mtime_ns
        self.assertTrue(os.path.exists(os.path.join(self.home, "Library/Caches/app/data.bin")))
        self.assertEqual(before, after)

    # ── cleaning: trash by default ───────────────────────────────────────────

    def test_a_confirmed_plan_trashes_items_by_default(self):
        self.write("Library/Caches/app/data.bin", 120)
        plan = self.build([self.caches_entry()])
        result = self.run_plan(plan)
        item = result["results"][0]
        self.assertEqual(item["status"], "trashed")
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library/Caches/app")))
        trashed = item["trashPath"]
        self.assertTrue(trashed and os.path.exists(trashed))
        with open(os.path.join(trashed, "app", "data.bin"), "rb") as handle:
            self.assertEqual(len(handle.read()), 120)
        self.assertEqual(result["totals"], {
            "items": 1, "trashed": 1, "deleted": 0, "skipped": 0, "failed": 0,
            "bytes": 120, "files": 1, "folders": 2,
        })

    def test_a_trash_collision_gets_a_new_name(self):
        self.write("Library/Caches/one.bin", 10)
        os.makedirs(self.trash_dir(), exist_ok=True)
        os.makedirs(os.path.join(self.trash_dir(), "Caches"), exist_ok=True)
        with open(os.path.join(self.trash_dir(), "Caches", "keep.bin"), "wb") as handle:
            handle.write(b"keep")
        plan = self.build([self.caches_entry()])
        result = self.run_plan(plan)
        self.assertEqual(os.path.basename(result["results"][0]["trashPath"]), "Caches.1")
        self.assertTrue(os.path.exists(os.path.join(self.trash_dir(), "Caches", "keep.bin")))
        with open(os.path.join(self.trash_dir(), "Caches.1", "one.bin"), "rb") as handle:
            self.assertEqual(handle.read(), b"x" * 10)

    def test_a_failed_trash_is_a_failure_not_a_delete(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()])
        measures = clean.verify_plan(plan)

        def refusing_rename(src, dst):
            raise OSError(errno.EACCES, "Permission denied")

        result = clean.execute_plan(
            plan, measures, env=self.env, platform=self.platform, rename=refusing_rename
        )
        item = result["results"][0]
        self.assertEqual(item["status"], "failed")
        self.assertIn("Permission denied", item["error"])
        # The Qleaner bug: the item would now be gone. Here it is still in place…
        self.assertTrue(os.path.exists(os.path.join(self.home, "Library/Caches/app/data.bin")))
        # …nothing is in the Trash on its behalf, and no bytes were counted.
        self.assertIsNone(item["trashPath"])
        self.assertEqual(result["totals"]["bytes"], 0)
        self.assertEqual(result["totals"]["failed"], 1)

    def test_transient_trash_errors_are_retried_then_succeed(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()])
        measures = clean.verify_plan(plan)
        calls = []
        sleeps = []

        def flaky_rename(src, dst):
            calls.append(src)
            if len(calls) <= 2:
                raise OSError(errno.EBUSY, "Device busy")
            return os.rename(src, dst)

        result = clean.execute_plan(
            plan, measures, env=self.env, platform=self.platform,
            rename=flaky_rename, sleep=sleeps.append,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [clean.RETRY_DELAY, clean.RETRY_DELAY * 2])
        self.assertEqual(result["results"][0]["status"], "trashed")
        self.assertEqual(result["totals"]["bytes"], 10)

    def test_a_partial_failure_keeps_the_rest_honest(self):
        self.write("Library/Caches/good.bin", 30)
        self.write("Library/Logs/bad.bin", 70)
        good = self.caches_entry()
        bad = make_entry("system.logs", {"macos": ["~/Library/Logs"]})
        plan = self.build([good, bad])
        measures = clean.verify_plan(plan)

        def failing_for_logs(src, dst):
            if "Logs" in src:
                raise OSError(errno.EPERM, "Operation not permitted")
            return os.rename(src, dst)

        result = clean.execute_plan(
            plan, measures, env=self.env, platform=self.platform, rename=failing_for_logs
        )
        statuses = {item["path"].split("/")[-1]: item["status"] for item in result["results"]}
        self.assertEqual(statuses, {"Caches": "trashed", "Logs": "failed"})
        self.assertEqual(result["totals"], {
            "items": 2, "trashed": 1, "deleted": 0, "skipped": 0, "failed": 1,
            "bytes": 30, "files": 1, "folders": 1,
        })
        self.assertTrue(os.path.exists(os.path.join(self.home, "Library/Logs/bad.bin")))
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library/Caches/good.bin")))

    def test_a_cancel_stops_before_the_next_item(self):
        self.write("Library/Caches/one.bin", 10)
        self.write("Library/Logs/two.bin", 20)
        plan = self.build([self.caches_entry(), make_entry("system.logs", {"macos": ["~/Library/Logs"]})])
        measures = clean.verify_plan(plan)
        result = clean.execute_plan(
            plan, measures, env=self.env, platform=self.platform, cancel=FlipAfter(1)
        )
        self.assertTrue(result["cancelled"])
        statuses = [item["status"] for item in result["results"]]
        self.assertEqual(statuses, ["trashed", "skipped"])
        self.assertEqual(result["results"][1]["code"], "cancelled")
        self.assertEqual(result["totals"]["bytes"], 10)
        self.assertTrue(os.path.exists(os.path.join(self.home, "Library/Logs/two.bin")))

    def test_a_cross_volume_trash_copies_verifies_then_removes(self):
        self.write("Library/Caches/app/data.bin", 100)
        os.symlink(
            os.path.join(self.home, "Library/Caches/app/data.bin"),
            os.path.join(self.home, "Library/Caches/app/link.bin"),
        )
        plan = self.build([self.caches_entry()])
        measures = clean.verify_plan(plan)

        def cross_device_rename(src, dst):
            raise OSError(errno.EXDEV, "Cross-device link")

        result = clean.execute_plan(
            plan, measures, env=self.env, platform=self.platform, rename=cross_device_rename
        )
        item = result["results"][0]
        self.assertEqual(item["status"], "trashed")
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library/Caches/app/data.bin")))
        # The copy replaced the original, byte for byte, links as links…
        moved = item["trashPath"]
        with open(os.path.join(moved, "app", "data.bin"), "rb") as handle:
            self.assertEqual(len(handle.read()), 100)
        self.assertTrue(os.path.islink(os.path.join(moved, "app", "link.bin")))
        # …and only the verified move was counted: 100 bytes, one file, two folders.
        self.assertEqual(
            (result["totals"]["bytes"], result["totals"]["files"], result["totals"]["folders"]),
            (100, 1, 2),
        )

    def test_a_failed_removal_after_a_copy_keeps_the_backup(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()])
        measures = clean.verify_plan(plan)

        def cross_device_rename(src, dst):
            raise OSError(errno.EXDEV, "Cross-device link")

        real_unlink = os.unlink

        def failing_unlink(target):
            if target.endswith("data.bin"):
                raise OSError(errno.EPERM, "Operation not permitted")
            return real_unlink(target)

        result = clean.execute_plan(
            plan, measures, env=self.env, platform=self.platform,
            rename=cross_device_rename, unlink=failing_unlink,
        )
        item = result["results"][0]
        self.assertEqual(item["status"], "failed")
        self.assertIn("verified copy stays in the Trash", item["error"])
        self.assertEqual(result["totals"]["bytes"], 0)
        # The copy is the only remaining bytes of the item: it must still exist.
        backup = os.path.join(self.trash_dir(), "Caches")
        self.assertTrue(os.path.exists(backup))
        self.assertTrue(os.path.exists(os.path.join(backup, "app", "data.bin")))

    def test_linux_trash_writes_the_freedesktop_sidecar(self):
        self.platform = "linux"
        try:
            self.write("Library/Caches/data.bin", 10)
            entry = make_entry("system.caches", {"linux": ["~/Library/Caches"]})
            plan = self.build([entry])
            result = self.run_plan(plan)
            self.assertEqual(result["results"][0]["status"], "trashed")
            info_dir = os.path.join(self.trash_dir(), "info")
            infos = os.listdir(info_dir)
            self.assertEqual(len(infos), 1)
            with open(os.path.join(info_dir, infos[0]), "r", encoding="utf-8") as handle:
                body = handle.read()
            self.assertTrue(body.startswith("[Trash Info]"))
            self.assertIn("Path=", body)
            self.assertIn("DeletionDate=", body)
            self.assertTrue(os.path.exists(os.path.join(self.trash_dir(), "files", "Caches", "data.bin")))
        finally:
            self.platform = "macos"

    # ── cleaning: explicit delete ────────────────────────────────────────────

    def test_delete_mode_removes_permanently_when_planned(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()], mode="delete")
        result = self.run_plan(plan)
        self.assertEqual(result["results"][0]["status"], "deleted")
        self.assertIsNone(result["results"][0]["trashPath"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "Library/Caches/app")))
        self.assertEqual(result["totals"]["deleted"], 1)
        self.assertEqual(result["totals"]["bytes"], 10)

    # ── the plan expires when items change ───────────────────────────────────

    def test_a_changed_item_expires_the_plan(self):
        target = self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()])
        with open(target, "ab") as handle:
            handle.write(b"grew")
        with self.assertRaises(clean.PlanError) as caught:
            clean.verify_plan(plan)
        self.assertEqual(caught.exception.code, "stale")
        self.assertTrue(os.path.exists(target))  # nothing was removed

    def test_a_new_file_under_an_item_expires_the_plan(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()])
        self.write("Library/Caches/app/added.bin", 5)
        with self.assertRaises(clean.PlanError) as caught:
            clean.verify_plan(plan)
        self.assertEqual(caught.exception.code, "stale")

    def test_a_vanished_item_expires_the_plan(self):
        target = self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()])
        os.remove(target)
        with self.assertRaises(clean.PlanError) as caught:
            clean.verify_plan(plan)
        self.assertEqual(caught.exception.code, "stale")

    def test_an_expired_plan_is_refused_by_the_clock(self):
        self.write("Library/Caches/app/data.bin", 10)
        plan = self.build([self.caches_entry()], clock=lambda: 1000.0)
        self.assertEqual(plan.expires_at, 1000.0 + clean.PLAN_TTL)
        with self.assertRaises(clean.PlanError) as caught:
            clean.verify_plan(plan, clock=lambda: 1000.0 + clean.PLAN_TTL + 1)
        self.assertEqual(caught.exception.code, "expired")

    def test_planned_skips_and_failures_carry_reasons_not_bytes(self):
        self.write("Library/Caches/app/data.bin", 10)
        busy = self.caches_entry(owningProcesses=["DemoApp"])
        plan = self.build([busy], names=["DemoApp"])
        result = self.run_plan(plan)
        item = result["results"][0]
        self.assertEqual(item["status"], "skipped")
        self.assertEqual(item["code"], "app-running")
        self.assertEqual(item["bytes"], 0)
        self.assertEqual(result["totals"]["skipped"], 1)

    def test_bad_plan_requests_are_refused(self):
        # build_plan directly: the build() helper defaults empty id lists away.
        for entry_ids in (None, [], "system.caches", [""], ["a", "a"], [3]):
            with self.assertRaises(clean.PlanError):
                clean.build_plan(
                    None, entry_ids, env=self.env, platform=self.platform,
                    catalog_entries=[self.caches_entry()],
                )
        with self.assertRaises(clean.PlanError):
            self.build([self.caches_entry()], mode="shred")
        with self.assertRaises(clean.PlanError):
            self.build([self.caches_entry()], entry_ids=["nope.entry"])

    def test_workers_are_bounded(self):
        with self.assertRaises(clean.PlanError):
            self.build([self.caches_entry()], workers=clean.scan.MAX_WORKERS + 1)


if __name__ == "__main__":
    unittest.main()
