"""Owned temporary artifacts exercise opt-in import, integrity and reversible writes."""
import json
import os
from pathlib import Path
import pytest
from source_lab import import_legacy as importer
from source_lab.evidence.schema import PlatformType, TargetIdentity
from source_lab.evidence.session import CollectorMetadata, SessionBundleWriter, SessionMetadata, SessionScope


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    source = tmp_path / "legacy"
    folder = source / "owned__sample"
    folder.mkdir(parents=True)
    (folder / "manifest-analysis.json").write_text('{"name":"Owned fixture"}')
    (folder / "ast").mkdir()
    (folder / "ast/owned.json").write_text('{"parser":"regex","nodes":[]}')
    storage = tmp_path / "state"
    monkeypatch.setenv("SOURCE_LAB_STORAGE", str(storage))
    return source, folder, storage


def signed_session(folder):
    path = folder / "runtime-sessions/ses_owned"
    meta = SessionMetadata(session_id="ses_owned", platform=PlatformType.BROWSER_EXTENSION,
        target=TargetIdentity(identifier="owned/sample"), collector=CollectorMetadata(engine="owned-fixture", profile_mode="synthetic"), scope=SessionScope())
    writer = SessionBundleWriter(path, meta)
    writer.append_event(0, "session_start", {"synthetic": True})
    writer.close()
    return path


def test_dry_run_excludes_binary_database_skill_and_key_inputs_without_writes(legacy):
    source, folder, storage = legacy
    for name in ("archive.zip", "target.apk", "private.key", "repos.db", ".env", "dataset.csv"):
        (folder / name).write_bytes(b"excluded")
    result = importer.plan(source, ["owned__sample"])
    assert result["count"] == 2 and len(result["excluded"]) == 6
    assert not storage.exists()


def test_copy_hashes_backup_and_rollback_preserve_originals(legacy):
    source, folder, storage = legacy
    target = storage / "analysis/owned__sample/manifest-analysis.json"
    target.parent.mkdir(parents=True)
    target.write_text("old operator output")
    original = (folder / "manifest-analysis.json").read_bytes()
    plan = importer.plan(source, ["owned__sample"])
    copied = importer.copy(plan, plan["fingerprint"])
    assert target.read_bytes() == original
    assert (folder / "manifest-analysis.json").read_bytes() == original
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    rollback = importer.rollback(copied["id"])
    assert rollback["restoreCount"] == 2
    importer.rollback(copied["id"], apply=True)
    assert target.read_text() == "old operator output"
    assert not (storage / "analysis/owned__sample/ast/owned.json").exists()


def test_changed_preview_is_refused_before_copy(legacy):
    source, folder, storage = legacy
    plan = importer.plan(source, ["owned__sample"])
    (folder / "manifest-analysis.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="changed after preview"):
        importer.copy(plan, plan["fingerprint"])
    assert not (storage / "analysis/owned__sample/manifest-analysis.json").exists()


def test_rollback_conflict_does_not_overwrite_newer_edits(legacy):
    source, folder, storage = legacy
    plan = importer.plan(source, ["owned__sample"])
    copied = importer.copy(plan, plan["fingerprint"])
    target = storage / "analysis/owned__sample/manifest-analysis.json"
    target.write_text("newer operator edit")
    with pytest.raises(ValueError, match="newer destination edit"):
        importer.rollback(copied["id"], apply=True)
    assert target.read_text() == "newer operator edit"


def test_imported_signed_session_verifies_and_tampering_fails(legacy):
    source, folder, storage = legacy
    session = signed_session(folder)
    plan = importer.plan(source, ["owned__sample"])
    assert plan["sessions"][0]["signature_verified"]
    copied = importer.copy(plan, plan["fingerprint"])
    from source_lab.evidence.session import SessionBundleReader
    assert SessionBundleReader(storage / "analysis/owned__sample/runtime-sessions/ses_owned").verify_integrity()["valid"]
    importer.rollback(copied["id"], apply=True)
    (session / "events.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="verification failed"):
        importer.plan(source, ["owned__sample"])


def test_private_session_members_are_held_out_as_a_whole(legacy):
    source, folder, storage = legacy
    session = signed_session(folder)
    (session / "browser.db").write_bytes(b"private browser state")
    plan = importer.plan(source, ["owned__sample"])
    assert not plan["sessions"] and any("whole bundle held out" in item for item in plan["excluded"])


def test_symlinks_and_credential_settings_are_rejected(legacy):
    source, folder, storage = legacy
    target = folder / "manifest-analysis.json"
    target.unlink()
    try:
        target.symlink_to(folder / "ast/owned.json")
    except OSError:
        pytest.skip("Symlink creation is not available on this host")
    with pytest.raises(ValueError, match="Linked"):
        importer.plan(source, ["owned__sample"])
    target.unlink()
    target.write_text("{}")
    settings = source / "runtime-settings.json"
    settings.write_text('{"testUrl":"https://user:private@example.test"}')
    with pytest.raises(ValueError):
        importer.plan(source, ["owned__sample"], settings)


def test_mid_copy_failure_restores_prior_files(legacy, monkeypatch):
    source, folder, storage = legacy
    plan = importer.plan(source, ["owned__sample"])
    original = importer.write
    count = 0
    def fail_once(relative, data):
        nonlocal count
        if relative.startswith("analysis/"):
            count += 1
            if count == 2:
                raise OSError("owned injected copy failure")
        return original(relative, data)
    monkeypatch.setattr(importer, "write", fail_once)
    with pytest.raises(OSError, match="injected"):
        importer.copy(plan, plan["fingerprint"])
    assert not list((storage / "analysis").rglob("*.json"))


def test_default_url_settings_are_imported_without_keys(legacy):
    source, folder, storage = legacy
    settings = source / "runtime-settings.json"
    settings.write_text('{"testUrl":"https://example.test/owned"}')
    result = importer.plan(source, ["owned__sample"], settings)
    copied = importer.copy(result, result["fingerprint"])
    assert json.loads((storage / "control/runtime-settings.json").read_text())["testUrl"].endswith("/owned")
    assert not list(storage.rglob("*.key"))
    importer.rollback(copied["id"], apply=True)
    assert not (storage / "control/runtime-settings.json").exists()


def test_import_conflicts_with_running_source_job(legacy):
    source, folder, storage = legacy
    result = importer.plan(source, ["owned__sample"])
    fd = importer.source_jobs.claim(str(importer.ROOT))
    try:
        with pytest.raises(ValueError, match="Another Source"):
            importer.copy(result, result["fingerprint"])
    finally:
        importer.source_jobs.release(fd)


def test_cli_is_dry_run_and_requires_explicit_attestation(legacy):
    import os
    import subprocess
    import sys
    source, folder, storage = legacy
    command = [sys.executable, str(importer.ROOT / "source-lab/run.py"), "import-legacy", "--source", str(source), "--slug", "owned__sample"]
    response = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert response.returncode == 0 and json.loads(response.stdout)["count"] == 2
    assert not storage.exists()
    response = subprocess.run([*command, "--copy"], capture_output=True, text=True, timeout=10)
    assert response.returncode != 0 and "--authorized" in response.stderr
