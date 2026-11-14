"""Windows analyzer rules from the research: import-table reading, injection chains, DLL proxies, hook engines, Electron fuses and ASAR."""

import tempfile
import unittest
from pathlib import Path

from source_lab.analyzers import WindowsAppAnalyzer
from source_lab.evidence.schema import FindingState, TargetIdentity
from builders import build_asar, build_pe


def analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        return WindowsAppAnalyzer(TargetIdentity("test/win")).analyze(root)


def ids(findings):
    return {f.finding_id for f in findings}


class TestWindowsResearchRules(unittest.TestCase):
    # @lat: [[source-tests#Windows research rules#Imports versus strings]]
    def test_import_table_beats_a_string_reference(self):
        imported = build_pe(imports={"kernel32.dll": ["CreateRemoteThread"]})
        text_only = build_pe(imports={"kernel32.dll": ["GetTickCount"]}, extra=b"CreateRemoteThread\x00")
        findings, _ = analyze({"imported.exe": imported, "stringy.exe": text_only})
        by_file = {f.evidence[0].file: f for f in findings if f.finding_id == "windows.pe.injection-api.createremotethread"}
        self.assertGreater(by_file["imported.exe"].confidence, by_file["stringy.exe"].confidence)
        self.assertIn("import table", by_file["imported.exe"].evidence[0].snippet)
        self.assertTrue(by_file["stringy.exe"].limitations)
        self.assertEqual(by_file["imported.exe"].state, FindingState.CAPABILITY)

    # @lat: [[source-tests#Windows research rules#Injection chains]]
    def test_classic_injection_hollowing_and_early_bird_chains(self):
        classic = build_pe(imports={"kernel32.dll": ["OpenProcess", "VirtualAllocEx", "WriteProcessMemory", "CreateRemoteThread"]})
        hollow = build_pe(imports={"ntdll.dll": ["NtUnmapViewOfSection"], "kernel32.dll": ["WriteProcessMemory", "SetThreadContext"]})
        early = build_pe(imports={"kernel32.dll": ["CreateProcessW", "QueueUserAPC", "ResumeThread"]})
        benign = build_pe(imports={"kernel32.dll": ["CreateFileW", "ReadFile"]})
        findings, _ = analyze({"classic.exe": classic, "hollow.exe": hollow, "early.exe": early, "benign.exe": benign})
        by_id = {f.finding_id: f.evidence[0].file for f in findings}
        self.assertEqual(by_id["windows.pe.classic-dll-injection"], "classic.exe")
        self.assertEqual(by_id["windows.pe.process-hollowing"], "hollow.exe")
        self.assertEqual(by_id["windows.pe.early-bird-apc"], "early.exe")
        self.assertFalse([f for f in findings if f.evidence[0].file == "benign.exe"])

    # @lat: [[source-tests#Windows research rules#DLL proxy and signature]]
    def test_dll_proxy_forwarding_and_unsigned_context(self):
        proxy = build_pe(exports=["Other"], forwarders={"GetFileVersionInfoW": "C:\\Windows\\System32\\version.GetFileVersionInfoW"}, dll=True)
        plain = build_pe(exports=["MyExport"], dll=True)
        findings, _ = analyze({"version.dll": proxy, "mylib.dll": plain})
        proxies = [f for f in findings if f.finding_id == "windows.pe.dll-proxy"]
        self.assertEqual([f.evidence[0].file for f in proxies], ["version.dll"])
        self.assertIn("forwards 1 export", proxies[0].hypothesis)
        self.assertGreaterEqual(proxies[0].confidence, 0.8)

        unsigned, _ = analyze({"dxgi.dll": build_pe(exports=["X"], dll=True)})  # system name, no forwarders, no signature
        weak = next(f for f in unsigned if f.finding_id == "windows.pe.dll-proxy")
        self.assertLess(weak.confidence, 0.6)
        signed, _ = analyze({"dxgi.dll": build_pe(exports=["X"], dll=True, signed=True)})
        self.assertNotIn("windows.pe.dll-proxy", ids(signed))

    # @lat: [[source-tests#Windows research rules#Hook engines and CLR weaving]]
    def test_hook_engines_clr_weaving_and_webview2_in_binaries(self):
        data = build_pe(imports={"kernel32.dll": ["GetTickCount"]}, managed=True, extra=b"HarmonyLib\x00DetourAttach\x00MH_CreateHook\x00AddScriptToExecuteOnDocumentCreatedAsync\x00AddHostObjectToScript\x00ExecuteScriptAsync\x00DOTNET_STARTUP_HOOKS\x00")
        findings, _ = analyze({"app.exe": data})
        found = ids(findings)
        for expected in ("windows.clr.il-weaving", "windows.pe.hook-engine.detours", "windows.pe.hook-engine.minhook", "windows.clr.startup-hook",
                         "windows.webview2.document-created-script", "windows.webview2.host-object-bridge", "windows.webview2.execute-script", "windows.pe.managed-clr"):
            self.assertIn(expected, found)

    # @lat: [[source-tests#Windows research rules#Electron fuses and ASAR]]
    def test_electron_fuses_asar_contents_and_unpacked_app(self):
        sentinel = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
        # wire order: RunAsNode, CookieEncryption, NodeOptionsEnv, NodeCliInspect, AsarIntegrity, OnlyLoadFromAsar, V8Snapshot, FileProtocol
        fuses = sentinel + bytes([1, 8]) + b"11010110"
        exe = build_pe(imports={"kernel32.dll": ["GetTickCount"]}, extra=fuses)
        asar = build_asar({"main.js": "new BrowserWindow({ webPreferences: { nodeIntegration: true, contextIsolation: false, sandbox: false, preload: 'p.js' } })"})
        findings, cov = analyze({"MyApp.exe": exe, "resources/app.asar": asar, "other/resources/app/package.json": "{}"})
        found = ids(findings)
        self.assertIn("windows.electron.fuse.run-as-node", found)
        self.assertIn("windows.electron.fuse.node-cli-inspect", found)
        self.assertIn("windows.electron.fuse.asar-integrity-disabled", found)
        self.assertNotIn("windows.electron.fuse.node-options-env", found)
        self.assertNotIn("windows.electron.fuse.cookie-encryption", found)  # encrypted (1) is the safe state
        self.assertNotIn("windows.electron.fuse.load-app-from-folder", found)
        for expected in ("windows.electron.node-integration", "windows.electron.context-isolation-disabled", "windows.electron.sandbox-disabled", "windows.electron.preload-script"):
            self.assertIn(expected, found)
        asar_hit = next(f for f in findings if f.finding_id == "windows.electron.node-integration")
        self.assertEqual(asar_hit.evidence[0].file, "resources/app.asar!main.js")
        self.assertIn("windows.electron.unpacked-app", found)


if __name__ == "__main__":
    unittest.main()
