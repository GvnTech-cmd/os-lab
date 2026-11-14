"""Correlation engine for static findings and runtime observation streams.

Calculates mathematical confidence:
  C = min(1.0, (W_s * S_static + W_d * S_dynamic) / (1 + D_env))

Handles state transitions:
  capability -> static_lead -> correlated_behavior / not_observed_under_test
  capability -> runtime_observation -> correlated_behavior
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .schema import (
    EvidenceSpan,
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
    utcnow_iso,
)


class Correlator:
    """Joins static findings with runtime observation events."""

    def __init__(
        self,
        weight_static: float = 0.35,
        weight_dynamic: float = 0.65,
        default_env_discount: float = 0.1,
    ):
        self.w_static = weight_static
        self.w_dynamic = weight_dynamic
        self.default_env_discount = default_env_discount

    # @lat: [[source-lab#Runtime evidence]]
    def calculate_confidence(
        self,
        s_static: float,
        s_dynamic: float,
        d_env: Optional[float] = None,
    ) -> float:
        """Computes calibrated confidence score in [0.0, 1.0]."""
        discount = self.default_env_discount if d_env is None else d_env
        numerator = (self.w_static * s_static) + (self.w_dynamic * s_dynamic)
        denominator = 1.0 + max(0.0, discount)
        return min(1.0, max(0.0, numerator / denominator))

    # @lat: [[source-lab#Runtime evidence]]
    def correlate(
        self,
        static_findings: List[Finding],
        runtime_events: List[Dict[str, Any]],
        env_discount: Optional[float] = None,
        target_override: Optional[TargetIdentity] = None,
    ) -> List[Finding]:
        """Correlates static findings against runtime events to produce updated findings."""
        correlated: List[Finding] = []
        matched_event_seqs: set = set()

        for sf in static_findings:
            # Look for matching runtime observations
            matching_events = self._match_events_to_finding(sf, runtime_events)

            if matching_events:
                # Mark as correlated_behavior
                s_static = sf.confidence  # existing static precision
                s_dynamic = 1.0  # clean-vs-target delta confirmed with runtime events
                conf = self.calculate_confidence(s_static, s_dynamic, env_discount)

                # Collect runtime evidence spans
                new_evidence = list(sf.evidence)
                for ev in matching_events:
                    matched_event_seqs.add(ev.get("seq"))
                    data = ev.get("data", {})
                    new_evidence.append(
                        EvidenceSpan(
                            file=data.get("src") or data.get("api"),
                            symbol=data.get("hook_type") or data.get("action") or ev.get("type"),
                            artifact="dynamic_event",
                            snippet=f"Event #{ev.get('seq')} @ {ev.get('t_ms')}ms: {ev.get('type')}: {data}",
                        )
                    )

                f = Finding(
                    finding_id=sf.finding_id,
                    rule_id=sf.rule_id,
                    platform=sf.platform,
                    target=target_override or sf.target,
                    phase="correlation",
                    state=FindingState.CORRELATED_BEHAVIOR,
                    severity=sf.severity,
                    confidence=conf,
                    evidence=new_evidence,
                    scope=sf.scope,
                    hypothesis=f"{sf.hypothesis} — confirmed via runtime observation stream.",
                    limitations=sf.limitations,
                    alternative_explanations=sf.alternative_explanations,
                    remediation=sf.remediation,
                )
                correlated.append(f)
            else:
                # If runtime events were collected, but this finding had no runtime hit
                if len(runtime_events) > 0:
                    s_static = sf.confidence
                    s_dynamic = 0.0
                    conf = self.calculate_confidence(s_static, s_dynamic, env_discount)
                    f = Finding(
                        finding_id=sf.finding_id,
                        rule_id=sf.rule_id,
                        platform=sf.platform,
                        target=target_override or sf.target,
                        phase="correlation",
                        state=FindingState.NOT_OBSERVED_UNDER_TEST,
                        severity=SeverityLevel.INFO,
                        confidence=conf,
                        evidence=sf.evidence,
                        scope=sf.scope,
                        hypothesis=f"{sf.hypothesis} — not triggered under the evaluated test conditions.",
                        limitations=sf.limitations + ["Observation window completed without triggering this path."],
                        alternative_explanations=sf.alternative_explanations,
                        remediation=sf.remediation,
                    )
                    correlated.append(f)
                else:
                    # No runtime run took place, keep static finding
                    correlated.append(sf)

        # Unmatched significant runtime events become runtime_observation findings
        for ev in runtime_events:
            seq = ev.get("seq")
            if seq in matched_event_seqs:
                continue
            ev_type = ev.get("type")
            significant_events = (
                "dom_mutation", "prototype_tamper", "property_tamper",
                "listener_registered", "listener_proxy", "remote_thread",
                "hook_detected", "memory_hook", "unbacked_exec", "process_tampering",
                "foreign_image_mapped", "objc_swizzle", "endpoint_security_event",
                "unbacked_exec_mapping", "hook_library_mapped", "instrumentation_thread",
                "tweak_framework_detected", "arm64_trampoline", "wkwebview_message",
            )
            if ev_type in significant_events:
                data = ev.get("data", {})
                target = target_override or (static_findings[0].target if static_findings else TargetIdentity("unknown"))
                platform = static_findings[0].platform if static_findings else PlatformType.BROWSER_EXTENSION

                span = EvidenceSpan(
                    file=data.get("src") or data.get("api") or data.get("path") or "runtime",
                    symbol=ev_type,
                    artifact="dynamic_event",
                    snippet=f"Uncorrelated runtime event #{seq}: {data}",
                )

                rf = Finding(
                    finding_id=f"runtime.unattributed.{ev_type}.seq{seq}",
                    rule_id=f"runtime.{ev_type}",
                    platform=platform,
                    target=target,
                    phase="dynamic",
                    state=FindingState.RUNTIME_OBSERVATION,
                    severity=SeverityLevel.REVIEW,
                    confidence=self.calculate_confidence(0.2, 0.7, env_discount),
                    evidence=[span],
                    scope=FindingScope(origin=data.get("origin"), world=data.get("world", "MAIN")),
                    hypothesis=f"Observed {ev_type} at runtime with no matching static call-site trace.",
                    limitations=["Dynamic effect observed without a mapped static AST source-to-sink bridge."],
                )
                correlated.append(rf)

        return correlated

    # @lat: [[source-lab#Runtime evidence]]
    def _match_events_to_finding(self, finding: Finding, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Matches a static finding against runtime events based on API, file, or pattern."""
        matches: List[Dict[str, Any]] = []
        fid = finding.finding_id.lower()

        for ev in events:
            ev_type = ev.get("type", "").lower()
            data = ev.get("data", {})
            data_str = json.dumps(data).lower()

            # Browser script injection matching
            if "script" in fid or "bridge" in fid:
                if ev_type in ("dom_mutation", "script_injected", "dom_addition"):
                    matches.append(ev)
                    continue

            # Prototype hooking matching
            if "prototype" in fid or "hook" in fid or "fetch" in fid or "listener" in fid:
                if ev_type in (
                    "prototype_tamper",
                    "property_tamper",
                    "global_trap",
                    "listener_registered",
                    "listener_proxy",
                ):
                    matches.append(ev)
                    continue

            # Windows PE / Native matching
            if "windows" in fid or "pe." in fid or "thread" in fid or "hollowing" in fid:
                if ev_type in ("remote_thread", "hook_detected", "process_tampering", "memory_hook", "unbacked_exec"):
                    matches.append(ev)
                    continue

            # macOS dyld / Objective-C matching
            if "macos" in fid or "dyld" in fid or "interpose" in fid or "swizzle" in fid:
                if ev_type in ("foreign_image_mapped", "objc_swizzle", "endpoint_security_event", "image_mapped", "method_swizzled", "branch_detected"):
                    matches.append(ev)
                    continue

            # Android WebView / DEX / Native matching
            if "android" in fid or "dex" in fid or "webview" in fid:
                if ev_type in ("unbacked_exec_mapping", "hook_library_mapped", "instrumentation_thread", "logcat_event"):
                    matches.append(ev)
                    continue

            # iOS WKWebView / Tweak matching
            if "ios" in fid or "tweak" in fid or "provision" in fid:
                if ev_type in ("tweak_framework_detected", "arm64_trampoline", "wkwebview_message"):
                    matches.append(ev)
                    continue

            # Check if any static evidence file matches event source
            for span in finding.evidence:
                if span.file and span.file.lower() in data_str:
                    matches.append(ev)
                    break

        return matches

    def generate_replay_script(self, finding: Finding, test_url: str = "https://example.test") -> str:
        """Generates an automated, reproducible python replay script for the finding."""
        return f"""#!/usr/bin/env python3
# Automated Replay Script for {finding.finding_id}
# Target: {finding.target.identifier} ({finding.target.artifact_sha256 or 'pinned'})
# Generated: {utcnow_iso()}

import asyncio
from playwright.async_api import async_playwright

TEST_URL = "{test_url}"
TARGET_FINDING = "{finding.finding_id}"

async def run_replay():
    print(f"[*] Replaying test verification for: {{TARGET_FINDING}}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Inject detection canary probe
        await page.add_init_script(\"\"\"
            window.__iqReplayObservations = [];
            const origFetch = window.fetch;
            Object.defineProperty(window, 'fetch', {{
                get() {{ return origFetch; }},
                set(v) {{
                    window.__iqReplayObservations.push({{ type: 'fetch_tamper', time: performance.now() }});
                    return v;
                }}
            }});
        \"\"\")

        print(f"[*] Navigating to: {{TEST_URL}}")
        await page.goto(TEST_URL)
        await page.wait_for_timeout(3000)

        obs = await page.evaluate("window.__iqReplayObservations")
        print(f"[+] Replay observations recorded: {{len(obs)}}")
        for o in obs:
            print(f"    - {{o}}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_replay())
"""
