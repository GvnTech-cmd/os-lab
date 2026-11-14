#!/usr/bin/env python3
"""
PENT-11 - SSL / Certificate Pinning Detector & Classifier (Static)

Classifies HOW an Android app pins its TLS certificates *before* any dynamic
analysis is attempted, so the right next step can be picked:

  * network_security_config  <pin-set> in a Network Security Config (res/xml)
  * okhttp                   OkHttp CertificatePinner / "sha256/<b64>" pins
  * trustmanager             custom X509TrustManager / SSLContext / key checks
  * third_party_library      TrustKit, react-native-ssl-pinning, Cordova plugins
  * flutter                  Dart SecurityContext / BoringSSL inside libflutter
  * native                   OpenSSL / BoringSSL / libcurl pinning in .so files
  * embedded_certificate     certificates / keystores bundled in assets or res/raw

It also reports weak validation (trust-all managers, allow-all hostname
verifiers, WebView onReceivedSslError -> proceed) because those mean there is
nothing to bypass at all.

Static only: it reads a local APK or a decompiled source directory and never
touches a network, a device or a running process. Use it on applications you
own or are explicitly authorised to assess (lab scope only).

Usage:
    python3 pinning_detector.py app.apk
    python3 pinning_detector.py ./decompiled-sources -o artifacts/pinning-detect
    python3 pinning_detector.py app.apk --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

TOOL_NAME = "pinning_detector"
TOOL_VERSION = "1.0.0"
TASK_ID = "PENT-11"

MAX_FILE_BYTES = 128 * 1024 * 1024      # skip anything larger (zip-bomb guard)
MAX_EVIDENCE_PER_RULE = 3               # evidence snippets kept per rule
ANDROID_NS = "http://schemas.android.com/apk/res/android"

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".mp3", ".mp4", ".ogg", ".wav",
    ".ttf", ".otf", ".woff", ".woff2", ".arsc", ".ttc",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", "META-INF"}
TEXT_EXTENSIONS = {
    ".java", ".kt", ".smali", ".xml", ".json", ".js", ".txt", ".gradle", ".properties",
    ".html", ".yaml", ".yml", ".md", ".cfg", ".conf", ".dart", ".ts",
}
CERT_EXTENSIONS = {".crt", ".cer", ".pem", ".der", ".bks", ".jks", ".p12", ".pfx", ".keystore", ".truststore"}

WEIGHT_STRONG, WEIGHT_MEDIUM, WEIGHT_WEAK = 3, 2, 1

METHOD_LABELS = {
    "network_security_config": "Network Security Config <pin-set>",
    "okhttp": "OkHttp CertificatePinner",
    "trustmanager": "Custom TrustManager / key check",
    "third_party_library": "Third-party pinning library",
    "flutter": "Flutter / Dart (BoringSSL)",
    "native": "Native (.so) TLS verification",
    "embedded_certificate": "Embedded certificate / keystore",
}

# What to look at in the lab once the method is known (existing lab assets only).
NEXT_STEP = {
    "network_security_config": "Static: scripts/apk_patcher.py injects a permissive Network Security Config. "
                               "Dynamic: hooks/ssl-pinning-bypass.js.",
    "okhttp": "Dynamic: hooks/ssl-pinning-bypass.js (OkHttp3 CertificatePinner hook) under the lab WF2.",
    "trustmanager": "Dynamic: hooks/ssl-pinning-bypass.js (TrustManager / HostnameVerifier replacement). "
                    "Read the custom checkServerTrusted first - it may pin a key, not a CA.",
    "third_party_library": "Dynamic: hooks/ssl-pinning-bypass.js, then library-specific hooks "
                           "(TrustKit, RN ssl-pinning, Cordova plugin) if the generic path is not enough.",
    "flutter": "Dynamic: hooks/flutter-ssl-bypass.js. Java-level hooks do not see Flutter TLS.",
    "native": "No generic Java hook applies. Locate the verify callback in the .so (static RE) "
              "before choosing a native hook.",
    "embedded_certificate": "Inspect the bundled certificate/keystore and find which code loads it; "
                            "the loader tells you which of the other methods is in use.",
}


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    id: str
    method: str                 # key of METHOD_LABELS, or "weakness"
    weight: int
    description: str
    patterns: tuple             # every pattern must match in the SAME file
    kinds: tuple = ("source", "dex")  # source (smali/java/kt) | dex | native | any (every file)
    lib_ok: bool = False        # may fire inside well-known third-party library paths


def _b(*pats: str) -> tuple:
    return tuple(re.compile(p.encode("utf-8")) for p in pats)


PIN_B64 = r"[A-Za-z0-9+/]{43}="

RULES: tuple = (
    # -- OkHttp ----------------------------------------------------------
    Rule("okhttp.pin_string", "okhttp", WEIGHT_STRONG,
         "Hard-coded OkHttp pin literal (sha256/<base64>)",
         _b(r"sha(?:256|1)/" + PIN_B64), ("any",), True),
    Rule("okhttp.builder_call", "okhttp", WEIGHT_STRONG,
         "CertificatePinner.Builder.add(...) / .certificatePinner(...) call site",
         _b(r"CertificatePinner\$Builder;->add\(|CertificatePinner\.Builder\(\)|\.certificatePinner\(|CertificatePinner\.Builder\b[\s\S]{0,200}\.add\("),
         ("source",)),
    Rule("okhttp.class_present", "okhttp", WEIGHT_WEAK,
         "OkHttp CertificatePinner class present (library bundled; not proof of use)",
         _b(r"okhttp3[/.]CertificatePinner|com[/.]squareup[/.]okhttp[/.]CertificatePinner")),

    # -- Custom TrustManager / key checks --------------------------------
    Rule("trustmanager.key_compare", "trustmanager", WEIGHT_STRONG,
         "checkServerTrusted combined with public-key / digest comparison (key pinning in code)",
         _b(r"checkServerTrusted", r"getPublicKey|getEncoded|MessageDigest|SubjectPublicKeyInfo"),
         ("source",)),
    Rule("trustmanager.custom_manager", "trustmanager", WEIGHT_MEDIUM,
         "Class implementing X509TrustManager that also builds an SSLContext",
         _b(r"X509TrustManager", r"checkServerTrusted", r"SSLContext"), ("source",)),
    Rule("trustmanager.factory_keystore", "trustmanager", WEIGHT_WEAK,
         "TrustManagerFactory + KeyStore referenced (app-supplied trust store?)",
         _b(r"TrustManagerFactory", r"KeyStore")),
    Rule("trustmanager.socket_factory", "trustmanager", WEIGHT_WEAK,
         "Custom SSLSocketFactory installed on a connection/client",
         _b(r"setSSLSocketFactory|setDefaultSSLSocketFactory|sslSocketFactory\(")),
    Rule("trustmanager.api_present", "trustmanager", WEIGHT_WEAK,
         "X509TrustManager / checkServerTrusted referenced",
         _b(r"checkServerTrusted")),

    # -- Third-party libraries -------------------------------------------
    Rule("lib.trustkit_init", "third_party_library", WEIGHT_STRONG,
         "TrustKit initialised (pins from NSC or config)",
         _b(r"TrustKit;->initialize|TrustKit\.initialize|initializeWithNetworkSecurityConfiguration")),
    Rule("lib.trustkit_present", "third_party_library", WEIGHT_WEAK,
         "TrustKit library present",
         _b(r"com[/.]datatheorem[/.]android[/.]trustkit")),
    Rule("lib.rn_ssl_pinning", "third_party_library", WEIGHT_MEDIUM,
         "react-native-ssl-pinning module",
         _b(r"react-native-ssl-pinning|RNSslPinning|RNSslPinningPackage"), ("any",)),
    Rule("lib.cordova_plugin", "third_party_library", WEIGHT_MEDIUM,
         "Cordova certificate-pinning plugin",
         _b(r"sslCertificateChecker|cordova-plugin-advanced-http|CordovaHttpPlugin|sslPinning"), ("any",)),
    Rule("lib.appmattus", "third_party_library", WEIGHT_WEAK,
         "Certificate-transparency / pinning library (appmattus)",
         _b(r"com[/.]appmattus[/.]certificatetransparency")),

    # -- Flutter ----------------------------------------------------------
    Rule("flutter.security_context", "flutter", WEIGHT_MEDIUM,
         "Dart SecurityContext with custom trusted certificates",
         _b(r"setTrustedCertificatesBytes|SecurityContext\(withTrustedRoots|setTrustedCertificates"), ("any",)),
    Rule("flutter.bad_cert_callback", "flutter", WEIGHT_WEAK,
         "Dart badCertificateCallback referenced (may accept or reject certs)",
         _b(r"badCertificateCallback"), ("any",)),
    Rule("flutter.pin_package", "flutter", WEIGHT_MEDIUM,
         "Dart pinning package (http_certificate_pinning / ssl_pinning_plugin)",
         _b(r"http_certificate_pinning|ssl_pinning_plugin|HttpCertificatePinning"), ("any",)),

    # -- Native ------------------------------------------------------------
    Rule("native.curl_pin", "native", WEIGHT_STRONG,
         "libcurl public-key pin (CURLOPT_PINNEDPUBLICKEY / sha256// literal)",
         _b(r"CURLOPT_PINNEDPUBLICKEY|pinnedpublickey|sha256//" + PIN_B64), ("native", "any")),
    Rule("native.peer_cert_check", "native", WEIGHT_MEDIUM,
         "OpenSSL/BoringSSL peer-certificate retrieval used for manual comparison",
         _b(r"SSL_get(?:1)?_peer_certificate|SSL_get_peer_cert_chain", r"X509_get_pubkey|X509_digest|X509_pubkey_digest|i2d_X509"),
         ("native",)),
    Rule("native.verify_callback", "native", WEIGHT_MEDIUM,
         "Custom verify callback installed (SSL_CTX_set_verify / set_custom_verify)",
         _b(r"SSL_CTX_set_verify|SSL_set_verify|SSL_CTX_set_cert_verify_callback|SSL_set_custom_verify|SSL_CTX_set_custom_verify"),
         ("native",)),
    Rule("native.x509_verify", "native", WEIGHT_WEAK,
         "OpenSSL X509 verification primitives referenced",
         _b(r"X509_verify_cert|X509_check_host|SSL_CTX_load_verify_locations|X509_STORE_add_cert"), ("native",)),
    Rule("native.pinning_word", "native", WEIGHT_WEAK,
         "Native library mentions certificate pinning",
         _b(r"(?i)cert(?:ificate)?[_ -]?pin(?:ning|ned)?|ssl[_ -]?pinning"), ("native",)),

    # -- Weak validation (nothing to bypass) -------------------------------
    Rule("weak.allow_all_hostname", "weakness", WEIGHT_STRONG,
         "Allow-all / no-op HostnameVerifier",
         _b(r"ALLOW_ALL_HOSTNAME_VERIFIER|AllowAllHostnameVerifier|NoopHostnameVerifier")),
    Rule("weak.trust_all", "weakness", WEIGHT_STRONG,
         "Trust-all TrustManager by name (TrustAll* / Insecure* / Unsafe*)",
         _b(r"(?i)trust[_-]?all(?:cert|manager|trust)\w*|Insecure(?:Trust|X509)\w*|UnsafeTrust\w*|AcceptAllCert\w*")),
    Rule("weak.webview_proceed", "weakness", WEIGHT_MEDIUM,
         "WebView onReceivedSslError that proceeds past TLS errors",
         _b(r"onReceivedSslError", r"SslErrorHandler;->proceed|handler\.proceed\("), ("source",)),
)


# ---------------------------------------------------------------------------
# Binary XML (AXML) decoder - lets us read the manifest and res/xml/*.xml
# straight out of an APK without apktool.
# ---------------------------------------------------------------------------

_RES_XML_TYPE = 0x0003
_RES_STRING_POOL = 0x0001
_RES_START_ELEMENT = 0x0102
_RES_END_ELEMENT = 0x0103
_RES_TEXT = 0x0104
_TYPE_REFERENCE, _TYPE_STRING, _TYPE_INT_DEC, _TYPE_INT_HEX, _TYPE_BOOL = 0x01, 0x03, 0x10, 0x11, 0x12


def _read_pool_string(data: bytes, base: int, utf8: bool) -> str:
    if utf8:
        n = data[base]
        o = base + 1
        if n & 0x80:
            n = ((n & 0x7F) << 8) | data[o]
            o += 1
        blen = data[o]
        o += 1
        if blen & 0x80:
            blen = ((blen & 0x7F) << 8) | data[o]
            o += 1
        return data[o:o + blen].decode("utf-8", "replace")
    (n,) = struct.unpack_from("<H", data, base)
    o = base + 2
    if n & 0x8000:
        (lo,) = struct.unpack_from("<H", data, o)
        n = ((n & 0x7FFF) << 16) | lo
        o += 2
    return data[o:o + n * 2].decode("utf-16-le", "replace")


def _parse_string_pool(data: bytes, pos: int) -> list:
    count, _styles, flags, strings_start = struct.unpack_from("<IIII", data, pos + 8)
    (header_size,) = struct.unpack_from("<H", data, pos + 2)
    utf8 = bool(flags & 0x100)
    out = []
    offsets_at = pos + header_size
    for i in range(count):
        (off,) = struct.unpack_from("<I", data, offsets_at + 4 * i)
        try:
            out.append(_read_pool_string(data, pos + strings_start + off, utf8))
        except (IndexError, struct.error):
            out.append("")
    return out


def decode_axml(data: bytes):
    """Decode Android binary XML into an ElementTree element (None if not AXML)."""
    if len(data) < 16 or struct.unpack_from("<H", data, 0)[0] != _RES_XML_TYPE:
        return None
    strings: list = []

    def s(idx: int) -> str:
        return strings[idx] if 0 <= idx < len(strings) else ""

    root = None
    stack: list = []
    pos = 8
    try:
        while pos + 8 <= len(data):
            ctype, _hsize, csize = struct.unpack_from("<HHI", data, pos)
            if csize < 8 or pos + csize > len(data):
                break
            if ctype == _RES_STRING_POOL:
                strings = _parse_string_pool(data, pos)
            elif ctype == _RES_START_ELEMENT:
                _ns, name = struct.unpack_from("<II", data, pos + 16)
                attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, pos + 24)
                elem = ET.Element(s(name))
                base = pos + 16 + attr_start
                for i in range(attr_count):
                    o = base + i * (attr_size or 20)
                    a_ns, a_name, a_raw = struct.unpack_from("<III", data, o)
                    _sz, _res0, dtype, ddata = struct.unpack_from("<HBBI", data, o + 12)
                    if a_raw != 0xFFFFFFFF:
                        value = s(a_raw)
                    elif dtype == _TYPE_BOOL:
                        value = "true" if ddata else "false"
                    elif dtype == _TYPE_STRING:
                        value = s(ddata)
                    elif dtype == _TYPE_REFERENCE:
                        value = "@0x%08x" % ddata
                    elif dtype in (_TYPE_INT_DEC, _TYPE_INT_HEX):
                        value = str(struct.unpack("<i", struct.pack("<I", ddata))[0])
                    else:
                        value = str(ddata)
                    key = ("android:" if s(a_ns) == ANDROID_NS else "") + s(a_name)
                    elem.set(key, value)
                if stack:
                    stack[-1].append(elem)
                else:
                    root = elem
                stack.append(elem)
            elif ctype == _RES_END_ELEMENT:
                if stack:
                    stack.pop()
            elif ctype == _RES_TEXT and stack:
                (idx,) = struct.unpack_from("<I", data, pos + 16)
                text = s(idx).strip()
                if text:
                    stack[-1].text = (stack[-1].text or "") + text
            pos += csize
    except (struct.error, IndexError):
        return root
    return root


def parse_xml_bytes(data: bytes):
    """Binary AXML or plain-text XML -> Element; None when it is neither."""
    root = decode_axml(data)
    if root is not None:
        return root
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
    if not head.startswith(b"<") or b"<!ENTITY" in data or b"<!DOCTYPE" in data:
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        return None


# ---------------------------------------------------------------------------
# Network Security Config + manifest analysis
# ---------------------------------------------------------------------------

def _tf(value):
    if value is None:
        return None
    return str(value).strip().lower() == "true"


def analyze_nsc(root, today: date | None = None) -> dict:
    """Summarise a <network-security-config> element tree."""
    today = today or date.today()
    configs = []
    warnings = []

    for dc in root.iter("domain-config"):
        domains = [{"name": (d.text or "").strip(),
                    "include_subdomains": _tf(d.get("includeSubdomains"))}
                   for d in dc.findall("domain")]
        pin_set = dc.find("pin-set")
        pins, expiration, expired = [], None, False
        if pin_set is not None:
            expiration = pin_set.get("expiration")
            for p in pin_set.findall("pin"):
                pins.append({"digest": p.get("digest", "SHA-256"), "value": (p.text or "").strip()})
            if expiration:
                try:
                    expired = datetime.strptime(expiration.strip(), "%Y-%m-%d").date() < today
                except ValueError:
                    pass
            names = ", ".join(d["name"] for d in domains) or "?"
            if len(pins) == 1:
                warnings.append(f"{names}: only one pin - no backup pin (lock-out risk)")
            if expired:
                warnings.append(f"{names}: pin-set expired on {expiration} - Android stops enforcing it")
        anchors = [c.get("src", "") for ta in dc.findall("trust-anchors") for c in ta.findall("certificates")]
        configs.append({
            "domains": domains,
            "pins": pins,
            "pin_set_expiration": expiration,
            "pin_set_expired": expired,
            "trust_anchors": anchors,
            "cleartext_permitted": _tf(dc.get("cleartextTrafficPermitted")),
        })

    base = root.find("base-config")
    base_info = None
    if base is not None:
        base_anchors = [c.get("src", "") for ta in base.findall("trust-anchors") for c in ta.findall("certificates")]
        base_info = {"trust_anchors": base_anchors, "cleartext_permitted": _tf(base.get("cleartextTrafficPermitted"))}
        if "user" in base_anchors:
            warnings.append("base-config trusts user-installed CAs (interception-friendly)")
        if base_info["cleartext_permitted"]:
            warnings.append("base-config permits cleartext traffic")

    debug = root.find("debug-overrides")
    debug_info = None
    if debug is not None:
        d_anchors = [c.get("src", "") for ta in debug.findall("trust-anchors") for c in ta.findall("certificates")]
        debug_info = {"trust_anchors": d_anchors}
        warnings.append("debug-overrides present: extra trust anchors apply to debuggable builds only")

    total_pins = sum(len(c["pins"]) for c in configs)
    active = any(c["pins"] and not c["pin_set_expired"] for c in configs)
    return {
        "domain_configs": configs,
        "base_config": base_info,
        "debug_overrides": debug_info,
        "pin_count": total_pins,
        "pinning_active": active,
        "warnings": warnings,
    }


def analyze_manifest(root) -> dict:
    info = {"package": root.get("package"), "network_security_config_ref": None,
            "uses_cleartext_traffic": None, "debuggable": None,
            "min_sdk": None, "target_sdk": None}
    app = root.find("application")
    if app is not None:
        info["network_security_config_ref"] = app.get("android:networkSecurityConfig") or app.get("networkSecurityConfig")
        info["uses_cleartext_traffic"] = _tf(app.get("android:usesCleartextTraffic") or app.get("usesCleartextTraffic"))
        info["debuggable"] = _tf(app.get("android:debuggable") or app.get("debuggable"))
    sdk = root.find("uses-sdk")
    if sdk is not None:
        info["min_sdk"] = sdk.get("android:minSdkVersion") or sdk.get("minSdkVersion")
        info["target_sdk"] = sdk.get("android:targetSdkVersion") or sdk.get("targetSdkVersion")
    return info


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    file: str
    where: str          # "line 12" or "offset 0x1f40"
    snippet: str

    def to_dict(self) -> dict:
        return {"file": self.file, "where": self.where, "snippet": self.snippet}


@dataclass
class ScanState:
    hits: dict = field(default_factory=dict)       # rule id -> list[Evidence]
    files_scanned: int = 0
    nsc_files: list = field(default_factory=list)  # (path, analysis)
    manifest: dict | None = None
    frameworks: set = field(default_factory=set)
    native_libs: list = field(default_factory=list)
    cert_files: list = field(default_factory=list)


def _file_kind(path: str) -> str:
    ext = os.path.splitext(path.lower())[1]
    if ext == ".so":
        return "native"
    if ext == ".dex":
        return "dex"
    if ext in (".smali", ".java", ".kt"):
        return "source"
    return "other"


LIBRARY_PATH = re.compile(
    r"(^|/)(okhttp3|okhttp|okio|kotlin|kotlinx|androidx|android/support|retrofit2|"
    r"org/conscrypt|org/bouncycastle|org/apache|com/google/(android|gson|common)|"
    r"com/squareup|io/reactivex|com/bumptech)/")


def _is_texty(path: str, data: bytes) -> bool:
    ext = os.path.splitext(path.lower())[1]
    if ext in TEXT_EXTENSIONS:
        return True
    return b"\x00" not in data[:1024]


def _snippet(data: bytes, start: int, end: int, texty: bool) -> tuple:
    if texty:
        line_no = data.count(b"\n", 0, start) + 1
        ls = data.rfind(b"\n", 0, start) + 1
        le = data.find(b"\n", end)
        le = len(data) if le == -1 else le
        text = data[ls:le].decode("utf-8", "replace").strip()
        return f"line {line_no}", text[:160]
    text = data[start:end].decode("latin-1", "replace")
    text = "".join(ch if 32 <= ord(ch) < 127 else "." for ch in text)
    return f"offset 0x{start:x}", text[:160]


FRAMEWORK_MARKERS = (
    (re.compile(r"(^|/)libflutter\.so$"), "flutter"),
    (re.compile(r"(^|/)libapp\.so$"), "flutter"),
    (re.compile(r"(^|/)libreactnativejni\.so$|index\.android\.bundle$"), "react-native"),
    (re.compile(r"(^|/)libil2cpp\.so$|libunity\.so$"), "unity"),
    (re.compile(r"(^|/)libmonosgen-2\.0\.so$|assemblies/.*\.dll$"), "xamarin"),
    (re.compile(r"(^|/)cordova\.js$|assets/www/"), "cordova"),
    (re.compile(r"(^|/)libcurl\.so$"), "libcurl"),
    (re.compile(r"(^|/)lib(ssl|crypto)(\.\d+)*\.so$|libboringssl\.so$|libconscrypt_jni\.so$"), "bundled-tls"),
)


def scan_blob(state: ScanState, path: str, data: bytes) -> None:
    """Scan one file's bytes against every rule."""
    state.files_scanned += 1
    norm = path.replace("\\", "/")
    low = norm.lower()
    ext = os.path.splitext(low)[1]

    for rx, name in FRAMEWORK_MARKERS:
        if rx.search(low):
            state.frameworks.add(name)
    if ext == ".so":
        state.native_libs.append(norm)

    base = os.path.basename(low)
    if low == "androidmanifest.xml" or base == "androidmanifest.xml":
        root = parse_xml_bytes(data)
        if root is not None and root.tag == "manifest" and state.manifest is None:
            state.manifest = analyze_manifest(root)
        return

    if ext == ".xml":
        root = parse_xml_bytes(data)
        if root is not None and root.tag == "network-security-config":
            state.nsc_files.append((norm, analyze_nsc(root)))
            return
        if root is not None and ext == ".xml" and low.startswith("res/"):
            # compiled resource XML that is not an NSC: nothing else to learn
            return

    if ext in CERT_EXTENSIONS and "meta-inf" not in low:
        state.cert_files.append(norm)

    kind = _file_kind(norm)
    texty = _is_texty(norm, data)
    in_library = kind == "source" and bool(LIBRARY_PATH.search(re.sub(r"^(smali[^/]*|src|sources)/", "", low)))
    for rule in RULES:
        if kind not in rule.kinds and "any" not in rule.kinds:
            continue
        if in_library and not rule.lib_ok and rule.weight > WEIGHT_WEAK:
            continue
        first = None
        ok = True
        for pat in rule.patterns:
            m = pat.search(data)
            if m is None:
                ok = False
                break
            if first is None:
                first = m
        if not ok:
            continue
        bucket = state.hits.setdefault(rule.id, [])
        if len(bucket) >= MAX_EVIDENCE_PER_RULE:
            continue
        where, snip = _snippet(data, first.start(), first.end(), texty)
        bucket.append(Evidence(norm, where, snip))


