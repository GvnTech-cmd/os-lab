"""Regression tests for the shared map core that the new adapters build on.

Covers Python/TS symbol extraction, alias and relative resolution, the role
cascade, filtering (including the platform-to-root mapping fix), the type
index, determinism, caps and the CLI.
"""

import json

from source_lab.sourcemap import MapFilter, RepoMap
from source_lab.sourcemap.__main__ import main as cli_main
from source_lab.sourcemap.report import to_json


def write(tmp_path, rel, text):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


# @lat: [[source-tests#Repo map adapters#Core python and typescript symbols]]
def test_core_python_and_ts_symbols(tmp_path):
    write(tmp_path, "pkg/mod.py", '''
from .util import thing as other
import os

class Service(Base):
    @staticmethod
    def run(user: "User", *args) -> dict:
        return {"ok": True}

async def fetch(url: str) -> bytes:
    return b""

__all__ = ["Service"]
''')
    write(tmp_path, "pkg/util.py", "thing = 1\n")
    write(tmp_path, "src/pages/Home.tsx", '''
import { db } from "@/lib/db";
import {
  useRouter,
} from "next/router";

export default function Home(): JSX.Element {
  const router = useRouter();
  return <div />;
}

export function useAuth() {
  return { user: null };
}
''')
    write(tmp_path, "src/lib/db.ts", "export interface User { id: number }\nexport const db = 1;\n")
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    py = {s["name"]: s for s in files["pkg/mod.py"]["symbols"]}
    assert py["Service"]["kind"] == "class"
    assert py["run"]["returns"]["type"] == "dict"
    assert py["run"]["decorators"] == ["@staticmethod"]
    assert py["fetch"]["returns"]["type"] == "bytes"
    assert files["pkg/mod.py"]["exports"] == ["Service"]
    ts = {s["name"]: s for s in files["src/pages/Home.tsx"]["symbols"]}
    assert ts["Home"]["kind"] == "component"
    assert ts["useAuth"]["kind"] == "hook"
    assert "default" in files["src/pages/Home.tsx"]["exports"]
    imports = {i["specifier"]: i for i in files["src/pages/Home.tsx"]["imports"]}
    router = imports["next/router"]
    assert router["names"] == ["useRouter"]  # multi-line import with a specifier
    assert router["line"] > 1


# @lat: [[source-tests#Repo map adapters#Core resolution and roles]]
def test_core_resolution_and_roles(tmp_path):
    write(tmp_path, "lib/db.ts", "export const db = 1;\n")
    write(tmp_path, "src/app/page.tsx", 'import { db } from "@/lib/db";\nimport x from "./missing";\nimport lodash from "lodash";\nexport default function Page() { return null; }\n')
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/mod.py", "from . import util\nimport numpy\n")
    write(tmp_path, "pkg/util.py", "x = 1\n")
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    ts_imports = {i["specifier"]: i for i in files["src/app/page.tsx"]["imports"]}
    assert ts_imports["@/lib/db"]["resolved"] == "lib/db.ts"
    assert ts_imports["@/lib/db"]["reason"] == "alias"
    assert ts_imports["./missing"]["external"] is False and ts_imports["./missing"]["reason"] == "missing"
    assert ts_imports["lodash"]["external"] is True and ts_imports["lodash"]["reason"] == "package"
    py_imports = {i["specifier"]: i for i in files["pkg/mod.py"]["imports"]}
    assert py_imports["."]["resolved"] == "pkg/__init__.py"
    assert py_imports["numpy"]["external"] is True
    roles = {p: f["role"]["kind"] for p, f in files.items()}
    assert roles["lib/db.ts"] == "lib"
    assert roles["pkg/mod.py"] == "unknown"


# @lat: [[source-tests#Repo map adapters#Core filtering]]
def test_core_filtering(tmp_path):
    write(tmp_path, "ext/manifest.json", json.dumps({"manifest_version": 3}))
    write(tmp_path, "ext/a.js", "const a = 1;\n")
    write(tmp_path, "mobile/AndroidManifest.xml",
          '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.x"/>\n')
    write(tmp_path, "mobile/app/src/main/java/com/x/M.kt", "package com.x\n\nclass M\n")
    bundle = RepoMap().generate(tmp_path)
    # platform names map to target roots before path filtering
    filtered = RepoMap.filter_map(bundle, MapFilter(targets=("android-app",)))
    assert set(filtered["files"]) == {"mobile/AndroidManifest.xml",
                                      "mobile/app/src/main/java/com/x/M.kt"}
    kinds = RepoMap.filter_map(bundle, MapFilter(kinds=("class",)))
    assert set(kinds["files"]) == {"mobile/app/src/main/java/com/x/M.kt"}
    roles = RepoMap.filter_map(bundle, MapFilter(roles=("config",)))
    assert set(roles["files"]) == {"ext/manifest.json", "mobile/AndroidManifest.xml"}
    # edges, entrypoints and cycles describe the full graph
    assert filtered["entrypoints"] == bundle["entrypoints"]
    assert filtered["cycles"] == bundle["cycles"]
    assert filtered["filter"]["applied"] is True


