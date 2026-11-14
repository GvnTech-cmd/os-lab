"""CLNP-01: permission probes classify only what a fresh read-only probe proves.

Every probe runs through a fake ``prober`` — no real TCC-protected folder is
ever listed, and no real user folder is touched (README rule 8).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleanup_lab import permissions, privilege  # noqa: E402


class Prober:
    """Fake os.listdir: raises per path, remembers which paths it saw."""

    def __init__(self, denied=(), missing=(), errors=()):
        self.denied = set(denied)
        self.missing = set(missing)
        self.errors = dict(errors)
        self.seen = []

    def __call__(self, path):
        self.seen.append(path)
        if path in self.denied:
            raise PermissionError(13, "Permission denied")
        if path in self.missing:
            raise FileNotFoundError(2, "No such file or directory")
        if path in self.errors:
            raise self.errors[path]
        return []


def env_home(base):
    return {"HOME": base, "USERPROFILE": base, "PATH": ""}


class FullDiskAccessProbe(unittest.TestCase):
    def test_macos_denied_probe_reports_grant_guidance_and_url(self):
        prober = Prober(denied={"/Users/u/Library/Safari", "/Users/u/Library/Mail"})
        record = permissions.fda("macos", env_home("/Users/u"), prober=prober)
        self.assertTrue(record["applicable"])
        self.assertIs(record["granted"], False)
        self.assertEqual(len(record["paths"]), 2)
        self.assertFalse(record["paths"][0]["readable"])
        self.assertIn("Full Disk Access", record["guidance"])
        self.assertEqual(prober.seen, ["/Users/u/Library/Safari", "/Users/u/Library/Mail"])

    def test_macos_granted_probe_has_no_guidance(self):
        record = permissions.fda("macos", env_home("/Users/u"), prober=Prober())
        self.assertIs(record["granted"], True)
        self.assertEqual(record["guidance"], "")

    def test_missing_folder_is_not_evidence(self):
        prober = Prober(missing={"/Users/u/Library/Mail"})
        record = permissions.fda("macos", env_home("/Users/u"), prober=prober)
        # Safari readable, Mail absent: readable is proven True, Mail makes no claim
        self.assertIs(record["granted"], True)
        self.assertIsNone(record["paths"][1]["readable"])

    def test_other_oserror_is_unknown_not_denied(self):
        prober = Prober(errors={"/Users/u/Library/Safari": OSError(5, "Input/output error")})
        record = permissions.fda("macos", env_home("/Users/u"), prober=prober)
        # Safari answers with an I/O error (no claim either way); Mail readable
        # proves the grant exists — denial (False) still wins over readable.
        self.assertIsNone(record["paths"][0]["readable"])
        prober2 = Prober(errors={"/Users/u/Library/Mail": OSError(5, "Input/output error")},
                         denied={"/Users/u/Library/Safari"})
        record2 = permissions.fda("macos", env_home("/Users/u"), prober=prober2)
        self.assertIs(record2["granted"], False)

    def test_not_applicable_elsewhere(self):
        record = permissions.fda("linux", env_home("/home/u"), prober=Prober())
        self.assertFalse(record["applicable"])
        self.assertIsNone(record["granted"])
        self.assertEqual(record["paths"], [])
        self.assertIn("macOS privacy setting", record["reason"])


class Delegation(unittest.TestCase):
    def test_privilege_disk_access_keeps_the_cln20_shape(self):
        prober = Prober(denied={"/Users/u/Library/Mail"})
        legacy = privilege.disk_access("macos", env_home("/Users/u"), prober=prober)
        moved = permissions.fda("macos", env_home("/Users/u"), prober=Prober(denied={"/Users/u/Library/Mail"}))
        self.assertEqual(set(legacy), {"applicable", "granted", "paths", "guidance"})
        self.assertEqual(legacy["granted"], moved["granted"])
        self.assertEqual([p["path"] for p in legacy["paths"]], [p["path"] for p in moved["paths"]])
        self.assertEqual(legacy["guidance"], moved["guidance"])

    def test_privilege_disk_access_windows_payload_unchanged(self):
        legacy = privilege.disk_access("windows", env_home("/Users/u"), prober=Prober())
        self.assertEqual(
            legacy,
            {"applicable": False, "granted": None, "paths": [], "guidance": "",
             "reason": "Full Disk Access is a macOS privacy setting."},
        )


class ProbeRegistry(unittest.TestCase):
    def test_registry_covers_all_ids_in_order(self):
        payload = permissions.probe("macos", env_home("/Users/u"), prober=Prober())
        ids = [record["id"] for record in payload["permissions"]]
        self.assertEqual(ids, [
            "macos-full-disk-access", "macos-desktop-folder", "macos-documents-folder",
            "macos-downloads-folder", "hidden-roots",
        ])

    def test_folder_grants_are_reactive_only(self):
        prober = Prober()
        payload = permissions.probe("macos", env_home("/Users/u"), prober=prober)
        # No consent-dialog-triggering probe happened: only the two FDA paths.
        self.assertEqual(len(prober.seen), 2)
        for record in payload["permissions"]:
            if record["id"] == "macos-full-disk-access":
                continue
            self.assertIsNone(record["granted"])
            self.assertEqual(record["results"], [])

    def test_non_macos_records_are_not_applicable(self):
        payload = permissions.probe("linux", env_home("/home/u"), prober=Prober())
        by_id = {record["id"]: record for record in payload["permissions"]}
        for id_ in ("macos-full-disk-access", "macos-desktop-folder", "macos-documents-folder", "macos-downloads-folder"):
            self.assertFalse(by_id[id_]["applicable"])
        self.assertTrue(by_id["hidden-roots"]["applicable"])
        self.assertTrue(by_id["hidden-roots"]["guidance"])


class Classification(unittest.TestCase):
    def test_desktop_denied_classifies_to_folder_permission(self):
        path = "/Users/u/Desktop/SomeApp"
        result = permissions.classify_unreadable(
            [path], platform="macos", env=env_home("/Users/u"), prober=Prober(denied={path})
        )
        self.assertEqual(result["classified"][0]["permissionId"], "macos-desktop-folder")
        self.assertEqual(result["unmatched"], [])

    def test_library_tcc_folder_classifies_to_full_disk_access(self):
        path = "/Users/u/Library/Mail/V3/Attachments"
        result = permissions.classify_unreadable(
            [path], platform="macos", env=env_home("/Users/u"), prober=Prober(denied={path})
        )
        self.assertEqual(result["classified"][0]["permissionId"], "macos-full-disk-access")

    def test_plain_library_cache_path_classifies_to_hidden_roots(self):
        path = "/Users/u/Library/SomeCache"
        result = permissions.classify_unreadable(
            [path], platform="macos", env=env_home("/Users/u"), prober=Prober(denied={path})
        )
        self.assertEqual(result["classified"][0]["permissionId"], "hidden-roots")

    def test_recovered_path_makes_no_claim(self):
        path = "/Users/u/Desktop/Gone"
        result = permissions.classify_unreadable(
            [path], platform="macos", env=env_home("/Users/u"), prober=Prober()
        )
        self.assertEqual(result["classified"], [])
        self.assertEqual(result["unmatched"][0]["state"], "recovered")

    def test_linux_dot_directory_classifies_to_hidden_roots(self):
        path = "/home/u/.config/locked-app"
        result = permissions.classify_unreadable(
            [path], platform="linux", env=env_home("/home/u"), prober=Prober(denied={path})
        )
        self.assertEqual(result["classified"][0]["permissionId"], "hidden-roots")

    def test_denied_path_outside_known_scopes_stays_unmatched(self):
        path = "/srv/shared/other-user"
        result = permissions.classify_unreadable(
            [path], platform="linux", env=env_home("/home/u"), prober=Prober(denied={path})
        )
        self.assertEqual(result["classified"], [])
        self.assertEqual(result["unmatched"][0]["state"], "permission-denied")

    def test_empty_and_non_string_paths_are_ignored(self):
        result = permissions.classify_unreadable(["", None, "/x"], platform="linux", env=env_home("/home/u"), prober=Prober())
        self.assertEqual(len(result["unmatched"]), 1)


class Report(unittest.TestCase):
    def test_report_folds_classification_into_records(self):
        denied = "/Users/u/Downloads/Locked"
        prober = Prober(denied={denied})
        payload = permissions.report(
            [denied], platform="macos", env=env_home("/Users/u"), prober=prober
        )
        by_id = {record["id"]: record for record in payload["permissions"]}
        self.assertEqual(by_id["macos-downloads-folder"]["granted"], False)
        self.assertEqual(by_id["macos-downloads-folder"]["grantUrl"], permissions.FDA_GRANT_URL)
        self.assertIn("Downloads", by_id["macos-downloads-folder"]["guidance"])
        self.assertEqual(by_id["macos-downloads-folder"]["results"][0]["path"], denied)

    def test_report_without_scan_paths_has_no_classification_key(self):
        payload = permissions.report(platform="linux", env=env_home("/home/u"), prober=Prober())
        self.assertNotIn("classification", payload)


if __name__ == "__main__":
    unittest.main()
