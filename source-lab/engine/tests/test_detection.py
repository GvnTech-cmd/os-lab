"""Unit tests for platform auto-detection."""

import plistlib
import tempfile
import unittest
from pathlib import Path

from source_lab.cli.run_detection import detect_platform
from source_lab.evidence.schema import PlatformType

FIXTURES = Path(__file__).parent / "fixtures" / "injection"


class TestPlatformDetection(unittest.TestCase):
    # @lat: [[source-tests#Platform detection#Browser extension]]
    def test_detects_browser_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text('{"manifest_version": 3}', encoding="utf-8")
            self.assertEqual(detect_platform(root), PlatformType.BROWSER_EXTENSION)

    # @lat: [[source-tests#Platform detection#Android app]]
    def test_detects_android_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AndroidManifest.xml").write_text("<manifest />", encoding="utf-8")
            self.assertEqual(detect_platform(root), PlatformType.ANDROID_APP)

    # @lat: [[source-tests#Platform detection#iOS app]]
    def test_detects_ios_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Fixture.xcodeproj").mkdir()
            with open(root / "Info.plist", "wb") as f:
                plistlib.dump({"CFBundleIdentifier": "com.example.mac"}, f)
            self.assertEqual(detect_platform(root), PlatformType.IOS_APP)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with open(root / "Info.plist", "wb") as f:
                plistlib.dump({"LSRequiresIPhoneOS": True, "UIDeviceFamily": [1, 2]}, f)
            self.assertEqual(detect_platform(root), PlatformType.IOS_APP)

    # @lat: [[source-tests#Platform detection#macOS app]]
    def test_detects_macos_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Fixture.app"
            root.mkdir()
            with open(root / "Info.plist", "wb") as f:
                plistlib.dump({"CFBundleIdentifier": "com.example.mac"}, f)
            self.assertEqual(detect_platform(root), PlatformType.MACOS_APP)

    # @lat: [[source-tests#Platform detection#Windows app]]
    def test_detects_windows_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Fixture.sln").write_text("", encoding="utf-8")
            self.assertEqual(detect_platform(root), PlatformType.WINDOWS_APP)

    # @lat: [[source-tests#Platform detection#Electron app]]
    def test_detects_electron_app(self):
        self.assertEqual(detect_platform(FIXTURES / "windows_fixture"), PlatformType.WINDOWS_APP)


if __name__ == "__main__":
    unittest.main()
