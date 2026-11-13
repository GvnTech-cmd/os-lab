"""PENT-11: static SSL/certificate-pinning detector & classifier.

All fixtures are synthetic and built in-memory; nothing here touches a network or a device.
"""
import json
import os
import struct
import zipfile
from datetime import date

import pytest

from scripts import pinning_detector as pd

PIN = "sha256/" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/AbCdE" + "="  # 43 b64 chars + '='
assert len(PIN) == len("sha256/") + 44


# --------------------------------------------------------------------------
# Minimal Android binary-XML (AXML) encoder, used only to build fixtures
# --------------------------------------------------------------------------

def build_axml(tree):
    """tree = (tag, {attr: str|bool}, [children], text). 'android:x' attrs get the android namespace."""
    strings = []

    def sid(text):
        if text not in strings:
            strings.append(text)
        return strings.index(text)

    sid(pd.ANDROID_NS)
    body = bytearray()

    def emit(node):
        tag, attrs, kids, text = node
        name = sid(tag)
        packed = b""
        for key, val in attrs.items():
            ns = 0xFFFFFFFF
            if key.startswith("android:"):
                ns, key = sid(pd.ANDROID_NS), key[len("android:"):]
            if isinstance(val, bool):
                raw, dtype, data = 0xFFFFFFFF, 0x12, 0xFFFFFFFF if val else 0
            else:
                raw = sid(val)
                dtype, data = 0x03, raw
            packed += struct.pack("<IIIHBBI", ns, sid(key), raw, 8, 0, dtype, data)
        size = 36 + len(packed)
        body.extend(struct.pack("<HHIII", 0x0102, 16, size, 1, 0xFFFFFFFF))
        body.extend(struct.pack("<IIHHHHHH", 0xFFFFFFFF, name, 0x14, 0x14, len(attrs), 0, 0, 0))
        body.extend(packed)
        if text:
            body.extend(struct.pack("<HHIII", 0x0104, 16, 28, 1, 0xFFFFFFFF))
            body.extend(struct.pack("<IHBBI", sid(text), 8, 0, 3, 0))
        for kid in kids:
            emit(kid)
        body.extend(struct.pack("<HHIIIII", 0x0103, 16, 24, 1, 0xFFFFFFFF, 0xFFFFFFFF, name))

    emit(tree)

    pool_strings = b""
    offsets = []
    for s in strings:
        offsets.append(len(pool_strings))
        enc = s.encode("utf-16-le")
        pool_strings += struct.pack("<H", len(s)) + enc + b"\x00\x00"
    while len(pool_strings) % 4:
        pool_strings += b"\x00"
    strings_start = 28 + 4 * len(strings)
    pool = struct.pack("<HHIIIIII", 0x0001, 28, strings_start + len(pool_strings),
                       len(strings), 0, 0, strings_start, 0)
    pool += b"".join(struct.pack("<I", o) for o in offsets) + pool_strings
    total = 8 + len(pool) + len(body)
    return struct.pack("<HHI", 0x0003, 8, total) + pool + bytes(body)


def nsc_tree(pins=("AAAA", "BBBB"), expiration=None, domain="api.lab.test"):
    pin_set_attrs = {"expiration": expiration} if expiration else {}
    pin_kids = [("pin", {"digest": "SHA-256"}, [], p) for p in pins]
    return ("network-security-config", {}, [
        ("domain-config", {}, [
            ("domain", {"includeSubdomains": True}, [], domain),
            ("pin-set", pin_set_attrs, pin_kids, None),
        ], None),
    ], None)


def manifest_tree(nsc_ref=True):
    app_attrs = {"android:networkSecurityConfig": "@xml/network_security_config"} if nsc_ref else {}
    return ("manifest", {"package": "lab.test.app"}, [
        ("uses-sdk", {"android:minSdkVersion": "24", "android:targetSdkVersion": "34"}, [], None),
        ("application", app_attrs, [], None),
    ], None)


