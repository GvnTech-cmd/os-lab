"""Tests for the Windows/Electron ``app.asar`` adapter.

The asar fixture is built in the test itself: the helper below writes the
real Chromium pickle layout (8/16-byte header, JSON directory, content
region) so no external tooling and no disk extraction are involved.
"""

import json
import struct

import pytest

from source_lab.sourcemap import RepoMap
from source_lab.sourcemap.archives import asar as asar_module
from source_lab.sourcemap.archives.asar import AsarError, load_asar
from source_lab.sourcemap.vfs import ArchiveFS, DiskFS, OverlayFS


def build_asar(files: dict, unpacked=()) -> bytes:
    """Serialize {member path: bytes} into asar bytes.

    Mirrors the real layout: only packed members consume offset space and
    their bytes are contiguous after the header; unpacked members carry the
    ``unpacked`` flag and their bytes live outside the archive.
    """
    unpacked = set(unpacked)

    def node_for(path):
        node = header["files"]
        parts = path.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {}).setdefault("files", {})
        return node, parts[-1]

    header: dict = {"files": {}}
    offset = 0
    for path in sorted(files):
        node, leaf = node_for(path)
        node[leaf] = {"size": len(files[path])}
        if path in unpacked:
            node[leaf]["unpacked"] = True
        else:
            node[leaf]["offset"] = str(offset)
            offset += len(files[path])
    body = b"".join(files[p] for p in sorted(files) if p not in unpacked)
    blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
    padded = blob + b"\x00" * ((4 - len(blob) % 4) % 4)
    header_payload = struct.pack("<I", len(blob)) + padded
    header_pickle = struct.pack("<I", len(header_payload)) + header_payload
    size_pickle = struct.pack("<II", 4, len(header_pickle))
    return bytes(size_pickle) + bytes(header_pickle) + body


def make_electron_tree(tmp_path, asar_files, unpacked_files=None):
    unpacked_files = unpacked_files or {}
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "demo", "main": "resources/app.asar",
        "dependencies": {"electron": "^28.0.0"}}))
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "app.asar").write_bytes(
        build_asar(asar_files, unpacked=set(unpacked_files)))
    unpacked_dir = tmp_path / "resources" / "app.asar.unpacked"
    for rel, data in unpacked_files.items():
        target = unpacked_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return tmp_path


def electron_files() -> dict:
    return {
        "package.json": json.dumps({"main": "main.js", "preload": "preload.js"}).encode(),
        "main.js": (b"const { app } = require('electron');\n"
                    b"const util = require('./lib/util');\n"
                    b"const native = require('./lib/native');\n"
                    b"app.whenReady().then(() => util.add(1, 2));\n"),
        "lib/util.js": b"function add(a, b) { return a + b; }\nmodule.exports = { add };\n",
        "preload.js": b"window.addEventListener('load', () => {});\n",
        "index.html": b"<html><body id=\"root\"><script src=\"./renderer.js\"></script></body></html>\n",
        "styles.css": b"body { --accent: #fff; }\n#root { color: red; }\n",
        "native/addon.node": b"\x7fELF binary",
        "renderer.min.js": b"var a=1;" + b"t=2;" * 20,
    }


# @lat: [[source-tests#Repo map adapters#Asar header and mount]]
def test_asar_header_and_mount(tmp_path):
    blob = build_asar({"a.txt": b"hello", "dir/b.txt": b"world"})
    header, data_base, packed, unpacked, notes = load_asar(blob)
    assert header["files"]["a.txt"]["size"] == 5
    assert data_base == 8 + struct.unpack_from("<I", blob, 4)[0]
    assert set(packed) == {"a.txt", "dir/b.txt"}
    assert unpacked == set()
    assert notes == []

    disk = DiskFS(tmp_path)
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "app.asar").write_bytes(blob)
    archive = ArchiveFS(disk, "resources/app.asar", blob, packed, data_base)
    assert archive.exists("resources/app.asar!/a.txt")
    assert archive.read("resources/app.asar!/a.txt") == b"hello"
    assert archive.is_dir("resources/app.asar!/dir")
    assert not archive.is_dir("resources/app.asar!/a.txt")
    assert archive.list("resources/app.asar!/dir") == ["resources/app.asar!/dir/b.txt"]
    overlay = OverlayFS([archive, disk])
    assert overlay.read("resources/app.asar!/dir/b.txt") == b"world"
    assert overlay.exists("resources/app.asar")
    assert "resources/app.asar" in overlay.list("resources")
    assert "resources/app.asar!" in overlay.list("resources")
    assert "resources/app.asar!/a.txt" in overlay.list("resources/app.asar!")


# @lat: [[source-tests#Repo map adapters#Asar header validation]]
def test_asar_header_rejects_garbage():
    with pytest.raises(AsarError):
        asar_module.read_header(b"not an asar at all")
    blob = bytearray(build_asar({"a.txt": b"x"}))
    blob[0] = 9  # break the magic
    with pytest.raises(AsarError):
        asar_module.read_header(bytes(blob))


