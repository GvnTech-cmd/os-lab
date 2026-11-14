import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import cli  # noqa: E402
from cleanup_lab.catalog import CatalogError  # noqa: E402

READY = {
    "engine": {"name": "cleanup-lab", "version": "0.1.0", "python": "3.12.1", "mode": "stdlib"},
    "state": "ready",
    "platform": {"id": "macos", "label": "macOS", "supported": True},
    "home": "/home/ada",
    "stateDir": "/home/ada/Library/Application Support/os-lab/cleanup",
    "requirements": [
        {"id": "platform", "label": "Supported operating system", "found": True,
         "required": True, "hint": "Runs on macOS, Linux and Windows.", "detail": "macOS"},
    ],
    "capabilities": [
        {"id": "detectors", "label": "Detector catalog", "found": False, "detail": "No detector catalog yet"},
    ],
    "reasons": [],
    "checkedAt": 1.0,
}


class CliTest(unittest.TestCase):
    def run_cli(self, argv, report=None):
        stream = io.StringIO()
        with mock.patch.object(cli, "probe", return_value=report or READY):
            code = cli.main(argv, stream=stream)
        return code, stream.getvalue()

    def test_status_exit_codes_follow_the_state(self):
        self.assertEqual(self.run_cli(["status"])[0], 0)
        needs_setup = dict(READY, state="needs-setup", reasons=["Set OSLAB_CLEANUP_STATE to a writable folder."])
        code, text = self.run_cli(["status"], needs_setup)
        self.assertEqual(code, 1)
        self.assertIn("What to fix:", text)
        self.assertIn("Set OSLAB_CLEANUP_STATE", text)

    def test_json_is_machine_readable(self):
        code, text = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["state"], "ready")

    def test_doctor_lists_every_hint(self):
        report = dict(
            READY,
            state="needs-setup",
            reasons=["Install Python 3.11 or newer."],
            requirements=[
                {"id": "python", "label": "Python 3.11 or newer", "found": False,
                 "required": True, "hint": "Install Python 3.11 or newer.", "detail": "3.9.6"},
                {"id": "home", "label": "Home folder readable", "found": True,
                 "required": True, "hint": "Make it readable.", "detail": "/home/ada"},
            ],
        )
        code, text = self.run_cli(["doctor"], report)
        self.assertEqual(code, 1)
        self.assertIn("Install Python 3.11 or newer.", text)
        self.assertIn("(needs attention)", text)
        self.assertIn("Make it readable.", text)

    def test_doctor_ready_message_makes_no_scan_claim(self):
        code, text = self.run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("nothing has been scanned yet", text)
        self.assertNotIn("can scan and plan", text)

    def test_control_characters_in_values_are_escaped(self):
        report = dict(READY, home="/home/\x1b[31mada")
        code, text = self.run_cli(["doctor"], report)
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", text)
        self.assertIn("\\x1b", text)

    def test_unknown_subcommand_is_a_usage_error(self):
        stream = io.StringIO()
        with mock.patch.object(cli, "probe") as probe, mock.patch("sys.stderr", stream):
            with self.assertRaises(SystemExit) as raised:
                cli.main(["scan"], stream=io.StringIO())
        self.assertEqual(raised.exception.code, 2)
        probe.assert_not_called()

    def test_no_subcommand_prints_help_and_returns_usage(self):
        stream = io.StringIO()
        with mock.patch.object(cli, "probe") as probe:
            code = cli.main([], stream=stream)
        self.assertEqual(code, 2)
        self.assertIn("status|doctor|catalog", stream.getvalue())
        probe.assert_not_called()

    def test_catalog_prints_paths_and_reasons(self):
        report = {
            "platform": "linux",
            "entries": [
                {"id": "system.demo", "name": "Demo", "risk": "low", "defaultSelected": False,
                 "paths": [{"template": "~/a", "path": "/home/ada/a", "reason": ""}]},
                {"id": "system.two", "name": "Two", "risk": "medium", "defaultSelected": False,
                 "paths": [{"template": "${XDG_CACHE_HOME}/b", "path": None,
                            "reason": "${XDG_CACHE_HOME} is not set"}]},
            ],
        }
        stream = io.StringIO()
        with mock.patch.object(cli, "catalog_report", return_value=report):
            code = cli.main(["catalog"], stream=stream)
        self.assertEqual(code, 0)
        text = stream.getvalue()
        self.assertIn("2 entries", text)
        self.assertIn("/home/ada/a", text)
        self.assertIn("${XDG_CACHE_HOME} is not set", text)

    def test_catalog_json_is_machine_readable(self):
        report = {"platform": "macos", "entries": []}
        stream = io.StringIO()
        with mock.patch.object(cli, "catalog_report", return_value=report):
            code = cli.main(["catalog", "--json"], stream=stream)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue()), report)

    def test_invalid_catalog_is_a_problem_not_a_usage_error(self):
        stderr = io.StringIO()
        with mock.patch.object(cli, "catalog_report", side_effect=CatalogError("system.json: broken")), \
                mock.patch("sys.stderr", stderr):
            code = cli.main(["catalog"], stream=io.StringIO())
        self.assertEqual(code, 1)
        self.assertIn("system.json: broken", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