def make_apk(tmp_path, files, name="t.apk"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for fname, data in files.items():
            zf.writestr(fname, data)
    return str(path)


def dex(*strings):
    """Fake dex: header magic + NUL-separated strings (what the detector sees in a real dex)."""
    return b"dex\n035\x00" + b"\x00".join(s.encode() for s in strings) + b"\x00"


def methods_of(report):
    return {m["method"]: m for m in report["methods"]}


# --------------------------------------------------------------------------
# AXML / NSC
# --------------------------------------------------------------------------

def test_axml_roundtrip_decodes_tags_attrs_and_text():
    root = pd.decode_axml(build_axml(nsc_tree()))
    assert root.tag == "network-security-config"
    dc = root.find("domain-config")
    assert dc.find("domain").text == "api.lab.test"
    assert dc.find("domain").get("includeSubdomains") == "true"
    assert [p.text for p in dc.find("pin-set").findall("pin")] == ["AAAA", "BBBB"]


def test_decode_axml_rejects_garbage():
    assert pd.decode_axml(b"not axml at all, definitely") is None
    assert pd.decode_axml(b"") is None


def test_analyze_manifest_reads_package_sdk_and_nsc_ref():
    info = pd.analyze_manifest(pd.decode_axml(build_axml(manifest_tree())))
    assert info["package"] == "lab.test.app"
    assert (info["min_sdk"], info["target_sdk"]) == ("24", "34")
    assert info["network_security_config_ref"] == "@xml/network_security_config"


def test_nsc_pinning_classified_high(tmp_path):
    apk = make_apk(tmp_path, {
        "AndroidManifest.xml": build_axml(manifest_tree()),
        "res/xml/network_security_config.xml": build_axml(nsc_tree()),
        "classes.dex": dex("Lcom/example/Main;"),
    })
    report = pd.analyze(apk)
    assert report["pinning_status"] == "pinned"
    assert report["primary_method"] == "network_security_config"
    assert methods_of(report)["network_security_config"]["confidence"] == "high"
    nsc = report["network_security_config"][0]
    assert nsc["pin_count"] == 2 and nsc["pinning_active"]
    assert report["manifest"]["package"] == "lab.test.app"


def test_nsc_expired_pin_set_is_downgraded():
    root = pd.decode_axml(build_axml(nsc_tree(expiration="2020-01-01")))
    nsc = pd.analyze_nsc(root, today=date(2026, 1, 1))
    assert nsc["pin_count"] == 2
    assert not nsc["pinning_active"]
    assert any("expired" in w for w in nsc["warnings"])


def test_nsc_single_pin_warns_about_missing_backup():
    nsc = pd.analyze_nsc(pd.decode_axml(build_axml(nsc_tree(pins=("ONLY",)))))
    assert any("backup" in w for w in nsc["warnings"])


def test_nsc_without_manifest_reference_is_flagged(tmp_path):
    apk = make_apk(tmp_path, {
        "AndroidManifest.xml": build_axml(manifest_tree(nsc_ref=False)),
        "res/xml/network_security_config.xml": build_axml(nsc_tree()),
    })
    nsc = pd.analyze(apk)["network_security_config"][0]
    assert any("unused" in w for w in nsc["warnings"])


def test_plain_text_nsc_in_decompiled_directory(tmp_path):
    xml = tmp_path / "res" / "xml"
    xml.mkdir(parents=True)
    (xml / "network_security_config.xml").write_text(
        '<network-security-config><domain-config><domain>a.lab.test</domain>'
        '<pin-set><pin digest="SHA-256">XYZ=</pin></pin-set></domain-config>'
        '<debug-overrides><trust-anchors><certificates src="user"/></trust-anchors></debug-overrides>'
        '</network-security-config>', encoding="utf-8")
    report = pd.analyze(str(tmp_path))
    assert report["target_type"] == "directory"
    assert report["primary_method"] == "network_security_config"
    assert any("debug-overrides" in w for w in report["network_security_config"][0]["warnings"])


def test_nsc_without_pins_is_not_pinning(tmp_path):
    tree = ("network-security-config", {}, [
        ("base-config", {"cleartextTrafficPermitted": True}, [], None)], None)
    apk = make_apk(tmp_path, {"res/xml/nsc.xml": build_axml(tree)})
    report = pd.analyze(apk)
    assert report["pinning_status"] == "none_detected"
    assert any("cleartext" in w for w in report["network_security_config"][0]["warnings"])


def test_xml_with_entities_is_refused():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><network-security-config>&a;</network-security-config>'
    assert pd.parse_xml_bytes(evil) is None


# --------------------------------------------------------------------------
# Code-level methods
# --------------------------------------------------------------------------

def test_okhttp_pin_literal_in_dex_is_high(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lokhttp3/CertificatePinner;", PIN, "api.lab.test")})
    report = pd.analyze(apk)
    assert report["primary_method"] == "okhttp"
    assert methods_of(report)["okhttp"]["confidence"] == "high"
    ev = methods_of(report)["okhttp"]["signals"][0]["evidence"][0]
    assert ev["where"].startswith("offset 0x")


def test_okhttp_class_only_is_just_possible(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lokhttp3/CertificatePinner;", "Lokhttp3/OkHttpClient;")})
    report = pd.analyze(apk)
    assert report["pinning_status"] == "possible"
    assert report["primary_method"] is None
    assert methods_of(report)["okhttp"]["confidence"] == "low"


def test_okhttp_builder_call_in_smali_reports_line_number(tmp_path):
    smali = tmp_path / "smali" / "com" / "lab"
    smali.mkdir(parents=True)
    (smali / "Net.smali").write_text(
        ".class public Lcom/lab/Net;\n.method build()V\n"
        "    invoke-virtual {v0, v1, v2}, Lokhttp3/CertificatePinner$Builder;->add(Ljava/lang/String;[Ljava/lang/String;)Lokhttp3/CertificatePinner$Builder;\n"
        ".end method\n", encoding="utf-8")
    report = pd.analyze(str(tmp_path))
    assert report["primary_method"] == "okhttp"
    ev = methods_of(report)["okhttp"]["signals"][0]["evidence"][0]
    assert ev["where"] == "line 3"


def test_okhttp_library_smali_does_not_count_as_app_pinning(tmp_path):
    lib = tmp_path / "smali" / "okhttp3"
    lib.mkdir(parents=True)
    (lib / "CertificatePinner.smali").write_text(
        ".class public Lokhttp3/CertificatePinner;\n"
        "invoke-virtual {p0}, Lokhttp3/CertificatePinner$Builder;->add(Ljava/lang/String;)V\n"
        'const-string v0, "sha256/"\n', encoding="utf-8")
    report = pd.analyze(str(tmp_path))
    assert report["pinning_status"] == "possible"          # class-present only


def test_custom_trustmanager_key_comparison_is_high(tmp_path):
    src = tmp_path / "src" / "com" / "lab"
    src.mkdir(parents=True)
    (src / "PinningTrustManager.java").write_text(
        "class PinningTrustManager implements X509TrustManager {\n"
        "  public void checkServerTrusted(X509Certificate[] chain, String a) {\n"
        "    byte[] enc = chain[0].getPublicKey().getEncoded();\n"
        "    if (!Arrays.equals(MessageDigest.getInstance(\"SHA-256\").digest(enc), PINNED)) throw new CertificateException();\n"
        "  }\n}\n", encoding="utf-8")
    report = pd.analyze(str(tmp_path))
    assert report["primary_method"] == "trustmanager"
    assert methods_of(report)["trustmanager"]["confidence"] == "high"


def test_trustmanager_api_references_alone_are_low(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Ljavax/net/ssl/X509TrustManager;", "checkServerTrusted",
                                                 "MessageDigest", "getEncoded")})
    report = pd.analyze(apk)
    assert report["pinning_status"] == "possible"
    assert methods_of(report)["trustmanager"]["confidence"] == "low"


def test_trustkit_initialisation_detected(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lcom/datatheorem/android/trustkit/TrustKit;",
                                                 "TrustKit;->initializeWithNetworkSecurityConfiguration")})
    report = pd.analyze(apk)
    assert report["primary_method"] == "third_party_library"


