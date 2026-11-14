"""Unit tests for Evidence Schema, Finding, Coverage, and Serialization."""

import json
import unittest

from source_lab.evidence.schema import (
    Coverage,
    EvidenceSpan,
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
    validate_finding,
)


class TestEvidenceSchema(unittest.TestCase):
    def setUp(self):
        self.target = TargetIdentity(
            identifier="test-owner/test-extension",
            repo="test-owner/test-extension",
            version="1.0.0",
        )
        self.finding = Finding(
            finding_id="browser.dynamic-script-registration",
            rule_id="RULE-BROWSER-SCRIPTING",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            phase="static",
            state=FindingState.STATIC_LEAD,
            severity=SeverityLevel.HIGH,
            confidence=0.85,
            evidence=[
                EvidenceSpan(
                    file="src/background.ts",
                    line=42,
                    col=5,
                    symbol="chrome.scripting.executeScript",
                    artifact="source",
                    snippet="chrome.scripting.executeScript({ target: { tabId }, files: ['hook.js'] });",
                )
            ],
            scope=FindingScope(origin="https://example.test", frame="all", world="MAIN"),
            hypothesis="A registered script may modify the page at document start.",
            limitations=["No runtime confirmation under active test profile."],
        )

    # @lat: [[source-tests#Evidence schema#Finding round trip]]
    def test_finding_to_dict_and_from_dict(self):
        d = self.finding.to_dict()
        self.assertEqual(d["schema_version"], 2)
        self.assertEqual(d["finding_id"], "browser.dynamic-script-registration")
        self.assertEqual(d["platform"], "browser-extension")
        self.assertEqual(d["state"], "static_lead")
        self.assertEqual(d["confidence"], 0.85)
        self.assertEqual(len(d["evidence"]), 1)
        self.assertEqual(d["evidence"][0]["line"], 42)

        # Reconstruct from dict
        reconstructed = Finding.from_dict(d)
        self.assertEqual(reconstructed.finding_id, self.finding.finding_id)
        self.assertEqual(reconstructed.state, FindingState.STATIC_LEAD)
        self.assertEqual(reconstructed.target.identifier, "test-owner/test-extension")
        self.assertEqual(reconstructed.evidence[0].line, 42)

    # @lat: [[source-tests#Evidence schema#Finding validation]]
    def test_validate_finding(self):
        errors = validate_finding(self.finding.to_dict())
        self.assertEqual(errors, [])

        # Missing required field
        invalid = self.finding.to_dict()
        del invalid["finding_id"]
        errors_invalid = validate_finding(invalid)
        self.assertIn("finding_id is required", errors_invalid)

    # @lat: [[source-tests#Evidence schema#Coverage serialization]]
    def test_coverage_serialization(self):
        cov = Coverage(
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            parser_mode="ast_tree_sitter",
            scanned_files=45,
            skipped_files=2,
        )
        d = cov.to_dict()
        self.assertEqual(d["schema_version"], 2)
        self.assertEqual(d["scanned_files"], 45)
        self.assertEqual(d["skipped_files"], 2)


if __name__ == "__main__":
    unittest.main()
