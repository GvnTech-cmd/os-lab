"""Unit tests for Correlator, confidence scoring, and state transitions."""

import unittest

from source_lab.evidence.correlate import Correlator
from source_lab.evidence.schema import (
    EvidenceSpan,
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
)


class TestCorrelator(unittest.TestCase):
    def setUp(self):
        self.correlator = Correlator(weight_static=0.35, weight_dynamic=0.65, default_env_discount=0.1)
        self.target = TargetIdentity(identifier="test/ext")

    # @lat: [[source-tests#Correlator#Confidence formula]]
    def test_calculate_confidence_formula(self):
        # Static only (0.6), dynamic 0.0, env discount 0.1
        # C = (0.35 * 0.6 + 0.65 * 0.0) / (1 + 0.1) = 0.21 / 1.1 = ~0.1909
        conf_not_observed = self.correlator.calculate_confidence(0.6, 0.0, 0.1)
        self.assertAlmostEqual(conf_not_observed, 0.21 / 1.1, places=3)

        # Correlated: Static 0.8, dynamic 1.0, env discount 0.1
        # C = (0.35 * 0.8 + 0.65 * 1.0) / 1.1 = (0.28 + 0.65) / 1.1 = 0.93 / 1.1 = ~0.8455
        conf_correlated = self.correlator.calculate_confidence(0.8, 1.0, 0.1)
        self.assertAlmostEqual(conf_correlated, 0.93 / 1.1, places=3)

    # @lat: [[source-tests#Correlator#State transitions]]
    def test_correlate_state_transitions(self):
        static_finding = Finding(
            finding_id="browser.content-script.injection",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            phase="static",
            state=FindingState.STATIC_LEAD,
            severity=SeverityLevel.HIGH,
            confidence=0.8,
            evidence=[EvidenceSpan(file="content.js", line=10, symbol="createElement('script')")],
            scope=FindingScope(),
            hypothesis="Script element dynamically inserted into page.",
        )

        untriggered_finding = Finding(
            finding_id="browser.native-messaging",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            phase="static",
            state=FindingState.STATIC_LEAD,
            severity=SeverityLevel.MEDIUM,
            confidence=0.7,
            evidence=[EvidenceSpan(file="bg.js", line=5, symbol="connectNative")],
            scope=FindingScope(),
            hypothesis="Native messaging host communication.",
        )

        runtime_events = [
            {
                "seq": 1,
                "t_ms": 15.2,
                "type": "dom_mutation",
                "data": {"src": "content.js", "action": "added", "node": "SCRIPT"},
            },
            {
                "seq": 2,
                "t_ms": 25.0,
                "type": "prototype_tamper",
                "data": {"api": "window.fetch", "hook_type": "proxy"},
            },
        ]

        correlated = self.correlator.correlate(
            static_findings=[static_finding, untriggered_finding],
            runtime_events=runtime_events,
            env_discount=0.1,
            target_override=self.target,
        )

        self.assertEqual(len(correlated), 3)

        # 1. First finding should transition to correlated_behavior
        f1 = next(f for f in correlated if f.finding_id == "browser.content-script.injection")
        self.assertEqual(f1.state, FindingState.CORRELATED_BEHAVIOR)
        self.assertGreater(f1.confidence, 0.8)
        self.assertTrue(any(e.artifact == "dynamic_event" for e in f1.evidence))

        # 2. Second finding should transition to not_observed_under_test
        f2 = next(f for f in correlated if f.finding_id == "browser.native-messaging")
        self.assertEqual(f2.state, FindingState.NOT_OBSERVED_UNDER_TEST)

        # 3. Third finding should be a new runtime_observation for unattributed prototype_tamper
        f3 = next(f for f in correlated if "runtime.unattributed" in f.finding_id)
        self.assertEqual(f3.state, FindingState.RUNTIME_OBSERVATION)
        self.assertIn("window.fetch", f3.evidence[0].file)

    # @lat: [[source-tests#Correlator#Live canary event names]]
    def test_live_canary_event_names_correlate(self):
        fetch_finding = Finding(
            finding_id="browser.prototype-wrapping.fetch",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            phase="static",
            state=FindingState.STATIC_LEAD,
            severity=SeverityLevel.HIGH,
            confidence=0.8,
            evidence=[],
            scope=FindingScope(),
            hypothesis="Fetch is wrapped by a prototype descriptor.",
        )
        listener_finding = Finding(
            finding_id="browser.event-listener.keydown",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            phase="static",
            state=FindingState.STATIC_LEAD,
            severity=SeverityLevel.MEDIUM,
            confidence=0.7,
            evidence=[],
            scope=FindingScope(),
            hypothesis="A sensitive listener is proxied.",
        )

        runtime_events = [
            {
                "seq": 1,
                "t_ms": 5.0,
                "type": "property_tamper",
                "data": {"property": "fetch", "valueType": "function"},
            },
            {
                "seq": 2,
                "t_ms": 9.0,
                "type": "listener_proxy",
                "data": {"eventType": "keydown", "target": "Window"},
            },
        ]

        correlated = self.correlator.correlate(
            static_findings=[fetch_finding, listener_finding],
            runtime_events=runtime_events,
            env_discount=0.1,
            target_override=self.target,
        )

        self.assertEqual(len(correlated), 2)
        for f in correlated:
            self.assertEqual(f.state, FindingState.CORRELATED_BEHAVIOR)
            self.assertTrue(any(e.artifact == "dynamic_event" for e in f.evidence))

    # @lat: [[source-tests#Correlator#Replay script]]
    def test_generate_replay_script(self):
        f = Finding(
            finding_id="browser.test-finding",
            platform=PlatformType.BROWSER_EXTENSION,
            target=self.target,
            phase="correlation",
            state=FindingState.CORRELATED_BEHAVIOR,
            severity=SeverityLevel.HIGH,
            confidence=0.85,
            evidence=[],
            scope=FindingScope(),
            hypothesis="Replay test.",
        )
        script = self.correlator.generate_replay_script(f, test_url="https://canary.test")
        self.assertIn("https://canary.test", script)
        self.assertIn("browser.test-finding", script)


if __name__ == "__main__":
    unittest.main()