def test_react_native_ssl_pinning_package(tmp_path):
    apk = make_apk(tmp_path, {"assets/index.android.bundle": b"import 'react-native-ssl-pinning'; fetch(url,{sslPinning:{}})"})
    report = pd.analyze(apk)
    assert "react-native" in report["frameworks"]
    assert report["primary_method"] == "third_party_library"


# --------------------------------------------------------------------------
# Flutter / native / embedded certs
# --------------------------------------------------------------------------

def test_flutter_security_context(tmp_path):
    apk = make_apk(tmp_path, {
        "lib/arm64-v8a/libflutter.so": b"\x7fELF" + b"\x00" * 16 + b"ssl_crypto_x509_session_verify_cert_chain",
        "lib/arm64-v8a/libapp.so": b"\x7fELF" + b"\x00" * 16 + b"setTrustedCertificatesBytes\x00SecurityContext",
    })
    report = pd.analyze(apk)
    assert "flutter" in report["frameworks"]
    assert report["primary_method"] == "flutter"
    assert "flutter-ssl-bypass.js" in methods_of(report)["flutter"]["next_step"]


def test_flutter_without_pinning_signals_is_not_pinned(tmp_path):
    apk = make_apk(tmp_path, {"lib/arm64-v8a/libflutter.so": b"\x7fELF" + b"\x00" * 64})
    report = pd.analyze(apk)
    assert report["pinning_status"] == "none_detected"
    assert "flutter" in report["frameworks"]


def test_native_curl_pin(tmp_path):
    pin = ("sha256//" + "A" * 43 + "=").encode()
    apk = make_apk(tmp_path, {"lib/x86_64/libnet.so": b"\x7fELF" + b"\x00" * 8 + b"CURLOPT_PINNEDPUBLICKEY\x00" + pin})
    report = pd.analyze(apk)
    assert report["primary_method"] == "native"
    assert "libnet.so" in report["native_libs"][0]


