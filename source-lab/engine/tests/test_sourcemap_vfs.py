"""Tests for the shared filesystem contract.

``RepoMap`` and ``Resolver`` take a ``FileSystem`` — never a ``Path`` — so
archives never need disk extraction.  These tests pin the contract:
``list``/``read``/``exists``/``stat``, sorted deterministic listings, and
path-traversal rejection on every implementation.
"""

import pytest

from source_lab.sourcemap.vfs import ArchiveFS, DiskFS, FileSystem, OverlayFS


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    (tmp_path / "src" / "deep" / "b.py").write_text("y = 2\n")
    (tmp_path / "README.md").write_text("readme\n")
    return tmp_path


# @lat: [[source-tests#Repo map adapters#VFS disk contract]]
def test_vfs_disk_contract(tree):
    fs = DiskFS(tree)
    assert fs.label == tree.name
    assert fs.list("") == ["README.md", "src"]
    assert fs.list("src") == ["src/a.py", "src/deep"]
    assert fs.read("src/a.py") == b"x = 1\n"
    assert fs.exists("src/deep/b.py") and not fs.exists("src/none.py")
    assert fs.is_dir("src/deep") and not fs.is_dir("src/a.py")
    assert fs.stat("src/a.py") == 6


# @lat: [[source-tests#Repo map adapters#VFS traversal rejection]]
def test_vfs_traversal_rejection(tree):
    fs = DiskFS(tree)
    for evil in ("../outside", "src/../../etc/passwd", "/etc/passwd", "a\\..\\..\\x"):
        with pytest.raises(ValueError):
            fs.normalize(evil)
    assert fs.exists("../" + tree.name + "/README.md") is False
    # the contract is shared: every implementation normalizes identically
    assert FileSystem.normalize("src/./deep/") == "src/deep"


# @lat: [[source-tests#Repo map adapters#VFS archive and overlay]]
def test_vfs_archive_and_overlay(tree):
    disk = DiskFS(tree)
    members = {"v.py": (0, 5), "dir/w.py": (5, 5)}
    data = b"AAAAABBBBB"
    archive = ArchiveFS(disk, "src/archive.asar", data, members, 0, unpacked={"u.py"})
    # lazy slices from the content region, nothing extracted to disk
    assert archive.read("src/archive.asar!/v.py") == b"AAAAA"
    assert archive.read("src/archive.asar!/dir/w.py") == b"BBBBB"
    assert archive.stat("src/archive.asar!/v.py") == 5
    assert archive.exists("src/archive.asar!/dir/w.py")
    assert not archive.exists("src/archive.asar!/u.py")  # unpacked: not served
    assert archive.list("src/archive.asar!/dir") == ["src/archive.asar!/dir/w.py"]
    # pass-through for real paths
    assert archive.read("README.md") == b"readme\n"

    overlay = OverlayFS([archive, disk])
    assert overlay.exists("src/archive.asar!/v.py")
    assert overlay.exists("src/a.py")
    assert overlay.list("src") == ["src/a.py", "src/archive.asar!", "src/deep"]
    with pytest.raises(FileNotFoundError):
        overlay.read("src/none.py")
