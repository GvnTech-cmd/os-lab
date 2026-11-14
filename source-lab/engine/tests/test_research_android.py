"""Android analyzer rules from the research: signing, injected libraries, manifest, WebView origins, DEX strings, in-app listeners."""

import tempfile
import unittest
from pathlib import Path

from source_lab.analyzers import AndroidAppAnalyzer
from source_lab.evidence.schema import TargetIdentity
from builders import build_apk, sha256_hex


def analyze_apk(files, certificate=None, schemes=("v2",)):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "app.apk"
        path.write_bytes(build_apk(files, certificate=certificate, schemes=schemes))
        return AndroidAppAnalyzer(TargetIdentity("test/apk")).analyze(path)


def analyze_tree(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return AndroidAppAnalyzer(TargetIdentity("test/src")).analyze(root)


def ids(findings):
    return {f.finding_id for f in findings}


class TestAndroidResearchRules(unittest.TestCase):
    # @lat: [[source-tests#Android research rules#APK signing block]]
    def test_signing_schemes_certificate_digest_and_unsigned(self):
        cert = b"\x30\x82\x02\x00 pretend certificate"
        findings, _ = analyze_apk({"AndroidManifest.xml": b"x"}, certificate=cert, schemes=("v2", "v3"))
        signing = next(f for f in findings if f.finding_id == "android.apk.signing")
        self.assertIn("v2", signing.evidence[0].snippet)
        self.assertIn(sha256_hex(cert)[:60], signing.evidence[0].snippet)
        self.assertTrue(signing.limitations)

        findings, _ = analyze_apk({"AndroidManifest.xml": b"x"})
        self.assertIn("android.apk.unsigned", ids(findings))
        self.assertNotIn("android.apk.signing", ids(findings))

        findings, _ = analyze_apk({"AndroidManifest.xml": b"x", "META-INF/CERT.RSA": b"sig"})
        v1 = next(f for f in findings if f.finding_id == "android.apk.signing")
        self.assertIn("v1", v1.evidence[0].snippet)
        self.assertTrue(any("v1" in lim for lim in v1.limitations))

    # @lat: [[source-tests#Android research rules#Injected libraries and DEX hooks]]
    def test_injected_native_libraries_and_dex_hook_strings(self):
        manifest = "android.permission.BIND_ACCESSIBILITY_SERVICE android.permission.SYSTEM_ALERT_WINDOW".encode("utf-16-le")
        dex = b"dex\n035 addWebMessageListener shouldInterceptRequest InMemoryDexClassLoader top/canyie/pine XposedBridge"
        findings, _ = analyze_apk({
            "AndroidManifest.xml": manifest,
            "classes.dex": dex,
            "lib/arm64-v8a/libfrida-gadget.so": b"\x7fELF" + b"\x00" * 12,
            "lib/arm64-v8a/libnative-lib.so": b"\x7fELF" + b"\x00" * 12,
            "apktool.yml": "version: 2",
        }, certificate=b"cert")
        found = ids(findings)
        for expected in ("android.apk.injected-native-lib", "android.permission.bind_accessibility_service", "android.permission.system_alert_window",
                         "android.dex.web-message-listener", "android.dex.intercept-request", "android.dex.in-memory-dex-loader", "android.dex.hook-framework", "android.dex.xposed-bridge", "android.apk.repackaging"):
            self.assertIn(expected, found)
        libs = [f.evidence[0].symbol for f in findings if f.finding_id == "android.apk.injected-native-lib"]
        self.assertEqual(libs, ["libfrida-gadget.so"])  # an ordinary native library is not flagged

    # @lat: [[source-tests#Android research rules#Manifest services and providers]]
    def test_accessibility_service_and_startup_provider(self):
        manifest = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <uses-permission android:name="android.permission.BIND_DEVICE_ADMIN"/>
  <application>
    <service android:name=".Spy" android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"><intent-filter><action android:name="android.accessibilityservice.AccessibilityService"/></intent-filter></service>
    <provider android:name="com.vendor.hook.InitProvider" android:authorities="x" android:initOrder="100"/>
    <provider android:name="androidx.startup.InitializationProvider" android:authorities="y" android:initOrder="100"/>
    <provider android:name="com.vendor.FilesProvider" android:authorities="z"/>
  </application>
</manifest>"""
        findings, _ = analyze_tree({"AndroidManifest.xml": manifest})
        found = ids(findings)
        self.assertIn("android.manifest.accessibility-service", found)
        self.assertIn("android.permission.bind_device_admin", found)
        providers = [f.evidence[0].symbol for f in findings if f.finding_id == "android.manifest.startup-provider"]
        self.assertEqual(providers, ["com.vendor.hook.InitProvider"])  # androidx and ordinary providers are not shims

    # @lat: [[source-tests#Android research rules#WebView origins and bridges]]
    def test_webview_origin_bridge_and_listener_rules(self):
        java = "\n".join([
            "webView.getSettings().setJavaScriptEnabled(true);",
            "webView.addJavascriptInterface(new Bridge(), \"app\");",
            "WebViewCompat.addWebMessageListener(webView, \"bridge\", Set.of(\"*\"), listener);",
            "WebViewCompat.addDocumentStartJavaScript(webView, SCRIPT, Set.of(\"*\"));",
            "webView.loadUrl(\"javascript:window.x=1\");",
            "String SCRIPT = \"document.addEventListener('keydown', function (e) { send(e.key) })\";",
            "@JavascriptInterface public void post(String s) {}",
            "public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) { return null; }",
        ])
        findings, _ = analyze_tree({"app/src/Main.java": java})
        found = ids(findings)
        for expected in ("android.webview.js-enabled-bridge", "android.webview.wildcard-origin", "android.webview.web-message-listener", "android.webview.javascript-url",
                         "android.webview.javascript-interface-annotation", "android.webview.intercept-request", "inapp.script-listener.keyboard"):
            self.assertIn(expected, found)

        quiet = "\n".join(["document.addEventListener('keydown', handler);", "label.setText(\"hi\");"])  # no injection API in the file
        findings, _ = analyze_tree({"app/src/Ui.java": quiet})
        self.assertNotIn("inapp.script-listener.keyboard", ids(findings))


if __name__ == "__main__":
    unittest.main()
