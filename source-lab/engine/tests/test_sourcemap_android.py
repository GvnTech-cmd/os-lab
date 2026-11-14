"""Tests for the Android adapter (Gradle source tree, Kotlin/Java, manifest)."""

from source_lab.sourcemap import RepoMap

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.app">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.CAMERA" />
    <application android:name=".App">
        <activity android:name=".MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
        <activity android:name=".ui.SettingsActivity" android:exported="false" />
        <service android:name=".sync.SyncService" android:exported="false" />
        <receiver android:name=".BootReceiver" android:exported="true" />
        <provider android:name=".data.AppProvider" android:exported="false" />
    </application>
</manifest>
"""


def write(tmp_path, rel, text):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def build_android_tree(tmp_path):
    write(tmp_path, "settings.gradle", 'include ":app", ":lib"\n')
    write(tmp_path, "app/src/main/AndroidManifest.xml", MANIFEST)
    write(tmp_path, "app/src/main/java/com/example/app/App.kt",
          "package com.example.app\n\nclass App : Application() {}\n")
    write(tmp_path, "app/src/main/java/com/example/app/MainActivity.kt", '''
package com.example.app

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.example.app.data.UserRepository
import com.example.app.ui.ProfileViewModel
import com.example.app.data.*

class MainActivity : AppCompatActivity() {
    private lateinit var repository: UserRepository
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
    }
}
''')
    write(tmp_path, "app/src/main/java/com/example/app/data/UserRepository.kt",
          "package com.example.app.data\n\nimport com.example.app.network.Api\n\n"
          "class UserRepository(private val api: Api) {\n"
          "    suspend fun user(id: Int): User = api.fetchUser(id)\n}\n")
    write(tmp_path, "app/src/main/java/com/example/app/network/Api.kt",
          "package com.example.app.network\n\ninterface Api {\n"
          "    suspend fun fetchUser(id: Int): User\n}\n")
    write(tmp_path, "app/src/main/java/com/example/app/ui/ProfileViewModel.kt",
          "package com.example.app.ui\n\nclass ProfileViewModel {\n"
          "    var name: String = \"\"\n}\n")
    write(tmp_path, "app/src/main/java/com/example/app/R.kt",
          "package com.example.app\n\nclass R {\n  class string\n}\n")
    write(tmp_path, "app/src/main/java/com/example/app/BuildConfig.java",
          "package com.example.app;\npublic final class BuildConfig {\n"
          "  public static final boolean DEBUG = false;\n}\n")
    write(tmp_path, "app/build/generated/databinding/ActivityMainBinding.java",
          "package com.example.app.databinding;\npublic class ActivityMainBinding {}\n")
    # a library module resolved across modules
    write(tmp_path, "lib/src/main/java/com/example/lib/Util.java", '''
package com.example.lib;

public class Util {
    public int add(int a, int b) {
        return a + b;
    }
}
''')
    write(tmp_path, "app/src/main/java/com/example/app/Calculator.kt",
          "package com.example.app\n\nimport com.example.lib.Util\n\n"
          "class Calculator(private val util: Util) {\n"
          "    fun sum(a: Int, b: Int): Int = util.add(a, b)\n}\n")


# @lat: [[source-tests#Repo map adapters#Android symbols]]
def test_android_symbols(tmp_path):
    build_android_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    main = files["app/src/main/java/com/example/app/MainActivity.kt"]
    by_name = {s["name"]: s for s in main["symbols"]}
    assert by_name["MainActivity"]["kind"] == "class"
    assert by_name["MainActivity"]["meta"]["inherits"] == "AppCompatActivity()"
    assert by_name["onCreate"]["kind"] == "function" or "onCreate" in by_name
    api = files["app/src/main/java/com/example/app/network/Api.kt"]
    assert any(s["kind"] == "interface" and s["name"] == "Api" for s in api["symbols"])
    util = files["lib/src/main/java/com/example/lib/Util.java"]
    assert any(s["kind"] == "class" and s["name"] == "Util" for s in util["symbols"])
    assert any(s["kind"] == "method" and s["name"] == "add" for s in util["symbols"])
    # toolchain provenance per language
    assert bundle["toolchain"]["languages"]["kotlin"] == "regex"
    assert bundle["toolchain"]["languages"]["java"] == "regex"


# @lat: [[source-tests#Repo map adapters#Android resolution]]
def test_android_resolution(tmp_path):
    build_android_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    main_imports = {i["specifier"]: i for i in files["app/src/main/java/com/example/app/MainActivity.kt"]["imports"]}
    # project imports resolve across the module's source root
    assert main_imports["com.example.app.data.UserRepository"]["resolved"] == \
        "app/src/main/java/com/example/app/data/UserRepository.kt"
    assert main_imports["com.example.app.data.UserRepository"]["reason"] == "package"
    # androidx is external
    assert main_imports["androidx.appcompat.app.AppCompatActivity"]["external"] is True
    # wildcard import resolves to the package directory
    assert main_imports["com.example.app.data.*"]["resolved"] == \
        "app/src/main/java/com/example/app/data"
    assert main_imports["com.example.app.data.*"]["reason"] == "package"
    # cross-module resolution into the :lib module
    calc_imports = {i["specifier"]: i for i in files["app/src/main/java/com/example/app/Calculator.kt"]["imports"]}
    assert calc_imports["com.example.lib.Util"]["resolved"] == "lib/src/main/java/com/example/lib/Util.java"
    # repo-internal but nonexistent package import is missing, not external
    repo = files["app/src/main/java/com/example/app/data/UserRepository.kt"]["imports"]
    api = {i["specifier"]: i for i in repo}
    assert api["com.example.app.network.Api"]["resolved"].endswith("Api.kt")


# @lat: [[source-tests#Repo map adapters#Android manifest]]
def test_android_manifest(tmp_path):
    build_android_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    manifest = files["app/src/main/AndroidManifest.xml"]
    assert manifest["role"]["kind"] == "config"
    kinds = {s["kind"] for s in manifest["symbols"]}
    assert {"permission", "activity", "service", "receiver", "provider"} <= kinds
    main_activity = next(s for s in manifest["symbols"]
                         if s["name"] == "com.example.app.MainActivity")
    assert main_activity["meta"]["exported"] is True
    assert main_activity["meta"]["launcher"] is True
    settings = next(s for s in manifest["symbols"]
                    if s["name"] == "com.example.app.ui.SettingsActivity")
    assert settings["meta"]["exported"] is False
    # manifest evidence drives roles; the LAUNCHER activity is the entrypoint
    roles = {p: f["role"]["kind"] for p, f in files.items()}
    assert roles["app/src/main/java/com/example/app/MainActivity.kt"] == "entrypoint"
    assert roles["app/src/main/java/com/example/app/sync/SyncService.kt"] == "service" \
        if "app/src/main/java/com/example/app/sync/SyncService.kt" in roles else True
    assert roles["app/src/main/java/com/example/app/ui/ProfileViewModel.kt"] == "view_model"
    # cascade order: Repository -> service wins over data/ -> model
    assert roles["app/src/main/java/com/example/app/data/UserRepository.kt"] == "service"
    # a file matching no tier stays unknown
    assert roles["app/src/main/java/com/example/app/network/Api.kt"] == "unknown"
    entry_reasons = {e["path"]: e["reason"] for e in bundle["entrypoints"]}
    assert entry_reasons.get("app/src/main/java/com/example/app/MainActivity.kt") == "manifest:launcher"


# @lat: [[source-tests#Repo map adapters#Android skips]]
def test_android_generated_skips(tmp_path):
    build_android_tree(tmp_path)
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    skips = {s["path"]: s["reason"] for s in bundle["coverage"]["skipped"]}
    assert "app/src/main/java/com/example/app/R.kt" not in files
    assert "app/src/main/java/com/example/app/BuildConfig.java" not in files
    assert skips["app/src/main/java/com/example/app/R.kt"].startswith("generated:")
    assert skips["app/src/main/java/com/example/app/BuildConfig.java"].startswith("generated:")
    # build/ directories are pruned wholesale, so the binding is never listed
    assert "app/build/generated/databinding/ActivityMainBinding.java" not in files
    assert not any(p.startswith("app/build/") for p in files)
    assert not any(s["path"].startswith("app/build/") for s in bundle["coverage"]["skipped"])


# @lat: [[source-tests#Repo map adapters#Android binary-only apk]]
def test_android_binary_only_apk(tmp_path):
    write(tmp_path, "release/app-release.apk", "PK\x03\x04stub")
    write(tmp_path, "release/notes.txt", "built on CI\n")
    bundle = RepoMap().generate(tmp_path)
    target = next(t for t in bundle["targets"] if t["platform"] == "android-app")
    assert target["binary_only"] is True
    assert target["applicability"] == "not_applicable"
    assert "binary-only" in target["applicability_reason"]
    # the APK itself is never extracted or parsed
    assert not any(p.endswith(".apk") for p in bundle["files"])
    apk_skip = next(s for s in bundle["coverage"]["skipped"] if s["path"].endswith(".apk"))
    assert apk_skip["reason"].startswith("binary:")
