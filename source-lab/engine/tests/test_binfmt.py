"""Tests for the stdlib binary parsers (PE, Mach-O, ASAR, APK signing block)."""

import unittest

from source_lab.analyzers.binfmt import parse_apk_signing, parse_asar, parse_macho, parse_pe
from source_lab.analyzers.binfmt.asar import iter_text_entries
from builders import build_apk, build_asar, build_code_signature, build_macho, build_pe, sha256_hex


class TestBinaryParsers(unittest.TestCase):
    # @lat: [[source-tests#Binary parsers#PE import and export tables]]
    def test_pe_imports_exports_and_forwarders(self):
        data = build_pe(
            imports={"kernel32.dll": ["VirtualAllocEx", "WriteProcessMemory"], "user32.dll": ["SetWindowsHookExW"]},
            exports=["Foo"],
            forwarders={"GetFileVersionInfoW": "C:\\Windows\\System32\\version.GetFileVersionInfoW"},
            signed=True,
            managed=True,
            dll=True,
        )
        info = parse_pe(data)
        self.assertIsNotNone(info)
        self.assertTrue(info.is_64 and info.is_dll and info.has_signature and info.is_managed)
        self.assertEqual(info.imported("VirtualAllocEx"), "kernel32.dll")
        self.assertEqual(info.imported("setwindowshookexw"), "user32.dll")
        self.assertIsNone(info.imported("CreateRemoteThread"))
        self.assertIn("Foo", info.exports)
        self.assertEqual(info.forwarders, [("GetFileVersionInfoW", "C:\\Windows\\System32\\version.GetFileVersionInfoW")])

    # @lat: [[source-tests#Binary parsers#A string is not an import]]
    def test_pe_string_reference_is_not_an_import(self):
        data = build_pe(imports={"kernel32.dll": ["GetTickCount"]}, extra=b"CreateRemoteThread\x00")
        info = parse_pe(data)
        self.assertIsNone(info.imported("CreateRemoteThread"))
        self.assertIn(b"CreateRemoteThread", data)

    # @lat: [[source-tests#Binary parsers#Malformed input is rejected]]
    def test_malformed_inputs_return_nothing(self):
        self.assertIsNone(parse_pe(b"MZ" + b"\x00" * 10))
        self.assertIsNone(parse_pe(b"not a pe"))
        self.assertEqual(parse_macho(b"\xcf\xfa\xed\xfe" + b"\x00" * 6), [])
        self.assertIsNone(parse_asar(b"\x00" * 8))
        self.assertFalse(parse_apk_signing(b"PK\x05\x06" + b"\x00" * 18).has_signing_block)

    # @lat: [[source-tests#Binary parsers#Mach-O load commands and signature]]
    def test_macho_commands_symbols_and_entitlements(self):
        signature = build_code_signature(
            flags=0x2 | 0x10000,
            entitlements={"com.apple.security.cs.disable-library-validation": True, "com.apple.security.get-task-allow": True},
            identifier="com.example.app",
            team_id="ABCDE12345",
        )
        data = build_macho(
            dylibs=[("LC_LOAD_DYLIB", "/usr/lib/libSystem.B.dylib"), ("LC_REEXPORT_DYLIB", "@rpath/libproxy.dylib"), ("LC_LOAD_WEAK_DYLIB", "/tmp/evil.dylib")],
            rpaths=["@executable_path/../Frameworks", "/tmp/plugins"],
            sections=[("__DATA", "__interpose"), ("__DATA", "__mod_init_func")],
            undefined=["task_for_pid", "mach_vm_write"],
            dyld_env=["DYLD_INSERT_LIBRARIES=/tmp/x.dylib"],
            signature=signature,
        )
        (info,) = parse_macho(data)
        self.assertEqual((info.cpu, info.filetype), ("arm64", "executable"))
        self.assertEqual([k for k, _ in info.dylibs], ["LC_LOAD_DYLIB", "LC_REEXPORT_DYLIB", "LC_LOAD_WEAK_DYLIB"])
        self.assertEqual(info.rpaths[1], "/tmp/plugins")
        self.assertTrue(info.has_section("__interpose") and info.has_section("__mod_init_func"))
        self.assertEqual(info.undefined_symbols, ["task_for_pid", "mach_vm_write"])
        self.assertEqual(info.dyld_environment, ["DYLD_INSERT_LIBRARIES=/tmp/x.dylib"])
        sig = info.signature
        self.assertTrue(sig.adhoc and sig.hardened_runtime)
        self.assertEqual((sig.identifier, sig.team_id), ("com.example.app", "ABCDE12345"))
        self.assertTrue(sig.entitlements["com.apple.security.get-task-allow"])

    # @lat: [[source-tests#Binary parsers#ASAR contents]]
    def test_asar_entries_and_text(self):
        data = build_asar({"main.js": "new BrowserWindow({ webPreferences: { nodeIntegration: true } })", "lib/util.js": "x=1", "native.node": "bin"}, unpacked=["native.node"])
        archive = parse_asar(data)
        self.assertEqual(sorted(e.path for e in archive.entries), ["lib/util.js", "main.js", "native.node"])
        self.assertTrue(next(e for e in archive.entries if e.path == "native.node").unpacked)
        texts = dict(iter_text_entries(data, archive))
        self.assertIn("nodeIntegration: true", texts["main.js"])
        self.assertEqual(texts["lib/util.js"], "x=1")

    # @lat: [[source-tests#Binary parsers#APK signing block]]
    def test_apk_signing_block_certificate_digest(self):
        cert = b"\x30\x82\x01\x0a fake certificate der"
        signed = parse_apk_signing(build_apk({"AndroidManifest.xml": b"x"}, certificate=cert, schemes=("v2", "v3")))
        self.assertTrue(signed.has_signing_block)
        self.assertEqual(signed.schemes, ["v2", "v3"])
        self.assertEqual(signed.certificate_sha256, [sha256_hex(cert)])
        unsigned = parse_apk_signing(build_apk({"AndroidManifest.xml": b"x"}))
        self.assertFalse(unsigned.has_signing_block)
        self.assertEqual(unsigned.schemes, [])


if __name__ == "__main__":
    unittest.main()
