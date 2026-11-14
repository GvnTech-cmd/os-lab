"""macOS analyzer rules from the research: entitlements, load commands, rpaths, interposition, symbols, plist and source rules."""

import plistlib
import tempfile
import unittest
from pathlib import Path

from source_lab.analyzers import MacOSAppAnalyzer
from source_lab.evidence.schema import FindingState, TargetIdentity
from builders import build_code_signature, build_macho


def analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return MacOSAppAnalyzer(TargetIdentity("test/mac")).analyze(root)


def ids(findings):
    return {f.finding_id for f in findings}


class TestMacOSResearchRules(unittest.TestCase):
    # @lat: [[source-tests#macOS research rules#Entitlements and signature flags]]
    def test_entitlements_and_signature_flags_come_from_the_signature(self):
        sig = build_code_signature(
            flags=0x2,
            entitlements={
                "com.apple.security.cs.disable-library-validation": True,
                "com.apple.security.cs.allow-dyld-environment-variables": True,
                "com.apple.security.get-task-allow": True,
                "com.apple.security.cs.allow-unsigned-executable-memory": True,
                "com.apple.security.cs.allow-jit": False,
            },
        )
        findings, _ = analyze({"My.app/Contents/MacOS/My": build_macho(signature=sig)})
        found = ids(findings)
        for expected in ("macos.entitlement.disable-library-validation", "macos.entitlement.allow-dyld-environment-variables", "macos.entitlement.get-task-allow", "macos.entitlement.allow-unsigned-executable-memory", "macos.macho.adhoc-signature"):
            self.assertIn(expected, found)
        self.assertNotIn("macos.entitlement.allow-jit", found)  # false means not granted

        hardened = build_code_signature(flags=0x10000, entitlements={})
        findings, _ = analyze({"My.app/Contents/MacOS/My": build_macho(signature=hardened)})
        self.assertFalse([f for f in findings if f.finding_id.startswith(("macos.entitlement", "macos.macho.adhoc", "macos.macho.hardened"))])
        findings, _ = analyze({"My.app/Contents/MacOS/My": build_macho(signature=build_code_signature(flags=0x0))})
        self.assertIn("macos.macho.hardened-runtime-missing", ids(findings))

    # @lat: [[source-tests#macOS research rules#Load commands and rpaths]]
    def test_dylib_proxies_suspicious_loads_and_missing_rpaths(self):
        macho = build_macho(
            dylibs=[("LC_LOAD_DYLIB", "/usr/lib/libSystem.B.dylib"), ("LC_REEXPORT_DYLIB", "@rpath/libreal.dylib"), ("LC_REEXPORT_DYLIB", "/usr/lib/libumbrella.dylib"), ("LC_LOAD_WEAK_DYLIB", "/tmp/evil.dylib")],
            rpaths=["@executable_path/../Frameworks", "@executable_path/../Plugins", "/Users/dev/hijack"],
        )
        findings, _ = analyze({"My.app/Contents/MacOS/My": macho, "My.app/Contents/Frameworks/.keep": b""})
        by_id = {}
        for f in findings:
            by_id.setdefault(f.finding_id, []).append(f.evidence[0].symbol)
        self.assertEqual(by_id["macos.macho.reexport-dylib"], ["@rpath/libreal.dylib"])  # system umbrella re-exports are normal
        self.assertEqual(by_id["macos.macho.non-system-dylib"], ["/tmp/evil.dylib"])
        self.assertCountEqual(by_id["macos.macho.rpath"], ["@executable_path/../Plugins", "/Users/dev/hijack"])  # Frameworks exists

    # @lat: [[source-tests#macOS research rules#Interposition constructors and injection symbols]]
    def test_interpose_section_constructors_and_symbols(self):
        macho = build_macho(
            sections=[("__DATA", "__interpose"), ("__DATA", "__mod_init_func")],
            undefined=["task_for_pid", "mach_vm_write", "thread_create_running", "rebind_symbols", "printf"],
            dyld_env=["DYLD_INSERT_LIBRARIES=/tmp/a.dylib"],
            filetype=6,
        )
        findings, _ = analyze({"libhook.dylib": macho})
        found = ids(findings)
        for expected in ("macos.macho.dyld-interposition", "macos.macho.constructor", "macos.macho.injection-symbol.task_for_pid", "macos.macho.injection-symbol.mach_vm_write",
                         "macos.macho.injection-symbol.thread_create_running", "macos.macho.injection-symbol.rebind_symbols", "macos.macho.dyld-environment"):
            self.assertIn(expected, found)
        self.assertNotIn("macos.macho.injection-symbol.printf", found)
        # a string alone is not a section
        decoy = b"\xcf\xfa\xed\xfe" + b"\x00" * 28 + b"__interpose"
        findings, cov = analyze({"decoy.dylib": decoy})
        self.assertTrue(all(f.confidence < 0.7 for f in findings if f.finding_id == "macos.macho.dyld-interposition"))

    # @lat: [[source-tests#macOS research rules#LSEnvironment and source rules]]
    def test_lsenvironment_and_source_rules(self):
        plist = plistlib.dumps({"CFBundleIdentifier": "com.x.app", "LSEnvironment": {"DYLD_INSERT_LIBRARIES": "/tmp/hook.dylib", "FOO": "bar"}})
        launchd = plistlib.dumps({"Label": "x", "EnvironmentVariables": {"DYLD_FRAMEWORK_PATH": "/tmp/fw"}})
        source = "\n".join([
            "rebind_symbols((struct rebinding[1]){{\"open\", my_open, (void *)&orig_open}}, 1);",
            "setenv(\"DYLD_INSERT_LIBRARIES\", path, 1);",
            "__attribute__((constructor)) static void init(void) {}",
            "let s = WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: false, in: WKContentWorld.page)",
            "let t = WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true, in: WKContentWorld.defaultClient)",
        ])
        findings, _ = analyze({"My.app/Contents/Info.plist": plist, "My.app/Contents/Library/LaunchDaemons/x.plist": launchd, "Hook.m": source})
        found = ids(findings)
        self.assertEqual(len([f for f in findings if f.finding_id == "macos.bundle.lsenvironment"]), 2)
        for expected in ("macos.fishhook.rebind-symbols", "macos.dyld.insert-libraries", "macos.objc.constructor", "macos.wkwebview.user-script-document-start", "macos.wkwebview.content-world-page", "macos.wkwebview.content-world-isolated"):
            self.assertIn(expected, found)
        self.assertTrue(all(f.state == FindingState.STATIC_LEAD for f in findings if f.finding_id.startswith("macos.wkwebview.content-world")))


if __name__ == "__main__":
    unittest.main()
