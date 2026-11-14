"""Tests for the structural repository map."""

import json

from source_lab.sourcemap import MapFilter, RepoMap
from source_lab.sourcemap.__main__ import main
from source_lab.sourcemap.report import to_json

def write(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


# @lat: [[source-tests#Repo map#Python symbols]]
def test_python_symbols(tmp_path):
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/mod.py", '''
from .util import thing as other
import os

class Service(Base):
    @staticmethod
    def run(user: User, *args, **kwargs) -> dict:
        return {"ok": True}

async def fetch(url: str) -> bytes:
    return b""

__all__ = ["Service"]
''')
    bundle = RepoMap().generate(tmp_path)
    item = bundle["files"]["pkg/mod.py"]
    names = {s["name"]: s for s in item["symbols"]}
    assert names["Service"]["kind"] == "class"
    assert names["run"]["returns"]["type"] == "dict"
    assert names["run"]["decorators"] == ["@staticmethod"]
    assert names["run"]["params"][0]["name"] == "user"
    assert names["fetch"]["returns"]["type"] == "bytes"
    assert item["exports"] == ["Service"]
    assert item["imports"][0]["specifier"] == ".util"
    assert item["imports"][0]["names"] == ["other"]


# @lat: [[source-tests#Repo map#TypeScript symbols]]
def test_typescript_symbols(tmp_path):
    write(tmp_path, "src/page.tsx", '''import {
  a,
  b as c,
} from "./multi"
import React from "react"

export default function Page() {
  return <div>{a}</div>
}

export const Card = (props: { title: string }) => <section>{props.title}</section>

export function useThing() {
  return 1
}

export type { User } from "./types"
''')
    bundle = RepoMap().generate(tmp_path)
    item = bundle["files"]["src/page.tsx"]
    names = {s["name"]: s for s in item["symbols"]}
    assert names["Page"]["kind"] == "component"
    assert names["Page"]["line"] == 7
    assert names["Card"]["kind"] == "component"
    assert names["Card"]["params"][0]["type"] == "{ title: string }"
    assert names["useThing"]["kind"] == "hook"
    assert item["imports"][0]["specifier"] == "./multi"
    assert item["imports"][0]["names"] == ["a", "c"]
    reexport = [i for i in item["imports"] if i["kind"] == "reexport"]
    assert reexport and reexport[0]["names"] == ["User"]


# @lat: [[source-tests#Repo map#Import resolution]]
def test_import_resolution(tmp_path):
    write(tmp_path, "src/lib/db.ts", "export const db = 1\n")
    write(tmp_path, "src/app/local/index.ts", "export const local = 1\n")
    write(tmp_path, "src/app/page.tsx", '''import { db } from "@/lib/db"
import { local } from "./local"
import React from "react"
''')
    bundle = RepoMap().generate(tmp_path)
    imports = {i["specifier"]: i for i in bundle["files"]["src/app/page.tsx"]["imports"]}
    assert imports["@/lib/db"]["resolved"] == "src/lib/db.ts"
    assert imports["./local"]["resolved"] == "src/app/local/index.ts"
    assert imports["react"]["external"] is True
    assert {"from": "src/app/page.tsx", "to": "src/lib/db.ts", "kind": "import"} in bundle["edges"]


# @lat: [[source-tests#Repo map#Role cascade]]
def test_role_cascade(tmp_path):
    write(tmp_path, "src/app/page.tsx", "export default function Page() { return <div/> }\n")
    write(tmp_path, "src/stores/user.ts", "export const user = 1\n")
    write(tmp_path, "src/lib/db.ts", "const db = new PrismaClient()\nexport default db\n")
    write(tmp_path, "src/misc/thing.ts", "export function helper() { return 1 }\n")
    roles = {path: item["role"]["kind"] for path, item in RepoMap().generate(tmp_path)["files"].items()}
    assert roles["src/app/page.tsx"] == "page"
    assert roles["src/stores/user.ts"] == "store"
    assert roles["src/lib/db.ts"] == "db"
    assert roles["src/misc/thing.ts"] == "unknown"


# @lat: [[source-tests#Repo map#Filtering]]
def test_filtering(tmp_path):
    write(tmp_path, "src/app/page.tsx", "export default function Page() { return <div/> }\n")
    write(tmp_path, "src/components/Button.tsx", "export const Button = () => <button/>\n")
    full = RepoMap(detail="full").generate(tmp_path)
    filtered = RepoMap(detail="full", filter=MapFilter(roles=("page",), kinds=("component",))).generate(tmp_path)
    assert set(filtered["files"]) == {"src/app/page.tsx"}
    assert filtered["edges"] == full["edges"]
    assert filtered["entrypoints"] == full["entrypoints"]
    assert filtered["filter"]["matched_files"] == 1
    both = MapFilter(roles=("page", "component"))
    assert set(RepoMap.filter_map(full, both)["files"]) == {"src/app/page.tsx", "src/components/Button.tsx"}
    assert RepoMap.filter_map(full, MapFilter(roles=("page",), kinds=("hook",)))["filter"]["matched_files"] == 0


# @lat: [[source-tests#Repo map#Filtering without symbols]]
def test_filtering_without_symbols(tmp_path, capsys):
    write(tmp_path, "src/components/Button.tsx", "export const Button = () => <button/>\n")
    files = RepoMap(detail="files").generate(tmp_path)
    filtered = RepoMap.filter_map(files, MapFilter(kinds=("component",)))
    assert filtered["filter"]["matched_files"] == 0
    out = tmp_path / "map.json"
    code = main(["--root", str(tmp_path), "--out", str(out), "--detail", "files",
                 "--kind", "component"])
    assert code == 2
    assert "kinds need symbols" in capsys.readouterr().err


# @lat: [[source-tests#Repo map#Type index]]
def test_type_index(tmp_path):
    write(tmp_path, "a.ts", "export interface User { id: string }\n")
    write(tmp_path, "b.ts", "export class User {}\n")
    write(tmp_path, "c.ts", 'import { User } from "./a"\nexport const u: User = { id: "1" }\n')
    types = RepoMap().generate(tmp_path)["types"]["User"]
    assert len(types) == 2
    assert {entry["file"] for entry in types} == {"a.ts", "b.ts"}
    assert next(e for e in types if e["file"] == "a.ts")["references"] == 1
    assert next(e for e in types if e["file"] == "b.ts")["references"] == 0


# @lat: [[source-tests#Repo map#Target segmentation]]
def test_target_segmentation(tmp_path):
    write(tmp_path, "ext/manifest.json", '{"manifest_version": 3, "permissions": []}')
    write(tmp_path, "ext/background.js", "console.log(1)\n")
    write(tmp_path, "mobile/AndroidManifest.xml", "<manifest/>")
    write(tmp_path, "mobile/app/src/main/AndroidManifest.xml", "<manifest/>")
    bundle = RepoMap().generate(tmp_path)
    platforms = {t["platform"] for t in bundle["targets"]}
    assert platforms == {"browser-extension", "android-app"}
    only = RepoMap(target_classes=["android-app"]).generate(tmp_path)
    assert all(path.startswith("mobile/") for path in only["files"])


# @lat: [[source-tests#Repo map#Binary-only target]]
def test_binary_only_target(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"PK\\x03\\x04")
    bundle = RepoMap().generate(apk)
    assert bundle["targets"][0]["platform"] == "android-app"
    assert bundle["coverage"]["applicability"] == "not_applicable"
    assert bundle["stats"]["source_files"] == 0


# @lat: [[source-tests#Repo map#Determinism]]
def test_determinism(tmp_path):
    write(tmp_path, "src/a.ts", 'import { b } from "./b"\nexport const a = b\n')
    write(tmp_path, "src/b.ts", "export const b = 1\n")
    first = to_json(RepoMap().generate(tmp_path))
    second = to_json(RepoMap().generate(tmp_path))
    assert first == second


# @lat: [[source-tests#Repo map#Caps and coverage]]
def test_caps_and_coverage(tmp_path):
    write(tmp_path, "big.ts", "x" * 2000)
    write(tmp_path, "app.min.js", "var x=1\n")
    bundle = RepoMap(max_kb=1).generate(tmp_path)
    reasons = {item["path"]: item["reason"] for item in bundle["coverage"]["skipped"]}
    assert "large" in reasons["big.ts"]
    assert "minified" in reasons["app.min.js"]
    stopped = RepoMap(budget_ms=0).generate(tmp_path)
    assert stopped["stats"]["truncated"] is True
    assert any(s["reason"].startswith("not_visited") for s in stopped["coverage"]["skipped"])


# @lat: [[source-tests#Repo map#CLI generation and query]]
def test_cli_generation_and_query(tmp_path, capsys):
    write(tmp_path, "src/components/Button.tsx", "export const Button = () => <button/>\n")
    write(tmp_path, "src/app/page.tsx", "export default function Page() { return <div/> }\n")
    out = tmp_path / "map.json"
    assert main(["--root", str(tmp_path), "--out", str(out), "--detail", "full"]) == 0
    assert json.loads(out.read_text())["stats"]["source_files"] == 2
    assert main(["query", "--map", str(out), "--kind", "component", "--role", "component"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result["files"]) == {"src/components/Button.tsx"}


# @lat: [[source-tests#Repo map#Markup adapters]]
def test_markup_adapters(tmp_path):
    write(tmp_path, "site/index.astro", '---\nimport X from "./X.astro"\nexport const title = "x"\n---\n<h1>{title}</h1>\n')
    write(tmp_path, "site/Widget.svelte", '<script>\nfunction go() {}\n</script>\n<div>{go()}</div>\n')
    write(tmp_path, "site/index.html", '<div id="root" class="a b"></div><script src="./app.js"></script>')
    write(tmp_path, "site/style.css", '@import "./x.css";\n:root { --brand: red; }\n.a { color: red; }\n')
    files = RepoMap().generate(tmp_path)["files"]
    assert files["site/index.astro"]["imports"][0]["specifier"] == "./X.astro"
    assert any(s["name"] == "go" for s in files["site/Widget.svelte"]["symbols"])
    assert {"root", "a", "b"} <= {s["name"] for s in files["site/index.html"]["symbols"]}
    assert any(s["name"] == "--brand" for s in files["site/style.css"]["symbols"])


# @lat: [[source-tests#Repo map#PHP and Rust resolution]]
def test_php_and_rust_resolution(tmp_path):
    write(tmp_path, "composer.json", '{"autoload": {"psr-4": {"App\\\\": "src/"}}}')
    write(tmp_path, "src/Models/User.php", "<?php\nnamespace App\\Models;\nclass User {}\n")
    write(tmp_path, "src/Controller.php", "<?php\nuse App\\Models\\User;\nclass Controller {}\n")
    write(tmp_path, "rust/src/lib.rs", "mod foo;\nuse crate::foo::Bar;\npub fn run() {}\n")
    write(tmp_path, "rust/src/foo.rs", "pub struct Bar;\n")
    bundle = RepoMap().generate(tmp_path)
    php = {i["specifier"]: i for i in bundle["files"]["src/Controller.php"]["imports"]}
    assert php["App\\Models\\User"]["resolved"] == "src/Models/User.php"
    rust = {i["specifier"]: i for i in bundle["files"]["rust/src/lib.rs"]["imports"]}
    assert rust["foo"]["resolved"] == "rust/src/foo.rs"
    assert rust["crate::foo::Bar"]["resolved"] == "rust/src/foo.rs"


# @lat: [[source-tests#Repo map#Ranking]]
def test_ranking(tmp_path):
    write(tmp_path, "src/a.ts", 'import { b } from "./b"\nexport const a = b\n')
    write(tmp_path, "src/b.ts", 'import { a } from "./a"\nexport const b = a\n')
    write(tmp_path, "src/c.ts", 'import { a } from "./a"\nexport const c = a\n')
    bundle = RepoMap().generate(tmp_path)
    assert bundle["entrypoints"][0]["path"] == "src/c.ts"
    assert ["src/a.ts", "src/b.ts", "src/a.ts"] in bundle["cycles"]


# @lat: [[source-tests#Repo map#Legacy AST fallback]]
def test_legacy_ast_fallback(tmp_path):
    from source_lab.pipeline.ext_repo_analyzer import _regex_ast, build_ast_file

    source = "import {\n  a,\n} from './x'\nexport default function Page() {}\ndef run():\n    pass\n"
    ast = _regex_ast(source, "tsx")
    imports = [node["text"] for node in ast["nodes"] if node["type"] == "import"]
    assert imports and "from './x'" in imports[0]
    names = {node.get("name") for node in ast["nodes"]}
    assert {"Page", "run"} <= names
    big = tmp_path / "big.py"
    big.write_text("x" * 2000)
    skipped = build_ast_file(big, "python", None, None, None, max_kb=1)
    assert skipped["parser"] == "none"
