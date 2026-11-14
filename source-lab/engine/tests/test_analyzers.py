"""Unit tests for multi-platform static analyzers (Browser, Windows, macOS, Android, iOS)."""

import unittest
import tempfile
from pathlib import Path

from source_lab.analyzers import (
    AndroidAppAnalyzer,
    BrowserExtensionAnalyzer,
    IOSAppAnalyzer,
    MacOSAppAnalyzer,
    WindowsAppAnalyzer,
)
from source_lab.evidence.schema import FindingState, PlatformType, SeverityLevel, TargetIdentity

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "injection"


class TestStaticAnalyzers(unittest.TestCase):
    # @lat: [[source-tests#Static analyzers#Browser positive and clean]]
    def test_browser_analyzer_positive_vs_clean(self):
        pos_dir = FIXTURES_DIR / "browser_positive"
        clean_dir = FIXTURES_DIR / "browser_clean"

        analyzer = BrowserExtensionAnalyzer(TargetIdentity("test/browser"))
        self.assertTrue(analyzer.identify(pos_dir))
        self.assertTrue(analyzer.identify(clean_dir))

        # Positive fixture analysis
        pos_findings, pos_cov = analyzer.analyze(pos_dir)
        self.assertGreater(len(pos_findings), 0)
        finding_ids = [f.finding_id for f in pos_findings]
        self.assertIn("browser.manifest.broad-host-permissions", finding_ids)
        self.assertIn("browser.manifest.content-script-registration", finding_ids)
        self.assertIn("browser.dom-script-injection", finding_ids)
        self.assertIn("browser.prototype-wrapping.fetch", finding_ids)
        self.assertEqual(pos_cov.platform, PlatformType.BROWSER_EXTENSION)

        # Clean fixture analysis: no injection call-sites
        clean_findings, clean_cov = analyzer.analyze(clean_dir)
        clean_ids = [f.finding_id for f in clean_findings]
        self.assertNotIn("browser.dom-script-injection", clean_ids)
        self.assertNotIn("browser.prototype-wrapping.fetch", clean_ids)

    # @lat: [[source-tests#Static analyzers#Android project]]
    def test_android_analyzer(self):
        android_dir = FIXTURES_DIR / "android_fixture"
        analyzer = AndroidAppAnalyzer(TargetIdentity("test/android"))
        self.assertTrue(analyzer.identify(android_dir))

        findings, cov = analyzer.analyze(android_dir)
        self.assertGreater(len(findings), 0)
        finding_ids = [f.finding_id for f in findings]
        self.assertIn("android.manifest.debuggable", finding_ids)
        self.assertIn("android.manifest.exported-activity", finding_ids)
        self.assertIn("android.permission.system_alert_window", finding_ids)
        self.assertIn("android.webview.js-interface-bridge", finding_ids)
        self.assertIn("android.webview.allow-universal-access", finding_ids)
        self.assertEqual(cov.platform, PlatformType.ANDROID_APP)

    # @lat: [[source-tests#Static analyzers#iOS project]]
    def test_ios_analyzer(self):
        ios_dir = FIXTURES_DIR / "ios_fixture"
        analyzer = IOSAppAnalyzer(TargetIdentity("test/ios"))
        self.assertTrue(analyzer.identify(ios_dir))

        findings, cov = analyzer.analyze(ios_dir)
        self.assertGreater(len(findings), 0)
        finding_ids = [f.finding_id for f in findings]
        self.assertIn("ios.plist.allows-arbitrary-loads", finding_ids)
        self.assertIn("ios.plist.custom-url-scheme", finding_ids)
        self.assertIn("ios.wkwebview.user-script-injection", finding_ids)
        self.assertIn("ios.objc.method-swizzle", finding_ids)
        self.assertEqual(cov.platform, PlatformType.IOS_APP)

    # @lat: [[source-tests#Static analyzers#iOS plist parse failure]]
    def test_ios_invalid_plist_records_limitation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ios_fixture"
            root.mkdir()
            (root / "Info.plist").write_text("not a plist", encoding="utf-8")

            analyzer = IOSAppAnalyzer(TargetIdentity("test/ios-invalid"))
            findings, cov = analyzer.analyze(root)

            self.assertFalse(any(f.finding_id.startswith("ios.plist") for f in findings))
            self.assertTrue(any("Failed to parse Info.plist" in limit for limit in cov.limitations))

    # @lat: [[source-tests#Static analyzers#Windows Electron]]
    def test_windows_analyzer(self):
        win_dir = FIXTURES_DIR / "windows_fixture"
        analyzer = WindowsAppAnalyzer(TargetIdentity("test/windows"))
        self.assertTrue(analyzer.identify(win_dir))

        findings, cov = analyzer.analyze(win_dir)
        self.assertGreater(len(findings), 0)
        finding_ids = [f.finding_id for f in findings]
        self.assertIn("windows.electron.node-integration", finding_ids)
        self.assertIn("windows.electron.context-isolation-disabled", finding_ids)
        self.assertIn("windows.webview2.document-created-script", finding_ids)
        self.assertEqual(cov.platform, PlatformType.WINDOWS_APP)

    # @lat: [[source-tests#Static analyzers#macOS sources]]
    def test_macos_analyzer(self):
        # Can analyze Objective-C files and plists in ios_fixture
        ios_dir = FIXTURES_DIR / "ios_fixture"
        analyzer = MacOSAppAnalyzer(TargetIdentity("test/macos"))
        findings, cov = analyzer.analyze(ios_dir)
        self.assertGreater(len(findings), 0)
        finding_ids = [f.finding_id for f in findings]
        self.assertIn("macos.objc.method-swizzle", finding_ids)
        self.assertIn("macos.wkwebview.user-script", finding_ids)
        self.assertEqual(cov.platform, PlatformType.MACOS_APP)


if __name__ == "__main__":
    unittest.main()
