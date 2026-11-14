"""Offline scenarios reusable by engine, console and future UI tests."""
import hashlib
import json
import secrets
import zipfile

import pytest

from fixture_workspace import build_workspace
from source_lab.contracts import validate
from source_lab.evidence.session import SessionBundleReader


# @lat: [[source-tests#Workspace fixtures#Offline integration workspace]]
def test_offline_integration_workspace(tmp_path):
    key = secrets.token_bytes(32)
    result = build_workspace(tmp_path / "workspace", key)
    root, output = result["root"], result["output"]
    assert not validate(json.loads((output / "analysis-v2.json").read_text()), "AnalysisV2")
    assert not validate(json.loads((output / "repo-map.json").read_text()), "RepoMapV1")
    reader = SessionBundleReader(result["session"], hmac_key=key)
    assert reader.verify_integrity()["signature_verified"]
    assert reader.get_metadata().collector.profile_mode == "synthetic"
    assert json.loads((root / "ui-fixture.json").read_text())["synthetic"]
    archives = list((root / "merged").glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        assert json.loads(archive.read("manifest.json"))["manifest_version"] == 3
    for name, expected in result["manifest"]["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    assert key not in b"".join(p.read_bytes() for p in root.rglob("*") if p.is_file())
    assert not list(root.rglob("*.db"))


# @lat: [[source-tests#Workspace fixtures#Existing workspace preserved]]
def test_existing_workspace_preserved(tmp_path):
    marker = tmp_path / "keep.txt"
    marker.write_text("operator data")
    with pytest.raises(FileExistsError):
        build_workspace(tmp_path, secrets.token_bytes(32))
    assert marker.read_text() == "operator data"
