"""Tests for the iOS adapter: reuses the Swift and ObjC adapters, adds
Info.plist / pbxproj / provisioning target discovery and storyboard edges."""

import json

from source_lab.sourcemap import RepoMap

IOS_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleIdentifier</key><string>com.example.tracker</string>
    <key>CFBundleExecutable</key><string>Tracker</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSRequiresIPhoneOS</key><true/>
    <key>UIDeviceFamily</key><array><integer>1</integer></array>
    <key>MinimumOSVersion</key><string>16.0</string>
</dict></plist>
"""

PBXPROJ_IOS = """// !$*UTF8*$!
{
        archiveVersion = 1;
        objects = {
                AA01 /* Tracker.app */ = {isa = PBXFileReference; explicitFileType = wrapper.application; path = Tracker.app; sourceTree = BUILT_PRODUCTS_DIR; };
                AA02 /* AppDelegate.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = AppDelegate.swift; sourceTree = "<group>"; };
                AA03 /* DetailViewController.m */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.c.objc; path = DetailViewController.m; sourceTree = "<group>"; };
                AA04 /* Main.storyboard */ = {isa = PBXFileReference; lastKnownFileType = file.storyboard; path = Main.storyboard; sourceTree = "<group>"; };
                AA05 /* TrackerTests.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = TrackerTests.swift; sourceTree = "<group>"; };
                CC01 /* Debug */ = {
                        isa = XCBuildConfiguration;
                        buildSettings = {
                                INFOPLIST_FILE = Tracker/Info.plist;
                                PRODUCT_BUNDLE_IDENTIFIER = com.example.tracker;
                                SDKROOT = iphoneos;
                                TARGETED_DEVICE_FAMILY = "1,2";
                        };
                        name = Debug;
                };
                BB02 /* TrackerTests */ = {isa = PBXFileSystemSynchronizedRootGroup; path = TrackerTests; sourceTree = "<group>"; };
        };
}
"""


def write(tmp_path, rel, text):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def build_ios_tree(tmp_path):
    write(tmp_path, "Tracker.xcodeproj/project.pbxproj", PBXPROJ_IOS)
    write(tmp_path, "Tracker/Info.plist", IOS_PLIST)
    write(tmp_path, "Tracker/AppDelegate.swift", '''
import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
}
''')
    write(tmp_path, "Tracker/DetailViewController.h", '''
#import <UIKit/UIKit.h>

@interface DetailViewController : UIViewController
@property (nonatomic, strong) NSString *recordID;
- (void)reload:(NSString *)recordID;
@end
''')
    write(tmp_path, "Tracker/DetailViewController.m", '''
#import "DetailViewController.h"

@implementation DetailViewController
- (void)reload:(NSString *)recordID {}
@end
''')
    write(tmp_path, "Tracker/Main.storyboard", '''<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.CocoaTouch.Storyboard">
    <scenes>
        <scene sceneID="s0">
            <objects>
                <viewController id="v1" customClass="DetailViewController" sceneMemberID="viewController"/>
            </objects>
        </scene>
    </scenes>
</document>
''')
    write(tmp_path, "Tracker/Tracker.entitlements",
          '<?xml version="1.0"?><plist version="1.0"><dict>'
          '<key>aps-environment</key><string>development</string></dict></plist>')
    write(tmp_path, "Tracker/Views/HistoryView.swift",
          "import SwiftUI\n\nstruct HistoryView: View { var body: some View { Text(\"\") } }\n")
    write(tmp_path, "Tracker/Models/Record.swift",
          "struct Record: Codable { let id: Int }\n")
    write(tmp_path, "TrackerTests/TrackerTests.swift", '''
import XCTest
@testable import Tracker

final class TrackerTests: XCTestCase {}
''')


# @lat: [[source-tests#Repo map adapters#iOS target detection]]
def test_ios_target_detection(tmp_path):
    build_ios_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    target = next(t for t in bundle["targets"] if t["platform"] == "ios-app")
    assert target["confidence"] >= 0.8
    assert any("Tracker.xcodeproj" in e for e in target["evidence"])
    assert any("UIDeviceFamily" in e for e in target["evidence"])
    assert any("entitlements" in e for e in target["evidence"])
    # source roots from the pbxproj heuristic
    assert "Tracker" in target["source_roots"]
    assert "TrackerTests" in target["source_roots"]
    assert target["applicability"] == "full"
    assert bundle["coverage"]["applicability"] == "full"


# @lat: [[source-tests#Repo map adapters#iOS symbols and header resolution]]
def test_ios_symbols_and_header_resolution(tmp_path):
    build_ios_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    header = files["Tracker/DetailViewController.h"]
    assert header["lang"] == "objc"
    impl = files["Tracker/DetailViewController.m"]
    assert any(s["kind"] == "implementation" and s["name"] == "DetailViewController"
               for s in impl["symbols"])
    # quoted local header resolves through the pbxproj source root
    imports = {i["specifier"]: i for i in impl["imports"]}
    assert imports["DetailViewController.h"]["resolved"] == "Tracker/DetailViewController.h"
    swift = files["Tracker/AppDelegate.swift"]
    assert any(s["kind"] == "class" and s["name"] == "AppDelegate" for s in swift["symbols"])
    # swift module imports stay external, objc framework imports external
    assert all(i["external"] for i in swift["imports"])
    records = files["Tracker/Models/Record.swift"]
    assert records["role"]["kind"] == "model"
    tests = files["TrackerTests/TrackerTests.swift"]
    assert tests["role"]["kind"] == "test"


# @lat: [[source-tests#Repo map adapters#iOS storyboard edges]]
def test_ios_storyboard_edges(tmp_path):
    build_ios_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    storyboard = files["Tracker/Main.storyboard"]
    assert storyboard["lang"] == "storyboard"
    imports = {i["specifier"]: i for i in storyboard["imports"]}
    ref = imports["customClass:DetailViewController"]
    assert ref["resolved"] == "Tracker/DetailViewController.h"
    assert ref["reason"] == "storyboard" and ref["external"] is False
    # an unresolved class reference is missing, never external
    write(tmp_path, "Tracker/Second.storyboard",
          '<document><viewController customClass="MissingVC"/></document>')
    bundle = RepoMap().generate(tmp_path)
    second = bundle["files"]["Tracker/Second.storyboard"]["imports"][0]
    assert second["resolved"] is None and second["external"] is False
    assert second["reason"] == "missing"


# @lat: [[source-tests#Repo map adapters#iOS binary ipa]]
def test_ios_binary_ipa(tmp_path):
    write(tmp_path, "release/Tracker.ipa", "PK\x03\x04stub")
    write(tmp_path, "release/notes.txt", "uploaded to TestFlight\n")
    bundle = RepoMap().generate(tmp_path)
    target = next(t for t in bundle["targets"] if t["platform"] == "ios-app")
    assert target["binary_only"] is True
    assert target["applicability"] == "not_applicable"
    assert "no extraction" in target["applicability_reason"] or \
        "binary-only" in target["applicability_reason"]
    # no IPA VFS: nothing inside the ipa is ever listed or read
    assert not any(".ipa" in p for p in bundle["files"])
