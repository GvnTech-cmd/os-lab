# PENT-11 Verification Report

**Task:** PENT-11 - SSL/Certificate Pinning Detector & Classifier (Static)
**Contributor:** Mevlit Kaan Öztürk (`kkaanozturk`), MYO062
**Date:** 2026-11-13
**Deliverable:** `android-lab/lab/scripts/pinning_detector.py`
**Tests:** `android-lab/lab/tests/test_pinning_detector.py`

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Pro (10.0.26300) |
| Python | 3.15.2 |
| Test runner | pytest |
| Network / device / emulator | none used (static analysis only) |

## 2. What was verified

The detector reads a local APK or decompiled source directory and classifies the TLS pinning method
(Network Security Config, OkHttp, custom TrustManager, third-party library, Flutter, native `.so`,
embedded certificate), reports weak validation (trust-all, allow-all hostname verifier, WebView
`proceed`), and recommends the matching lab hook as the next step.

## 3. Automated tests

Command, run from `android-lab/lab`:

```bash
python -m pytest tests/test_pinning_detector.py -v
```

Result: **32 passed, 0 failed** (about 0.6 s).

All fixtures are synthetic and built in memory (including a small Android binary-XML encoder used
only by the tests), so no third-party app or live target is involved.

| Area | Tests covering it |
|---|---|
| Binary XML decoding, manifest, NSC | AXML round trip, garbage input rejected, manifest package/SDK/NSC reference, NSC pinned = high, expired pin-set, single pin, NSC not referenced by manifest, plain-text NSC in a directory, NSC without pins, XML entities refused |
| OkHttp | pin literal in dex = high, class-only = `possible`, smali call site with line number, library smali not counted as app pinning |
| TrustManager / libraries | key comparison in source = high, API references alone = low, TrustKit init, react-native-ssl-pinning |
| Flutter / native / certs | Flutter SecurityContext, Flutter without pinning signals, libcurl pin, native primitives alone = low, embedded certificate (META-INF ignored) |
| Weak validation / negatives | trust-all + allow-all, WebView proceed, clean app, ranking of several methods |
| Reports / CLI | Markdown report, JSON + Markdown files, `--json` writes nothing, missing and non-zip targets rejected, oversized entries skipped |

Individual results:

```
test_axml_roundtrip_decodes_tags_attrs_and_text PASSED
test_decode_axml_rejects_garbage PASSED
test_analyze_manifest_reads_package_sdk_and_nsc_ref PASSED
test_nsc_pinning_classified_high PASSED
test_nsc_expired_pin_set_is_downgraded PASSED
test_nsc_single_pin_warns_about_missing_backup PASSED
test_nsc_without_manifest_reference_is_flagged PASSED
test_plain_text_nsc_in_decompiled_directory PASSED
test_nsc_without_pins_is_not_pinning PASSED
test_xml_with_entities_is_refused PASSED
test_okhttp_pin_literal_in_dex_is_high PASSED
test_okhttp_class_only_is_just_possible PASSED
test_okhttp_builder_call_in_smali_reports_line_number PASSED
test_okhttp_library_smali_does_not_count_as_app_pinning PASSED
test_custom_trustmanager_key_comparison_is_high PASSED
test_trustmanager_api_references_alone_are_low PASSED
test_trustkit_initialisation_detected PASSED
test_react_native_ssl_pinning_package PASSED
test_flutter_security_context PASSED
test_flutter_without_pinning_signals_is_not_pinned PASSED
test_native_curl_pin PASSED
test_native_verify_primitives_alone_stay_low PASSED
test_embedded_certificate_in_assets PASSED
test_trust_all_and_allow_all_reported_as_weak_validation PASSED
test_webview_proceed_in_source PASSED
test_clean_app_has_no_findings PASSED
test_multiple_methods_ranked_by_confidence PASSED
test_markdown_report_lists_method_and_evidence PASSED
test_cli_writes_reports PASSED
test_cli_json_mode_prints_and_writes_nothing PASSED
test_cli_rejects_missing_and_non_zip_targets PASSED
test_oversized_entries_are_skipped PASSED
```

