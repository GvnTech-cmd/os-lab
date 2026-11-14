"""CLN-20: typed privileged actions and the macOS disk-access probe.

Every command runs through a fake ``runner``/``executor`` and every elevation
lookup through a fake ``which`` — no real ``sudo``, ``pkexec``, ``osascript``,
UAC prompt or package list is ever touched (README rule 8).
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import privilege  # noqa: E402


AUTOREMOVE_SAMPLE = "\n".join([
    "Reading package lists... Done",
    "Building dependency tree... Done",
    "Reading state information... Done",
    "The following packages will be REMOVED:",
    "  libfoo1* libbar2:* oldapp*",
    "The following packages have been kept back:",
    "  linux-image-generic",
    "The following packages will be upgraded:",
    "  curl",
    "0 upgraded, 0 newly installed, 3 to remove and 1 not upgraded.",
    "Remv libfoo1 [1.2-1]",
]) + "\n"

JOURNAL_SAMPLE = "Archived and active journals take up to 3.9G in the file system.\n"

#: The repo root that holds ``cleanup-lab/catalog`` (four levels above this file).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class Result:
    """A stand-in for subprocess.CompletedProcess."""

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class Runner:
    """Records argv and answers per program."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        key = argv[0]
        answer = self.answers.get(key)
        if isinstance(answer, Exception):
            raise answer
        return answer


def which_found(names):
    def which(name, path=None):
        if name in names:
            return "/usr/bin/" + name
        return None
    return which


