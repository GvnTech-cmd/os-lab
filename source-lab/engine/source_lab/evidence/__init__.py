"""Evidence contract, validation, correlation and reporting for injection detection."""

from .schema import (
    PlatformType,
    FindingState,
    SeverityLevel,
    EvidenceSpan,
    FindingScope,
    TargetIdentity,
    Finding,
    Coverage,
    validate_finding,
    validate_coverage,
)
from .correlate import Correlator
from .report import EvidenceReportWriter
from .session import SessionBundleReader, SessionBundleWriter

__all__ = [
    "PlatformType",
    "FindingState",
    "SeverityLevel",
    "EvidenceSpan",
    "FindingScope",
    "TargetIdentity",
    "Finding",
    "Coverage",
    "validate_finding",
    "validate_coverage",
    "Correlator",
    "EvidenceReportWriter",
    "SessionBundleReader",
    "SessionBundleWriter",
]
