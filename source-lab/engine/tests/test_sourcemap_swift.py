"""Tests for the Swift adapter (macOS/iOS)."""

import json

from source_lab.sourcemap import RepoMap
from source_lab.sourcemap.extract.swift import extract as swift_extract

MACOS_PLIST = {
    "CFBundleIdentifier": "com.example.myapp",
    "CFBundleExecutable": "MyApp",
    "CFBundlePackageType": "APPL",
    "LSMinimumSystemVersion": "12.0",
}

IOS_PLIST = {
    "CFBundleIdentifier": "com.example.iosapp",
    "CFBundleExecutable": "iOSApp",
    "CFBundlePackageType": "APPL",
    "LSRequiresIPhoneOS": True,
    "UIDeviceFamily": [1],
    "MinimumOSVersion": "16.0",
}

PBXPROJ_MACOS = """// !$*UTF8*$!
{
        objects = {
                AA01 /* MyApp.app */ = {isa = PBXFileReference; explicitFileType = wrapper.application; path = MyApp.app; sourceTree = BUILT_PRODUCTS_DIR; };
                AA02 /* AppDelegate.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = AppDelegate.swift; sourceTree = "<group>"; };
                AA03 /* ProfileView.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = ProfileView.swift; sourceTree = "<group>"; };
                BB01 /* Build configuration list */ = {
                        isa = XCConfigurationList;
                        buildConfigurations = (
                                CC01 /* Debug */,
                        );
                };
                CC01 /* Debug */ = {
                        isa = XCBuildConfiguration;
                        buildSettings = {
                                INFOPLIST_FILE = MyApp/Info.plist;
                                PRODUCT_BUNDLE_IDENTIFIER = com.example.myapp;
                                SDKROOT = macosx;
                                SWIFT_VERSION = 5.9;
                        };
                        name = Debug;
                };
        };
}
"""

PBXPROJ_IOS = """// !$*UTF8*$!
{
        objects = {
                CC01 /* Debug */ = {
                        isa = XCBuildConfiguration;
                        buildSettings = {
                                INFOPLIST_FILE = iOSApp/Info.plist;
                                PRODUCT_BUNDLE_IDENTIFIER = com.example.iosapp;
                                SDKROOT = iphoneos;
                                TARGETED_DEVICE_FAMILY = "1,2";
                        };
                };
        };
}
"""


def write(tmp_path, rel, text):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


# @lat: [[source-tests#Repo map adapters#Swift symbols]]
def test_swift_symbols():
    text = '''
import Foundation

@objc public final class NetworkService: NSObject {
    private var session: URLSession

    @MainActor
    func refresh(token: String, for user: User) async throws -> Data {
        return Data()
    }

    init(session: URLSession) {
        self.session = session
    }
}

struct ProfileView: View {
    @Published var name: String = ""
}

enum State: String {
    case idle
}

protocol Fetching {
    func fetch() -> Data
}

extension NetworkService: Fetching {
    func fetch() -> Data { Data() }
}

typealias Handler = (Data) -> Void
'''
    out = swift_extract(text)
    by_name = {s.name: s for s in out.symbols}
    service = next(s for s in out.symbols if s.name == "NetworkService" and s.kind == "class")
    assert service.exported is True and service.access == "public"
    assert "@objc" in service.decorators and "final" not in service.decorators
    refresh = by_name["refresh"]
    assert refresh.kind == "method"
    assert refresh.returns.type == "Data" and refresh.returns.source == "annotation"
    assert "@MainActor" in refresh.decorators
    assert [p.name for p in refresh.params] == ["token", "for"]
    assert by_name["init"].kind == "method"
    assert by_name["ProfileView"].kind == "struct"
    assert by_name["State"].kind == "enum"
    assert by_name["Fetching"].kind == "protocol"
    assert by_name["Handler"].kind == "type"
    extension = next(s for s in out.symbols if s.kind == "extension")
    assert extension.meta.get("extends") == "NetworkService"
    assert [i.specifier for i in out.imports] == ["Foundation"]
    assert all(i.reason == "swift-module" for i in out.imports)


