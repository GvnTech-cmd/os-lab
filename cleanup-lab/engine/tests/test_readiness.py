import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import readiness  # noqa: E402


def fake_root(base, detectors=0):
    root = os.path.join(base, "checkout")
    os.makedirs(os.path.join(root, "cleanup-lab", "catalog"), exist_ok=True)
    for index in range(detectors):
        with open(os.path.join(root, "cleanup-lab", "catalog", "detector-%d.json" % index), "w") as handle:
            handle.write("{}")
    with open(os.path.join(root, "cleanup-lab", "catalog", "schema.json"), "w") as handle:
        handle.write("{}")
    return root


def fake_env(base, state=True):
    home = os.path.join(base, "home")
    os.makedirs(home, exist_ok=True)
    env = {"HOME": home, "PATH": ""}
    if state:
        env["OSLAB_CLEANUP_STATE"] = os.path.join(home, "state", "cleanup")
    return env


REPORT_KEYS = {"engine", "state", "platform", "home", "stateDir", "requirements", "capabilities", "reasons", "checkedAt"}


class ProbeTest(unittest.TestCase):
    def probe(self, base, **kwargs):
        kwargs.setdefault("sys_platform", "darwin")
        kwargs.setdefault("version", (3, 12, 1))
        return readiness.probe(root=fake_root(base, kwargs.pop("detectors", 0)), **kwargs)

    def test_ready_never_writes_the_state_folder(self):
        with tempfile.TemporaryDirectory() as base:
            env = fake_env(base)
            report = self.probe(base, env=env)
            self.assertEqual(set(report), REPORT_KEYS)
            self.assertEqual(report["state"], "ready", report["reasons"])
            self.assertEqual(report["reasons"], [])
            self.assertEqual(report["platform"], {"id": "macos", "label": "macOS", "supported": True})
            self.assertFalse(os.path.exists(env["OSLAB_CLEANUP_STATE"]))
            found = {item["id"]: item["found"] for item in report["requirements"]}
            self.assertEqual(found, {"platform": True, "python": True, "home": True, "trash": True, "state": True})
            self.assertEqual(report["requirements"][1]["detail"], "3.12.1")

    def test_python_311_is_new_enough(self):
        with tempfile.TemporaryDirectory() as base:
            report = self.probe(base, env=fake_env(base), version=(3, 11, 0))
            python = [item for item in report["requirements"] if item["id"] == "python"][0]
            self.assertTrue(python["found"], "(3, 11, 0) must not compare below MIN_PYTHON")
            self.assertEqual(report["state"], "ready")

    def test_unusable_trash_needs_setup(self):
        with tempfile.TemporaryDirectory() as base:
            env = fake_env(base)
            trash = os.path.join(env["HOME"], ".Trash")
            os.makedirs(trash)
            os.chmod(trash, 0o500)
            try:
                report = self.probe(base, env=env)
            finally:
                os.chmod(trash, 0o700)
            item = [entry for entry in report["requirements"] if entry["id"] == "trash"][0]
            self.assertFalse(item["found"])
            self.assertEqual(report["state"], "needs-setup")

    def test_shared_state_folder_needs_setup(self):
        with tempfile.TemporaryDirectory() as base:
            env = fake_env(base)
            os.makedirs(env["OSLAB_CLEANUP_STATE"])
            os.chmod(env["OSLAB_CLEANUP_STATE"], 0o755)
            report = self.probe(base, env=env)
            item = [entry for entry in report["requirements"] if entry["id"] == "state"][0]
            self.assertFalse(item["found"])
            self.assertIn("writable by your user only", item["hint"])

    def test_old_python_needs_setup(self):
        with tempfile.TemporaryDirectory() as base:
            report = self.probe(base, env=fake_env(base), version=(3, 9, 6))
            self.assertEqual(report["state"], "needs-setup")
            self.assertIn("python", [item["id"] for item in report["requirements"] if not item["found"]])
            self.assertTrue(any("3.11" in reason for reason in report["reasons"]))

    def test_unsupported_platform_is_unavailable(self):
        with tempfile.TemporaryDirectory() as base:
            report = self.probe(base, env=fake_env(base), sys_platform="aix")
            self.assertEqual(report["state"], "unavailable")
            self.assertFalse(report["platform"]["supported"])
            self.assertTrue(report["reasons"])

    def test_missing_home_needs_setup(self):
        with tempfile.TemporaryDirectory() as base:
            env = {"HOME": os.path.join(base, "no-such-home"), "PATH": ""}
            report = self.probe(base, env=env)
            self.assertEqual(report["state"], "needs-setup")
            home = [item for item in report["requirements"] if item["id"] == "home"][0]
            self.assertFalse(home["found"])
            self.assertIn("readable", home["hint"])

    def test_detector_count_and_native_backend(self):
        with tempfile.TemporaryDirectory() as base:
            report = self.probe(base, env=fake_env(base), detectors=3)
            capabilities = {item["id"]: item for item in report["capabilities"]}
            self.assertTrue(capabilities["detectors"]["found"])
            self.assertIn("3 detector(s)", capabilities["detectors"]["detail"])
            self.assertFalse(capabilities["native-scan"]["found"])

    def test_no_catalog_is_reported_but_not_required(self):
        with tempfile.TemporaryDirectory() as base:
            report = self.probe(base, env=fake_env(base))
            capabilities = {item["id"]: item for item in report["capabilities"]}
            self.assertFalse(capabilities["detectors"]["found"])
            self.assertEqual(report["state"], "ready")

    def test_tools_are_found_on_a_fake_path(self):
        with tempfile.TemporaryDirectory() as base:
            env = fake_env(base)
            bin_dir = os.path.join(base, "bin")
            os.makedirs(bin_dir)
            docker = os.path.join(bin_dir, "docker")
            with open(docker, "w") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(docker, 0o755)
            env["PATH"] = bin_dir
            report = self.probe(base, env=env)
            capabilities = {item["id"]: item for item in report["capabilities"]}
            self.assertTrue(capabilities["containers"]["found"])
            self.assertIn(docker, capabilities["containers"]["detail"])
            self.assertFalse(capabilities["simulators"]["found"])
            self.assertFalse(capabilities["package-managers"]["found"])

    def test_windows_reports_the_recycle_bin(self):
        with tempfile.TemporaryDirectory() as base:
            report = self.probe(base, env=fake_env(base), sys_platform="win32")
            trash = [item for item in report["requirements"] if item["id"] == "trash"][0]
            self.assertTrue(trash["found"])
            self.assertEqual(trash["detail"], "Recycle Bin")


if __name__ == "__main__":
    unittest.main()
