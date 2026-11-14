"""Unit tests for collectors, session bundle writers/readers, and telemetry importers."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from source_lab.collectors.android.importer import AndroidTelemetryImporter
from source_lab.collectors.browser.runner import BrowserCanaryRunner
from source_lab.collectors.ios.importer import IOSTelemetryImporter
from source_lab.collectors.macos.importer import MacOSTelemetryImporter
from source_lab.collectors.windows.importer import WindowsTelemetryImporter
from source_lab.evidence.schema import PlatformType, TargetIdentity
from source_lab.evidence.session import (
    CollectorMetadata,
    SessionBundleReader,
    SessionBundleWriter,
    SessionMetadata,
    SessionScope,
)


class TestCollectorsAndImporters(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="iq_test_collectors_"))
        self.target = TargetIdentity(identifier="test/sample", package_name="com.test.sample")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # @lat: [[source-tests#Collectors#Browser canary bundle]]
    def test_browser_canary_runner_bundle(self):
        runner = BrowserCanaryRunner(output_root=self.tmp_dir, target_id=self.target)
        session_dir = runner.run_session(test_url="https://example.test", duration_sec=0.1)
        self.assertTrue(session_dir.is_dir())
        self.assertTrue((session_dir / "session.json").is_file())
        self.assertTrue((session_dir / "events.jsonl").is_file())
        self.assertTrue((session_dir / "manifest.json").is_file())

        reader = SessionBundleReader(session_dir)
        self.assertTrue(reader.verify_integrity()["valid"])
        events = reader.read_events()
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0]["type"], "session_start")

    # @lat: [[source-tests#Collectors#Unique session ids]]
    def test_import_session_ids_are_unique(self):
        importer = WindowsTelemetryImporter(output_root=self.tmp_dir, target=self.target)
        with patch("source_lab.collectors.windows.importer.time.time", return_value=1700000000):
            first = importer.import_session(pe_sieve_data={"hooks": []})
            second = importer.import_session(pe_sieve_data={"hooks": []})

        self.assertNotEqual(first, second)
        for session_dir in (first, second):
            self.assertTrue(session_dir.is_dir())
            reader = SessionBundleReader(session_dir)
            self.assertTrue(reader.verify_integrity()["valid"])
            events = reader.read_events()
            self.assertEqual(sum(1 for e in events if e["type"] == "session_start"), 1)

    # @lat: [[source-tests#Collectors#Refuse existing session directory]]
    def test_writer_refuses_existing_session_directory(self):
        session_dir = self.tmp_dir / "runtime-sessions" / "ses_fixed"
        meta = SessionMetadata(
            session_id="ses_fixed",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            collector=CollectorMetadata(engine="test"),
            scope=SessionScope(),
        )
        writer = SessionBundleWriter(session_dir, meta)
        writer.append_event(0.0, "session_start", {})
        writer.close()

        with self.assertRaises(FileExistsError):
            SessionBundleWriter(session_dir, meta)

    # @lat: [[source-tests#Collectors#Windows importer]]
    def test_windows_importer(self):
        importer = WindowsTelemetryImporter(output_root=self.tmp_dir, target=self.target)
        pe_sieve = {
            "hooks": [{"module": "user32.dll", "function": "SetWindowsHookExW", "hooked_to": "0x7ffa1234", "type": "detour_jump"}],
            "unbacked_exec": True,
            "unbacked_regions": ["0x1f0000-0x1f1000"],
        }
        etw = [{"EventID": 8, "Data": {"SourceImage": "injected.exe", "TargetImage": "explorer.exe", "StartAddress": "0x7ffa1000"}}]
        session_dir = importer.import_session(pe_sieve_data=pe_sieve, etw_events=etw)

        reader = SessionBundleReader(session_dir)
        self.assertTrue(reader.verify_integrity()["valid"])
        events = reader.read_events()
        event_types = [e["type"] for e in events]
        self.assertIn("memory_hook", event_types)
        self.assertIn("unbacked_exec", event_types)
        self.assertIn("remote_thread", event_types)

    # @lat: [[source-tests#Collectors#macOS importer]]
    def test_macos_importer(self):
        importer = MacOSTelemetryImporter(output_root=self.tmp_dir, target=self.target)
        dyld = ["/Library/Frameworks/Hook.framework/Hook"]
        swizzles = [{"class": "NSURLSession", "selector": "dataTaskWithRequest:", "new_imp": "0x1000"}]
        session_dir = importer.import_session(dyld_images=dyld, swizzled_methods=swizzles)

        reader = SessionBundleReader(session_dir)
        self.assertTrue(reader.verify_integrity()["valid"])
        events = reader.read_events()
        event_types = [e["type"] for e in events]
        self.assertIn("foreign_image_mapped", event_types)
        self.assertIn("objc_swizzle", event_types)

    # @lat: [[source-tests#Collectors#Android importer]]
    def test_android_importer(self):
        importer = AndroidTelemetryImporter(output_root=self.tmp_dir, target=self.target)
        maps = [
            "7f123000-7f125000 r-xp 00000000 00:00 0   /data/local/tmp/frida-agent.so",
            "7f200000-7f201000 rwxp 00000000 00:00 0   [anon:dalvik-main]",
        ]
        threads = ["gum-js-loop", "pool-frida"]
        session_dir = importer.import_session(maps_lines=maps, threads=threads)

        reader = SessionBundleReader(session_dir)
        self.assertTrue(reader.verify_integrity()["valid"])
        events = reader.read_events()
        event_types = [e["type"] for e in events]
        self.assertIn("hook_library_mapped", event_types)
        self.assertIn("instrumentation_thread", event_types)

    # @lat: [[source-tests#Collectors#iOS importer]]
    def test_ios_importer(self):
        importer = IOSTelemetryImporter(output_root=self.tmp_dir, target=self.target)
        dylibs = ["/Library/MobileSubstrate/DynamicLibraries/Tweak.dylib"]
        trampolines = [{"symbol": "_SecItemCopyMatching", "bytes": "50 00 00 58 00 02 1f d6"}]
        session_dir = importer.import_session(loaded_dylibs=dylibs, trampolines=trampolines)

        reader = SessionBundleReader(session_dir)
        self.assertTrue(reader.verify_integrity()["valid"])
        events = reader.read_events()
        event_types = [e["type"] for e in events]
        self.assertIn("tweak_framework_detected", event_types)
        self.assertIn("arm64_trampoline", event_types)


if __name__ == "__main__":
    unittest.main()


import pytest
from source_lab.cli.run_detection import _verified_events
from source_lab.evidence.schema import Coverage


@pytest.mark.parametrize("importer,platform,options", [
    (WindowsTelemetryImporter, PlatformType.WINDOWS_APP, {"pe_sieve_data": {"hooks": [{"module": "owned.dll", "function": "Owned"}]}}),
    (MacOSTelemetryImporter, PlatformType.MACOS_APP, {"dyld_images": ["/owned/Hook.dylib"]}),
    (AndroidTelemetryImporter, PlatformType.ANDROID_APP, {"threads": ["gum-js-loop"]}),
    (IOSTelemetryImporter, PlatformType.IOS_APP, {"loaded_dylibs": ["/owned/MobileSubstrate/Tweak.dylib"]}),
])
@pytest.mark.parametrize("synthetic", [False, True])
def test_signed_native_import_review_and_correlation(tmp_path, importer, platform, options, synthetic):
    target = TargetIdentity(identifier="owned/sample")
    path = importer(tmp_path, target).import_session(**options, synthetic=synthetic)
    reader = SessionBundleReader(path)
    assert reader.verify_integrity()["signature_verified"]
    meta = reader.get_metadata()
    assert meta.platform == platform
    assert "no native collector was launched" in meta.limitations[0]
    coverage = Coverage(platform=platform, target=target)
    events = _verified_events(reader, coverage)
    assert bool(events) is not synthetic
    if synthetic:
        assert any("Synthetic" in text for text in coverage.limitations)
    else:
        mismatch = Coverage(platform=platform, target=TargetIdentity(identifier="other/target"))
        assert _verified_events(reader, mismatch) == []


def test_browser_synthetic_bundle_cannot_supply_live_proof(tmp_path):
    target = TargetIdentity(identifier="owned/browser")
    path = BrowserCanaryRunner(tmp_path, target).run_session(duration_sec=0)
    reader = SessionBundleReader(path)
    assert reader.verify_integrity()["valid"]
    assert reader.get_metadata().collector.profile_mode == "synthetic"
    coverage = Coverage(platform=PlatformType.BROWSER_EXTENSION, target=target)
    assert not _verified_events(reader, coverage)