# @lat: [[source-tests#Repo map adapters#Swift resolution and roles]]
def test_swift_module_resolution_and_roles(tmp_path):
    write(tmp_path, "MyApp/AppDelegate.swift", '''
import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {}
}
''')
    write(tmp_path, "MyApp/Views/ProfileView.swift", "struct ProfileView: View {}\n")
    write(tmp_path, "MyApp/ViewModels/ProfileViewModel.swift",
          "final class ProfileViewModel: ObservableObject {}\n")
    write(tmp_path, "MyApp/Models/User.swift", "struct User: Codable { let id: Int }\n")
    write(tmp_path, "MyApp/Services/NetworkService.swift", "final class NetworkService {}\n")
    write(tmp_path, "MyAppTests/AppTests.swift", '''
@testable import MyApp
import XCTest

final class AppTests: XCTestCase {}
''')
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    roles = {p: f["role"]["kind"] for p, f in files.items()}
    assert roles["MyApp/AppDelegate.swift"] == "entrypoint"
    assert roles["MyApp/Views/ProfileView.swift"] == "view"
    assert roles["MyApp/ViewModels/ProfileViewModel.swift"] == "view_model"
    assert roles["MyApp/Models/User.swift"] == "model"
    assert roles["MyApp/Services/NetworkService.swift"] == "service"
    assert roles["MyAppTests/AppTests.swift"] == "test"
    # Swift modules are never file-resolved, @testable import behaves the same
    imports = {i["specifier"]: i for i in files["MyAppTests/AppTests.swift"]["imports"]}
    assert imports["XCTest"]["external"] is True and imports["XCTest"]["reason"] == "swift-module"
    assert imports["MyApp"]["external"] is True and imports["MyApp"]["reason"] == "swift-module"
    # every swift import stays external: nothing local resolves through a module
    for entry in files.values():
        for imp in entry.get("imports", []):
            if imp["reason"] == "swift-module":
                assert imp["external"] and imp["resolved"] is None


# @lat: [[source-tests#Repo map adapters#Swift targets]]
def test_swift_target_detection(tmp_path):
    # macOS: xcodeproj SDKROOT macosx + APPL plist without iOS keys
    write(tmp_path, "MyApp.xcodeproj/project.pbxproj", PBXPROJ_MACOS)
    write(tmp_path, "MyApp/Info.plist",
          "\n".join(f"<{k}>{v}</{k}>" for k, v in MACOS_PLIST.items()))
    write(tmp_path, "MyApp/AppDelegate.swift",
          "final class AppDelegate: NSObject, NSApplicationDelegate {}\n")
    bundle = RepoMap().generate(tmp_path)
    target = next(t for t in bundle["targets"] if t["platform"] == "macos-app")
    assert target["confidence"] >= 0.8
    assert any("MyApp.xcodeproj" in e for e in target["evidence"])
    assert "MyApp" in target["source_roots"]
    assert target["applicability"] == "full"

    # iOS: SDKROOT iphoneos + UIDeviceFamily
    ios_root = tmp_path / "ios"
    ios_root.mkdir()
    write(ios_root, "iOSApp.xcodeproj/project.pbxproj", PBXPROJ_IOS)
    write(ios_root, "iOSApp/Info.plist",
          "\n".join(f"<{k}>{v}</{k}>" for k, v in IOS_PLIST.items()))
    write(ios_root, "iOSApp/AppDelegate.swift",
          "final class AppDelegate: UIResponder, UIApplicationDelegate {}\n")
    bundle = RepoMap().generate(ios_root)
    target = next(t for t in bundle["targets"] if t["platform"] == "ios-app")
    assert target["confidence"] >= 0.8
    assert "iOSApp" in target["source_roots"]

    # binary-only .app is not_applicable
    bin_root = tmp_path / "bundled"
    (bin_root / "Old.app" / "Contents" / "MacOS").mkdir(parents=True)
    (bin_root / "Old.app" / "Contents" / "MacOS" / "Old").write_bytes(b"\xcf\xfa\xed\xfe")
    bundle = RepoMap().generate(bin_root)
    target = next(t for t in bundle["targets"] if t["platform"] == "macos-app")
    assert target["applicability"] == "not_applicable"
    assert "binary-only" in target["applicability_reason"]


# @lat: [[source-tests#Repo map adapters#Swift provisioning evidence]]
def test_swift_provisioning_and_entitlements(tmp_path):
    write(tmp_path, "iOSApp.xcodeproj/project.pbxproj", PBXPROJ_IOS)
    write(tmp_path, "iOSApp/Info.plist",
          "\n".join(f"<{k}>{v}</{k}>" for k, v in IOS_PLIST.items()))
    (tmp_path / "iOSApp" / "embedded.mobileprovision").write_bytes(
        b"\x30\x82\x04" + b"\x00" * 16)
    write(tmp_path, "iOSApp/App.entitlements",
          '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0">'
          "<dict><key>aps-environment</key><string>development</string></dict></plist>")
    bundle = RepoMap().generate(tmp_path)
    target = next(t for t in bundle["targets"] if t["platform"] == "ios-app")
    assert any("mobileprovision" in e for e in target["evidence"])
    assert any("entitlements" in e for e in target["evidence"])