def test_native_verify_primitives_alone_stay_low(tmp_path):
    apk = make_apk(tmp_path, {"lib/x86_64/libssl_user.so": b"\x7fELF\x00X509_verify_cert\x00"})
    report = pd.analyze(apk)
    assert report["pinning_status"] == "possible"
    assert methods_of(report)["native"]["confidence"] == "low"


def test_embedded_certificate_in_assets(tmp_path):
    apk = make_apk(tmp_path, {
        "assets/server.crt": b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
        "META-INF/CERT.RSA": b"signature, must be ignored",
    })
    report = pd.analyze(apk)
    m = methods_of(report)["embedded_certificate"]
    assert m["confidence"] == "medium"
    assert report["pinning_status"] == "likely_pinned"
    assert all("META-INF" not in e["file"] for s in m["signals"] for e in s["evidence"])


# --------------------------------------------------------------------------
# Weak validation / negatives
# --------------------------------------------------------------------------

def test_trust_all_and_allow_all_reported_as_weak_validation(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lorg/apache/http/conn/ssl/SSLSocketFactory;->ALLOW_ALL_HOSTNAME_VERIFIER",
                                                 "Lcom/lab/TrustAllCerts;")})
    report = pd.analyze(apk)
    assert report["weak_validation_note"]
    ids = {w["rule"] for w in report["weak_validation"]}
    assert {"weak.allow_all_hostname", "weak.trust_all"} <= ids
    assert report["pinning_status"] == "none_detected"      # weakness is not pinning


def test_webview_proceed_in_source(tmp_path):
    (tmp_path / "Web.java").write_text(
        "public void onReceivedSslError(WebView v, SslErrorHandler handler, SslError e) { handler.proceed(); }",
        encoding="utf-8")
    ids = {w["rule"] for w in pd.analyze(str(tmp_path))["weak_validation"]}
    assert "weak.webview_proceed" in ids


def test_clean_app_has_no_findings(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lcom/example/Main;", "onCreate"),
                              "res/layout/a.xml": b"<LinearLayout/>"})
    report = pd.analyze(apk)
    assert report["pinning_status"] == "none_detected"
    assert report["methods"] == [] and report["weak_validation"] == []


def test_multiple_methods_ranked_by_confidence(tmp_path):
    apk = make_apk(tmp_path, {
        "AndroidManifest.xml": build_axml(manifest_tree()),
        "res/xml/network_security_config.xml": build_axml(nsc_tree()),
        "classes.dex": dex("Lokhttp3/CertificatePinner;"),
    })
    ranked = [m["method"] for m in pd.analyze(apk)["methods"]]
    assert ranked[0] == "network_security_config"
    assert "okhttp" in ranked


# --------------------------------------------------------------------------
# Reports & CLI
# --------------------------------------------------------------------------

def test_markdown_report_lists_method_and_evidence(tmp_path):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lokhttp3/CertificatePinner;", PIN)})
    md = pd.render_markdown(pd.analyze(apk))
    assert "PENT-11" in md and "OkHttp CertificatePinner" in md and "sha256/" in md


def test_cli_writes_reports(tmp_path, capsys):
    apk = make_apk(tmp_path, {"classes.dex": dex("Lokhttp3/CertificatePinner;", PIN)})
    out = tmp_path / "out"
    assert pd.main([apk, "-o", str(out)]) == 0
    data = json.loads((out / "pinning-report.json").read_text(encoding="utf-8"))
    assert data["task"] == "PENT-11" and data["primary_method"] == "okhttp"
    assert (out / "pinning-report.md").exists()
    assert "okhttp" in capsys.readouterr().out.lower()


def test_cli_json_mode_prints_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    apk = make_apk(tmp_path, {"classes.dex": dex("x")})
    assert pd.main([apk, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["pinning_status"] == "none_detected"
    assert not (tmp_path / "artifacts").exists()


def test_cli_rejects_missing_and_non_zip_targets(tmp_path):
    assert pd.main([str(tmp_path / "nope.apk")]) == 1
    bogus = tmp_path / "bogus.apk"
    bogus.write_bytes(b"this is not a zip")
    assert pd.main([str(bogus)]) == 1


def test_oversized_entries_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(pd, "MAX_FILE_BYTES", 10)
    apk = make_apk(tmp_path, {"classes.dex": dex("Lokhttp3/CertificatePinner;", PIN)})
    assert pd.analyze(apk)["files_scanned"] == 0
