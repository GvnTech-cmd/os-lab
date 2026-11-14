"""Source Lab read-only API boundaries on the existing localhost console."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from web_ui import LabHttpHandler, REPO_ROOT
import source_artifacts


@pytest.fixture(scope="module")
def source_server(tmp_path_factory):
    storage = tmp_path_factory.mktemp("source-api") / "workspace"
    generator = Path(REPO_ROOT) / "source-lab/engine/tests/fixture_workspace.py"
    env = dict(os.environ)
    env.pop("IQ_SESSION_HMAC_KEY", None)
    env.pop("IQ_SESSION_HMAC_KEY_FILE", None)
    result = subprocess.run([sys.executable, str(generator), str(storage)], input=secrets.token_hex(32),
                            text=True, capture_output=True, timeout=30, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SOURCE_LAB_STORAGE", str(storage))
        server = ThreadingHTTPServer(("127.0.0.1", 0), LabHttpHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", storage
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


def get(server, endpoint, params=None, headers=None):
    url = server[0] + endpoint + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers=headers or {})
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


# @lat: [[source-tests#Artifact API#Evidence and session review]]
def test_evidence_and_session_review(source_server):
    status, headers, body = get(source_server, "/api/source/evidence")
    assert status == 200
    assert headers["Cache-Control"] == "no-store" and headers["X-Content-Type-Options"] == "nosniff"
    assert any(row["slug"] == "fixture__sample" for row in json.loads(body)["targets"])
    status, _, body = get(source_server, "/api/source/evidence", {"slug": "fixture__sample"})
    assert status == 200
    detail = json.loads(body)
    assert detail["hasV2Analysis"] and detail["coverage"] and detail["scorecard"]
    assert detail["sessions"][0]["collector"]["profile_mode"] == "synthetic"
    assert detail["sessions"][0]["integrity"] == "not-verified"
    status, _, body = get(source_server, "/api/source/evidence", {"slug": "fixture__sample", "session": "ses_fixture_synthetic"})
    assert status == 200 and json.loads(body)["integrity"] == "not-verified"
    assert len(json.loads(body)["events"]) == 2


# @lat: [[source-tests#Artifact API#Report allowlist]]
def test_report_allowlist(source_server):
    for filename in source_artifacts.REPORTS:
        status, headers, body = get(source_server, "/api/source/evidence/report", {"slug": "fixture__sample", "file": filename})
        assert status == 200 and body
        assert headers["Content-Disposition"] == f'attachment; filename="fixture__sample-{filename}"'
        assert headers["Cache-Control"] == "no-store"
    status, _, _ = get(source_server, "/api/source/evidence/report", {"slug": "fixture__sample", "file": "manifest.sig"})
    assert status == 400
    status, _, _ = get(source_server, "/api/source/evidence/report", {"slug": "fixture__sample", "file": "report.stix.json"})
    assert status == 400  # CLI-only STIX remains an explicit scope decision.


# @lat: [[source-tests#Artifact API#Host and parameter boundaries]]
def test_host_and_parameter_boundaries(source_server):
    assert get(source_server, "/api/source/evidence", headers={"Host": "outside.example"})[0] == 403
    for params in ({"slug": "../../etc"}, {"slug": "one__two/../three"},
                   {"slug": "fixture__sample", "session": "../ses_secret"},
                   {"session": "ses_fixture_synthetic"}, {"unexpected": "value"}):
        assert get(source_server, "/api/source/evidence", params)[0] == 400
    assert get(source_server, "/api/source/evidence?slug=one__two&slug=three__four")[0] == 400
    assert get(source_server, "/api/source/evidence", {"slug": "missing__target"})[0] == 404
    for name in ("skills", "repos", "openapi"):
        assert get(source_server, f"/api/source/{name}")[0] == 404


# @lat: [[source-tests#Artifact API#Symlinks and nonregular files refused]]
def test_symlink_and_fifo_boundaries(source_server):
    if os.name == "nt":
        pytest.skip("symlink/FIFO creation requires POSIX test permissions")
    storage = source_server[1]
    link = storage / "analysis/link__target"
    link.symlink_to(storage / "analysis/fixture__sample", target_is_directory=True)
    assert get(source_server, "/api/source/evidence", {"slug": "link__target"})[0] == 404
    target = storage / "analysis/link__file"
    target.mkdir()
    (target / "summary.md").symlink_to(storage / "analysis/fixture__sample/summary.md")
    assert get(source_server, "/api/source/evidence/report", {"slug": "link__file", "file": "summary.md"})[0] == 404
    fifo = storage / "analysis/fifo__target"
    fifo.mkdir()
    os.mkfifo(fifo / "summary.md")
    assert get(source_server, "/api/source/evidence/report", {"slug": "fifo__target", "file": "summary.md"})[0] == 404


# @lat: [[source-tests#Artifact API#Bounded and malformed artifacts]]
def test_bounded_and_malformed_artifacts(source_server):
    storage = source_server[1]
    large = storage / "analysis/large__target"
    large.mkdir()
    with (large / "findings.json").open("wb") as file:
        file.truncate(source_artifacts.MAX_JSON + 1)
    assert get(source_server, "/api/source/evidence", {"slug": "large__target"})[0] == 413
    with (large / "summary.md").open("wb") as file:
        file.truncate(source_artifacts.MAX_REPORT + 1)
    assert get(source_server, "/api/source/evidence/report", {"slug": "large__target", "file": "summary.md"})[0] == 413
    for index, content in enumerate(('not-json', '[1]', '[{"schema_version":9}]', '[{"schema_version":2,"confidence":NaN}]')):
        target = storage / f"analysis/invalid__{index}"
        target.mkdir()
        (target / "findings.json").write_text(content)
        assert get(source_server, "/api/source/evidence", {"slug": f"invalid__{index}"})[0] == 400


# @lat: [[source-tests#Artifact API#Event timeline truncation]]
def test_event_timeline_truncation(source_server):
    session = source_server[1] / "analysis/events__target/runtime-sessions/ses_limits"
    session.mkdir(parents=True)
    file = session / "events.jsonl"
    file.write_text(''.join(json.dumps({"seq": i, "type": "fixture"}) + '\n' for i in range(501)))
    status, _, body = get(source_server, "/api/source/evidence", {"slug": "events__target", "session": "ses_limits"})
    assert status == 200
    assert len(json.loads(body)["events"]) == 500 and json.loads(body)["truncated"]
    file.write_text('{}\n' * 500)
    assert not json.loads(get(source_server, "/api/source/evidence", {"slug": "events__target", "session": "ses_limits"})[2])["truncated"]


# @lat: [[source-tests#Artifact API#Aggregate response budget]]
def test_aggregate_budget(source_server, monkeypatch):
    target = source_server[1] / "analysis/budget__target"
    target.mkdir()
    (target / "analysis-v2.json").write_text(json.dumps({"schema_version": 2, "padding": "x" * 600}))
    (target / "findings.json").write_text('[]' + ' ' * 600)
    monkeypatch.setattr(source_artifacts, "MAX_TOTAL", 1000)
    assert get(source_server, "/api/source/evidence", {"slug": "budget__target"})[0] == 413


# @lat: [[source-tests#Artifact API#Directory listing cap]]
def test_directory_listing_cap(tmp_path, monkeypatch):
    for name in ("first__target", "second__target"):
        (tmp_path / "analysis" / name).mkdir(parents=True)
    monkeypatch.setenv("SOURCE_LAB_STORAGE", str(tmp_path))
    monkeypatch.setattr(source_artifacts, "MAX_TARGETS", 1)
    result = source_artifacts.SourceArtifacts(REPO_ROOT).evidence()
    assert len(result["targets"]) == 1 and result["truncated"]


def test_windows_reparse_points_are_redirects_even_when_directory_mode():
    from types import SimpleNamespace
    import stat
    from source_artifacts import redirected
    assert redirected(Path("unused"), SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400))
    assert not redirected(Path("unused"), SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0))
