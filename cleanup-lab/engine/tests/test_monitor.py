"""CLNP-09: the monitor evaluates pure state over injected snapshots and clocks.

No test touches a real volume: the CLN-28 snapshot and the clock are fakes,
and the store lives in a generated temp state folder (README rule 8).
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import monitor  # noqa: E402


def env_state(base):
    return {"HOME": base, "USERPROFILE": base, "OSLAB_CLEANUP_STATE": base}


def volume(mount, free, total, is_home=False, error=None):
    measurable = isinstance(free, int) and isinstance(total, int)
    return {"mountPoint": mount, "name": mount, "device": mount, "filesystem": "apfs",
            "kind": "root", "totalBytes": total, "freeBytes": free,
            "usedBytes": (total - free) if measurable else None,
            "usage": ((total - free) / total) if measurable else None,
            "isHome": is_home, "pressure": "ok", "error": error}


HOME = volume("/", free=800, total=1000, is_home=True)
LOW = volume("/", free=100, total=1000, is_home=True)  # below the 20 % floor


def config(**overrides):
    base = monitor.default_config()
    base["enabled"] = True
    base["volumes"] = [{"mountPoint": "", "minFreeBytes": 100, "minFreePercent": 20.0, "enabled": True}]
    base.update(overrides)
    return monitor.validate_config(base)


class ConfigValidation(unittest.TestCase):
    def test_defaults_are_disabled_with_sensible_floors(self):
        base = monitor.default_config()
        self.assertFalse(base["enabled"])
        self.assertEqual(base["intervalSeconds"], 300)
        self.assertEqual(base["volumes"][0]["minFreeBytes"], 10 * 1024 * 1024 * 1024)
        self.assertEqual(base["volumes"][0]["minFreePercent"], 10.0)

    def test_unknown_keys_and_bad_types_are_refused(self):
        for bad in [
            {"nope": True},
            {"enabled": "yes"},
            {"intervalSeconds": 10},
            {"intervalSeconds": True},
            {"cooldownSeconds": -1},
            {"volumes": []},
            {"volumes": "x"},
            {"volumes": [{"mountPoint": "/", "minFreeBytes": -1}]},
            {"volumes": [{"mountPoint": "/", "minFreePercent": 101}]},
            {"volumes": [{"mountPoint": "/"}, {"mountPoint": "/"}]},
        ]:
            with self.assertRaises(monitor.MonitorConfigError):
                monitor.validate_config(dict(config(), **bad))

    def test_validated_config_is_normalized(self):
        result = monitor.validate_config({"enabled": True, "volumes": [{"mountPoint": "/x"}]})
        self.assertEqual(result["volumes"][0]["minFreeBytes"], monitor.DEFAULT_MIN_FREE_BYTES)
        self.assertTrue(result["volumes"][0]["enabled"])
        self.assertEqual(result["cooldownSeconds"], monitor.DEFAULT_COOLDOWN)


class Evaluate(unittest.TestCase):
    def test_crossing_below_threshold_warns_once_and_disarms(self):
        state = monitor.evaluate(config(), monitor._fresh_state(), [LOW], now=1000)
        warnings = [event for event in state["events"] if event["kind"] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["volume"], "/")
        self.assertEqual(warnings[0]["thresholdBytes"], 200)  # percent floor wins
        self.assertIs(state["volumes"][monitor._volume_key("/")]["armed"], False)
        # Staying low re-evaluates quietly: no second warning is added.
        again = monitor.evaluate(config(), state, [LOW], now=2000)
        self.assertEqual(len([event for event in again["events"] if event["kind"] == "warning"]), 1)

    def test_rearm_requires_recovery_above_threshold_plus_margin(self):
        state = monitor.evaluate(config(), monitor._fresh_state(), [LOW], now=1000)
        # Barely above the threshold (inside the margin) stays disarmed and quiet.
        inside = monitor.evaluate(config(), state, [volume("/", free=201, total=1000, is_home=True)], now=2000)
        self.assertIs(inside["volumes"][monitor._volume_key("/")]["armed"], False)
        self.assertEqual([event for event in inside["events"] if event["kind"] == "recovered"], [])
        # Recovered past the margin re-arms and announces it once.
        recovered = monitor.evaluate(config(), inside, [volume("/", free=250, total=1000, is_home=True)], now=3000)
        self.assertIs(recovered["volumes"][monitor._volume_key("/")]["armed"], True)
        self.assertEqual(len([event for event in recovered["events"] if event["kind"] == "recovered"]), 1)
        # A fresh crossing warns again.
        recrossed = monitor.evaluate(config(), recovered, [LOW], now=4000)
        self.assertEqual(len([event for event in recrossed["events"] if event["kind"] == "warning"]), 1)

    def test_cooldown_suppresses_a_second_warning_after_quick_rearm(self):
        state = monitor.evaluate(config(), monitor._fresh_state(), [LOW], now=1000)
        recovered = monitor.evaluate(config(), state, [volume("/", free=300, total=1000, is_home=True)], now=1100)
        recrossed = monitor.evaluate(config(), recovered, [LOW], now=1200)
        # The first warning stays in the history; the cooldown adds no second one.
        self.assertEqual(len([event for event in recrossed["events"] if event["kind"] == "warning"]), 1)
        self.assertIs(recrossed["volumes"][monitor._volume_key("/")]["armed"], False)
        # After the cooldown a fresh crossing warns again (history keeps both).
        later = monitor.evaluate(config(), recrossed, [volume("/", free=300, total=1000, is_home=True)], now=1200 + 3600)
        later_warning = monitor.evaluate(config(), later, [LOW], now=1200 + 7200)
        self.assertEqual(len([event for event in later_warning["events"] if event["kind"] == "warning"]), 2)

    def test_unmounted_volume_records_an_error_not_a_failure(self):
        state = monitor.evaluate(config(), monitor._fresh_state(), [HOME], now=1000)
        gone = monitor.evaluate(config(), state, [volume("/", free=900, total=1000, is_home=True)], now=2000)
        config_other = monitor.validate_config(dict(config(), volumes=[{"mountPoint": "/Volumes/Gone", "minFreeBytes": 10, "minFreePercent": 5.0, "enabled": True}]))
        result = monitor.evaluate(config_other, gone, [HOME], now=3000)
        errors = [event for event in result["events"] if event["kind"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["volume"], "/Volumes/Gone")

    def test_unmeasurable_volume_reports_its_error(self):
        broken = volume("/", free=None, total=None, is_home=True, error="diskutil failed")
        state = monitor.evaluate(config(), monitor._fresh_state(), [broken], now=1000)
        errors = [event for event in state["events"] if event["kind"] == "error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["message"], "diskutil failed")

    def test_disabled_volumes_and_absolute_floor(self):
        absolute = monitor.validate_config(dict(config(), volumes=[{"mountPoint": "", "minFreeBytes": 500, "minFreePercent": 0, "enabled": True}]))
        state = monitor.evaluate(absolute, monitor._fresh_state(), [volume("/", free=450, total=1000, is_home=True)], now=1000)
        self.assertEqual(len([event for event in state["events"] if event["kind"] == "warning"]), 1)
        self.assertEqual(state["events"][-1]["thresholdBytes"], 500)

    def test_event_list_stays_bounded(self):
        state = monitor._fresh_state()
        for index in range(150):
            state["events"] = monitor._append_event(state["events"], {"at": index, "kind": "error", "volume": "x", "freeBytes": None, "thresholdBytes": None, "message": str(index)})
        self.assertEqual(len(state["events"]), monitor.MAX_EVENTS)


class Store(unittest.TestCase):
    def test_round_trip_through_the_private_store(self):
        with tempfile.TemporaryDirectory() as base:
            saved = monitor.save_config(config(), env=env_state(base))
            self.assertIsNone(saved["configError"])
            loaded = monitor.load(env=env_state(base))
            self.assertEqual(loaded["config"], config())
            path = os.path.join(base, "monitor.json")
            with open(path, encoding="utf-8") as handle:
                raw = json.load(handle)
            self.assertEqual(raw["version"], 1)
            self.assertFalse(os.path.exists(path + ".tmp-" + str(os.getpid())))

    def test_missing_store_defaults_to_disabled(self):
        with tempfile.TemporaryDirectory() as base:
            loaded = monitor.load(env=env_state(base))
            self.assertFalse(loaded["config"]["enabled"])
            self.assertIsNone(loaded["configError"])

    def test_corrupt_store_disables_and_reports(self):
        with tempfile.TemporaryDirectory() as base:
            with open(os.path.join(base, "monitor.json"), "w", encoding="utf-8") as handle:
                handle.write("{not json")
            loaded = monitor.load(env=env_state(base))
            self.assertFalse(loaded["config"]["enabled"])
            self.assertIn("unreadable", loaded["configError"])
            # A versioned store with a bad config is refused the same way.
            with open(os.path.join(base, "monitor.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "config": {"nope": 1}, "state": {}}, handle)
            refused = monitor.load(env=env_state(base))
            self.assertIn("invalid", refused["configError"])
            self.assertFalse(refused["config"]["enabled"])

    def test_unknown_version_is_reported(self):
        with tempfile.TemporaryDirectory() as base:
            with open(os.path.join(base, "monitor.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 99, "config": {}, "state": {}}, handle)
            loaded = monitor.load(env=env_state(base))
            self.assertIn("unknown version", loaded["configError"])


class RunEvaluation(unittest.TestCase):
    def test_disabled_monitor_does_not_probe(self):
        calls = []

        def fake_inventory():
            calls.append(1)
            return {"volumes": [HOME]}

        with tempfile.TemporaryDirectory() as base:
            result = monitor.run_evaluation(env=env_state(base), inventory=fake_inventory, clock=lambda: 1000)
        self.assertFalse(result["evaluated"])
        self.assertEqual(calls, [])

    def test_enabled_monitor_evaluates_and_persists(self):
        with tempfile.TemporaryDirectory() as base:
            monitor.save_config(config(), env=env_state(base))
            result = monitor.run_evaluation(
                env=env_state(base),
                inventory=lambda: {"volumes": [volume("/", free=100, total=1000, is_home=True)]},
                clock=lambda: 5000,
            )
            self.assertTrue(result["evaluated"])
            self.assertEqual(len([event for event in result["state"]["events"] if event["kind"] == "warning"]), 1)
            loaded = monitor.load(env=env_state(base))
            self.assertEqual(loaded["state"]["lastEvaluationAt"], 5000)


class Status(unittest.TestCase):
    def test_status_resolves_home_volume_and_reports_state(self):
        with tempfile.TemporaryDirectory() as base:
            monitor.save_config(config(), env=env_state(base))
            payload = monitor.status(
                env=env_state(base),
                inventory=lambda: {"volumes": [volume("/", free=100, total=1000, is_home=True)]},
                clock=lambda: 9000,
            )
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["volumes"][0]["mountPoint"], "/")
        self.assertEqual(payload["volumes"][0]["volume"]["freeBytes"], 100)
        self.assertEqual(payload["activeWarnings"], [])  # status reads state, never evaluates
        self.assertIsNone(payload["state"]["lastEvaluationAt"])

    def test_status_with_empty_mount_resolves_to_none_without_inventory(self):
        with tempfile.TemporaryDirectory() as base:
            monitor.save_config(config(), env=env_state(base))
            payload = monitor.status(env=env_state(base), inventory=lambda: {"volumes": []}, clock=lambda: 1)
        self.assertEqual(payload["volumes"][0]["mountPoint"], "")
        self.assertIsNone(payload["volumes"][0]["volume"])


if __name__ == "__main__":
    unittest.main()
