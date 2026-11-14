"""The audit chain uses private, generated state and detects changed rows."""
import os
import sqlite3
import sys
import tempfile
import unittest
import io
from unittest import mock

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
from cleanup_lab import history, cli  # noqa: E402


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cln-history-")
        self.env = {"OSLAB_CLEANUP_STATE": os.path.join(self.tmp.name, "state")}
        self.result = {"planId": "abc", "mode": "trash", "cancelled": False,
                       "totals": {"items": 1, "bytes": 42},
                       "results": [{"path": "/test/cache", "bytes": 42,
                                    "status": "trashed", "mode": "trash"}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_then_append_and_verify(self):
        self.assertEqual(history.read(env=self.env)["total"], 0)
        history.prepare(env=self.env)
        self.assertEqual(history.append(self.result, env=self.env), 1)
        self.assertEqual(history.append(self.result, env=self.env), 2)
        report = history.read(env=self.env, limit=1, verify=True)
        self.assertEqual(report["total"], 2)
        self.assertEqual([row["id"] for row in report["entries"]], [2])
        self.assertEqual(report["entries"][0]["result"]["results"][0]["path"], "/test/cache")
        if os.name != "nt":
            self.assertEqual(os.stat(os.path.join(self.env["OSLAB_CLEANUP_STATE"], history.KEY)).st_mode & 0o777, 0o600)

    def test_changed_payload_and_removed_middle_row_are_detected(self):
        history.prepare(env=self.env)
        history.append(self.result, env=self.env)
        history.append(self.result, env=self.env)
        path = os.path.join(self.env["OSLAB_CLEANUP_STATE"], history.DATABASE)
        with sqlite3.connect(path) as db:
            db.execute("UPDATE history SET payload = 'tampered' WHERE id = 1")
        with self.assertRaises(history.HistoryError):
            history.read(env=self.env, verify=True)
        with self.assertRaises(history.HistoryError):
            history.append(self.result, env=self.env)
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM history WHERE id = 1")
        with self.assertRaises(history.HistoryError):
            history.read(env=self.env, verify=True)

    def test_missing_key_and_database_are_refused(self):
        history.prepare(env=self.env)
        folder = self.env["OSLAB_CLEANUP_STATE"]
        os.unlink(os.path.join(folder, history.KEY))
        with self.assertRaises(history.HistoryError):
            history.prepare(env=self.env)

    def test_truncated_tail_is_detected(self):
        history.prepare(env=self.env)
        history.append(self.result, env=self.env)
        path = os.path.join(self.env["OSLAB_CLEANUP_STATE"], history.DATABASE)
        with sqlite3.connect(path) as db:
            db.execute("DELETE FROM history WHERE id = 1")
        with self.assertRaises(history.HistoryError):
            history.read(env=self.env, verify=True)

    def test_bad_limit(self):
        with self.assertRaises(ValueError):
            history.read(env=self.env, limit=0)

    def test_cli_verify_detects_tampering(self):
        history.prepare(env=self.env)
        history.append(self.result, env=self.env)
        with mock.patch.dict(os.environ, self.env):
            output = io.StringIO()
            self.assertEqual(cli.main(["history", "--verify", "--json"], stream=output), 0)
            self.assertEqual(__import__("json").loads(output.getvalue())["total"], 1)
            path = os.path.join(self.env["OSLAB_CLEANUP_STATE"], history.DATABASE)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE history SET payload = '{}' WHERE id = 1")
            with mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(cli.main(["history", "--verify"], stream=io.StringIO()), 1)


if __name__ == "__main__":
    unittest.main()
