"""Research H1-H5 scoring matrix and the benign-versus-malicious decision matrix.

The Pentester paper ("Extended Heuristic Scoring Matrix") lifts the crawler's five heuristics to all five platforms:

- H1  target scope and entitlement breadth
- H2  cross-context injection APIs
- H3  pre-DOM / pre-entry hooks
- H4  repackaging and multi-module shims
- H5  dynamic code evaluation and W^X relaxation

Every rule id maps to one dimension, so a scorecard can be computed from findings alone. The scorecard is a triage aid over
static indicators: it never turns a `capability` or a `static_lead` into observed behaviour. The decision matrix attaches
the benign context and the decisive verification test the paper gives for each signal family.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Pattern, Tuple

from .schema import Finding, SeverityLevel

DIMENSIONS: Dict[str, str] = {
    "H1": "Target scope and entitlement breadth",
    "H2": "Cross-context injection APIs",
    "H3": "Pre-DOM / pre-entry hooks",
    "H4": "Repackaging and multi-module shims",
    "H5": "Dynamic code evaluation and W^X relaxation",
}

# First match wins; patterns are anchored on the finding id.
_DIMENSION_RULES: List[Tuple[str, str]] = [
    # --- browser -------------------------------------------------------------------------------------------------
    (r"^browser\.manifest\.broad-host-permissions$", "H1"),
    (r"^browser\.manifest\.(privileged-permission\.(nativemessaging|cookies|proxy|management|history)|externally-connectable)", "H1"),
    (r"^browser\.manifest\.privileged-permission\.", "H2"),
    (r"^browser\.manifest\.(content-script-registration|main-world-content-script|document-start-all-frames)$", "H3"),
    (r"^browser\.manifest\.(persistent-background|web-accessible-resources)$", "H4"),
    (r"^browser\.manifest\.csp-", "H5"),
    (r"^browser\.(dynamic-eval|remote-code)", "H5"),
    (r"^browser\.(shim|storage-wrapper)", "H4"),
    (r"^browser\.userscript\.(broad-match|metadata)$", "H1"),
    (r"^browser\.userscript\.(document-start|page-world)$", "H3"),
    (r"^browser\.userscript\.", "H2"),
    (r"^browser\.(main-world-injection|userscripts-api)", "H3"),
    (r"^browser\.", "H2"),
    # --- windows -------------------------------------------------------------------------------------------------
    (r"^windows\.pe\.(se-debug-privilege)$", "H1"),
    (r"^windows\.pe\.(dll-proxy|unsigned|managed-clr)$", "H4"),
    (r"^windows\.electron\.(node-integration|context-isolation-disabled|sandbox-disabled|web-security-disabled|insecure-content|remote-module)$", "H1"),
    (r"^windows\.electron\.(preload-script)$", "H3"),
    (r"^windows\.electron\.(asar-|fuse\.|unpacked-app)", "H4"),
    (r"^windows\.electron\.entrypoint$", "H4"),
    (r"^windows\.webview2\.document-created-script$", "H3"),
    (r"^windows\.(pe|webview2|clr)\.", "H2"),
    (r"^windows\.", "H2"),
    # --- macOS ---------------------------------------------------------------------------------------------------
    (r"^macos\.entitlement\.(allow-unsigned-executable-memory|disable-executable-page-protection|allow-jit)$", "H5"),
    (r"^macos\.macho\.hardened-runtime-missing$", "H5"),
    (r"^macos\.macho\.dyld-environment$", "H1"),
    (r"^macos\.(dyld\.insert-libraries)$", "H1"),
    (r"^macos\.objc\.constructor$", "H3"),
    (r"^macos\.entitlement\.", "H1"),
    (r"^macos\.macho\.(dyld-interposition|constructor)$", "H3"),
    (r"^macos\.macho\.(reexport-dylib|rpath|adhoc-signature|non-system-dylib|weak-dylib|unsigned)", "H4"),
    (r"^macos\.macho\.(injection-symbol)", "H2"),
    (r"^macos\.(bundle\.lsenvironment)$", "H1"),
    (r"^macos\.wkwebview\.(user-script|content-world)", "H3"),
    (r"^macos\.", "H2"),
    # --- android -------------------------------------------------------------------------------------------------
    (r"^android\.(manifest\.debuggable|apk\.debuggable-indicator|permission\.|manifest\.accessibility|webview\.wildcard-origin)", "H1"),
    (r"^android\.(webview\.document-start-script|manifest\.startup-provider)$", "H3"),
    (r"^android\.(apk\.(injected-native-lib|signing|unsigned|repackaging)|native\.hook-library|dex\.hook-framework)", "H4"),
    (r"^android\.(dcl\.native-library-load|webview\.(js-interface-bridge|js-enabled-bridge)|webview\.allow-)", "H5"),
    (r"^android\.", "H2"),
    # --- iOS -----------------------------------------------------------------------------------------------------
    (r"^ios\.(provision\.get-task-allow|entitlement\.get-task-allow|plist\.)", "H1"),
    (r"^ios\.(provision\.(team-identity|profile-type)|macho\.hook-framework-ref|framework\.injected|jailbreak-path)", "H4"),
    (r"^ios\.(entitlement\.dynamic-codesigning|macho\.dynamic-codesigning)", "H5"),
    (r"^ios\.(wkwebview\.(user-script-injection|content-world)|tweak\.filter-plist)", "H3"),
    (r"^ios\.", "H2"),
    # --- cross-platform ------------------------------------------------------------------------------------------
    (r"^(inapp|native)\.script-listener", "H2"),
]
_COMPILED: List[Tuple[Pattern[str], str]] = [(re.compile(p), d) for p, d in _DIMENSION_RULES]


def dimension_of(finding_id: str) -> Optional[str]:
    """The H1-H5 dimension of a finding id, or None for an id the matrix does not cover."""
    for pattern, dimension in _COMPILED:
        if pattern.search(finding_id):
            return dimension
    return None


# severity weight x confidence per finding, summed per dimension and capped
_WEIGHT = {
    SeverityLevel.INFO: 0.0,
    SeverityLevel.LOW: 1.0,
    SeverityLevel.MEDIUM: 2.0,
    SeverityLevel.HIGH: 4.0,
    SeverityLevel.CRITICAL: 6.0,
    SeverityLevel.REVIEW: 2.0,
}
DIMENSION_CAP = 10.0


def _band(total: float) -> str:
    if total >= 30:
        return "very-high"
    if total >= 15:
        return "high"
    if total >= 5:
        return "moderate"
    return "low"


def scorecard(findings: List[Finding]) -> Dict[str, Any]:
    """H1-H5 triage scorecard over a finding list.

    Each dimension sums severity weight times confidence, capped at 10; the total is the sum of the five (0-50).
    Findings the matrix does not cover are counted under `unmapped`, not scored.
    """
    dims: Dict[str, Dict[str, Any]] = {
        key: {"name": name, "score": 0.0, "findings": 0, "finding_ids": []} for key, name in DIMENSIONS.items()
    }
    unmapped = 0
    for f in findings:
        key = f.heuristic or dimension_of(f.finding_id)
        if key not in dims:
            unmapped += 1
            continue
        severity = f.severity if isinstance(f.severity, SeverityLevel) else SeverityLevel(str(f.severity))
        dims[key]["score"] += _WEIGHT[severity] * float(f.confidence)
        dims[key]["findings"] += 1
        if f.finding_id not in dims[key]["finding_ids"]:
            dims[key]["finding_ids"].append(f.finding_id)
    for entry in dims.values():
        entry["score"] = round(min(DIMENSION_CAP, entry["score"]), 2)
    total = round(sum(entry["score"] for entry in dims.values()), 2)
    return {
        "matrix": "H1-H5 (research: Extended Heuristic Scoring Matrix)",
        "dimensions": dims,
        "total": total,
        "max": DIMENSION_CAP * len(DIMENSIONS),
        "band": _band(total),
        "unmapped_findings": unmapped,
        "note": "A triage aid over static indicators. It ranks what to read first; it does not show observed behaviour.",
    }


# ---------------------------------------------------------------------------------------------------------------------
# Decision matrix: benign / dual-use context and the decisive verification test, per signal family
# ---------------------------------------------------------------------------------------------------------------------

_DECISION: List[Tuple[str, str, str]] = [
    (
        r"^windows\.pe\.dll-proxy",
        "A deliberate user-installed game mod (BepInEx, ReShade) or a legacy compatibility shim.",
        "Compare the export table's forwarding entries, verify the file signer against the application vendor, and inspect outbound network sockets.",
    ),
    (
        r"^windows\.pe\.(injection-api|se-debug|hook-engine)",
        "A debugger, crash reporter, profiler, game overlay or security product.",
        "Check that the symbol is in the import table (not just a string), verify the Authenticode signer, and resolve what the target process is at runtime.",
    ),
    (
        r"^windows\.(webview2|electron)\.",
        "A hybrid app bridging native features to its own first-party web origin.",
        "Check the origin the bridge or preload is exposed to; a wildcard or remote origin turns a native bridge into a remote-code path.",
    ),
    (
        r"^(macos|ios)\.wkwebview\.(user-script|content-world)",
        "A Web3 wallet injecting an EIP-1193 provider, or a password-manager autofill helper.",
        "Run the canary probe and inspect the intercepted event listeners and the messageHandlers payloads; key and input listeners in the injected script indicate credential capture.",
    ),
    (
        r"^(macos|ios)\.objc\.",
        "An APM or analytics SDK (Firebase Performance, Datadog, New Relic) linked at build time.",
        "Check where the swizzling code ships: the app's own signed binary or Frameworks/ is expected, an external dylib or a different Team ID is not (dladdr on the IMP at runtime proves it).",
    ),
    (
        r"^(macos|ios)\.(macho|entitlement|framework)\.",
        "Developer tooling or a deliberate plug-in architecture.",
        "Check the signer and Team ID against the publisher and whether the entitlement or load command is needed by a shipped feature.",
    ),
    (
        r"^android\.webview\.(document-start-script|js-interface-bridge|js-enabled-bridge|wildcard-origin|web-message-listener)",
        "A hybrid app bridging native camera or biometrics to its own first-party web origin.",
        "Inspect allowedOriginRules in jadx; if a wildcard or untrusted HTTP origin can invoke @JavascriptInterface methods, treat it as a high-severity bridge vulnerability.",
    ),
    (
        r"^android\.(apk|native)\.",
        "A debug build, an instrumentation test harness or a legitimate native SDK.",
        "Compare the v2/v3 signing certificate SHA-256 with the store release and inspect lib/<abi>/ for injected hook libraries.",
    ),
    (
        r"^browser\.userscript\.",
        "A user-installed userscript doing what its description says.",
        "Read the @match and @grant lines against the script's stated purpose, and check where GM_xmlhttpRequest sends data (@connect).",
    ),
    (
        r"^browser\.",
        "A privacy blocker, dark-mode or accessibility extension using the same low-level hooks as offensive tooling (uBlock Origin, Privacy Badger, Dark Reader).",
        "Correlate the manifest permissions with the actual script paths and runtime behaviour, and check the destination of every data flow; capability alone is not intent.",
    ),
    (
        r"^(inapp|native)\.script-listener",
        "A form helper or accessibility feature attaching listeners inside the app's own pages.",
        "Check which origins the script is injected into; listeners on third-party pages that read key, input or paste events indicate credential capture.",
    ),
]
_DECISION_COMPILED = [(re.compile(p), benign, verify) for p, benign, verify in _DECISION]


def decision_for(finding_id: str) -> Optional[Tuple[str, str]]:
    """(benign context, verification test) for a finding id, or None."""
    for pattern, benign, verify in _DECISION_COMPILED:
        if pattern.search(finding_id):
            return benign, verify
    return None


def enrich_findings(findings: List[Finding]) -> List[Finding]:
    """Stamps each finding with its H1-H5 dimension, benign context and verification test (never overwrites)."""
    for f in findings:
        if not f.heuristic:
            f.heuristic = dimension_of(f.finding_id)
        decision = decision_for(f.finding_id)
        if decision:
            benign, verification = decision
            if not f.verification:
                f.verification = verification
            if benign not in f.alternative_explanations and not f.alternative_explanations:
                f.alternative_explanations.append(benign)
    return findings
