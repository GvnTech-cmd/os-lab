import json
import ntpath
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import catalog  # noqa: E402

ROOT = str(Path(__file__).resolve().parents[3])
CATALOG_DIR = os.path.join(ROOT, "cleanup-lab", "catalog")
BASE_ENV = {"HOME": "/home/ada", "PATH": "", "TMPDIR": "/tmp/folders"}


def demo(**overrides):
    entry = {
        "id": "system.demo",
        "name": "Demo cache",
        "category": "system",
        "risk": "low",
        "hint": "A cache.",
        "impact": "Rebuilt on next run.",
        "defaultSelected": False,
        "needsPrivilege": False,
        "paths": {"macos": ["~/Library/Demo"]},
    }
    entry.update(overrides)
    return entry


def write_catalog(base, files):
    folder = os.path.join(base, "cleanup-lab", "catalog")
    os.makedirs(folder, exist_ok=True)
    for name, entries in files.items():
        document = {"version": catalog.CATALOG_VERSION, "family": name.split(".")[0], "entries": entries}
        with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
            json.dump(document, handle)
    return base


class ExpandTest(unittest.TestCase):
    def test_home_forms(self):
        self.assertEqual(catalog.expand("~/Library/Caches", "macos", BASE_ENV)[0], "/home/ada/Library/Caches")
        self.assertEqual(catalog.expand("{home}/x", "macos", BASE_ENV)[0], "/home/ada/x")
        self.assertEqual(catalog.expand("~", "linux", BASE_ENV)[0], "/home/ada")
        self.assertEqual(
            catalog.expand("~user/x", "linux", BASE_ENV), (None, "only '~' and '~/...' are supported")
        )

    def test_cache_context_per_platform(self):
        self.assertEqual(
            catalog.expand("{cache}/pip", "macos", BASE_ENV)[0], "/home/ada/Library/Caches/pip"
        )
        self.assertEqual(
            catalog.expand("{cache}/pip", "linux", dict(BASE_ENV, XDG_CACHE_HOME="/xdg"))[0], "/xdg/pip"
        )
        self.assertEqual(
            catalog.expand("{cache}/pip", "linux", BASE_ENV)[0], "/home/ada/.cache/pip"
        )
        self.assertEqual(
            catalog.expand("{cache}/pip", "windows", dict(BASE_ENV, LOCALAPPDATA="C:/Local")),
            (ntpath.normpath("C:/Local/pip"), ""),
        )

    def test_environment_variable_and_fallback(self):
        self.assertEqual(
            catalog.expand("${XDG_CACHE_HOME}/a", "linux", dict(BASE_ENV, XDG_CACHE_HOME="/xdg"))[0],
            "/xdg/a",
        )
        self.assertEqual(
            catalog.expand("${XDG_CACHE_HOME:-~/.cache}/a", "linux", BASE_ENV)[0],
            "/home/ada/.cache/a",
        )
        self.assertEqual(
            catalog.expand("${XDG_CACHE_HOME}", "linux", BASE_ENV),
            (None, "${XDG_CACHE_HOME} is not set"),
        )

    def test_windows_style_variable(self):
        self.assertEqual(
            catalog.expand("%LOCALAPPDATA%\\Temp", "windows", dict(BASE_ENV, LOCALAPPDATA="C:/Local")),
            (ntpath.normpath("C:/Local/Temp"), ""),
        )
        self.assertEqual(
            catalog.expand("%NOPE%\\Temp", "windows", BASE_ENV), (None, "%NOPE% is not set")
        )

    def test_unavailable_context_is_reported(self):
        self.assertEqual(
            catalog.expand("{localappdata}/x", "linux", BASE_ENV),
            (None, "{localappdata} is not available on this system"),
        )

    def test_relative_path_is_refused(self):
        self.assertEqual(
            catalog.expand("relative/x", "linux", BASE_ENV), (None, "resolves to a relative path")
        )


