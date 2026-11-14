"""Report generator for evidence findings and coverage.

Exports:
- findings.json
- coverage.json
- analysis-v2.json
- Markdown summary report
- SARIF 2.1 format
- STIX 2.1 format
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .heuristics import DIMENSIONS, scorecard
from .schema import Coverage, Finding, TargetIdentity, utcnow_iso


class EvidenceReportWriter:
    """Serializes evidence into versioned artifacts, Markdown, SARIF, and STIX."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_findings(self, findings: List[Finding]) -> Path:
        p = self.output_dir / "findings.json"
        data = [f.to_dict() for f in findings]
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return p

    def write_coverage(self, coverage: Coverage) -> Path:
        p = self.output_dir / "coverage.json"
        p.write_text(json.dumps(coverage.to_dict(), indent=2), encoding="utf-8")
        return p

    def write_analysis_v2(self, target: TargetIdentity, findings: List[Finding], coverage: Coverage) -> Path:
        p = self.output_dir / "analysis-v2.json"
        doc = {
            "schema_version": 2,
            "generated_at": utcnow_iso(),
            "target": target.to_dict(),
            "coverage": coverage.to_dict(),
            "finding_summary": {
                "total": len(findings),
                "by_state": {},
                "by_severity": {},
            },
            "scorecard": scorecard(findings),
            "findings": [f.to_dict() for f in findings],
        }
        for f in findings:
            st = f.state.value if hasattr(f.state, "value") else str(f.state)
            sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
            doc["finding_summary"]["by_state"][st] = doc["finding_summary"]["by_state"].get(st, 0) + 1
            doc["finding_summary"]["by_severity"][sev] = doc["finding_summary"]["by_severity"].get(sev, 0) + 1

        p.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return p

    def export_markdown(self, target: TargetIdentity, findings: List[Finding], coverage: Coverage) -> str:
        """Generates a comprehensive Markdown audit report."""
        lines: List[str] = [
            f"# Injection Detection Audit Report: {target.identifier}",
            "",
            f"- **Target Origin:** `{target.repo or target.identifier}`",
            f"- **Commit / Package SHA-256:** `{target.commit or target.artifact_sha256 or 'pinned'}`",
            f"- **Platform:** `{coverage.platform.value if hasattr(coverage.platform, 'value') else coverage.platform}`",
            f"- **Analyzer Version:** `{coverage.analyzer_version}` (Rules: `{coverage.rule_version}`)",
            f"- **Parser Mode:** `{coverage.parser_mode}`",
            f"- **Audit Date (UTC):** `{coverage.timestamp}`",
            "",
            "## 1. Executive Summary & Coverage",
            "",
            f"Static scan analyzed **{coverage.scanned_files} files** (skipped {coverage.skipped_files}).",
        ]

        if coverage.limitations:
            lines.append("\n### Known Analysis Limitations:")
            for lim in coverage.limitations:
                lines.append(f"- ⚠️ {lim}")

        card = scorecard(findings)
        lines.extend([
            "",
            "## 2. H1-H5 Scorecard",
            "",
            f"Total **{card['total']} / {card['max']:.0f}** (`{card['band']}`). {card['note']}",
            "",
            "| Dimension | Score | Findings |",
            "| --- | --- | --- |",
        ])
        for key, entry in card["dimensions"].items():
            lines.append(f"| {key} {entry['name']} | {entry['score']:.2f} / 10 | {entry['findings']} |")
        if card["unmapped_findings"]:
            lines.append(f"\n_{card['unmapped_findings']} finding(s) are outside the matrix and were not scored._")

        lines.extend([
            "",
            "## 3. Findings Inventory",
            "",
            "| ID | State | Severity | Confidence | Scope | Hypothesis |",
            "| --- | --- | --- | --- | --- | --- |",
        ])

        for f in findings:
            st = f.state.value if hasattr(f.state, "value") else str(f.state)
            sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
            world = f.scope.world or "any"
            lines.append(
                f"| `{f.finding_id}` | `{st}` | `{sev}` | **{f.confidence:.2f}** | {world} | {f.hypothesis} |"
            )

        lines.extend(["", "## 4. Detailed Evidence Spans", ""])
        for idx, f in enumerate(findings, 1):
            st = f.state.value if hasattr(f.state, "value") else str(f.state)
            sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
            lines.extend([
                f"### {idx}. [{sev.upper()}] {f.finding_id} (`{st}`)",
                "",
                f"- **Hypothesis:** {f.hypothesis}",
                f"- **Confidence:** {f.confidence:.2f}",
                "- **Evidence Locations:**",
            ])
            for sp in f.evidence:
                loc = f"`{sp.file or 'binary'}`"
                if sp.line:
                    loc += f": line {sp.line}"
                if sp.symbol:
                    loc += f" (symbol: `{sp.symbol}`)"
                lines.append(f"  - {loc} [{sp.artifact}]")
                if sp.snippet:
                    lines.append(f"    ```\n    {sp.snippet.strip()}\n    ```")

            if f.alternative_explanations:
                lines.append("- **Alternative Explanations:**")
                for alt in f.alternative_explanations:
                    lines.append(f"  - {alt}")

            if f.verification:
                lines.append(f"- **Decisive verification test:** {f.verification}")
            if f.heuristic:
                lines.append(f"- **Matrix dimension:** {f.heuristic} ({DIMENSIONS.get(f.heuristic, '')})")
            if f.remediation:
                lines.append(f"- **Remediation / Hardening:** {f.remediation}")
            lines.append("")

        return "\n".join(lines)

    def export_sarif(self, target: TargetIdentity, findings: List[Finding]) -> Dict[str, Any]:
        """Exports findings to SARIF 2.1 schema."""
        rules: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []

        for f in findings:
            rule_id = f.rule_id or f.finding_id
            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "name": rule_id.replace(".", "_"),
                    "shortDescription": {"text": f.hypothesis},
                    "fullDescription": {"text": f.hypothesis},
                    **({"properties": {k: v for k, v in (("heuristic", f.heuristic), ("verification", f.verification)) if v}} if (f.heuristic or f.verification) else {}),
                }

            locations = []
            for sp in f.evidence:
                if sp.file:
                    loc = {
                        "physicalLocation": {
                            "artifactLocation": {"uri": sp.file},
                            "region": {
                                "startLine": sp.line or 1,
                                "startColumn": sp.col or 1,
                            },
                        }
                    }
                    locations.append(loc)

            sev_map = {
                "critical": "error",
                "high": "error",
                "medium": "warning",
                "low": "note",
                "info": "note",
                "review": "warning",
            }
            sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)

            results.append({
                "ruleId": rule_id,
                "level": sev_map.get(sev.lower(), "warning"),
                "message": {"text": f"{f.hypothesis} (state: {f.state.value if hasattr(f.state, 'value') else f.state})"},
                "locations": locations or [{"physicalLocation": {"artifactLocation": {"uri": "manifest.json"}}}],
            })

        return {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "iExtensionCrawler-Workbench",
                            "version": "2.0.0",
                            "rules": list(rules.values()),
                        }
                    },
                    "results": results,
                }
            ],
        }

    def export_stix(self, target: TargetIdentity, findings: List[Finding]) -> Dict[str, Any]:
        """Exports findings to STIX 2.1 Threat Intelligence format."""
        objects: List[Dict[str, Any]] = []
        target_ref = f"identity--{target.identifier.replace('/', '_')}"

        objects.append({
            "type": "identity",
            "spec_version": "2.1",
            "id": target_ref,
            "created": utcnow_iso(),
            "modified": utcnow_iso(),
            "name": target.identifier,
            "identity_class": "software",
        })

        for idx, f in enumerate(findings):
            indicator_id = f"indicator--{f.finding_id.replace('.', '-')}-{idx}"
            objects.append({
                "type": "indicator",
                "spec_version": "2.1",
                "id": indicator_id,
                "created": utcnow_iso(),
                "modified": utcnow_iso(),
                "name": f.finding_id,
                "description": f.hypothesis,
                "indicator_types": ["malicious-activity", "anomalous-activity"],
                "pattern": f"[{f.platform.value if hasattr(f.platform, 'value') else f.platform}:finding = '{f.finding_id}']",
                "pattern_type": "stix",
                "valid_from": utcnow_iso(),
                "confidence": int(f.confidence * 100),
            })

        return {
            "type": "bundle",
            "id": f"bundle--{target.identifier.replace('/', '_')}",
            "objects": objects,
        }


class ReportExporter:
    """Convenience exporter that writes artifacts for a specific finding/coverage set."""

    def __init__(self, findings: List[Finding], coverage: Coverage, target: TargetIdentity):
        self.findings = findings
        self.coverage = coverage
        self.target = target

    def export_analysis_v2(self, path: Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        writer = EvidenceReportWriter(p.parent)
        writer.write_analysis_v2(self.target, self.findings, self.coverage)
        return p

    def export_findings_json(self, path: Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        writer = EvidenceReportWriter(p.parent)
        writer.write_findings(self.findings)
        return p

    def export_sarif(self, path: Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        writer = EvidenceReportWriter(p.parent)
        sarif_data = writer.export_sarif(self.target, self.findings)
        p.write_text(json.dumps(sarif_data, indent=2), encoding="utf-8")
        return p

    def export_markdown(self, path: Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        writer = EvidenceReportWriter(p.parent)
        md = writer.export_markdown(self.target, self.findings, self.coverage)
        p.write_text(md, encoding="utf-8")
        return p

    def export_stix(self, path: Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        writer = EvidenceReportWriter(p.parent)
        stix_data = writer.export_stix(self.target, self.findings)
        p.write_text(json.dumps(stix_data, indent=2), encoding="utf-8")
        return p