# @lat: [[source-tests#Repo map adapters#Core type index]]
def test_core_type_index(tmp_path):
    write(tmp_path, "a.ts", "export interface User { id: number }\n")
    write(tmp_path, "b.ts", "export interface User { name: string }\n")
    write(tmp_path, "use.ts", 'import type { User } from "./a";\nexport const u: User = null as any;\n')
    bundle = RepoMap().generate(tmp_path)
    entries = bundle["types"]["User"]
    assert len(entries) == 2  # no name merging
    assert {e["file"] for e in entries} == {"a.ts", "b.ts"}
    a_entry = next(e for e in entries if e["file"] == "a.ts")
    assert a_entry["references"] >= 1  # only resolved imports count


# @lat: [[source-tests#Repo map adapters#Core determinism and caps]]
def test_core_determinism_and_caps(tmp_path):
    write(tmp_path, "app.py", "def main():\n    pass\n")
    write(tmp_path, "lib.js", "export function helper() { return 1; }\n")
    first = RepoMap().generate(tmp_path)
    second = RepoMap().generate(tmp_path)
    assert to_json(first) == to_json(second)

    # a tiny file cap truncates and records the skip with a named reason
    (tmp_path / "big.py").write_text("x = '" + "a" * 600 + "'\n")
    capped = RepoMap(caps=_caps_with(file_bytes=100)).generate(tmp_path)
    skips = {s["path"]: s["reason"] for s in capped["coverage"]["skipped"]}
    assert skips["big.py"].startswith("size:")

    # minified bundles are skipped as generated
    write(tmp_path, "vendor.min.js", "var a=1;" + "b=2;" * 50)
    capped = RepoMap(caps=_caps_with(file_bytes=100000)).generate(tmp_path)
    skips = {s["path"]: s["reason"] for s in capped["coverage"]["skipped"]}
    assert skips["vendor.min.js"].startswith("generated: minified")


def _caps_with(**kwargs):
    from source_lab.sourcemap.engine import Caps
    return Caps(**kwargs)


# @lat: [[source-tests#Repo map adapters#Core cli and query]]
def test_core_cli_and_query(tmp_path, capsys):
    write(tmp_path, "a.py", "def main():\n    pass\n")
    out = tmp_path / "map.json"
    assert cli_main(["generate", "--root", str(tmp_path), "--out", str(out)]) == 0
    assert out.exists()
    capsys.readouterr()
    assert cli_main(["query", "--map", str(out), "--lang", "python"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is True and payload["matched_files"] == 1
    # kind filter on a files-detail artifact explains itself
    files_only = tmp_path / "map-files.json"
    assert cli_main(["generate", "--root", str(tmp_path), "--out", str(files_only),
                     "--map-detail", "files"]) == 0
    capsys.readouterr()
    assert cli_main(["query", "--map", str(files_only), "--kind", "function"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["matched_files"] == 0
    assert "symbol detail" in payload["hint"]


# @lat: [[source-tests#Repo map adapters#Core ranking]]
def test_core_ranking(tmp_path):
    write(tmp_path, "main.py", "import a\nimport b\n")
    write(tmp_path, "a.py", "import b\n")
    write(tmp_path, "b.py", "import c\n")
    write(tmp_path, "c.py", "import a\n")
    bundle = RepoMap().generate(tmp_path)
    entry_paths = [e["path"] for e in bundle["entrypoints"]]
    assert "main.py" in entry_paths
    assert bundle["cycles"] and sorted(set(bundle["cycles"][0])) == ["a.py", "b.py", "c.py"]
    scores = dict(bundle["entrypoints"][0]) if bundle["entrypoints"] else {}
    assert all("score" in e for e in bundle["entrypoints"])