# @lat: [[source-tests#Repo map adapters#Asar path traversal rejection]]
def test_asar_rejects_traversal_paths():
    evil = {"files": {"..": {"files": {"evil.js": {"size": 1, "offset": "0"}}},
                      "/abs": {"size": 1, "offset": "1"},
                      "ok.txt": {"size": 0, "offset": "2"}}}
    packed, unpacked, limitations = asar_module.read_directory(evil)
    assert set(packed) == {"ok.txt"}
    assert unpacked == set()
    assert any("traversal rejected" in note for note in limitations)


# @lat: [[source-tests#Repo map adapters#Asar caps]]
def test_asar_caps():
    files = {f"f{i}.txt": b"x" for i in range(10)}
    header, data_base, packed, unpacked, limitations = load_asar(
        build_asar(files), max_entries=5)
    assert len(packed) <= 5
    assert any("entry cap" in note for note in limitations)
    _, _, packed, _, limitations = load_asar(
        build_asar({"big.bin": b"y" * 100}), max_bytes=50)
    assert packed == {} or any("cap" in note for note in limitations)


# @lat: [[source-tests#Repo map adapters#Asar generation]]
def test_asar_generation(tmp_path):
    make_electron_tree(tmp_path, electron_files())
    bundle = RepoMap().generate(tmp_path)
    files = bundle["files"]
    # virtual paths exist, container and binaries skipped
    assert "resources/app.asar!/main.js" in files
    assert "resources/app.asar!/lib/util.js" in files
    assert files["resources/app.asar!/main.js"]["lang"] == "js"
    assert files["resources/app.asar!/index.html"]["lang"] == "html"
    assert files["resources/app.asar!/styles.css"]["lang"] == "css"
    container = [s for s in bundle["coverage"]["skipped"]
                 if s["path"] == "resources/app.asar"]
    assert container and "archive container" in container[0]["reason"]
    addon = [s for s in bundle["coverage"]["skipped"]
             if s["path"] == "resources/app.asar!/native/addon.node"]
    assert addon and addon[0]["reason"].startswith("binary:")
    assert any(note["archive"] == "resources/app.asar"
               for note in bundle["coverage"]["archives"])


# @lat: [[source-tests#Repo map adapters#Asar resolution and entrypoints]]
def test_asar_resolution_and_entrypoints(tmp_path):
    tree = electron_files()
    tree["lib/native.js"] = b"module.exports = {};\n"
    unpacked = {"lib/native.js": b"module.exports = {};\n"}
    make_electron_tree(tmp_path, tree, unpacked)
    bundle = RepoMap().generate(tmp_path)
    imports = {i["specifier"]: i
               for i in bundle["files"]["resources/app.asar!/main.js"]["imports"]}
    assert imports["./lib/util"]["resolved"] == "resources/app.asar!/lib/util.js"
    assert imports["./lib/util"]["reason"] == "relative"
    # unpacked overlay: the member is not packed, resolution falls to disk
    assert imports["./lib/native"]["resolved"] == "resources/app.asar.unpacked/lib/native.js"
    assert imports["./lib/native"]["reason"] == "unpacked"
    # node_modules stays external
    assert imports["electron"]["external"] is True
    assert imports["electron"]["reason"] == "package"
    # package.json main and preload become explicit entrypoints
    entry_paths = {e["path"]: e["reason"] for e in bundle["entrypoints"]}
    assert entry_paths.get("resources/app.asar!/main.js") == "package.json:main"
    assert entry_paths.get("resources/app.asar!/preload.js") == "package.json:preload"
    targets = {t["platform"]: t for t in bundle["targets"]}
    assert "windows-app" in targets
    assert any("app.asar" in e for e in targets["windows-app"]["evidence"])


# @lat: [[source-tests#Repo map adapters#Asar applicability]]
def test_asar_applicability(tmp_path):
    # asar with no JS is partial
    make_electron_tree(tmp_path, {
        "package.json": json.dumps({"main": "main.js"}).encode(),
        "assets/img.png": b"\x89PNG",
    })
    bundle = RepoMap().generate(tmp_path)
    targets = {t["platform"]: t for t in bundle["targets"]}
    assert targets["windows-app"]["applicability"] == "partial"

    # a PE with no asar and no source is not_applicable
    binary_root = tmp_path / "binary-only"
    binary_root.mkdir()
    (binary_root / "App.exe").write_bytes(b"MZ\x90\x00stub")
    (binary_root / "notes.txt").write_text("readme\n")
    bundle = RepoMap().generate(binary_root)
    targets = {t["platform"]: t for t in bundle["targets"]}
    assert targets["windows-app"]["applicability"] == "not_applicable"
    assert "binary-only" in targets["windows-app"]["applicability_reason"]
