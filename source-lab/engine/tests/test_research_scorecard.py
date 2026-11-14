"""H1-H5 scorecard, decision-matrix enrichment, and how both reach the reports and the CLI."""

import json
import tempfile
import unittest
from pathlib import Path

from source_lab.analyzers import BrowserExtensionAnalyzer
from source_lab.cli.run_detection import main
from source_lab.evidence.heuristics import DIMENSIONS, decision_for, dimension_of, enrich_findings, scorecard
from source_lab.evidence.report import ReportExporter
from source_lab.evidence.schema import EvidenceSpan, Finding, FindingScope, FindingState, PlatformType, SeverityLevel, TargetIdentity, validate_finding


def finding(finding_id, severity=SeverityLevel.HIGH, confidence=0.8, platform=PlatformType.BROWSER_EXTENSION, state=FindingState.STATIC_LEAD):
    return Finding(
        finding_id=finding_id, platform=platform, target=TargetIdentity("t"), phase="static", state=state, severity=severity, confidence=confidence,
        evidence=[EvidenceSpan(file="a", line=1)], scope=FindingScope(), hypothesis="h",
    )


class TestScorecard(unittest.TestCase):
    # @lat: [[source-tests#Research scorecard#Every platform maps into H1-H5]]
    def test_rule_ids_of_all_platforms_map_to_the_five_dimensions(self):
        samples = {
            "browser.manifest.broad-host-permissions": "H1", "browser.dom-script-injection": "H2", "browser.manifest.main-world-content-script": "H3",
            "browser.shim.runtime-multiplexer": "H4", "browser.dynamic-eval": "H5", "browser.userscript.broad-match": "H1",
            "windows.pe.injection-api.writeprocessmemory": "H2", "windows.pe.dll-proxy": "H4", "windows.electron.node-integration": "H1", "windows.webview2.document-created-script": "H3",
            "macos.entitlement.disable-library-validation": "H1", "macos.macho.dyld-interposition": "H3", "macos.macho.reexport-dylib": "H4", "macos.entitlement.allow-jit": "H5",
            "android.permission.system_alert_window": "H1", "android.dcl.dex-class-loader": "H2", "android.webview.document-start-script": "H3", "android.apk.injected-native-lib": "H4", "android.webview.js-enabled-bridge": "H5",
            "ios.provision.get-task-allow": "H1", "ios.macho.hook-symbol.MSHookFunction": "H2", "ios.wkwebview.user-script-injection": "H3", "ios.framework.injected": "H4", "ios.entitlement.dynamic-codesigning": "H5",
        }
        for finding_id, expected in samples.items():
            self.assertEqual(dimension_of(finding_id), expected, finding_id)
        self.assertEqual(set(samples.values()), set(DIMENSIONS))
        self.assertIsNone(dimension_of("something.unknown"))

    # @lat: [[source-tests#Research scorecard#Scoring arithmetic]]
    def test_scores_weight_severity_by_confidence_and_cap_each_dimension(self):
        card = scorecard([
            finding("browser.manifest.broad-host-permissions", SeverityLevel.HIGH, 0.5),  # 4 * 0.5 = 2.0 in H1
            finding("browser.dom-script-injection", SeverityLevel.CRITICAL, 1.0),  # 6 in H2
            finding("browser.prototype-wrapping.fetch", SeverityLevel.CRITICAL, 1.0),  # 6 more in H2 -> capped at 10
            finding("browser.cross-world-messaging", SeverityLevel.INFO, 1.0),  # weight 0
            finding("something.unknown"),
        ])
        self.assertEqual(card["dimensions"]["H1"]["score"], 2.0)
        self.assertEqual(card["dimensions"]["H2"]["score"], 10.0)
        self.assertEqual(card["total"], 12.0)
        self.assertEqual(card["band"], "moderate")
        self.assertEqual(card["unmapped_findings"], 1)
        self.assertEqual(scorecard([])["band"], "low")
        self.assertIn("does not show observed behaviour", card["note"])

    # @lat: [[source-tests#Research scorecard#Decision matrix enrichment]]
    def test_enrichment_adds_dimension_and_verification_without_overwriting(self):
        a = finding("windows.pe.dll-proxy", platform=PlatformType.WINDOWS_APP)
        b = finding("browser.debugger-attach")
        b.verification = "custom test"
        c = finding("windows.electron.preload-script", platform=PlatformType.WINDOWS_APP)
        enrich_findings([a, b, c])
        self.assertEqual(a.heuristic, "H4")
        self.assertIn("export table", a.verification)
        self.assertEqual(b.verification, "custom test")
        self.assertIn("uBlock", b.alternative_explanations[0])
        self.assertIsNotNone(decision_for("android.webview.wildcard-origin"))
        self.assertIn("allowedOriginRules", decision_for("android.webview.document-start-script")[1])
        self.assertEqual(validate_finding(a), [])
        restored = Finding.from_dict(a.to_dict())
        self.assertEqual((restored.heuristic, restored.verification), (a.heuristic, a.verification))
        self.assertNotIn("heuristic", finding("browser.dynamic-eval").to_dict())  # optional fields stay out until set

    # @lat: [[source-tests#Research scorecard#Reports carry the scorecard]]
    def test_reports_and_cli_carry_scorecard_dimension_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ext"
            root.mkdir()
            (root / "manifest.json").write_text(json.dumps({"manifest_version": 3, "permissions": ["debugger"], "content_scripts": [{"matches": ["<all_urls>"], "js": ["a.js"], "world": "MAIN"}]}), encoding="utf-8")
            (root / "a.js").write_text("chrome.debugger.attach({tabId: 1}, '1.3')\n", encoding="utf-8")
            out = Path(tmp) / "out"
            self.assertEqual(main([str(root), "-o", str(out)]), 0)
            doc = json.loads((out / "analysis-v2.json").read_text())
            self.assertGreater(doc["scorecard"]["total"], 0)
            self.assertIn("H3", doc["scorecard"]["dimensions"])
            debugger = next(f for f in doc["findings"] if f["finding_id"] == "browser.debugger-attach")
            self.assertEqual(debugger["heuristic"], "H2")
            self.assertTrue(debugger["verification"])
            summary = (out / "summary.md").read_text()
            self.assertIn("H1-H5 Scorecard", summary)
            self.assertIn("Decisive verification test", summary)
            sarif = json.loads((out / "report.sarif").read_text())
            rules = sarif["runs"][0]["tool"]["driver"]["rules"]
            self.assertTrue(any(r.get("properties", {}).get("heuristic") for r in rules))
            # the scorecard never changes a finding's state
            self.assertTrue(all(f["state"] in ("capability", "static_lead") for f in doc["findings"]))

    # @lat: [[source-tests#Research scorecard#A lone userscript]]
    def test_single_userscript_file_is_analysed_without_a_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "x.user.js"
            script.write_text("// ==UserScript==\n// @name X\n// @match *://*/*\n// ==/UserScript==\n", encoding="utf-8")
            findings, coverage = BrowserExtensionAnalyzer(TargetIdentity("t")).analyze(script)
        self.assertIn("browser.userscript.broad-match", {f.finding_id for f in findings})
        self.assertFalse(any("manifest" in lim.lower() for lim in coverage.limitations))


if __name__ == "__main__":
    unittest.main()