def scan_apk(state: ScanState, apk_path: str) -> None:
    with zipfile.ZipFile(apk_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.file_size > MAX_FILE_BYTES:
                continue
            name = info.filename
            if os.path.splitext(name.lower())[1] in SKIP_EXTENSIONS:
                continue
            if name.startswith("META-INF/"):
                continue
            try:
                data = zf.read(info)
            except (zipfile.BadZipFile, RuntimeError, OSError):
                continue
            scan_blob(state, name, data)


def scan_dir(state: ScanState, root_dir: str) -> None:
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if os.path.splitext(fn.lower())[1] in SKIP_EXTENSIONS:
                continue
            full = os.path.join(root, fn)
            try:
                if os.path.getsize(full) > MAX_FILE_BYTES:
                    continue
                with open(full, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            scan_blob(state, os.path.relpath(full, root_dir), data)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _confidence(score: int, strongest: int) -> str:
    if strongest >= WEIGHT_STRONG or score >= 4:
        return "high"
    if score >= WEIGHT_MEDIUM:
        return "medium"
    return "low"


def classify(state: ScanState) -> dict:
    methods: dict = {}
    weaknesses: list = []
    rule_by_id = {r.id: r for r in RULES}

    for rid, ev in state.hits.items():
        rule = rule_by_id[rid]
        entry = {"rule": rid, "weight": rule.weight, "description": rule.description,
                 "evidence": [e.to_dict() for e in ev]}
        if rule.method == "weakness":
            weaknesses.append(entry)
            continue
        m = methods.setdefault(rule.method, {"score": 0, "strongest": 0, "signals": []})
        m["score"] += rule.weight
        m["strongest"] = max(m["strongest"], rule.weight)
        m["signals"].append(entry)

    # Network Security Config: parsed structurally, so it outranks regex hints.
    for path, nsc in state.nsc_files:
        if nsc["pin_count"] == 0:
            continue
        m = methods.setdefault("network_security_config", {"score": 0, "strongest": 0, "signals": []})
        weight = WEIGHT_STRONG if nsc["pinning_active"] else WEIGHT_WEAK
        m["score"] += weight
        m["strongest"] = max(m["strongest"], weight)
        m["signals"].append({
            "rule": "nsc.pin_set", "weight": weight,
            "description": f"{nsc['pin_count']} pin(s) in {len(nsc['domain_configs'])} domain-config(s)"
                           + ("" if nsc["pinning_active"] else " (all pin-sets expired)"),
            "evidence": [{"file": path, "where": "pin-set", "snippet": ", ".join(
                d["name"] for c in nsc["domain_configs"] if c["pins"] for d in c["domains"])[:160]}],
        })
        ref = (state.manifest or {}).get("network_security_config_ref")
        if state.manifest is not None and not ref:
            nsc["warnings"].append("manifest has no android:networkSecurityConfig - this file may be unused")

    if state.cert_files:
        methods["embedded_certificate"] = {
            "score": WEIGHT_MEDIUM, "strongest": WEIGHT_MEDIUM,
            "signals": [{"rule": "cert.bundled", "weight": WEIGHT_MEDIUM,
                         "description": f"{len(state.cert_files)} certificate/keystore file(s) bundled",
                         "evidence": [{"file": f, "where": "file", "snippet": ""} for f in state.cert_files[:5]]}],
        }

    # Framework hints strengthen the matching method but never create pinning on their own.
    if "flutter" in state.frameworks and "flutter" in methods:
        methods["flutter"]["score"] += WEIGHT_WEAK
    if "react-native" in state.frameworks and "third_party_library" in methods:
        methods["third_party_library"]["score"] += WEIGHT_WEAK

    ranked = []
    for name, m in methods.items():
        ranked.append({
            "method": name,
            "label": METHOD_LABELS[name],
            "confidence": _confidence(m["score"], m["strongest"]),
            "score": m["score"],
            "signals": sorted(m["signals"], key=lambda s: -s["weight"]),
            "next_step": NEXT_STEP[name],
        })
    order = {"high": 0, "medium": 1, "low": 2}
    ranked.sort(key=lambda r: (order[r["confidence"]], -r["score"]))

    strong_weak = any(w["weight"] >= WEIGHT_STRONG for w in weaknesses)
    top = ranked[0] if ranked else None
    if top and top["confidence"] == "high":
        status = "pinned"
    elif top and top["confidence"] == "medium":
        status = "likely_pinned"
    elif top:
        status = "possible"
    else:
        status = "none_detected"

    return {
        "pinning_status": status,
        "primary_method": top["method"] if top and top["confidence"] != "low" else None,
        "methods": ranked,
        "weak_validation": weaknesses,
        "weak_validation_note": ("Trust-all / allow-all validation found: TLS may be interceptable "
                                 "without any bypass." if strong_weak else None),
    }


def analyze(target: str) -> dict:
    """Run the full static analysis on an APK or decompiled directory."""
    state = ScanState()
    if os.path.isdir(target):
        kind = "directory"
        scan_dir(state, target)
    else:
        kind = "apk"
        scan_apk(state, target)

    result = classify(state)
    return {
        "task": TASK_ID,
        "tool": f"{TOOL_NAME} {TOOL_VERSION}",
        "target": os.path.abspath(target),
        "target_type": kind,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "scope_notice": "Static analysis of a local file only. Use on apps you own or are authorised to assess.",
        "files_scanned": state.files_scanned,
        "manifest": state.manifest,
        "frameworks": sorted(state.frameworks),
        "native_libs": sorted(state.native_libs),
        "network_security_config": [{"file": p, **a} for p, a in state.nsc_files],
        **result,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def render_markdown(r: dict) -> str:
    out = [f"# SSL / Certificate Pinning Report ({r['task']})", "",
           f"- **Target:** `{r['target']}` ({r['target_type']})",
           f"- **Timestamp:** {r['timestamp']}",
           f"- **Files scanned:** {r['files_scanned']}",
           f"- **Status:** **{r['pinning_status']}**",
           f"- **Primary method:** {METHOD_LABELS.get(r['primary_method'], 'n/a')}"]
    if r["manifest"]:
        mf = r["manifest"]
        out.append(f"- **Package:** `{mf.get('package')}` (minSdk {mf.get('min_sdk')}, targetSdk {mf.get('target_sdk')})")
    if r["frameworks"]:
        out.append(f"- **Frameworks:** {', '.join(r['frameworks'])}")
    out += ["", f"> {r['scope_notice']}", "", "## Classification", ""]
    if not r["methods"]:
        out.append("No pinning indicators found.")
    else:
        out += ["| Method | Confidence | Score | Next step |", "|---|---|---|---|"]
        for m in r["methods"]:
            out.append(f"| {m['label']} | {m['confidence']} | {m['score']} | {m['next_step']} |")
        for m in r["methods"]:
            out += ["", f"### {m['label']}", ""]
            for s in m["signals"]:
                out.append(f"- ({s['weight']}) {s['description']}")
                for e in s["evidence"]:
                    out.append(f"  - `{e['file']}` {e['where']}: `{e['snippet']}`")
    for nsc in r["network_security_config"]:
        out += ["", f"## Network Security Config: `{nsc['file']}`", ""]
        for c in nsc["domain_configs"]:
            doms = ", ".join(d["name"] for d in c["domains"]) or "?"
            out.append(f"- **{doms}** - {len(c['pins'])} pin(s)"
                       + (f", expires {c['pin_set_expiration']}" if c["pin_set_expiration"] else ""))
        for w in nsc["warnings"]:
            out.append(f"- WARNING: {w}")
    if r["weak_validation"]:
        out += ["", "## Weak validation", ""]
        if r["weak_validation_note"]:
            out.append(r["weak_validation_note"])
        for w in r["weak_validation"]:
            out.append(f"- {w['description']}")
            for e in w["evidence"]:
                out.append(f"  - `{e['file']}` {e['where']}: `{e['snippet']}`")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    p = argparse.ArgumentParser(
        description="PENT-11 static SSL/certificate-pinning detector & classifier (lab scope only)")
    p.add_argument("target", help="Path to an APK or a decompiled source directory")
    p.add_argument("-o", "--out", help="Directory for JSON + Markdown reports "
                                       "(default: artifacts/pinning-detect)")
    p.add_argument("--json", action="store_true", help="Print the JSON report to stdout and write no files")
    args = p.parse_args(argv)

    if not os.path.exists(args.target):
        print(f"Error: target does not exist: {args.target}", file=sys.stderr)
        return 1
    if os.path.isfile(args.target) and not zipfile.is_zipfile(args.target):
        print(f"Error: not a valid APK/zip archive: {args.target}", file=sys.stderr)
        return 1

    report = analyze(args.target)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=== SSL / Certificate Pinning Detector (static) ===")
    print(f"Status        : {report['pinning_status']}")
    print(f"Primary method: {METHOD_LABELS.get(report['primary_method'], 'n/a')}")
    for m in report["methods"]:
        print(f"  - {m['label']}: {m['confidence']} (score {m['score']})")
    if report["weak_validation_note"]:
        print(f"WARNING: {report['weak_validation_note']}")

    out_dir = args.out or os.path.join("artifacts", "pinning-detect")
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "pinning-report.json")
    md_path = os.path.join(out_dir, "pinning-report.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    print(f"\nReports saved to:\n  JSON : {json_path}\n  MD   : {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
