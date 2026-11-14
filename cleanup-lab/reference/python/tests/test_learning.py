import json
import os
import tempfile
import unittest

from cleanup_ref import learning as ln

DAY = 86_400
NOW = 1_800_000_000.0


def item(path, *, chosen=True, size=1000, at=NOW, category="Developer", source="deep_sweep"):
    return ln.CleanedItem(path=path, name=os.path.basename(path), category=category, detection_source=source,
                          size_freed=size, user_chosen=chosen, cleaned_at=at)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "state", "cleaned-items.json")
        self.clock = [NOW]
        self.store = ln.LedgerStore(self.path, retention_days=90, clock=lambda: self.clock[0])

    def tearDown(self):
        self._tmp.cleanup()

    def test_rows_are_pruned_but_lifetime_totals_are_kept(self):
        self.store.record(item("/p/a/node_modules", at=NOW - 100 * DAY, size=5))
        self.store.record(item("/p/b/node_modules", at=NOW, size=7))
        s = self.store.summary()
        self.assertEqual((s.lifetime_count, s.lifetime_bytes, s.window_count, s.window_bytes), (2, 12, 1, 7))
        self.assertEqual([i.path for i in self.store.recent_items()], ["/p/b/node_modules"])

    def test_corrupt_ledger_is_moved_aside_not_overwritten(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as fh:
            fh.write("{not json")
        self.store.record(item("/p/a/node_modules"))
        self.assertIsNotNone(self.store.recovered_from)
        with open(self.store.recovered_from) as fh:
            self.assertEqual(fh.read(), "{not json")
        with open(self.path) as fh:
            self.assertEqual(json.load(fh)["lifetime_count"], 1)

    def test_make_derives_user_chosen_and_never_negative_bytes(self):
        row = ln.CleanedItem.make(path="/p/x/target", name="target", category="Developer",
                                  detection_source="deep_sweep", size_freed=-3, default_selected=True, at=NOW)
        self.assertFalse(row.user_chosen)
        self.assertEqual(row.size_freed, 0)


class ProfileTests(unittest.TestCase):
    def test_groups_by_basename_and_ranks_by_score(self):
        rows = [item(f"/p/{n}/node_modules", size=1000) for n in "abc"] + [item("/p/z/target", size=100)]
        profile = ln.build_profile(rows, now=NOW)
        self.assertEqual(profile[0].key.path_pattern, "node_modules")
        self.assertEqual(profile[0].frequency, 3)
        self.assertGreater(profile[0].score, profile[1].score)

    def test_recency_halves_the_score_every_half_life(self):
        fresh = ln.build_profile([item("/p/a/x", at=NOW)], now=NOW)[0].score
        old = ln.build_profile([item("/p/a/x", at=NOW - 30 * DAY)], now=NOW, half_life_days=30)[0].score
        self.assertAlmostEqual(old, fresh / 2)

    def test_preselect_needs_repeated_user_choice_and_skips_risky_rows(self):
        profile = ln.build_profile([item(f"/p/{n}/node_modules") for n in "abc"], now=NOW)
        args = dict(category="Developer", detection_source="deep_sweep", path="/q/new/node_modules",
                    name="node_modules", already_default_selected=False, profile=profile)
        self.assertTrue(ln.should_preselect(risk="low", **args))
        for risk in ("high", "credentials", "privacy", "HIGH"):
            self.assertFalse(ln.should_preselect(risk=risk, **args), risk)
        self.assertFalse(ln.should_preselect(risk="low", **{**args, "already_default_selected": True}))
        weak = ln.build_profile([item("/p/a/node_modules", chosen=False)] * 3, now=NOW)
        self.assertFalse(ln.should_preselect(risk="low", **{**args, "profile": weak}))

    def test_quick_clean_seeds_pick_recent_existing_unique_paths(self):
        rows = [
            item("/p/old/node_modules", at=NOW - 2 * DAY),
            item("/p/new/node_modules", at=NOW - DAY),
            item("/p/gone/target", at=NOW),
        ]
        profile = ln.build_profile(rows, now=NOW)
        seeds = ln.quick_clean_seeds(profile, rows, path_exists=lambda p: "gone" not in p)
        self.assertEqual([s.path for s in seeds], ["/p/new/node_modules"])
        self.assertEqual(ln.quick_clean_seeds([], rows), [])


if __name__ == "__main__":
    unittest.main()