Regression check: running the whole `tests/` folder gives 183 passed, 13 skipped and 7 failed. The 7
failures are in `test_cleanup_console.py`, `test_oslab_console.py` and `test_web_ui.py`. They are
existing tests of other components and none touches the new files. I did not compare against an
unmodified checkout, so I cannot say whether they also fail without this change.

## 4. Manual end-to-end run

A demo APK was built with the test helpers: binary manifest, binary NSC with two pins, a dex containing
an OkHttp pin literal, the `CertificatePinner` class name and a `TrustAllCerts` class name.

```bash
python scripts/pinning_detector.py demo-pinned.apk -o out/
```

Console result: `Status: pinned`, primary method OkHttp (high, score 4), NSC pin-set (high, score 3),
plus the trust-all warning. Generated `pinning-report.md`:

# SSL / Certificate Pinning Report (PENT-11)

- **Target:** `demo-pinned.apk` (apk)
- **Timestamp:** 2026-11-13T17:42:04
- **Files scanned:** 3
- **Status:** **pinned**
- **Primary method:** OkHttp CertificatePinner
- **Package:** `lab.test.app` (minSdk 24, targetSdk 34)

> Static analysis of a local file only. Use on apps you own or are authorised to assess.

## Classification

| Method | Confidence | Score | Next step |
|---|---|---|---|
| OkHttp CertificatePinner | high | 4 | Dynamic: hooks/ssl-pinning-bypass.js (OkHttp3 CertificatePinner hook) under the lab WF2. |
| Network Security Config <pin-set> | high | 3 | Static: scripts/apk_patcher.py injects a permissive Network Security Config. Dynamic: hooks/ssl-pinning-bypass.js. |

### OkHttp CertificatePinner

- (3) Hard-coded OkHttp pin literal (sha256/<base64>)
  - `classes.dex` offset 0x24: `sha256/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/AbCdE=`
- (1) OkHttp CertificatePinner class present (library bundled; not proof of use)
  - `classes.dex` offset 0x9: `okhttp3/CertificatePinner`

### Network Security Config <pin-set>

- (3) 2 pin(s) in 1 domain-config(s)
  - `res/xml/network_security_config.xml` pin-set: `api.lab.test`

## Network Security Config: `res/xml/network_security_config.xml`

- **api.lab.test** - 2 pin(s)

## Weak validation

Trust-all / allow-all validation found: TLS may be interceptable without any bypass.
- Trust-all TrustManager by name (TrustAll* / Insecure* / Unsafe*)
  - `classes.dex` offset 0x61: `TrustAllCerts`


## 5. Safety and scope checks

- Static only: no sockets, subprocesses, device or Frida access in the tool.
- Zip entries are read in memory and never extracted (no path traversal); entries over 128 MB are skipped.
- XML containing `<!ENTITY` or `<!DOCTYPE` is refused.
- Pin values reported are public hashes, not secrets.
- The report states that use is limited to apps you own or are authorised to assess.

## 6. Known limitations

- Detection is heuristic. On a compiled dex only strings are visible, so call sites cannot be seen;
  strong confidence there comes from pin literals, not from code structure. Obfuscated apps that
  hide class names and pin strings can be missed.
- `high` means strong evidence of pinning code, not proof that it is active at runtime.
- When several methods are `high`, the order follows the score. In the demo the OkHttp literal (score 4)
  is listed ahead of the NSC pin-set (score 3) although both are high.
- Native `.so` analysis is string-based; no disassembly.
- Not tested against real third-party APKs, only synthetic fixtures. Real-APK validation in the Android
  lab would need an APK you are authorised to analyse.
- No proof video was recorded.

## 7. Conclusion

All 32 PENT-11 tests pass and the CLI works end to end on a synthetic APK. The limitations above are
the remaining gaps before calling this fully verified against real apps.
