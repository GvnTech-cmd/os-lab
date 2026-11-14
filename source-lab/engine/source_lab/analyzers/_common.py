"""Shared building blocks for the analyzers: a declarative rule type and a line scanner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from source_lab.evidence.schema import (
    EvidenceSpan,
    Finding,
    FindingScope,
    FindingState,
    PlatformType,
    SeverityLevel,
    TargetIdentity,
)


@dataclass(frozen=True)
class Rule:
    """One text rule: a regex over a line, optionally gated on another regex matching the whole file."""

    finding_id: str
    pattern: str
    severity: SeverityLevel
    confidence: float
    symbol: str
    hypothesis: str
    alternatives: Tuple[str, ...] = ()
    rule_id: Optional[str] = None
    state: FindingState = FindingState.STATIC_LEAD
    #: regex that must also match somewhere in the file (for example a rule about listeners only inside injected scripts)
    requires: Optional[str] = None
    remediation: Optional[str] = None
    world: Optional[str] = None
    process: Optional[str] = None


def scan_text(
    rel_path: str,
    text: str,
    rules: Sequence[Rule],
    target: TargetIdentity,
    platform: PlatformType,
    max_per_rule: int = 3,
    artifact: str = "source",
) -> List[Finding]:
    """Applies `rules` to `text`, at most `max_per_rule` findings per rule, each with a line-precise evidence span."""
    findings: List[Finding] = []
    lines = text.splitlines()
    for rule in rules:
        if rule.requires and not re.search(rule.requires, text):
            continue
        regex = re.compile(rule.pattern)
        hits = 0
        for number, line in enumerate(lines, 1):
            match = regex.search(line)
            if not match:
                continue
            findings.append(
                Finding(
                    finding_id=rule.finding_id,
                    rule_id=rule.rule_id or rule.finding_id.split(".")[-1],
                    platform=platform,
                    target=target,
                    phase="static",
                    state=rule.state,
                    severity=rule.severity,
                    confidence=rule.confidence,
                    evidence=[EvidenceSpan(file=rel_path, line=number, col=match.start() + 1, symbol=rule.symbol, artifact=artifact, snippet=line.strip()[:180])],
                    scope=FindingScope(world=rule.world, process=rule.process),
                    hypothesis=rule.hypothesis,
                    alternative_explanations=list(rule.alternatives),
                    remediation=rule.remediation,
                )
            )
            hits += 1
            if hits >= max_per_rule:
                break
    return findings


def make_finding(
    finding_id: str,
    platform: PlatformType,
    target: TargetIdentity,
    severity: SeverityLevel,
    confidence: float,
    hypothesis: str,
    span: EvidenceSpan,
    state: FindingState = FindingState.CAPABILITY,
    rule_id: Optional[str] = None,
    scope: Optional[FindingScope] = None,
    alternatives: Sequence[str] = (),
    limitations: Sequence[str] = (),
    remediation: Optional[str] = None,
) -> Finding:
    """A finding that does not come from a line regex (manifest keys, binary structure, archive contents)."""
    return Finding(
        finding_id=finding_id,
        rule_id=rule_id or finding_id.split(".")[-1],
        platform=platform,
        target=target,
        phase="static",
        state=state,
        severity=severity,
        confidence=confidence,
        evidence=[span],
        scope=scope or FindingScope(),
        hypothesis=hypothesis,
        alternative_explanations=list(alternatives),
        limitations=list(limitations),
        remediation=remediation,
    )
