"""CLNP-20: custom overlay entries obey the shipped catalog's own rules.

Every creation path is validated read-only against a generated temp tree; no
real user folder is touched (README rule 8).
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import catalog, custom_catalog, safety  # noqa: E402

PLATFORM = "macos"


def env_state(base):
    return {"HOME": base, "USERPROFILE": base, "OSLAB_CLEANUP_STATE": base, "PATH": ""}


class CreationPathValidation(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.folder = os.path.join(self.base, "MyCache")
        os.makedirs(self.folder)

    def test_relative_path_is_refused(self):
        with self.assertRaises(custom_catalog.CustomCatalogError):
            custom_catalog.validate_creation_path("relative/path", PLATFORM)

    def test_missing_and_symlink_paths_are_refused(self):
        with self.assertRaises(custom_catalog.CustomCatalogError):
            custom_catalog.validate_creation_path(os.path.join(self.base, "gone"), PLATFORM)
        target = os.path.join(self.base, "real")
        os.makedirs(target)
        link = os.path.join(self.base, "link")
        os.symlink(target, link)
        with self.assertRaises(custom_catalog.CustomCatalogError):
            custom_catalog.validate_creation_path(link, PLATFORM)

    def test_files_are_refused(self):
        marker = os.path.join(self.base, "file.txt")
        with open(marker, "w") as handle:
            handle.write("x")
        with self.assertRaises(custom_catalog.CustomCatalogError):
            custom_catalog.validate_creation_path(marker, PLATFORM)

    def test_protected_and_system_roots_are_refused(self):
        env = env_state(self.base)
        with self.assertRaises(custom_catalog.CustomCatalogError):
            custom_catalog.validate_creation_path(self.base, PLATFORM, env=env)  # == home
        for system in safety.SYSTEM_ROOTS.get(PLATFORM, ()):
            if os.path.isdir(system):
                with self.assertRaises(custom_catalog.CustomCatalogError):
                    custom_catalog.validate_creation_path(system, PLATFORM)
                return
        self.fail("the macOS system roots table needs a folder that exists here")

    def test_tilde_paths_expand_to_the_temp_home(self):
        canonical = custom_catalog.validate_creation_path("~/MyCache", PLATFORM, env_state(self.base))
        self.assertEqual(canonical, os.path.normpath(self.folder))


class Entries(unittest.TestCase):
    def test_entry_passes_the_shipped_validator_and_resolves(self):
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "cache"))
            entry = custom_catalog.build_entry("My Cache", os.path.join(base, "cache"), PLATFORM,
                                               clock=lambda: 1000.0)
            self.assertEqual(entry["id"], "custom.my-cache")
            self.assertEqual(entry["family"], "custom")
            self.assertFalse(entry["defaultSelected"])
            self.assertEqual(entry["risk"], "low")
            self.assertEqual(entry["file"], "<overlay>")
            resolved = catalog.resolve(entry, PLATFORM, env=env_state(base))
            self.assertEqual(resolved[0]["path"], os.path.join(base, "cache"))

    def test_ids_derive_from_the_name_and_dodge_collisions(self):
        with tempfile.TemporaryDirectory() as base:
            folder = os.path.join(base, "cache")
            os.makedirs(folder)
            first = custom_catalog.build_entry("My Cache", folder, PLATFORM,
                                               taken=("custom.my-cache",), clock=lambda: 1)
            self.assertEqual(first["id"], "custom.my-cache-2")

    def test_add_is_once_per_path_and_persists(self):
        with tempfile.TemporaryDirectory() as base:
            env = env_state(base)
            folder = os.path.join(base, "cache")
            os.makedirs(folder)
            result = custom_catalog.add("Cache", folder, [], platform=PLATFORM, env=env,
                                        clock=lambda: 1000.0)
            self.assertEqual(len(result["entries"]), 1)
            with self.assertRaises(custom_catalog.CustomCatalogError):
                custom_catalog.add("Again", folder, result["entries"], platform=PLATFORM, env=env)
            loaded = custom_catalog.load(env=env)
            self.assertEqual(loaded["entries"][0]["id"], "custom.cache")

    def test_remove_and_unknown_id(self):
        with tempfile.TemporaryDirectory() as base:
            env = env_state(base)
            folder = os.path.join(base, "cache")
            os.makedirs(folder)
            result = custom_catalog.add("Cache", folder, [], platform=PLATFORM, env=env)
            removed = custom_catalog.remove(result["entries"][0]["id"], result["entries"], env=env)
            self.assertEqual(removed["entries"], [])
            with self.assertRaises(custom_catalog.CustomCatalogError):
                custom_catalog.remove("custom.ghost", removed["entries"], env=env)

    def test_corrupt_store_is_empty_with_an_error(self):
        with tempfile.TemporaryDirectory() as base:
            env = env_state(base)
            with open(os.path.join(base, "custom-catalog.json"), "w", encoding="utf-8") as handle:
                handle.write("{nope")
            loaded = custom_catalog.load(env=env)
            self.assertEqual(loaded["entries"], [])
            self.assertIn("unreadable", loaded["error"])


class CatalogMerge(unittest.TestCase):
    def test_load_merges_the_overlay_and_shipped_ids_win(self):
        with tempfile.TemporaryDirectory() as base:
            env = env_state(base)
            root = tempfile.mkdtemp()
            os.makedirs(os.path.join(root, "cleanup-lab", "catalog"))
            with open(os.path.join(root, "cleanup-lab", "catalog", "custom.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "family": "custom", "entries": [{
                    "id": "custom.shipped", "name": "Shipped", "category": "system", "risk": "low",
                    "hint": "h", "impact": "i", "defaultSelected": False, "needsPrivilege": False,
                    "paths": {PLATFORM: ["/tmp/shipped"]},
                }]}, handle)
            folder = os.path.join(base, "cache")
            os.makedirs(folder)
            custom_catalog.add("Cache", folder, [], platform=PLATFORM, env=env)
            entries = catalog.load(root, env=env)
            ids = [entry["id"] for entry in entries]
            self.assertIn("custom.cache", ids)
            self.assertIn("custom.shipped", ids)
            # A colliding overlay id is skipped, not an error.
            os.makedirs(os.path.join(base, "other"))
            custom_catalog.add("Shipped Two", os.path.join(base, "other"), [], platform=PLATFORM, env=env,
                               catalog_ids=["custom.cache"], clock=lambda: 2000.0)
            entries = catalog.load(root, env=env)
            self.assertEqual([entry["id"] for entry in entries].count("custom.shipped"), 1)

    def test_report_carries_the_overlay_error(self):
        with tempfile.TemporaryDirectory() as base:
            root = tempfile.mkdtemp()
            os.makedirs(os.path.join(root, "cleanup-lab", "catalog"))
            with open(os.path.join(base, "custom-catalog.json"), "w", encoding="utf-8") as handle:
                handle.write("{broken")
            report = catalog.report(root, PLATFORM, env=env_state(base))
            self.assertIn("unreadable", report["overlayError"])


if __name__ == "__main__":
    unittest.main()
