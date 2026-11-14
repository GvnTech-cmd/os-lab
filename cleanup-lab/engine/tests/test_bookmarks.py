"""CLNP-14: bookmark records validate, order, filter and survive corruption.

The store lives in a generated temp state folder; the catalog is a fake id
→ risk mapping. No real user file is touched (README rule 8).
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import bookmarks  # noqa: E402

CATALOG = [
    {"id": "system.user-caches", "risk": "low"},
    {"id": "system.shared-font-caches", "risk": "low"},
    {"id": "dev.pip-cache", "risk": "medium"},
    {"id": "browser.chrome-history", "risk": "privacy"},
    {"id": "system.trash", "risk": "high"},
    {"id": "credentials.x", "risk": "credentials"},
]


def env_state(base):
    return {"HOME": base, "USERPROFILE": base, "OSLAB_CLEANUP_STATE": base}


def record(entry_id, priority=1, *, quick=True, hook=False, alert=None):
    item = {
        "entryId": entry_id, "createdAt": 1000.0 + priority, "priority": priority,
        "quickClean": quick,
        "autoCleanHook": bookmarks.default_hook() | {"enabled": hook},
        "sizeAlert": bookmarks.default_size_alert(),
    }
    if alert:
        item["sizeAlert"] = bookmarks.default_size_alert() | alert
    return item


class Validation(unittest.TestCase):
    def test_unknown_keys_and_bad_values_are_refused(self):
        for bad in [
            {"entryId": "x", "createdAt": 1, "nope": 1},
            {"entryId": "", "createdAt": 1},
            {"entryId": "x", "createdAt": "now"},
            {"entryId": "x", "createdAt": 1, "priority": 0},
            {"entryId": "x", "createdAt": 1, "priority": True},
            {"entryId": "x", "createdAt": 1, "quickClean": "yes"},
            {"entryId": "x", "createdAt": 1, "sizeAlert": {"thresholdBytes": -1}},
            {"entryId": "x", "createdAt": 1, "autoCleanHook": {"enabled": 1}},
        ]:
            with self.assertRaises(bookmarks.BookmarksError):
                bookmarks.validate_bookmark(bad, catalog_ids={"x"})

    def test_unknown_catalog_entry_is_refused_at_write_time(self):
        with self.assertRaises(bookmarks.BookmarksError):
            bookmarks.validate_bookmark({"entryId": "ghost", "createdAt": 1}, catalog_ids={"real"})


class StoreRoundTrip(unittest.TestCase):
    def test_save_and_load_round_trips_sorted_by_priority(self):
        with tempfile.TemporaryDirectory() as base:
            env = env_state(base)
            bookmarks.save([
                record("dev.pip-cache", 2),
                record("system.user-caches", 1),
            ], env=env, catalog_ids={item["id"] for item in CATALOG})
            loaded = bookmarks.load(env=env)
            self.assertIsNone(loaded["error"])
            self.assertEqual([item["entryId"] for item in loaded["bookmarks"]],
                             ["system.user-caches", "dev.pip-cache"])

    def test_corrupt_store_is_empty_with_an_error(self):
        with tempfile.TemporaryDirectory() as base:
            env = env_state(base)
            with open(os.path.join(base, "bookmarks.json"), "w", encoding="utf-8") as handle:
                handle.write("{oops")
            loaded = bookmarks.load(env=env)
            self.assertEqual(loaded["bookmarks"], [])
            self.assertIn("unreadable", loaded["error"])
            with open(os.path.join(base, "bookmarks.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "bookmarks": [
                    {"entryId": "x", "createdAt": 1, "priority": 1},
                    {"entryId": "x", "createdAt": 2, "priority": 2},
                ]}, handle)
            duplicated = bookmarks.load(env=env)
            self.assertEqual(duplicated["bookmarks"], [])
            self.assertIn("twice", duplicated["error"])

    def test_add_is_once_per_entry_and_appends_priority(self):
        current = [record("system.user-caches", 1)]
        result = bookmarks.add("dev.pip-cache", current, clock=lambda: 2000.0,
                               catalog_ids={item["id"] for item in CATALOG})
        self.assertEqual([item["entryId"] for item in result["bookmarks"]],
                         ["system.user-caches", "dev.pip-cache"])
        self.assertEqual(result["bookmarks"][1]["priority"], 2)
        with self.assertRaises(bookmarks.BookmarksError):
            bookmarks.add("system.user-caches", result["bookmarks"], clock=lambda: 3000.0)

    def test_remove_renumbers_the_priority_order(self):
        current = [record("a", 1), record("b", 2), record("c", 3)]
        result = bookmarks.remove("b", current)
        self.assertEqual([(item["entryId"], item["priority"]) for item in result["bookmarks"]],
                         [("a", 1), ("c", 2)])
        with self.assertRaises(bookmarks.BookmarksError):
            bookmarks.remove("ghost", current)

    def test_update_changes_typed_fields_only(self):
        current = [record("a", 1)]
        result = bookmarks.update("a", {
            "quickClean": False,
            "autoCleanHook": {"enabled": True},
            "sizeAlert": {"enabled": True, "thresholdBytes": 42},
        }, current)
        item = result["bookmarks"][0]
        self.assertFalse(item["quickClean"])
        self.assertTrue(item["autoCleanHook"]["enabled"])
        self.assertEqual(item["sizeAlert"]["thresholdBytes"], 42)
        self.assertTrue(item["sizeAlert"]["armed"])
        with self.assertRaises(bookmarks.BookmarksError):
            bookmarks.update("a", {"nope": 1}, current)
        with self.assertRaises(bookmarks.BookmarksError):
            bookmarks.update("ghost", {}, current)


class PlanFiltering(unittest.TestCase):
    def test_ids_follow_priority_and_refusals_name_the_reason(self):
        records = [
            record("system.trash", 1, quick=True),          # high → refused
            record("browser.chrome-history", 2, quick=True),  # privacy → refused
            record("dev.pip-cache", 3, quick=True),         # medium → included
            record("system.user-caches", 4, quick=True),    # low → included
        ]
        ids, refusals = bookmarks.plan_entry_ids(records, CATALOG, flag="quickClean")
        self.assertEqual(ids, ["dev.pip-cache", "system.user-caches"])
        self.assertEqual([item["entryId"] for item in refusals], ["system.trash", "browser.chrome-history"])
        self.assertIn("high-risk", refusals[0]["reason"])
        self.assertIn("privacy-risk", refusals[1]["reason"])

    def test_hook_flag_refuses_the_same_classes(self):
        records = [record("credentials.x", 1, hook=True), record("dev.pip-cache", 2, hook=True)]
        ids, refusals = bookmarks.plan_entry_ids(records, CATALOG, flag="autoCleanHook")
        self.assertEqual(ids, ["dev.pip-cache"])
        self.assertEqual(refusals[0]["entryId"], "credentials.x")

    def test_unflagged_bookmarks_are_skipped(self):
        records = [record("a", 1, quick=False), record("b", 2, quick=True)]
        ids, _ = bookmarks.plan_entry_ids(records, [{"id": "a", "risk": "low"}, {"id": "b", "risk": "low"}])
        self.assertEqual(ids, ["b"])

    def test_stale_bookmarks_are_refused_not_dropped(self):
        records = [record("ghost", 1, quick=True)]
        ids, refusals = bookmarks.plan_entry_ids(records, CATALOG)
        self.assertEqual(ids, [])
        self.assertIn("no longer in the catalog", refusals[0]["reason"])


class SizeAlerts(unittest.TestCase):
    def test_crossing_warns_once_and_disarms(self):
        records = [record("system.user-caches", 1, alert={"enabled": True, "thresholdBytes": 100})]
        updated, events = bookmarks.evaluate_size_alerts(
            records, {"system.user-caches": 150}, now=1000)
        self.assertFalse(updated[0]["sizeAlert"]["armed"])
        self.assertEqual(updated[0]["sizeAlert"]["lastAlertAt"], 1000)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["bookmark"], "system.user-caches")
        self.assertEqual(events[0]["sizeBytes"], 150)
        # Staying above the threshold is quiet.
        _, again = bookmarks.evaluate_size_alerts(updated, {"system.user-caches": 200}, now=2000)
        self.assertEqual(again, [])

    def test_recovery_rearms(self):
        records = [record("a", 1, alert={"enabled": True, "thresholdBytes": 100, "armed": False, "lastAlertAt": 900})]
        updated, events = bookmarks.evaluate_size_alerts(records, {"a": 50}, now=1000)
        self.assertTrue(updated[0]["sizeAlert"]["armed"])
        self.assertEqual(events[0]["kind"], "recovered")
        # A fresh crossing warns again.
        _, crossed = bookmarks.evaluate_size_alerts(updated, {"a": 120}, now=2000)
        self.assertEqual(crossed[0]["kind"], "warning")

    def test_disabled_or_unmeasured_alerts_do_nothing(self):
        records = [record("a", 1, alert={"enabled": False}), record("b", 2, alert={"enabled": True})]
        updated, events = bookmarks.evaluate_size_alerts(records, {"a": 10**9}, now=1000)
        self.assertEqual(events, [])
        self.assertFalse(updated[0]["sizeAlert"]["armed"] is False)


if __name__ == "__main__":
    unittest.main()
