"""Android rules from the research: signing, injected native libraries, accessibility, startup providers, WebView origins.

The Android paper and the Playbook list four static checkpoints: the signing certificate against the store release, injected
native libraries and manifest shims, outbound WebView injection, and unsafe native bridges. Origins and certificates are
reported as evidence for the auditor to compare; the analyzer cannot know the publisher's expected certificate.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Sequence, Tuple

from source_lab.evidence.schema import EvidenceSpan, Finding, FindingScope, FindingState, PlatformType, SeverityLevel, TargetIdentity

from ._common import Rule, make_finding
from .binfmt import parse_apk_signing

P = PlatformType.ANDROID_APP
SEV = SeverityLevel
_ANDROID = "{http://schemas.android.com/apk/res/android}"

SOURCE_RULES: Tuple[Rule, ...] = (
    Rule("android.webview.web-message-listener", r"addWebMessageListener\s*\(", SEV.MEDIUM, 0.65, "addWebMessageListener",
         "Registers a native listener that web content can message, a bridge from page scripts into the app.", ("Hybrid app bridge to its own origin.",), rule_id="RULE-ANDR-WEB-MESSAGE-LISTENER"),
    Rule("android.webview.intercept-request", r"shouldInterceptRequest\s*\(", SEV.MEDIUM, 0.6, "shouldInterceptRequest",
         "Intercepts WebView subresource requests, so the app can proxy, inspect or rewrite what pages load.", ("Offline cache or ad blocker.",), rule_id="RULE-ANDR-INTERCEPT-REQUEST"),
    Rule("android.webview.javascript-url", r"loadUrl\s*\(\s*[\"']javascript:", SEV.MEDIUM, 0.65, "loadUrl(\"javascript:...\")",
         "Runs a script inside the page by loading a javascript: URL.", ("Legacy way to call page JavaScript.",), rule_id="RULE-ANDR-JAVASCRIPT-URL"),
    Rule("android.webview.js-enabled", r"setJavaScriptEnabled\s*\(\s*true\s*\)", SEV.LOW, 0.4, "setJavaScriptEnabled(true)",
         "Turns on JavaScript in the WebView, a precondition for every bridge and injection above.", ("Any app that renders web content.",), rule_id="RULE-ANDR-JS-ENABLED"),
    Rule("android.webview.wildcard-origin", r"(addWebMessageListener|addDocumentStartJavaScript)\s*\([^;]*[\"']\*[\"']", SEV.HIGH, 0.85, "wildcard allowed origin",
         "Registers a bridge or document-start script for the wildcard origin, so any page the WebView loads can reach it.", ("Development placeholder that shipped.",), rule_id="RULE-ANDR-WILDCARD-ORIGIN"),
    Rule("android.webview.javascript-interface-annotation", r"@JavascriptInterface\b", SEV.LOW, 0.5, "@JavascriptInterface",
         "Marks a method as callable from page JavaScript.", ("Bridge to the app's own first-party origin.",), rule_id="RULE-ANDR-JS-INTERFACE-ANNOTATION"),
)

#: extra signatures searched in DEX strings: (needle, finding id, severity, confidence, hypothesis)
DEX_SIGNATURES: Tuple[Tuple[bytes, str, SeverityLevel, float, str], ...] = (
    (b"addWebMessageListener", "android.dex.web-message-listener", SEV.MEDIUM, 0.7, "DEX registers a WebView message listener bridge"),
    (b"shouldInterceptRequest", "android.dex.intercept-request", SEV.MEDIUM, 0.6, "DEX intercepts WebView subresource requests"),
    (b"InMemoryDexClassLoader", "android.dex.in-memory-dex-loader", SEV.HIGH, 0.85, "DEX loads bytecode from memory with InMemoryDexClassLoader"),
    (b"Lcom/swift/sandhook", "android.dex.hook-framework", SEV.CRITICAL, 0.9, "DEX references the SandHook ART hooking framework"),
    (b"me/weishu/epic", "android.dex.hook-framework", SEV.CRITICAL, 0.9, "DEX references the Epic ART hooking framework"),
    (b"top/canyie/pine", "android.dex.hook-framework", SEV.CRITICAL, 0.9, "DEX references the Pine ART hooking framework"),
    (b"lab/galaxy/yahfa", "android.dex.hook-framework", SEV.CRITICAL, 0.9, "DEX references the YAHFA ART hooking framework"),
)

_INJECTED_LIB = re.compile(r"(^|/)lib/[^/]+/(libfrida-gadget|libgadget|libsubstrate|libxposed[\w-]*|libdobby|libpine|libepic|libwhale|libyahfa|libsandhook[\w-]*|liblspd|libriru[\w-]*|libzygisk[\w-]*)\.so$|(^|/)jniLibs/[^/]+/(libfrida-gadget|libgadget|libsubstrate|libdobby)\.so$", re.I)

#: permission -> (finding id suffix, severity, confidence, meaning)
EXTRA_PERMISSIONS = {
    "android.permission.BIND_ACCESSIBILITY_SERVICE": ("bind_accessibility_service", SEV.HIGH, 0.75, "an accessibility service can read the screen and perform gestures in other apps"),
    "android.permission.BIND_DEVICE_ADMIN": ("bind_device_admin", SEV.HIGH, 0.7, "a device-admin component can lock, wipe and resist uninstall"),
    "android.permission.MANAGE_EXTERNAL_STORAGE": ("manage_external_storage", SEV.MEDIUM, 0.5, "broad access to shared storage"),
    "android.permission.QUERY_ALL_PACKAGES": ("query_all_packages", SEV.LOW, 0.4, "can enumerate every installed app"),
}


def analyze_manifest_xml(root_el: ET.Element, rel_path: str, target: TargetIdentity) -> List[Finding]:
    """Permissions, accessibility services and startup providers from a cleartext manifest."""
    findings: List[Finding] = []

    def span(symbol: str, snippet: str) -> EvidenceSpan:
        return EvidenceSpan(file=rel_path, symbol=symbol, artifact="manifest", snippet=snippet[:180])

    for perm in root_el.findall("uses-permission"):
        name = perm.get(_ANDROID + "name") or perm.get("android:name")
        if name in EXTRA_PERMISSIONS:
            suffix, severity, confidence, meaning = EXTRA_PERMISSIONS[name]
            findings.append(make_finding(f"android.permission.{suffix}", P, target, severity, confidence,
                f"The app requests {name}: {meaning}.", span(name, f'<uses-permission android:name="{name}" />'), rule_id="RULE-ANDR-PERM",
                alternatives=["Accessibility tool, device-management app or file manager."]))

    app = root_el.find("application")
    if app is None:
        return findings
    for service in app.findall("service"):
        name = service.get(_ANDROID + "name") or service.get("android:name") or "unnamed"
        permission = service.get(_ANDROID + "permission") or service.get("android:permission")
        actions = [a.get(_ANDROID + "name") or a.get("android:name") for a in service.iter("action")]
        if permission == "android.permission.BIND_ACCESSIBILITY_SERVICE" or "android.accessibilityservice.AccessibilityService" in actions:
            findings.append(make_finding("android.manifest.accessibility-service", P, target, SEV.HIGH, 0.8,
                f"The app declares the accessibility service '{name}', which can observe and drive other apps' UI.", span(name, f"<service android:name='{name}' ... AccessibilityService>"),
                rule_id="RULE-ANDR-ACCESSIBILITY", scope=FindingScope(process=name), alternatives=["Genuine assistive technology."]))
    for provider in app.findall("provider"):
        name = provider.get(_ANDROID + "name") or provider.get("android:name") or "unnamed"
        init_order = provider.get(_ANDROID + "initOrder") or provider.get("android:initOrder")
        library = name.startswith(("androidx.", "com.google.", "com.facebook.", "io.sentry.", "com.crashlytics.", "com.squareup."))
        looks_like_shim = bool(re.search(r"(Init|Startup|Hook|Inject|Loader|Boot)", name.rsplit(".", 1)[-1])) or (init_order not in (None, "0"))
        if looks_like_shim and not library:
            findings.append(make_finding("android.manifest.startup-provider", P, target, SEV.MEDIUM, 0.5,
                f"The provider '{name}' runs before Application.onCreate (initOrder={init_order}), the manifest hook that startup shims and injected gadgets use.",
                span(name, f"<provider android:name='{name}' initOrder={init_order}>"), rule_id="RULE-ANDR-STARTUP-PROVIDER", scope=FindingScope(process=name),
                alternatives=["SDK initialisation through a content provider."]))
    return findings


def analyze_binary_manifest(raw: bytes, archive_name: str, target: TargetIdentity) -> List[Finding]:
    """Permissions and accessibility from a compiled manifest, found as strings (UTF-8 or UTF-16LE) in the string pool."""
    findings: List[Finding] = []
    file = f"{archive_name}!AndroidManifest.xml"
    for name, (suffix, severity, confidence, meaning) in {**EXTRA_PERMISSIONS, "android.permission.SYSTEM_ALERT_WINDOW": ("system_alert_window", SEV.HIGH, 0.85, "overlay windows can draw over other apps")}.items():
        if name.encode() in raw or name.encode("utf-16-le") in raw:
            findings.append(make_finding(f"android.permission.{suffix}", P, target, severity, min(confidence, 0.85),
                f"The compiled manifest references {name}: {meaning}.", EvidenceSpan(file=file, symbol=name, artifact="manifest", snippet=f"binary XML string pool contains {name}"),
                rule_id="RULE-ANDR-PERM", limitations=["Read from the compiled manifest's string pool; declared versus requested is not distinguished."]))
    return findings


def analyze_injected_lib_name(path: str, target: TargetIdentity, container: Optional[str] = None) -> Optional[Finding]:
    """A finding when a file path is a known hooking or instrumentation library."""
    norm = path.replace("\\", "/")
    if not _INJECTED_LIB.search(norm):
        return None
    where = f"{container}!{norm}" if container else norm
    return make_finding("android.apk.injected-native-lib", P, target, SEV.CRITICAL, 0.9,
        f"The package ships the hooking or instrumentation library {norm.rsplit('/', 1)[-1]}, the injected-gadget layout of a repackaged app.",
        EvidenceSpan(file=where, symbol=norm.rsplit("/", 1)[-1], artifact="binary", binary_path=norm, snippet="native library name matches a hooking framework"),
        rule_id="RULE-ANDR-INJECTED-LIB", scope=FindingScope(process="app"), alternatives=["Instrumented test build or a debugging variant."])


def analyze_apk_signing(apk_name: str, data: bytes, names: Sequence[str], target: TargetIdentity) -> List[Finding]:
    """Signing schemes and certificate digest; flags an unsigned package."""
    info = parse_apk_signing(data)
    v1 = [n for n in names if re.match(r"^META-INF/[^/]+\.(RSA|DSA|EC)$", n, re.I)]
    where = EvidenceSpan(file=apk_name, symbol="signing", artifact="binary", binary_path=apk_name)
    if not info.has_signing_block and not v1:
        return [make_finding("android.apk.unsigned", P, target, SEV.MEDIUM, 0.7, "The APK carries no signature (no signing block and no META-INF signature file), so it cannot be installed as-is and its publisher is unknown.",
            EvidenceSpan(file=apk_name, symbol="signing", artifact="binary", binary_path=apk_name, snippet="no APK signing block, no META-INF/*.RSA|DSA|EC"), rule_id="RULE-ANDR-SIGNING",
            alternatives=["An intermediate build artefact that is signed later."])]
    schemes = info.schemes or (["v1"] if v1 else [])
    digest = ", ".join(info.certificate_sha256) or "not extracted"
    snippet = f"schemes={schemes}; signing certificate SHA-256={digest}"
    limitations = ["Compare the certificate digest with the publisher's store release; this analyzer does not know the expected value."]
    if not info.has_signing_block and v1:
        limitations.append("Only the v1 (JAR) signature is present: it does not cover the whole file and is weaker than v2/v3.")
    span = EvidenceSpan(file=where.file, symbol="signing", artifact="binary", binary_path=apk_name, snippet=snippet[:180])
    return [make_finding("android.apk.signing", P, target, SEV.INFO, 0.9, f"The APK is signed with {', '.join(schemes)}; the signing certificate digest is recorded for comparison with the store release.",
        span, rule_id="RULE-ANDR-SIGNING", limitations=limitations)]


def analyze_js_enabled_bridge(rel_path: str, text: str, target: TargetIdentity) -> Optional[Finding]:
    """JavaScript enabled together with a native bridge in one file: the matrix's H5 combination."""
    enabled = re.search(r"setJavaScriptEnabled\s*\(\s*true\s*\)", text)
    bridge = re.search(r"addJavascriptInterface\s*\(", text)
    if not (enabled and bridge):
        return None
    line = text[: bridge.start()].count("\n") + 1
    return make_finding("android.webview.js-enabled-bridge", P, target, SEV.HIGH, 0.8,
        "JavaScript is enabled and a native object is exposed with addJavascriptInterface in the same file: any page that loads in the WebView can call into the app.",
        EvidenceSpan(file=rel_path, line=line, symbol="setJavaScriptEnabled + addJavascriptInterface", artifact="source", snippet=text.splitlines()[line - 1].strip()[:180]),
        state=FindingState.STATIC_LEAD, rule_id="RULE-ANDR-JS-ENABLED-BRIDGE", alternatives=["Bridge limited to the app's own first-party origin."])
