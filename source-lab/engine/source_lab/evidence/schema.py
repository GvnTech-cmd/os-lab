"""Evidence schema and validation for cross-platform injection detection.

Defines the V2 evidence contract:
- Finding (schema_version 2)
- Coverage (schema_version 2)
- TargetIdentity
- EvidenceSpan
- FindingScope
- State transitions (capability -> static_lead -> runtime_observation -> correlated_behavior -> not_observed_under_test)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class PlatformType(str, Enum):
    BROWSER_EXTENSION = "browser-extension"
    WINDOWS_APP = "windows-app"
    MACOS_APP = "macos-app"
    ANDROID_APP = "android-app"
    IOS_APP = "ios-app"


# @lat: [[source-lab#Detection]]
class FindingState(str, Enum):
    CAPABILITY = "capability"
    STATIC_LEAD = "static_lead"
    RUNTIME_OBSERVATION = "runtime_observation"
    CORRELATED_BEHAVIOR = "correlated_behavior"
    NOT_OBSERVED_UNDER_TEST = "not_observed_under_test"


class SeverityLevel(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    REVIEW = "review"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceSpan:
    file: Optional[str] = None
    line: Optional[int] = None
    col: Optional[int] = None
    end_line: Optional[int] = None
    end_col: Optional[int] = None
    symbol: Optional[str] = None
    artifact: str = "source"  # source, binary, manifest, dynamic_event, memory_dump
    snippet: Optional[str] = None
    binary_path: Optional[str] = None
    offset: Optional[str] = None
    image: Optional[str] = None
    process_id: Optional[int] = None
    address: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceSpan:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FindingScope:
    origin: Optional[str] = None
    frame: Optional[str] = None  # top, all, child, none
    world: Optional[str] = None  # MAIN, ISOLATED, USER_SCRIPT, background, native
    process: Optional[str] = None
    target_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FindingScope:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TargetIdentity:
    identifier: str
    repo: Optional[str] = None
    commit: Optional[str] = None
    version: Optional[str] = None
    artifact_sha256: Optional[str] = None
    signing_identity: Optional[str] = None
    package_name: Optional[str] = None
    build_arch: Optional[str] = None
    acquisition_method: str = "crawler_clone"  # crawler_clone, binary_download, package_store

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TargetIdentity:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Finding:
    finding_id: str
    platform: PlatformType
    target: TargetIdentity
    phase: str  # static, dynamic, correlation
    state: FindingState
    severity: SeverityLevel
    confidence: float  # 0.0 to 1.0
    evidence: List[EvidenceSpan]
    scope: FindingScope
    hypothesis: str
    limitations: List[str] = field(default_factory=list)
    schema_version: int = 2
    rule_id: Optional[str] = None
    remediation: Optional[str] = None
    alternative_explanations: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow_iso)
    # Research H1-H5 dimension (see evidence/heuristics.py) and the decisive test that separates benign from malicious.
    heuristic: Optional[str] = None
    verification: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "finding_id": self.finding_id,
            "rule_id": self.rule_id or self.finding_id,
            "platform": self.platform.value if isinstance(self.platform, PlatformType) else self.platform,
            "target": self.target.to_dict() if hasattr(self.target, "to_dict") else self.target,
            "phase": self.phase,
            "state": self.state.value if isinstance(self.state, FindingState) else self.state,
            "severity": self.severity.value if isinstance(self.severity, SeverityLevel) else self.severity,
            "confidence": round(float(self.confidence), 3),
            "evidence": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.evidence],
            "scope": self.scope.to_dict() if hasattr(self.scope, "to_dict") else self.scope,
            "hypothesis": self.hypothesis,
            "limitations": self.limitations,
            "alternative_explanations": self.alternative_explanations,
            "remediation": self.remediation,
            "created_at": self.created_at,
            **({"heuristic": self.heuristic} if self.heuristic else {}),
            **({"verification": self.verification} if self.verification else {}),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Finding:
        target = TargetIdentity.from_dict(data.get("target", {}))
        evidence = [EvidenceSpan.from_dict(e) for e in data.get("evidence", [])]
        scope = FindingScope.from_dict(data.get("scope", {}))
        return cls(
            schema_version=data.get("schema_version", 2),
            finding_id=data["finding_id"],
            rule_id=data.get("rule_id"),
            platform=PlatformType(data["platform"]),
            target=target,
            phase=data.get("phase", "static"),
            state=FindingState(data["state"]),
            severity=SeverityLevel(data["severity"]),
            confidence=float(data.get("confidence", 0.5)),
            evidence=evidence,
            scope=scope,
            hypothesis=data.get("hypothesis", ""),
            limitations=data.get("limitations", []),
            alternative_explanations=data.get("alternative_explanations", []),
            remediation=data.get("remediation"),
            created_at=data.get("created_at", utcnow_iso()),
            heuristic=data.get("heuristic"),
            verification=data.get("verification"),
        )


@dataclass
class Coverage:
    platform: PlatformType
    target: TargetIdentity
    analyzer_version: str = "2.0.0"
    rule_version: str = "2026.10"
    parser_mode: str = "ast"  # ast, regex_fallback, binary_pe, binary_macho, dex
    scanned_files: int = 0
    skipped_files: int = 0
    failed_stages: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    baseline_identity: Optional[str] = None
    schema_version: int = 2
    timestamp: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "platform": self.platform.value if isinstance(self.platform, PlatformType) else self.platform,
            "target": self.target.to_dict() if hasattr(self.target, "to_dict") else self.target,
            "analyzer_version": self.analyzer_version,
            "rule_version": self.rule_version,
            "parser_mode": self.parser_mode,
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "failed_stages": self.failed_stages,
            "limitations": self.limitations,
            "baseline_identity": self.baseline_identity,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Coverage:
        target = TargetIdentity.from_dict(data.get("target", {}))
        return cls(
            schema_version=data.get("schema_version", 2),
            platform=PlatformType(data["platform"]),
            target=target,
            analyzer_version=data.get("analyzer_version", "2.0.0"),
            rule_version=data.get("rule_version", "2026.10"),
            parser_mode=data.get("parser_mode", "ast"),
            scanned_files=data.get("scanned_files", 0),
            skipped_files=data.get("skipped_files", 0),
            failed_stages=data.get("failed_stages", []),
            limitations=data.get("limitations", []),
            baseline_identity=data.get("baseline_identity"),
            timestamp=data.get("timestamp", utcnow_iso()),
        )


# @lat: [[source-lab#Detection]]
def validate_finding(finding: Union[Finding, Dict[str, Any]]) -> List[str]:
    """Validates finding against the V2 evidence contract; returns list of errors."""
    data = finding.to_dict() if isinstance(finding, Finding) else finding
    errors: List[str] = []

    if data.get("schema_version") != 2:
        errors.append(f"schema_version must be 2, got {data.get('schema_version')}")

    if not data.get("finding_id"):
        errors.append("finding_id is required")

    try:
        PlatformType(data.get("platform", ""))
    except ValueError:
        errors.append(f"invalid platform: {data.get('platform')}")

    try:
        FindingState(data.get("state", ""))
    except ValueError:
        errors.append(f"invalid state: {data.get('state')}")

    try:
        SeverityLevel(data.get("severity", ""))
    except ValueError:
        errors.append(f"invalid severity: {data.get('severity')}")

    conf = data.get("confidence")
    if conf is None or not (0.0 <= float(conf) <= 1.0):
        errors.append(f"confidence must be float between 0.0 and 1.0, got {conf}")

    target = data.get("target")
    if not isinstance(target, dict) or not target.get("identifier"):
        errors.append("target.identifier is required")

    evidence = data.get("evidence")
    if not isinstance(evidence, list) or len(evidence) == 0:
        errors.append("evidence must be a non-empty list of spans")

    if not data.get("hypothesis"):
        errors.append("hypothesis explanation is required")

    return errors


def validate_coverage(coverage: Union[Coverage, Dict[str, Any]]) -> List[str]:
    """Validates coverage object; returns list of errors."""
    data = coverage.to_dict() if isinstance(coverage, Coverage) else coverage
    errors: List[str] = []

    if data.get("schema_version") != 2:
        errors.append(f"schema_version must be 2, got {data.get('schema_version')}")

    try:
        PlatformType(data.get("platform", ""))
    except ValueError:
        errors.append(f"invalid platform: {data.get('platform')}")

    target = data.get("target")
    if not isinstance(target, dict) or not target.get("identifier"):
        errors.append("target.identifier is required")

    return errors
