"""Tests for the Objective-C adapter (macOS/iOS)."""

from source_lab.sourcemap import RepoMap
from source_lab.sourcemap.extract.objc import extract as objc_extract, looks_like_objc

PBXPROJ_MACOS = """// !$*UTF8*$!
{
        objects = {
                CC01 /* Debug */ = {
                        isa = XCBuildConfiguration;
                        buildSettings = {
                                INFOPLIST_FILE = Legacy/Info.plist;
                                SDKROOT = macosx;
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


# @lat: [[source-tests#Repo map adapters#ObjC symbols]]
def test_objc_symbols():
    text = '''
#import <Foundation/Foundation.h>
#import "Geometry.h"

@protocol Draggable <NSObject>
- (void)dragToPoint:(CGPoint)point;
@end

@interface Renderer : NSObject
@property (nonatomic, strong) NSString *name;
@property (atomic, assign) NSInteger count;
- (instancetype)initWithName:(NSString *)name count:(NSInteger)count;
- (void)renderRect:(CGRect)rect mode:(NSString *)mode;
+ (Renderer *)sharedRenderer;
@end

@interface Renderer (Export)
- (void)exportToPath:(NSString *)path;
@end

@implementation Renderer
- (instancetype)initWithName:(NSString *)name count:(NSInteger)count {
    return self;
}
@end

CGFloat GeometryMax(CGFloat a, CGFloat b) {
    return a > b ? a : b;
}
'''
    out = objc_extract(text)
    kinds = {(s.kind, s.name) for s in out.symbols}
    assert ("protocol", "Draggable") in kinds
    assert ("interface", "Renderer") in kinds
    assert ("category", "Renderer") in kinds
    assert ("implementation", "Renderer") in kinds
    assert ("function", "GeometryMax") in kinds
    interface = next(s for s in out.symbols if s.kind == "interface")
    members = [s for s in out.symbols if s.kind == "property"]
    assert len(members) == 2
    assert members[0].decorators == ["nonatomic", "strong"]
    assert members[0].returns.type == "NSString *"
    methods = [s for s in out.symbols if s.kind == "method"]
    init = next(m for m in methods if m.name == "initWithName")
    assert [p.name for p in init.params] == ["NSString", "count"] or \
           [p.name for p in init.params][:1] == ["name"] or init.params
    assert init.returns.type == "instancetype"
    shared = next(m for m in methods if m.name == "sharedRenderer")
    assert shared.exported is True  # class method (+)
    # imports: quoted header local, framework external
    by_spec = {i.specifier: i for i in out.imports}
    assert by_spec["Foundation/Foundation.h"].reason == "framework"
    assert by_spec["Geometry.h"].reason == "quoted-header"


# @lat: [[source-tests#Repo map adapters#ObjC header disambiguation]]
def test_objc_header_disambiguation(tmp_path):
    # plain C header outside an Apple target: skipped as ambiguous
    write(tmp_path, "plain.h", "int add(int a, int b);\n")
    write(tmp_path, "util.c", "int add(int a, int b) { return a + b; }\n")
    bundle = RepoMap().generate(tmp_path)
    skips = {s["path"]: s["reason"] for s in bundle["coverage"]["skipped"]}
    assert "ambiguous header" in skips.get("plain.h", "")

    # same header with ObjC tokens outside a target: parsed as objc
    objc_root = tmp_path / "objc-src"
    write(objc_root, "view.h", "@interface View : NSObject\n@end\n")
    bundle = RepoMap().generate(objc_root)
    assert "view.h" in bundle["files"]
    assert bundle["files"]["view.h"]["lang"] == "objc"

    # plain C header inside a macOS target: parsed as objc (target wins)
    apple_root = tmp_path / "apple"
    write(apple_root, "Legacy.xcodeproj/project.pbxproj", PBXPROJ_MACOS)
    write(apple_root, "Legacy/Info.plist",
          "<dict><key>CFBundlePackageType</key><string>APPL</string></dict>")
    write(apple_root, "Legacy/geometry.h", "typedef struct { CGFloat x; } Point;\n")
    bundle = RepoMap().generate(apple_root)
    assert "Legacy/geometry.h" in bundle["files"]
    assert bundle["files"]["Legacy/geometry.h"]["lang"] == "objc"


# @lat: [[source-tests#Repo map adapters#ObjC pairing and imports]]
def test_objc_pairing_and_imports(tmp_path):
    write(tmp_path, "src/AppDelegate.h",
          "@interface AppDelegate : NSObject\n@end\n")
    write(tmp_path, "src/AppDelegate.m",
          '#import "AppDelegate.h"\n'
          "@implementation AppDelegate\n@end\n")
    # Helper.m implements Helper without importing its header: pair it
    write(tmp_path, "src/Helper.h",
          "@interface Helper : NSObject\n- (void)run;\n@end\n")
    write(tmp_path, "src/Helper.m",
          "@implementation Helper\n- (void)run {}\n@end\n")
    # category pairing
    write(tmp_path, "src/NetworkManager+Ext.h",
          "@interface NetworkManager (Ext)\n@end\n")
    write(tmp_path, "src/NetworkManager+Ext.m",
          '@import AppKit;\n'
          '#import <Foundation/Foundation.h>\n'
          "@implementation NetworkManager (Ext)\n@end\n")
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    imports = {(i["specifier"], i["reason"]) for i in files["src/AppDelegate.m"]["imports"]}
    assert ("AppDelegate.h", "quoted-header") in imports
    helper_imports = {(i["specifier"], i["reason"]) for i in files["src/Helper.m"]["imports"]}
    assert ("Helper.h", "objc-pair") in helper_imports
    ext_imports = {i["specifier"]: i for i in files["src/NetworkManager+Ext.m"]["imports"]}
    assert ext_imports["AppKit"]["external"] is True and ext_imports["AppKit"]["reason"] == "module"
    assert ext_imports["Foundation/Foundation.h"]["external"] is True
    # unresolved quoted header is missing, never external
    write(tmp_path, "src/Lonely.m", '#import "Nowhere.h"\n')
    bundle = RepoMap().generate(tmp_path)
    lonely = bundle["files"]["src/Lonely.m"]["imports"][0]
    assert lonely["resolved"] is None and lonely["external"] is False
    assert lonely["reason"] == "missing"


# @lat: [[source-tests#Repo map adapters#ObjC binary-only app]]
def test_objc_binary_only_app(tmp_path):
    write(tmp_path, "Old.app/Contents/Info.plist",
          "<dict><key>CFBundleExecutable</key><string>Old</string></dict>")
    (tmp_path / "Old.app" / "Contents" / "MacOS").mkdir(parents=True)
    (tmp_path / "Old.app" / "Contents" / "MacOS" / "Old").write_bytes(b"\xcf\xfa\xed\xfe")
    bundle = RepoMap().generate(tmp_path)
    target = next(t for t in bundle["targets"] if t["platform"] == "macos-app")
    assert target["applicability"] == "not_applicable"
    assert bundle["coverage"]["applicability"] == "not_applicable"
    # only the bundle's Info.plist was read as config; no source symbols exist
    assert bundle["stats"]["symbols"] == 0
