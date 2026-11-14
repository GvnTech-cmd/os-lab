"""iOS analyzer rules from the research: provisioning identity, injected frameworks, hook symbols, entitlements, content worlds."""

import plistlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from source_lab.analyzers import IOSAppAnalyzer
from source_lab.evidence.schema import TargetIdentity
from builders import build_code_signature, build_macho


def provision(**fields):
    base = {"TeamIdentifier": ["ABCDE12345"], "TeamName": "Example Ltd", "AppIDName": "Example", "ExpirationDate": "2027-01-01", "Entitlements": {}}
    base.update(fields)
    return b"\x30\x82cms-envelope" + plistlib.dumps(base, fmt=plistlib.FMT_XML) + b"signature-bytes"


def analyze_tree(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return IOSAppAnalyzer(TargetIdentity("test/ios")).analyze(root)


def analyze_ipa(files):
    with tempfile.TemporaryDirectory() as tmp:
        ipa = Path(tmp) / "app.ipa"
        with zipfile.ZipFile(ipa, "w") as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        return IOSAppAnalyzer(TargetIdentity("test/ipa")).analyze(ipa)


def ids(findings):
    return {f.finding_id for f in findings}


class TestIOSResearchRules(unittest.TestCase):
    # @lat: [[source-tests#iOS research rules#Provisioning identity and profile type]]
    def test_team_identity_profile_type_and_dynamic_codesigning(self):
        findings, _ = analyze_tree({"embedded.mobileprovision": provision(ProvisionsAllDevices=True, Entitlements={"dynamic-codesigning": True})})
        found = ids(findings)
        self.assertIn("ios.provision.team-identity", found)
        self.assertIn("ios.provision.profile-type", found)
        self.assertIn("ios.entitlement.dynamic-codesigning", found)
        team = next(f for f in findings if f.finding_id == "ios.provision.team-identity")
        self.assertIn("ABCDE12345", team.evidence[0].snippet)
        self.assertTrue(team.limitations)  # the analyzer cannot know the publisher's expected Team ID
        profile = next(f for f in findings if f.finding_id == "ios.provision.profile-type")
        self.assertIn("enterprise", profile.hypothesis)

        dev, _ = analyze_tree({"embedded.mobileprovision": provision(ProvisionedDevices=["a", "b"], Entitlements={"get-task-allow": True})})
        self.assertIn("development", next(f for f in dev if f.finding_id == "ios.provision.profile-type").hypothesis)
        store, _ = analyze_tree({"embedded.mobileprovision": provision()})
        self.assertNotIn("ios.provision.profile-type", ids(store))

    # @lat: [[source-tests#iOS research rules#Injected frameworks and hook symbols]]
    def test_injected_frameworks_load_commands_and_hook_symbols(self):
        binary = build_macho(
            dylibs=[("LC_LOAD_DYLIB", "@executable_path/Frameworks/FridaGadget.dylib"), ("LC_LOAD_DYLIB", "/usr/lib/libSystem.B.dylib")],
            undefined=["MSHookFunction", "MSHookMessageEx", "rebind_symbols", "vm_remap", "NSLog"],
            signature=build_code_signature(flags=0x10000, entitlements={"get-task-allow": True, "dynamic-codesigning": True}),
        )
        findings, _ = analyze_tree({"App.app/App": binary, "App.app/Frameworks/FridaGadget.dylib": b"\xcf\xfa\xed\xfe" + b"\x00" * 28, "App.app/Frameworks/Firebase.framework/Firebase": b"\x00"})
        found = ids(findings)
        for expected in ("ios.framework.injected", "ios.macho.hook-framework-ref", "ios.macho.hook-symbol.MSHookFunction", "ios.macho.hook-symbol.MSHookMessageEx",
                         "ios.macho.hook-symbol.rebind_symbols", "ios.macho.hook-symbol.vm_remap", "ios.entitlement.get-task-allow", "ios.entitlement.dynamic-codesigning"):
            self.assertIn(expected, found)
        self.assertNotIn("ios.macho.hook-symbol.NSLog", found)
        injected = [f.evidence[0].symbol for f in findings if f.finding_id == "ios.framework.injected"]
        self.assertEqual(injected, ["FridaGadget.dylib"])  # an ordinary framework is not flagged
        # one structured finding per hook framework, not a second string-search duplicate
        self.assertEqual(len([f for f in findings if f.finding_id == "ios.macho.hook-framework-ref" and "FridaGadget" in (f.evidence[0].snippet or "")]), 1)

    # @lat: [[source-tests#iOS research rules#User-script worlds and in-app listeners]]
    def test_content_worlds_timing_listeners_and_jailbreak_paths(self):
        swift = "\n".join([
            "let page = WKUserScript(source: js, injectionTime: .atDocumentStart, forMainFrameOnly: false, in: WKContentWorld.page)",
            "let iso = WKUserScript(source: js2, injectionTime: .atDocumentEnd, forMainFrameOnly: true, in: WKContentWorld.defaultClient)",
            "let js = \"window.addEventListener('keydown', e => post(e.key))\"",
            "let path = \"/var/jb/usr/lib/libhooker.dylib\"",
        ])
        findings, _ = analyze_tree({"App/View.swift": swift})
        found = ids(findings)
        for expected in ("ios.wkwebview.content-world-main", "ios.wkwebview.content-world-isolated", "ios.wkwebview.user-script-document-start", "inapp.script-listener.keyboard", "ios.jailbreak-path"):
            self.assertIn(expected, found)
        main = next(f for f in findings if f.finding_id == "ios.wkwebview.content-world-main")
        isolated = next(f for f in findings if f.finding_id == "ios.wkwebview.content-world-isolated")
        self.assertEqual((main.scope.world, isolated.scope.world), ("MAIN", "ISOLATED"))
        self.assertEqual(main.evidence[0].line, 1)
        self.assertEqual(isolated.evidence[0].line, 2)

    # @lat: [[source-tests#iOS research rules#IPA archives]]
    def test_ipa_framework_binary_and_plist_inspection(self):
        gadget_user = build_macho(dylibs=[("LC_LOAD_DYLIB", "@rpath/libsubstrate.dylib")], undefined=["MSHookFunction"])
        plist = plistlib.dumps({"CFBundleIdentifier": "com.example", "DYLD": "/Library/MobileSubstrate/DynamicLibraries/x.dylib"})
        findings, _ = analyze_ipa({
            "Payload/App.app/App": gadget_user,
            "Payload/App.app/Info.plist": plist,
            "Payload/App.app/Frameworks/FridaGadget.dylib": b"\x00",
            "Payload/App.app/Frameworks/Real.framework/Real": b"\x00",
            "Payload/App.app/embedded.mobileprovision": provision(),
        })
        found = ids(findings)
        for expected in ("ios.framework.injected", "ios.macho.hook-framework-ref", "ios.macho.hook-symbol.MSHookFunction", "ios.provision.team-identity"):
            self.assertIn(expected, found)


if __name__ == "__main__":
    unittest.main()
