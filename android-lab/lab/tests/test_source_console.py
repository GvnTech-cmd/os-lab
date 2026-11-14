"""Source action previews, API contracts and lifecycle boundary regressions."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
import web_ui
import oslab
import source_api
import source_control
import source_jobs
from source_artifacts import ArtifactError


@pytest.fixture(scope="module")
def console(tmp_path_factory):
    storage = tmp_path_factory.mktemp("source-console") / "state"
    script = Path(web_ui.REPO_ROOT) / "source-lab/engine/tests/fixture_workspace.py"
    result = subprocess.run([sys.executable, str(script), str(storage)], input=secrets.token_hex(32),
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("SOURCE_LAB_STORAGE", str(storage))
        patch.setenv("SOURCE_LAB_RESOURCES", str(storage / "resources"))
        patch.delenv("IQ_SESSION_HMAC_KEY", raising=False)
        patch.delenv("IQ_SESSION_HMAC_KEY_FILE", raising=False)
        patch.setattr(web_ui, "JOBS", oslab.JobService(web_ui.REPO_ROOT))
        patch.setattr(web_ui, "SIGNER", oslab.PlanSigner())
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_ui.LabHttpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{server.server_port}", storage
        for job in web_ui.JOBS.list():
            if job["state"] == "running":
                web_ui.JOBS.cancel(job["id"])
        server.shutdown()
        server.server_close()
        thread.join(2)


def call(console, route, data=None, method=None, headers=None):
    request = urllib.request.Request(console[0] + route, data=json.dumps(data).encode() if data is not None else None,
                                     method=method, headers=headers if headers is not None else {"X-OSLab": "1"})
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    if "json" in response.headers.get("Content-Type", ""):
        body = json.loads(body)
    return response.status, body


def wait_job(job_id):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        job = web_ui.JOBS.get(job_id)
        if job.finished_at is not None and job.proc is None:
            return job
        time.sleep(.03)
    pytest.fail("Source job did not finish")


def confirmed(console, route, options):
    status, preview = call(console, route, {"options": options, "preview": True})
    assert status == 200, preview
    status, result = call(console, route, {"options": options, "token": preview["token"]})
    assert status == 202, result
    return wait_job(result["job"]["id"])


def test_retained_read_routes_and_absent_snapshots(console):
    for route in ("detection", "analyzer", "analyzer/merged", "sources", "spotlight?q=sample",
                  "deep-analysis", "deep-analysis?repo=local/sample", "deep-analysis/merge", "pipeline", "settings/runtime"):
        status, result = call(console, "/api/source/" + route)
        assert status == 200, (route, result)
    assert call(console, "/api/source/brain")[0] == 404
    brain = console[1] / "brain-data"
    brain.mkdir(exist_ok=True)
    (brain / "manifest.json").write_text(json.dumps({"tabs": [{"id": "test", "label": "Owned fixture", "file": "fixture.json"}]}))
    (brain / "fixture.json").write_text('{"nodes":[]}')
    assert call(console, "/api/source/brain")[1]["data"]["tabs"][0]["graph"] == "/api/source/brain/files/fixture.json"
    assert call(console, "/api/source/brain/files/fixture.json")[1] == {"nodes": []}
    assert call(console, "/api/source/pipeline")[1]["source"] == "bundled-reference"
    assert call(console, "/api/source")[0] == 404
    assert call(console, "/api/source/skills")[0] == 404


def test_catalogs_source_files_and_exports(console):
    folder = console[1] / "resources/sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "browser-extensions-merged.csv").write_text('extension_name,description\nOwned,"contains, comma"\n')
    status, result = call(console, "/api/source/sources")
    assert status == 200 and result["mergedExtensions"][0]["description"] == "contains, comma"
    assert call(console, "/api/source/sources?download=browser-extensions-merged.csv")[0] == 200
    assert call(console, "/api/source/sources?download=../../private")[0] == 400
    assert call(console, "/api/source/analyzer/merged?export=csv")[0] == 200
    assert call(console, "/api/source/deep-analysis?repo=local/sample&file=manifest.json")[0] == 200
    assert call(console, "/api/source/deep-analysis?repo=local/sample&file=../private")[0] in (400, 403)
    assert call(console, "/api/source/deep-analysis?repo=local/sample&file=.env")[0] == 403


def test_exact_preview_and_real_detection_job(console):
    route = "/api/source/detection"
    options = {"target": "targets/sample", "platform": "browser-extension"}
    assert call(console, route, {"options": options})[0] == 409
    status, preview = call(console, route, {"options": options, "preview": True})
    assert status == 200 and preview["plan"]["privileged"] is False
    assert "--platform" in preview["plan"]["engineArgs"]
    changed = {**options, "platform": "auto"}
    assert call(console, route, {"options": changed, "token": preview["token"]})[0] == 409
    status, result = call(console, route, {"options": options, "token": preview["token"]})
    assert status == 202
    job = wait_job(result["job"]["id"])
    assert job.state == "succeeded" and job.exit_code == 0
    assert job.lines and (console[1] / "analysis/local__sample/analysis-v2.json").is_file()
    assert call(console, route)[1]["run"]["id"] == job.id
    assert call(console, "/api/jobs/" + job.id)[1]["logs"]


@pytest.mark.parametrize("route,options", [
    ("detection", {"target": "../../outside"}),
    ("detection", {"target": "targets/sample", "platform": []}),
    ("detection", {"target": "targets/sample", "output": "/tmp/out"}),
    ("detection", {"target": "targets/sample", "runCanary": "true"}),
    ("analyzer", {"sourceFile": "../../private.csv"}),
    ("analyzer", {"repos": ["owner/repo;whoami"]}),
    ("analyzer", {"repos": ["owner/repo"], "workers": True}),
    ("analyzer", {"repos": ["owner/repo"], "token": "never-accept-a-client-secret"}),
    ("deep-analysis", {"repos": ["owner/repo"], "workspace": "../../outside"}),
    ("deep-analysis/merge", {"slugs": ["../../outside"]}),
    ("deep-analysis/merge", {"slugs": ["local__sample"], "allowClone": "yes"}),
    ("settings/runtime", {"action": "set-canary", "testUrl": "https://user:secret@example.test"}),
    ("settings/runtime", {"action": "set-canary", "testUrl": "https://example.test?token=private"}),
])
def test_hostile_options_refused(console, route, options):
    assert call(console, "/api/source/" + route, {"options": options, "preview": True})[0] in (400, 409)


def test_mutation_guards_and_delete_contract(console):
    assert call(console, "/api/source/detection", {}, headers={})[0] == 403
    assert call(console, "/api/source/detection", {}, headers={"X-OSLab": "1", "Host": "other.invalid"})[0] == 403
    assert call(console, "/api/source/detection", {}, method="DELETE", headers={})[0] == 403
    assert call(console, "/api/source/detection", {}, method="DELETE")[0] == 404
    assert call(console, "/api/source/analyzer", {}, method="DELETE")[0] == 404
    assert call(console, "/api/source/detection?platform=auto", {})[0] == 400
    assert call(console, "/api/source/detection?target=x&target=y")[0] == 400
    assert call(console, "/api/source/brain/files/%2e%2e/private.json")[0] == 400


def test_merge_background_plan_and_build(console):
    options = {"slugs": ["local__sample"], "allowClone": False, "name": "Console owned fixture", "plan": True}
    plan_job = confirmed(console, "/api/source/deep-analysis/merge", options)
    assert plan_job.state == "succeeded"
    result = confirmed(console, "/api/source/deep-analysis/merge", {**options, "plan": False})
    assert result.state == "succeeded"
    assert call(console, "/api/source/deep-analysis/merge?download=console_owned_fixture")[0] == 200


def test_runtime_settings_jobs_never_return_key(console, monkeypatch):
    route = "/api/source/settings/runtime"
    job = confirmed(console, route, {"action": "generate-key"})
    assert job.state == "succeeded", job.lines
    key_file = console[1] / "control/session-hmac.key"
    original = key_file.read_text().strip()
    assert len(original) >= 32
    if os.name == "posix":
        assert key_file.stat().st_mode & 0o777 == 0o600
    status, response = call(console, route)
    assert status == 200 and response["key"]["configured"]
    assert original not in json.dumps(response)
    assert call(console, route, {"options": {"action": "generate-key"}, "preview": True})[0] == 409
    job = confirmed(console, route, {"action": "generate-key", "rotate": True})
    assert job.state == "succeeded" and original != key_file.read_text().strip()
    job = confirmed(console, route, {"action": "set-canary", "testUrl": "https://example.test/owned"})
    assert job.state == "succeeded"
    assert call(console, route)[1]["canary"]["testUrl"] == "https://example.test/owned"
    monkeypatch.setenv("IQ_SESSION_HMAC_KEY", "owned-test-value-" * 4)
    assert call(console, route, {"options": {"action": "generate-key", "rotate": True}, "preview": True})[0] == 409
    assert "owned-test-value-" not in json.dumps(call(console, route)[1])


def test_symlink_input_and_nested_output_refused(console):
    if os.name != "posix":
        pytest.skip("requires POSIX symlink permission")
    link = console[1] / "targets/sample/redirect"
    link.symlink_to("/tmp", target_is_directory=True)
    try:
        status, _ = call(console, "/api/source/detection", {"preview": True, "options": {"target": "targets/sample"}})
        assert status == 400
    finally:
        link.unlink()
    link = console[1] / "analysis/local__sample/summary.md"
    original = link.read_bytes()
    link.unlink()
    link.symlink_to("/tmp/private-summary")
    try:
        assert call(console, "/api/source/detection", {"preview": True, "options": {"target": "targets/sample"}})[0] == 400
    finally:
        link.unlink()
        link.write_bytes(original)


def test_credentials_are_redacted_from_artifacts_and_logs(console, monkeypatch):
    secret = "fixture-credential-" + secrets.token_hex(16)
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    file = console[1] / "brain-data/credential.json"
    file.parent.mkdir(exist_ok=True)
    file.write_text(json.dumps({"message": secret, "api_key": "private-field", "url": "https://person:private@example.test/"}))
    status, result = call(console, "/api/source/brain/files/credential.json")
    assert status == 200
    assert secret not in json.dumps(result) and "private-field" not in json.dumps(result)
    assert "person:private" not in json.dumps(result)
    plan = {"lab": "source", "action": "doctor", "program": sys.executable,
            "args": ["-c", "import os; print(os.environ['GITHUB_TOKEN'])"],
            "display": "owned log fixture", "runnable": True, "timeoutSec": 5}
    job = web_ui.JOBS.start(plan)
    job = wait_job(job.id)
    assert job.state == "succeeded" and secret not in str(job.lines)
    assert secret not in (console[1] / "control/jobs.json").read_text()


def test_cross_service_conflict_cancellation_and_restart(console):
    plan = {"lab": "source", "action": "detect", "program": sys.executable,
            "args": ["-c", "import time; print('started',flush=True); time.sleep(30)"],
            "display": "owned cancellation fixture", "runnable": True, "timeoutSec": 10}
    job = web_ui.JOBS.start(plan)
    second = oslab.JobService(web_ui.REPO_ROOT)
    with pytest.raises((ArtifactError, oslab.PlanError)):
        second.start(plan)
    assert call(console, "/api/source/detection", {"jobId": job.id}, method="DELETE")[0] == 200
    assert wait_job(job.id).state == "cancelled"
    # Persist a dead console's unfinished record; a new service must never call it successful.
    rows = json.loads((console[1] / "control/jobs.json").read_text())
    rows[-1]["state"] = "running"
    source_jobs.atomic(web_ui.REPO_ROOT, "control/jobs.json", json.dumps(rows).encode())
    recovered = oslab.JobService(web_ui.REPO_ROOT)
    assert recovered.get(rows[-1]["id"]).state == "interrupted"
    assert recovered.get(rows[-1]["id"]).exit_code != 0


def test_timeout_escalates_to_descendants(console):
    if os.name != "posix":
        pytest.skip("POSIX process group assertion")
    script = "import signal,subprocess,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); print('ready',flush=True); time.sleep(30)"
    plan = {"lab": "source", "action": "detect", "program": sys.executable,
            "args": ["-c", script], "display": "owned timeout fixture", "runnable": True, "timeoutSec": .3}
    job = web_ui.JOBS.start(plan)
    assert wait_job(job.id).state == "timed-out"
    assert job.exit_code != 0


def test_both_crawler_post_adapters_offline(console):
    folder = console[1] / "resources/sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "owned-list.txt").write_text(str(console[1] / "targets/sample") + "\n")
    options = {"sourceFile": "owned-list.txt", "workers": 1, "depth": 1, "noAst": True, "noMetadata": True, "keepWorkspace": True}
    for route in ("/api/source/analyzer", "/api/source/deep-analysis"):
        job = confirmed(console, route, options)
        assert job.state == "succeeded", job.lines


def test_preview_bound_to_storage_configuration(console, monkeypatch):
    options = {"target": "targets/sample"}
    route = "/api/source/detection"
    status, preview = call(console, route, {"preview": True, "options": options})
    assert status == 200
    # Even an operator root change invalidates an earlier exact-command preview.
    monkeypatch.setenv("SOURCE_LAB_PYTHON", "/different/python")
    assert call(console, route, {"options": options, "token": preview["token"]})[0] == 409


def test_runtime_ambiguous_keys_are_unavailable(console, monkeypatch):
    key = console[1] / "environment-fixture.key"
    key.write_text("different-fixture-key-" * 4)
    monkeypatch.setenv("IQ_SESSION_HMAC_KEY", "owned-fixture-key-" * 4)
    monkeypatch.setenv("IQ_SESSION_HMAC_KEY_FILE", str(key))
    response = call(console, "/api/source/settings/runtime")[1]
    assert not response["key"]["configured"]
    assert response["key"]["problem"]


def test_private_zip_contents_are_refused(console, monkeypatch):
    import zipfile
    monkeypatch.setenv("GITHUB_TOKEN", "owned-private-fixture-value-" * 3)
    target = console[1] / "merged/private_fixture.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(".env", "fixture-only")
    assert call(console, "/api/source/deep-analysis/merge?download=private_fixture")[0] == 403
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("script.js", os.environ["GITHUB_TOKEN"])
    assert call(console, "/api/source/deep-analysis/merge?download=private_fixture")[0] == 403


def test_crawler_and_merge_cancel_handlers_scope_job_ids(console):
    for route in ("analyzer", "deep-analysis", "deep-analysis/merge"):
        assert call(console, "/api/source/" + route, {"action": "cancel", "jobId": "missing"})[0] == 404
    assert call(console, "/api/source/deep-analysis/merge?plan=1&slugs=local__sample")[0] == 200


def test_oversized_logs_do_not_leak_split_secrets(console, monkeypatch):
    credential = "owned-split-credential-" + secrets.token_hex(16)
    monkeypatch.setenv("GITHUB_TOKEN", credential)
    code = "import os; print('x'*8188+os.environ['GITHUB_TOKEN']); print('done')"
    plan = {"lab": "source", "action": "doctor", "program": sys.executable, "args": ["-c", code],
            "display": "owned oversized log fixture", "runnable": True, "timeoutSec": 5}
    job = wait_job(web_ui.JOBS.start(plan).id)
    assert job.state == "succeeded" and job.truncated
    assert job.lines == ["[oversized log line omitted]", "done"]


def test_engine_tree_stops_after_console_crash(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux process state probe")
    import shutil
    checkout = tmp_path / "checkout"
    (checkout / "console").mkdir(parents=True)
    (checkout / "source-lab").mkdir()
    for module in (Path(web_ui.REPO_ROOT) / "console").glob("*.py"):
        shutil.copy2(module, checkout / "console" / module.name)
    marker = tmp_path / "engine.pid"
    (checkout / "source-lab/run.py").write_text(
        "import os,time\nfrom pathlib import Path\nPath(" + repr(str(marker)) + ").write_text(str(os.getpid()))\ntime.sleep(30)\n")
    monkeypatch.setenv("SOURCE_LAB_STORAGE", str(tmp_path / "state"))
    code = "import sys,time;sys.path.insert(0,sys.argv[1]+'/console');import source_control,oslab;oslab.JobService(sys.argv[1]).start(source_control.build_plan(sys.argv[1],{'lab':'source','action':'doctor'}));time.sleep(30)"
    parent = subprocess.Popen([sys.executable, "-c", code, str(checkout)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.03)
        assert marker.exists()
        pid = int(marker.read_text())
        parent.kill()
        parent.wait(timeout=5)
        while time.monotonic() < deadline:
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], text=True, capture_output=True).stdout.strip()
            if not state or state.startswith("Z"):
                break
            time.sleep(.03)
        assert not state or state.startswith("Z"), "Engine survived the console process"
        record = oslab.JobService(str(checkout)).list()[0]
        assert record["state"] == "interrupted" and record["exitCode"] is None
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)


def test_runtime_verification_and_default_canary(console):
    route = "/api/source/settings/runtime"
    # Regenerate the owned fixture with the console-managed key, never printed.
    if not (console[1] / "control/session-hmac.key").exists():
        assert confirmed(console, route, {"action": "generate-key"}).state == "succeeded"
    key = (console[1] / "control/session-hmac.key").read_text().strip()
    script = Path(web_ui.REPO_ROOT) / "source-lab/engine/tests/fixture_workspace.py"
    fixture = console[1] / "verification-fixture"
    result = subprocess.run([sys.executable, str(script), str(fixture)], input=key.encode().hex(),
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0
    import shutil
    original = next((fixture / "analysis").glob("*/runtime-sessions/ses_*"))
    destination = console[1] / "analysis/local__verification/runtime-sessions" / original.name
    shutil.copytree(original, destination)
    options = {"action": "verify-session", "slug": "local__verification", "session": original.name}
    job = confirmed(console, route, options)
    assert job.state == "succeeded", job.lines
    (destination / "manifest.sig").unlink()
    job = confirmed(console, route, options)
    assert job.state == "failed"
    assert key not in json.dumps(call(console, route)[1])
    plan = source_control.build_plan(web_ui.REPO_ROOT, {"lab": "source", "action": "detect", "options": {
        "target": source_control.candidates(web_ui.REPO_ROOT)[0]["key"], "runCanary": True}})
    assert call(console, route)[1]["canary"]["testUrl"] in plan["engineArgs"]


def test_overview_pinned_crawler_formats(console):
    path = console[1] / "analysis/owned__matrix"
    path.mkdir()
    (path / "manifest-analysis.json").write_text(json.dumps({"name": "Owned fixture", "manifest_version": 2,
        "manifest_keys": ["background", "browser_action", "permissions"], "background": "scripts: background.js",
        "permissions": ["tabs", "tabs", "nativeMessaging"], "heuristic_score": 3}))
    (path / "dependencies.json").write_text(json.dumps({"package.json": {"deps": {
        "dependencies": {"react": "1"}, "devDependencies": {"react": "1", "vite": "1"}}}}))
    status, data = call(console, "/api/source/analyzer/merged")
    assert status == 200
    prop = next(row for row in data["propsMatrix"] if row["name"] == "browser_action")
    assert prop["mv2"] == 1 and prop["mv3"] == 0 and prop["migrationNote"]
    assert "owned__matrix" in data["swGroups"]["persistentScript"]
    dep = next(row for row in data["depsMatrix"] if row["name"] == "react")
    assert dep["count"] == 1 and dep["category"] == "UI / Framework"
    assert set(dep["sections"]) == {"dependencies", "devDependencies"}
    perm = next(row for row in data["permsMatrix"] if row["name"] == "nativeMessaging")
    assert perm["risk"] == "high"
    status, csv = call(console, "/api/source/analyzer/merged?export=csv")
    assert status == 200 and b"migration" in csv and b"browser_action" in csv
    assert call(console, "/api/source/analyzer/merged?export=json")[0] == 200


def test_crawler_lists_are_private_bounded_and_link_safe(console):
    folder = console[1] / "resources/sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "owned.txt").write_text("owned/sample\n")
    (folder / "not-a-list.json").write_text("{}")
    if os.name == "posix":
        (folder / "linked.txt").symlink_to(folder / "owned.txt")
    status, result = call(console, "/api/source/analyzer")
    assert status == 200
    files = {item["name"] for item in result["sourceFiles"]}
    assert "owned.txt" in files and "not-a-list.json" not in files and "linked.txt" not in files
    assert result["sourceFilesTruncated"] is False


def test_crawler_tuning_and_catalog_join(console):
    options = {"repos": ["owned/sample"], "retries": 2, "cloneTimeout": 10, "apiMaxWait": 1,
               "maxTreeEntries": 10, "maxAstFiles": 2, "noMap": True}
    plan = source_control.build_plan(web_ui.REPO_ROOT, {"lab": "source", "action": "crawl", "options": options})
    assert "--retries" in plan["engineArgs"] and "--no-map" in plan["engineArgs"]
    for field, value in [("retries", 6), ("cloneTimeout", 601), ("mapDetail", "shell"), ("maxAstFiles", -1)]:
        with pytest.raises(ArtifactError):
            source_control.build_plan(web_ui.REPO_ROOT, {"lab": "source", "action": "crawl", "options": {**options, field: value}})
    source = console[1] / "resources/sources"
    source.mkdir(parents=True, exist_ok=True)
    for name, content in [("browser-extensions.csv", "Category,Extension,Repo Link,Description\n"),
                          ("browser-extension-repos.csv", "repo_url,repo_name,category\nhttps://github.com/owned/sample,sample,Testing\n")]:
        (source / name).write_text(content)
    before = {p.name: p.read_bytes() for p in source.glob("*.csv")}
    # Any preexisting hostile list link must be refused before a worker starts.
    link = source / "linked.txt"
    if link.is_symlink():
        assert call(console, "/api/source/sources", {"options": {}, "preview": True})[0] == 400
        link.unlink()
    job = confirmed(console, "/api/source/sources", {})
    assert job.state == "succeeded", job.lines
    assert before == {p.name: p.read_bytes() for p in source.glob("*.csv")}
    assert call(console, "/api/source/sources?origin=generated")[1]["stats"]["totalMerged"] == 1
    assert call(console, "/api/source/sources?origin=generated&download=browser-extensions-merged.csv")[0] == 200


def test_source_list_entries_cannot_escape_workspace(console):
    sources = console[1] / "resources/sources"
    sources.mkdir(parents=True, exist_ok=True)
    file = sources / "guarded.txt"
    for value in ("/etc", "../../outside", "https://user:private@github.com/owned/sample", "https://github.com/owned/sample?token=private"):
        file.write_text(value + "\n")
        assert call(console, "/api/source/analyzer", {"options": {"sourceFile": "guarded.txt"}, "preview": True})[0] == 400
    file.write_text("https://github.com/owned/sample.git\n")
    status, preview = call(console, "/api/source/analyzer", {"options": {"sourceFile": "guarded.txt"}, "preview": True})
    assert status == 200 and "owned/sample" in preview["plan"]["engineArgs"]


def test_deep_ast_and_selected_private_crawl(console):
    base = console[1] / "analysis/local__sample"
    (base / "ast").mkdir(exist_ok=True)
    (base / "ast-index.json").write_text(json.dumps([{"path": "content.js", "file": "ast/content.js.json", "parser": "regex"}]))
    (base / "ast/content.js.json").write_text(json.dumps({"nodes": [{"name": "owned"}], "parser": "regex"}))
    status, data = call(console, "/api/source/deep-analysis?repo=local/sample&file=content.js&view=ast")
    assert status == 200 and data["ast"]["parser"] == "regex"
    assert call(console, "/api/source/deep-analysis?repo=local/sample&file=absent.js&view=ast")[0] == 404
    assert call(console, "/api/source/deep-analysis?repo=local/sample&view=ast")[0] == 400
    job = confirmed(console, "/api/source/deep-analysis", {"target": "targets/sample", "noMetadata": True, "noAst": True})
    assert job.state == "succeeded", job.lines
    assert call(console, "/api/source/deep-analysis", {"options": {"target": "../../outside"}, "preview": True})[0] == 400


def test_source_requires_supported_python(monkeypatch):
    monkeypatch.setattr(source_control, "readiness", lambda root: {"python": {"version": "3.10.9"}, "storage": {"writable": True}, "optional": {}})
    status = source_control.lab_status(web_ui.REPO_ROOT, "linux")
    assert status["state"] == "unavailable"
    assert not status["requirements"][0]["found"]


def test_pipeline_reference_and_snapshot_provenance(console):
    status, reference = call(console, "/api/source/pipeline")
    assert status == 200 and reference["source"] == "bundled-reference"
    assert reference["date"] == "2026-11-09" and len(reference["data"]["stages"]) == 12
    folder = console[1] / "snapshots"
    folder.mkdir(exist_ok=True)
    path = folder / "pipeline.json"
    try:
        path.write_text(json.dumps({"date": "2026-01-01", "revision": "owned", "stages": []}))
        result = call(console, "/api/source/pipeline")[1]
        assert result["source"] == "operator-snapshot" and result["date"] == "2026-01-01"
        path.write_text("[]")
        assert call(console, "/api/source/pipeline")[0] == 400
    finally:
        path.unlink()


def test_brain_manifest_guards_providers_and_duplicate_tabs(console):
    path = console[1] / "brain-data/manifest.json"
    original = path.read_bytes() if path.exists() else None
    path.parent.mkdir(exist_ok=True)
    tab = {"id": "owned", "label": "Owned", "file": "owned.json"}
    try:
        for manifest in ({"tabs": [tab, tab]}, {"tabs": [tab], "providers": {"source": "../control/runtime-settings.json"}},
                         {"tabs": [tab], "providers": {"source": "https://example.test/owned.json"}},
                         {"tabs": [tab], "providers": {"source": "source.js"}}):
            path.write_text(json.dumps(manifest))
            assert call(console, "/api/source/brain")[0] == 400
    finally:
        if original is None:
            path.unlink()
        else:
            path.write_bytes(original)