class CatalogTest(unittest.TestCase):
    def test_catalog_mirrors_the_engine_allowlist_exactly(self):
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "cleanup-lab", "catalog", "actions"))
            import json
            source = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "catalog", "actions", "privileged.json",
            )
            with open(source, encoding="utf-8") as handle:
                data = json.load(handle)
            with open(os.path.join(base, "cleanup-lab", "catalog", "actions", "privileged.json"),
                      "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            for platform in ("linux", "macos", "windows"):
                actions = privilege._actions(base, platform)
                self.assertEqual(set(actions), set(privilege.ALLOWED[platform]))

    def test_drift_between_catalog_and_allowlist_is_refused(self):
        import json
        with tempfile.TemporaryDirectory() as base:
            folder = os.path.join(base, "cleanup-lab", "catalog", "actions")
            os.makedirs(folder)
            data = {"version": 1, "platforms": {
                "linux": {"apt-cache": {
                    "id": "privileged.linux.apt-cache", "name": "x", "risk": "low",
                    "previewMode": "files", "preview": None,
                    "measurePath": "/elsewhere", "run": ["apt-get", "clean"], "impact": "x",
                }},
                "macos": {}, "windows": {},
            }}
            with open(os.path.join(folder, "privileged.json"), "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            with self.assertRaises(privilege.PrivilegeError) as raised:
                privilege._actions(base, "linux")
            self.assertIn("invalid", str(raised.exception))


class PreviewTest(unittest.TestCase):
    ROOT = ROOT

    def test_files_preview_measures_and_names_the_elevated_command(self):
        measure = mock.Mock(return_value={"count": 12, "totalBytes": 1024, "notes": [], "missing": False})
        plan, material = privilege.preview(
            self.ROOT, "privileged.linux.apt-cache", platform="linux",
            which=which_found(["pkexec"]), measure=measure, clock=lambda: 1.0,
        )
        measure.assert_called_once_with("/var/cache/apt/archives")
        self.assertEqual(plan.count, 12)
        self.assertEqual(plan.total_bytes, 1024)
        self.assertEqual(plan.elevation, "pkexec")
        self.assertEqual(
            list(plan.elevation_argv), ["/usr/bin/pkexec", "--disable-internal-agent", "apt-get", "clean"]
        )
        self.assertEqual(material["count"], 12)

    def test_text_preview_runs_the_fixed_probe(self):
        runner = Runner({"journalctl": Result(stdout=JOURNAL_SAMPLE)})
        plan, material = privilege.preview(
            self.ROOT, "privileged.linux.journal-vacuum", platform="linux",
            which=which_found(["sudo"]), runner=runner, clock=lambda: 2.0,
        )
        self.assertEqual(runner.calls[0], ["journalctl", "--disk-usage"])
        self.assertIn("3.9G", material["output"])
        self.assertIsNone(plan.count)
        self.assertEqual(plan.elevation, "sudo")
        self.assertEqual(list(plan.elevation_argv), ["/usr/bin/sudo", "-n", "journalctl", "--vacuum-size=100M"])

    def test_packages_preview_parses_only_the_removed_section(self):
        runner = Runner({"apt-get": Result(stdout=AUTOREMOVE_SAMPLE)})
        plan, material = privilege.preview(
            self.ROOT, "privileged.linux.apt-autoremove", platform="linux",
            which=which_found(["pkexec"]), runner=runner, clock=lambda: 3.0,
        )
        self.assertEqual(material["candidates"], ["libbar2", "libfoo1", "oldapp"])
        self.assertEqual(plan.count, 3)
        self.assertNotIn("linux-image-generic", material["candidates"])
        self.assertNotIn("curl", material["candidates"])

    def test_failing_preview_probe_is_an_error(self):
        runner = Runner({"journalctl": Result(stderr="journalctl: failed", returncode=1)})
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege.preview(
                self.ROOT, "privileged.linux.journal-vacuum", platform="linux",
                which=which_found(["sudo"]), runner=runner,
            )
        self.assertIn("journalctl: failed", str(raised.exception))

    def test_unknown_action_and_unknown_platform_are_refused(self):
        with self.assertRaises(privilege.PrivilegeError):
            privilege.preview(self.ROOT, "privileged.linux.nope", platform="linux")
        with self.assertRaises(privilege.PrivilegeError):
            privilege.preview(self.ROOT, "privileged.freebsd.apt-cache", platform="freebsd")

    def test_preview_without_elevation_is_refused(self):
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege.preview(
                self.ROOT, "privileged.linux.apt-cache", platform="linux",
                which=lambda name, path=None: None, measure=lambda path: {"count": 0},
            )
        self.assertIn("No elevation mechanism", str(raised.exception))

    def test_digest_is_stable_for_the_same_candidates(self):
        measure = mock.Mock(return_value={"count": 1, "totalBytes": 5, "notes": [], "missing": False})
        one, _ = privilege.preview(self.ROOT, "privileged.linux.apt-cache", platform="linux",
                                   which=which_found(["pkexec"]), measure=measure, clock=lambda: 1.0)
        two, _ = privilege.preview(self.ROOT, "privileged.linux.apt-cache", platform="linux",
                                   which=which_found(["pkexec"]), measure=measure, clock=lambda: 2.0)
        self.assertEqual(one.digest, two.digest)


class ExecuteTest(unittest.TestCase):
    ROOT = ROOT

    def make_plan(self, clock_value=1.0, count=12):
        measure = mock.Mock(return_value={"count": count, "totalBytes": 1024, "notes": [], "missing": False})
        plan, _ = privilege.preview(
            self.ROOT, "privileged.linux.apt-cache", platform="linux",
            which=which_found(["pkexec"]), measure=measure, clock=lambda: clock_value,
        )
        return plan, measure

    def test_execute_reruns_the_preview_and_runs_the_fixed_argv(self):
        runner = Runner({"/usr/bin/pkexec": Result(stdout="")})
        plan, measure = self.make_plan()
        result = privilege.execute(
            self.ROOT, plan, which=which_found(["pkexec"]), runner=runner,
            measure=measure, clock=lambda: 2.0,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            runner.calls[0],
            ["/usr/bin/pkexec", "--disable-internal-agent", "apt-get", "clean"],
        )
        self.assertIsNone(result["bytesRemoved"])
        self.assertEqual(result["elevation"], "pkexec")

    def test_changed_candidates_refuse_the_run(self):
        runner = Runner({"/usr/bin/pkexec": Result(stdout="")})
        plan, _ = self.make_plan(count=12)
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege.execute(
                self.ROOT, plan, which=which_found(["pkexec"]),
                runner=runner, clock=lambda: 2.0,
                measure=mock.Mock(return_value={"count": 13, "totalBytes": 2048, "notes": [], "missing": False}),
            )
        self.assertIn("changed", str(raised.exception))
        self.assertEqual(runner.calls, [])

    def test_expired_preview_refuses_the_run(self):
        plan, _ = self.make_plan(clock_value=1.0)
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege.execute(
                self.ROOT, plan,
                which=which_found(["pkexec"]), runner=Runner({}), clock=lambda: 1.0 + privilege.PREVIEW_TTL + 1,
            )
        self.assertIn("expired", str(raised.exception))

    def test_zero_candidates_refuse_the_run(self):
        plan, measure = self.make_plan(count=0)
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege.execute(
                self.ROOT, plan, which=which_found(["pkexec"]),
                runner=Runner({}), measure=measure, clock=lambda: 2.0,
            )
        self.assertIn("no candidates", str(raised.exception))

    def test_a_failed_elevated_command_fails_honestly(self):
        runner = Runner({"/usr/bin/pkexec": Result(stderr="E: access denied", returncode=100)})
        plan, measure = self.make_plan()
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege.execute(
                self.ROOT, plan, which=which_found(["pkexec"]),
                runner=runner, measure=measure, clock=lambda: 2.0,
            )
        self.assertIn("E: access denied", str(raised.exception))

    def test_windows_executor_is_used_when_candidates_match(self):
        runner = Runner({"Dism.exe": Result(stdout="Component Store Cleanup Recommended: Yes")})
        plan, _ = privilege.preview(
            self.ROOT, "privileged.windows.dism-cleanup", platform="windows",
            which=lambda name, path=None: None, runner=runner,
            clock=lambda: 1.0,
        )
        executor = mock.Mock(return_value={"returncode": 0, "stdout": "", "stderr": ""})
        result = privilege.execute(
            self.ROOT, plan, which=lambda name, path=None: None, runner=runner,
            clock=lambda: 2.0, executor=executor,
        )
        executor.assert_called_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["command"], ["Dism.exe", "/online", "/Cleanup-Image", "/StartComponentCleanup"])
        self.assertIn("no console output", result["output"])


class ElevationTest(unittest.TestCase):
    def test_linux_prefers_pkexec_and_falls_back_to_sudo(self):
        argv = privilege._elevation("linux", ["apt-get", "clean"], {"PATH": "/x"}, which=which_found(["pkexec", "sudo"]))[1]
        self.assertEqual(argv, ["/usr/bin/pkexec", "--disable-internal-agent", "apt-get", "clean"])
        argv = privilege._elevation("linux", ["apt-get", "clean"], {"PATH": "/x"}, which=which_found(["sudo"]))[1]
        self.assertEqual(argv, ["/usr/bin/sudo", "-n", "apt-get", "clean"])

    def test_linux_without_elevation_raises_with_guidance(self):
        with self.assertRaises(privilege.PrivilegeError) as raised:
            privilege._elevation("linux", ["true"], {"PATH": "/x"}, which=which_found([]))
        self.assertIn("pkexec", str(raised.exception))

    def test_macos_builds_a_quoted_osascript_dialog(self):
        name, argv = privilege._elevation("macos", ["mdutil", "-E", "/"], {}, which=which_found(["osascript"]))
        self.assertEqual(name, "osascript")
        self.assertEqual(argv[0], "/usr/bin/osascript")
        self.assertEqual(argv[1], "-e")
        self.assertIn("do shell script", argv[2])
        self.assertIn("with administrator privileges", argv[2])
        self.assertIn("'mdutil -E /'", argv[2])

    def test_windows_marks_the_uac_mechanism(self):
        name, argv = privilege._elevation("windows", ["Dism.exe", "/x"], {})
        self.assertEqual(name, "uac")
        self.assertEqual(argv, ["Dism.exe", "/x"])


class DiskAccessTest(unittest.TestCase):
    def test_other_platforms_report_not_applicable(self):
        for platform in ("linux", "windows"):
            report = privilege.disk_access(platform)
            self.assertFalse(report["applicable"])
            self.assertIsNone(report["granted"])

    def test_a_permission_error_means_not_granted(self):
        def prober(path):
            if path.endswith("Safari"):
                raise PermissionError(path)
            raise FileNotFoundError(path)
        report = privilege.disk_access("macos", prober=prober)
        self.assertTrue(report["applicable"])
        self.assertFalse(report["granted"])
        self.assertIn("Full Disk Access", report["guidance"])

    def test_a_readable_protected_folder_means_granted(self):
        report = privilege.disk_access("macos", prober=lambda path: ["bookmark.plist"])
        self.assertTrue(report["granted"])
        self.assertEqual(report["guidance"], "")

    def test_missing_probe_paths_report_unknown(self):
        report = privilege.disk_access("macos", prober=lambda path: (_ for _ in ()).throw(FileNotFoundError(path)))
        self.assertIsNone(report["granted"])
        self.assertEqual(report["guidance"], "")


class CapabilitiesTest(unittest.TestCase):
    ROOT = ROOT

    def test_payload_shape_and_platform_filtering(self):
        report = privilege.capabilities(self.ROOT, platform="linux", which=which_found(["pkexec"]))
        self.assertTrue(report["applicable"])
        self.assertEqual(report["elevation"], "pkexec")
        self.assertEqual(
            [action["id"] for action in report["actions"]],
            ["privileged.linux.apt-cache", "privileged.linux.journal-vacuum", "privileged.linux.apt-autoremove"],
        )
        self.assertFalse(report["diskAccess"]["applicable"])

    def test_unsupported_platform_hides_everything(self):
        report = privilege.capabilities(self.ROOT, platform="freebsd")
        self.assertFalse(report["applicable"])
        self.assertEqual(report["actions"], [])
        self.assertIsNone(report["elevation"])

    def test_macos_carries_the_disk_access_probe(self):
        report = privilege.capabilities(self.ROOT, platform="macos", which=which_found(["osascript"]))
        self.assertTrue(report["diskAccess"]["applicable"])


if __name__ == "__main__":
    unittest.main()