class LoadTest(unittest.TestCase):
    def test_repository_catalog_loads(self):
        entries = catalog.load(ROOT, BASE_ENV)
        ids = [entry["id"] for entry in entries]
        self.assertEqual(ids[:2], ["browser.chrome.cache", "browser.chrome.history"])
        self.assertEqual(ids[-10:], ['system.user-caches', 'system.user-logs', 'system.trash', 'system.temp', 'system.local-temp', 'system.shared-temp', 'system.crash-reports', 'system.font-caches', 'system.shared-font-caches', 'system.spotlight-index'])
        self.assertEqual(len(ids), 66)
        self.assertEqual({entry["family"] for entry in entries}, {"browser", "developers", "system"})
        self.assertEqual({entry["file"] for entry in entries}, {"browser.json", "developers.json", "system.json"})

    def test_for_platform_filters_without_dropping_the_entry(self):
        with tempfile.TemporaryDirectory() as base:
            write_catalog(base, {"system.json": [demo(), demo(id="system.linux", paths={"linux": ["~/.x"]})]})
            entries = catalog.load(base, BASE_ENV)
            self.assertEqual([entry["id"] for entry in catalog.for_platform(entries, "macos")], ["system.demo"])
            self.assertEqual(len(catalog.for_platform(entries, "linux")), 1)

    def test_duplicate_ids_across_files_are_refused(self):
        with tempfile.TemporaryDirectory() as base:
            write_catalog(
                base,
                {"system.json": [demo()], "system.extra.json": [demo(id="system.demo")]},
            )
            with self.assertRaises(catalog.CatalogError) as raised:
                catalog.load(base, BASE_ENV)
            self.assertIn("duplicate id system.demo", str(raised.exception))

    def test_risky_entry_cannot_be_preselected(self):
        for risk in ("high", "credentials", "privacy"):
            with tempfile.TemporaryDirectory() as base:
                write_catalog(base, {"system.json": [demo(risk=risk, defaultSelected=True)]})
                with self.assertRaises(catalog.CatalogError) as raised:
                    catalog.load(base, BASE_ENV)
                self.assertIn("can never be pre-selected", str(raised.exception))

    def test_malformed_entries_are_named(self):
        cases = [
            ({"id": "demo"}, "is missing"),
            (demo(category="nope"), "category must be one of"),
            (demo(risk="critical"), "risk must be one of"),
            (demo(id="other.demo"), "must start with 'system.'"),
            (demo(id="demo"), "must look like 'family.name'"),
            (demo(paths={}), "paths must name at least one"),
            (demo(paths={"beos": ["/x"]}), "unknown platform"),
            (demo(extra="x"), "unknown key"),
            (demo(owningProcesses="Chrome"), "owningProcesses must be a list"),
            (demo(toolName="/bin/echo"), "toolName must be an executable name"),
            (demo(cleanable="no"), "cleanable must be a boolean"),
        ]
        for entry, message in cases:
            with self.subTest(message=message, entry=entry):
                with tempfile.TemporaryDirectory() as base:
                    write_catalog(base, {"system.json": [entry]})
                    with self.assertRaises(catalog.CatalogError) as raised:
                        catalog.load(base, BASE_ENV)
                    self.assertIn(message, str(raised.exception))

    def test_unknown_file_keys_and_versions_are_refused(self):
        with tempfile.TemporaryDirectory() as base:
            folder = os.path.join(base, "cleanup-lab", "catalog")
            os.makedirs(folder)
            with open(os.path.join(folder, "system.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 2, "family": "system", "entries": [demo()]}, handle)
            with self.assertRaises(catalog.CatalogError) as raised:
                catalog.load(base, BASE_ENV)
            self.assertIn("version must be 1", str(raised.exception))

    def test_report_carries_reasons_instead_of_guessing(self):
        with tempfile.TemporaryDirectory() as base:
            env = {"HOME": os.path.join(base, "home"), "PATH": "", "TMPDIR": "/tmp"}
            os.makedirs(env["HOME"])
            write_catalog(base, {"system.json": [demo(paths={"linux": ["${XDG_CACHE_HOME}/x", "~/y"]})]})
            report = catalog.report(base, "linux", env)
            paths = report["entries"][0]["paths"]
            self.assertEqual(paths[0], {"template": "${XDG_CACHE_HOME}/x", "path": None,
                                        "reason": "${XDG_CACHE_HOME} is not set", "source": "catalog"})
            self.assertEqual(paths[1]["path"], os.path.join(env["HOME"], "y"))


class SchemaTest(unittest.TestCase):
    def schema(self):
        with open(os.path.join(CATALOG_DIR, "schema.json"), "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_loader_required_keys_match_the_schema(self):
        schema = self.schema()
        self.assertEqual(
            set(schema["$defs"]["entry"]["required"]), set(catalog.REQUIRED_ENTRY_KEYS)
        )

    def test_every_catalog_file_uses_only_declared_fields(self):
        schema = self.schema()
        entry_schema = schema["$defs"]["entry"]
        required = set(entry_schema["required"])
        properties = set(entry_schema["properties"])
        risks = set(entry_schema["properties"]["risk"]["enum"])
        categories = set(entry_schema["properties"]["category"]["enum"])
        platforms = set(entry_schema["properties"]["paths"]["properties"])
        for name in sorted(os.listdir(CATALOG_DIR)):
            if not name.endswith(".json") or name == "schema.json":
                continue
            with self.subTest(file=name):
                with open(os.path.join(CATALOG_DIR, name), "r", encoding="utf-8") as handle:
                    document = json.load(handle)
                self.assertEqual(document["version"], catalog.CATALOG_VERSION)
                for entry in document["entries"]:
                    self.assertLessEqual(required, set(entry), "missing a schema-required key")
                    self.assertLessEqual(set(entry), properties, "field not declared in the schema")
                    self.assertIn(entry["risk"], risks)
                    self.assertIn(entry["category"], categories)
                    self.assertLessEqual(set(entry["paths"]), platforms)


if __name__ == "__main__":
    unittest.main()
