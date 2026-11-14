"""Console contract: typed scan, plan and clean jobs with polling and cancel.

The engine behaviour is covered by ``cleanup-lab/engine/tests/test_scan.py`` and
``test_clean.py``; these tests hold the HTTP-shaped layer to the same rules: no
free-form paths, catalog ids only, a plan that is single-use and expires when an
item changes, and a job that always answers.
"""
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "console"))
sys.path.insert(0, os.path.join(REPO_ROOT, "cleanup-lab", "engine"))

import cleanup_api  # noqa: E402
from cleanup_lab import catalog as catalog_module  # noqa: E402
from cleanup_lab import paths as paths_module  # noqa: E402


def wait_for(job, state=None, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if state is None and job.state != "running":
            return job
        if state is not None and job.state == state:
            return job
        time.sleep(0.01)
    raise AssertionError("job stayed {0!r}".format(job.state))


@pytest.fixture(autouse=True)
def clean_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("OSLAB_CLEANUP_STATE", str(tmp_path / "state"))
    def drain():
        for job in list(cleanup_api.JOBS.jobs.values()):
            job.cancel.set()
        deadline = time.time() + 10
        while time.time() < deadline:
            if not any(job.state == "running" for job in cleanup_api.JOBS.jobs.values()):
                return
            time.sleep(0.01)

    drain()
    cleanup_api.JOBS.jobs.clear()
    cleanup_api.PLANS.plans.clear()
    yield
    drain()
    cleanup_api.JOBS.jobs.clear()
    cleanup_api.PLANS.plans.clear()


def catalog_cache_target(tmp_path, monkeypatch):
    """Point HOME at the temp tree and return the catalog's user-cache folder."""
    platform = paths_module.platform_id()
    if platform not in ("macos", "linux"):
        pytest.skip("no catalog path for this test platform")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    if platform == "linux":
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / ".cache"))
    entry = next(
        item for item in catalog_module.load(REPO_ROOT) if item["id"] == "system.user-caches"
    )
    target = catalog_module.resolve(entry, platform)[0]["path"]
    os.makedirs(target, exist_ok=True)
    return target


def test_a_scan_job_measures_the_catalog_paths(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    with open(os.path.join(target, "one.bin"), "wb") as handle:
        handle.write(b"x" * 64)
    with open(os.path.join(target, "two.bin"), "wb") as handle:
        handle.write(b"y" * 36)

    api = cleanup_api.CleanupAPI(REPO_ROOT)
    job = api.post(
        "/api/cleanup/scan", {"entryIds": ["system.user-caches"], "workers": 1}
    )
    wait_for(job, "done")

    assert job.kind == "scan"
    assert job.request == {"entryIds": ["system.user-caches"], "workers": 1}
    assert job.error is None
    assert job.result["cancelled"] is False
    assert job.result["totals"]["sizeBytes"] == 100
    assert job.result["progress"]["phase"] == "done"
    path_report = job.result["entries"][0]["paths"][0]
    assert path_report["measured"] is True
    assert path_report["sizeBytes"] == 100
    assert job.finishedAt is not None

    polled = api.get("/api/cleanup/jobs/" + job.id, {})
    assert polled["id"] == job.id
    assert polled["state"] == "done"
    listed = api.get("/api/cleanup/jobs", {})
    assert [row["id"] for row in listed["jobs"]] == [job.id]


def test_the_scan_request_accepts_catalog_ids_only():
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    refused = [
        {"path": "/tmp"},
        {"entryIds": ["system.user-caches"], "root": "/tmp"},
        {"entryIds": []},
        {"entryIds": "system.user-caches"},
        {"entryIds": ["nope.entry"]},
        {"entryIds": ["system.user-caches", "system.user-caches"]},
        {"entryIds": [1]},
        {"workers": 0},
        {"workers": cleanup_api._module(REPO_ROOT, "scan").MAX_WORKERS + 1},
        {"workers": True},
        {"workers": "4"},
    ]
    for body in refused:
        with pytest.raises(cleanup_api.CleanupError) as caught:
            api.post("/api/cleanup/scan", body)
        assert caught.value.status == 400, body


def test_unknown_jobs_and_endpoints_are_404():
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    for path in ("/api/cleanup/jobs/nope", "/api/cleanup/jobs/nope/cancel"):
        with pytest.raises(cleanup_api.CleanupError) as caught:
            if path.endswith("/cancel"):
                api.post(path, {})
            else:
                api.get(path, {})
        assert caught.value.status == 404
    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.get("/api/cleanup/jobs/nope/deeper", {})
    assert caught.value.status == 404
    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.post("/api/cleanup/nope", {})
    assert caught.value.status == 404
    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.get("/api/cleanup/jobs", {"x": ["1"]})
    assert caught.value.status == 400


def test_cancel_reaches_a_running_scan(monkeypatch):
    """A fake catalog keeps the job running until cancel; the store maps it honestly."""

    def fake_scan(root, entry_ids, *, cancel, progress_callback, workers):
        progress_callback(
            {
                "phase": "scanning",
                "pathsDone": 0,
                "pathsTotal": 1,
                "bytesSeen": 0,
                "filesSeen": 0,
                "currentPath": "/fake",
            }
        )
        while not cancel.is_set():
            time.sleep(0.01)
        return {
            "cancelled": True,
            "entries": [],
            "totals": {},
            "progress": {"phase": "cancelled", "pathsDone": 0, "pathsTotal": 1},
        }

    class FakeModule:
        MAX_WORKERS = 4
        scan_catalog = staticmethod(fake_scan)

        @staticmethod
        def load(root):
            return [{"id": "fake.entry"}]

    monkeypatch.setattr(cleanup_api, "_module", lambda root, name: FakeModule())
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    job = api.post("/api/cleanup/scan", {"entryIds": ["fake.entry"]})
    deadline = time.time() + 5
    while job.progress["currentPath"] != "/fake" and time.time() < deadline:
        time.sleep(0.01)
    assert job.progress["currentPath"] == "/fake"

    answer = api.post("/api/cleanup/jobs/{0}/cancel".format(job.id), {})
    assert answer["id"] == job.id
    wait_for(job, "cancelled")
    assert job.result["cancelled"] is True
    assert job.progress["phase"] == "cancelled"

    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.post("/api/cleanup/jobs/{0}/cancel".format(job.id), {"force": True})
    assert caught.value.status == 400


def test_the_browser_route_starts_polls_and_cancels(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    with open(os.path.join(target, "blob.bin"), "wb") as handle:
        handle.write(b"z" * 4096)

    from web_ui import LabHttpHandler

    server = HTTPServer(("127.0.0.1", 0), LabHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:{0}".format(server.server_address[1])

    def call(path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = (
            {"Content-Type": "application/json", "X-OSLab": "1"} if body is not None else {}
        )
        request = urllib.request.Request(base + path, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, json.loads(answer.read().decode("utf-8"))

    try:
        status, started = call(
            "/api/cleanup/scan", {"entryIds": ["system.user-caches"], "workers": 1}
        )
        assert status == 202
        assert started["kind"] == "scan"
        deadline = time.time() + 10
        while time.time() < deadline:
            _, polled = call("/api/cleanup/jobs/" + started["id"])
            if polled["state"] != "running":
                break
            time.sleep(0.01)
        assert polled["state"] == "done"
        assert polled["result"]["totals"]["sizeBytes"] == 4096

        status, cancelled = call("/api/cleanup/jobs/{0}/cancel".format(started["id"]), {})
        assert status == 200
        assert cancelled["id"] == started["id"]
    finally:
        server.shutdown()
        server.server_close()


def wait_done(job, timeout=10):
    return wait_for(job, "done", timeout)


def test_a_plan_is_previewed_then_cleaned_from_the_console(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    with open(os.path.join(target, "one.bin"), "wb") as handle:
        handle.write(b"x" * 120)

    api = cleanup_api.CleanupAPI(REPO_ROOT)
    plan_job = wait_done(
        api.post("/api/cleanup/plan", {"entryIds": ["system.user-caches"], "workers": 1})
    )
    assert plan_job.kind == "plan"
    assert plan_job.error is None
    payload = plan_job.result
    assert payload["mode"] == "trash"
    assert payload["totals"]["ready"] == 1
    item = payload["items"][0]
    assert item["status"] == "ready"
    assert (item["sizeBytes"], item["files"]) == (120, 1)
    plan_id = payload["planId"]
    assert plan_id and plan_id == plan_job.result["planId"]

    clean_job = wait_done(api.post("/api/cleanup/clean", {"planId": plan_id}))
    assert clean_job.kind == "clean"
    assert clean_job.error is None
    result = clean_job.result
    assert result["planId"] == plan_id
    assert result["results"][0]["status"] == "trashed"
    assert result["totals"]["trashed"] == 1
    assert result["totals"]["bytes"] == 120
    assert not os.path.exists(os.path.join(target, "one.bin"))
    assert os.path.exists(result["results"][0]["trashPath"])

    listed = api.get("/api/cleanup/jobs", {})
    assert [row["kind"] for row in listed["jobs"]] == ["clean", "plan"]
    history = api.get("/api/cleanup/history", {})
    assert history["verified"] is True
    assert history["total"] == 1
    assert history["entries"][0]["result"]["results"][0]["path"] == target


def test_plan_and_clean_requests_are_typed(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    with open(os.path.join(target, "one.bin"), "wb") as handle:
        handle.write(b"x" * 10)

    api = cleanup_api.CleanupAPI(REPO_ROOT)
    for body in (
        {"path": target},
        {"entryIds": ["system.user-caches"], "root": target},
        {"entryIds": ["system.user-caches"], "command": "rm -rf"},
        {},
        {"entryIds": []},
        {"entryIds": "system.user-caches"},
        {"entryIds": ["nope.entry"]},
        {"entryIds": ["system.user-caches", "system.user-caches"]},
        {"entryIds": ["system.user-caches"], "mode": "shred"},
        {"entryIds": ["system.user-caches"], "workers": 0},
        {"entryIds": ["system.user-caches"], "workers": True},
    ):
        with pytest.raises(cleanup_api.CleanupError) as caught:
            api.post("/api/cleanup/plan", body)
        assert caught.value.status == 400, body

    for body in ({}, {"planId": ""}, {"planId": 3}, {"planId": "x", "force": True}):
        with pytest.raises(cleanup_api.CleanupError) as caught:
            api.post("/api/cleanup/clean", body)
        assert caught.value.status == 400, body

    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.post("/api/cleanup/clean", {"planId": "not-a-plan"})
    assert caught.value.status == 404


def test_a_changed_item_fails_the_clean_and_removes_nothing(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    original = os.path.join(target, "one.bin")
    with open(original, "wb") as handle:
        handle.write(b"x" * 20)

    api = cleanup_api.CleanupAPI(REPO_ROOT)
    plan = wait_done(api.post("/api/cleanup/plan", {"entryIds": ["system.user-caches"]}))
    with open(os.path.join(target, "added.bin"), "wb") as handle:
        handle.write(b"new")

    job = wait_for(api.post("/api/cleanup/clean", {"planId": plan.result["planId"]}), "failed")
    assert "changed since it was confirmed" in job.error
    assert job.result is None
    assert os.path.exists(original)
    assert os.path.exists(os.path.join(target, "added.bin"))
    assert not os.path.exists(os.path.join(tmp_path, ".Trash"))


def test_a_plan_is_single_use_and_expires(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    with open(os.path.join(target, "one.bin"), "wb") as handle:
        handle.write(b"x" * 5)

    api = cleanup_api.CleanupAPI(REPO_ROOT)
    plan = wait_done(api.post("/api/cleanup/plan", {"entryIds": ["system.user-caches"]}))
    plan_id = plan.result["planId"]
    wait_done(api.post("/api/cleanup/clean", {"planId": plan_id}))

    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.post("/api/cleanup/clean", {"planId": plan_id})
    assert caught.value.status == 409
    assert "already run" in str(caught.value)

    second = wait_done(api.post("/api/cleanup/plan", {"entryIds": ["system.user-caches"]}))
    record = cleanup_api.PLANS.get(second.result["planId"])
    assert record is not None
    record.plan.expires_at = time.time() - 1
    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.post("/api/cleanup/clean", {"planId": second.result["planId"]})
    assert caught.value.status == 410
    assert "expired" in str(caught.value)


def test_the_browser_route_plans_and_cleans(tmp_path, monkeypatch):
    target = catalog_cache_target(tmp_path, monkeypatch)
    with open(os.path.join(target, "blob.bin"), "wb") as handle:
        handle.write(b"z" * 64)

    from web_ui import LabHttpHandler

    server = HTTPServer(("127.0.0.1", 0), LabHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:{0}".format(server.server_address[1])

    def call(path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = (
            {"Content-Type": "application/json", "X-OSLab": "1"} if body is not None else {}
        )
        request = urllib.request.Request(base + path, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, json.loads(answer.read().decode("utf-8"))

    def wait(identifier):
        deadline = time.time() + 10
        while time.time() < deadline:
            _, job = call("/api/cleanup/jobs/" + identifier)
            if job["state"] != "running":
                return job
            time.sleep(0.01)
        raise AssertionError("job stayed running")

    try:
        status, plan = call("/api/cleanup/plan", {"entryIds": ["system.user-caches"]})
        assert status == 202
        plan = wait(plan["id"])
        assert plan["state"] == "done"
        assert plan["result"]["items"][0]["status"] == "ready"

        status, clean = call("/api/cleanup/clean", {"planId": plan["result"]["planId"]})
        assert status == 202
        clean = wait(clean["id"])
        assert clean["state"] == "done"
        assert clean["result"]["results"][0]["status"] == "trashed"
        assert clean["result"]["totals"]["bytes"] == 64
    finally:
        server.shutdown()
        server.server_close()


def test_container_prune_requires_single_use_preview_and_audits(tmp_path, monkeypatch):
    fake = tmp_path / "docker"
    fake.write_text("#!" + sys.executable + "\n"
                    "import json,os,sys\n"
                    "a=sys.argv[1:]\n"
                    "if a==['info']: print('ready'); sys.exit(0)\n"
                    "if a[:2]==['image','ls']: print(json.dumps({'ID':'one'})); sys.exit(0)\n"
                    "if a==['image','prune','--force']:\n"
                    " open(os.environ['FAKE_PRUNE_LOG'],'a').write('pruned\\n'); print('3B'); sys.exit(0)\n"
                    "sys.exit(2)\n")
    fake.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("FAKE_PRUNE_LOG", str(tmp_path / "pruned"))
    monkeypatch.setenv("OSLAB_CLEANUP_STATE", str(tmp_path / "private-state"))
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    assert api.get("/api/cleanup/containers", {})["engine"] == "docker"
    for body in ({"actionId": "/bin/sh"}, {"actionId": "containers.docker.dangling-images", "argv": ["sh"]}):
        with pytest.raises(cleanup_api.CleanupError) as refused:
            api.post("/api/cleanup/containers/preview", body)
        assert refused.value.status == 400
    preview = api.post("/api/cleanup/containers/preview", {"actionId": "containers.docker.dangling-images"})
    assert preview["candidateCount"] == 1
    assert preview["command"] == ["docker", "image", "prune", "--force"]
    job = api.post("/api/cleanup/containers/prune", {"previewId": preview["previewId"]})
    wait_for(job, "done")
    assert (tmp_path / "pruned").read_text() == "pruned\n"
    history = api.get("/api/cleanup/history", {})
    assert history["verified"] is True
    assert history["entries"][0]["result"]["actionId"] == "containers.docker.dangling-images"
    with pytest.raises(cleanup_api.CleanupError) as reused:
        api.post("/api/cleanup/containers/prune", {"previewId": preview["previewId"]})
    assert reused.value.status == 409


def test_vm_inventory_job_is_report_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    bundle = tmp_path / "VirtualBox VMs" / "fixture"
    bundle.mkdir(parents=True)
    (bundle / "fixture.vbox").write_bytes(b"config")
    (bundle / "disk.vdi").write_bytes(b"disk")
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    with pytest.raises(cleanup_api.CleanupError) as refused:
        api.post("/api/cleanup/vms/scan", {"path": str(tmp_path)})
    assert refused.value.status == 400
    job = api.post("/api/cleanup/vms/scan", {})
    wait_for(job, "done")
    assert job.result["items"][0]["id"] == "vms.virtualbox"
    assert job.result["items"][0]["reportOnly"] is True

def test_package_inventory_job_is_read_only_and_typed(monkeypatch):
    from cleanup_lab import packages
    monkeypatch.setattr(packages, "inventory", lambda: {"available": False, "items": [], "sources": [], "errors": []})
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    with pytest.raises(cleanup_api.CleanupError) as refused:
        api.post("/api/cleanup/packages/scan", {"argv": ["brew", "uninstall", "x"]})
    assert refused.value.status == 400
    job = api.post("/api/cleanup/packages/scan", {})
    wait_for(job, "done")
    assert job.kind == "packages"
    assert job.result["items"] == []

def test_macos_leftover_job_accepts_no_paths(monkeypatch):
    from cleanup_lab import leftovers_macos
    monkeypatch.setattr(leftovers_macos, "platform_id", lambda: "linux")
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    with pytest.raises(cleanup_api.CleanupError) as refused:
        api.post("/api/cleanup/leftovers/macos/scan", {"path": "/tmp"})
    assert refused.value.status == 400
    job = api.post("/api/cleanup/leftovers/macos/scan", {})
    wait_for(job, "done")
    assert job.result["available"] is False
    assert job.result["items"] == []


def test_cross_platform_leftover_job_rejects_paths(monkeypatch):
    from cleanup_lab import paths
    monkeypatch.setattr(paths, "platform_id", lambda: "unsupported")
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    with pytest.raises(cleanup_api.CleanupError) as refused:
        api.post("/api/cleanup/leftovers/scan", {"path": "/tmp"})
    assert refused.value.status == 400
    job = api.post("/api/cleanup/leftovers/scan", {})
    wait_for(job, "done")
    assert job.result["available"] is False

def test_deep_sweep_request_uses_configured_root_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    project = tmp_path / "Projects" / "web"
    project.mkdir(parents=True)
    (project / "package.json").write_text("{}")
    cache = project / "node_modules"
    cache.mkdir()
    (cache / "file").write_bytes(b"abc")
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    offered = api.get("/api/cleanup/deep-roots", {})["roots"]
    assert any(x["id"] == "home-projects" and x["available"] for x in offered)
    for request in ({"rootIds": ["/tmp"]}, {"rootIds": ["home-projects"], "path": "/tmp"},
                    {"rootIds": ["home-projects"], "minIdleDays": True},
                    {"rootIds": [["home-projects"]]}):
        with pytest.raises(cleanup_api.CleanupError) as raised:
            api.post("/api/cleanup/deep-scan", request)
        assert raised.value.status == 400
    job = api.post("/api/cleanup/deep-scan", {"rootIds": ["home-projects"], "minIdleDays": 0})
    wait_for(job, "done")
    assert job.result["items"][0]["id"] == "projects.node-modules"
    assert job.result["items"][0]["sizeBytes"] == 3


def test_the_relocation_status_lists_entries_and_destinations():
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    report = api.get("/api/cleanup/relocation", {})
    assert isinstance(report["entries"], list)
    for entry in report["entries"]:
        assert {"entryId", "name", "path", "relocatable", "interrupted"} <= set(entry)
    assert isinstance(report["destinations"], list)
    assert report["destinations"], "a host with no usable volume is a bug"
    for destination in report["destinations"]:
        assert {"mountPoint", "freeBytes", "totalBytes", "kind"} <= set(destination)
        assert destination["kind"] in ("root", "internal", "removable")


def test_relocation_plan_and_run_are_typed_single_use_and_audited(tmp_path, monkeypatch):
    import cleanup_lab.relocation as relocation_module

    record = {
        "action": "move", "entryId": "test.cache", "entryName": "Test cache",
        "homePath": str(tmp_path / "home"), "storePath": str(tmp_path / "store"),
        "destination": str(tmp_path), "files": 1, "sizeBytes": 10, "freeBytes": 1000,
        "state": "local_only", "steps": [{"op": "copy", "src": "a", "dst": "b"}],
        "fingerprint": {"files": 1, "bytes": 10},
    }
    monkeypatch.setattr(relocation_module, "build_plan", lambda *args, **kwargs: record)
    monkeypatch.setattr(relocation_module, "execute", lambda *args, **kwargs: {
        "entryId": "test.cache", "action": "move", "status": "completed",
        "bytesRelocated": 10, "bytesRemoved": None, "cancelled": False,
        "stepsDone": 1, "stepsTotal": 1,
        "homePath": record["homePath"], "storePath": record["storePath"],
    })
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    for body in ({"action": "nope", "entryId": "test.cache", "destination": "x"},
                 {"action": "move"},
                 {"entryId": "test.cache", "destination": "x"},
                 {"action": "move", "entryId": "", "destination": "x"}):
        with pytest.raises(cleanup_api.CleanupError) as raised:
            api.post("/api/cleanup/relocation/plan", body)
        assert raised.value.status == 400

    plan = api.post("/api/cleanup/relocation/plan",
                    {"action": "move", "entryId": "test.cache", "destination": str(tmp_path)})
    wait_for(plan, "done")
    assert plan.result["previewId"]
    assert plan.result["steps"] == record["steps"]
    assert plan.error is None

    run = api.post("/api/cleanup/relocation/run", {"previewId": plan.result["previewId"]})
    wait_for(run, "done")
    assert run.kind == "relocation-run"
    assert run.result["status"] == "completed"
    assert run.error is None

    with pytest.raises(cleanup_api.CleanupError) as raised:
        api.post("/api/cleanup/relocation/run", {"previewId": plan.result["previewId"]})
    assert raised.value.status == 409


def test_the_volumes_endpoint_reports_this_computers_volumes():
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    report = api.get("/api/cleanup/volumes", {})
    assert report["platform"] == paths_module.platform_id()
    assert report["threshold"] == pytest.approx(0.9)
    assert isinstance(report["volumes"], list)
    assert report["volumes"], "a host with no local volume is a bug"
    for volume in report["volumes"]:
        assert set(volume) >= {
            "mountPoint", "name", "device", "filesystem", "kind",
            "totalBytes", "freeBytes", "usedBytes", "usage", "isHome", "pressure", "error",
        }
        assert volume["kind"] in ("root", "internal", "removable", "unknown")
        assert volume["pressure"] in ("ok", "warning")
    if report["homeVolume"] is not None:
        assert any(volume["isHome"] for volume in report["volumes"])


def test_the_volumes_endpoint_takes_no_query_parameters():
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    with pytest.raises(cleanup_api.CleanupError) as caught:
        api.get("/api/cleanup/volumes", {"x": "1"})
    assert caught.value.status == 400
def test_the_privileged_capabilities_report_actions_and_disk_access():
    import cleanup_lab.privilege as privilege_module

    api = cleanup_api.CleanupAPI(REPO_ROOT)
    report = api.get("/api/cleanup/privileged", {})
    assert report["platform"] == paths_module.platform_id()
    assert isinstance(report["diskAccess"], dict)
    if not report["applicable"]:
        assert report["actions"] == []
        return
    assert report["elevation"] in ("pkexec", "sudo", "osascript", "uac")
    for action in report["actions"]:
        assert action["id"].startswith("privileged.")
        assert action["risk"] in ("low", "medium", "high")
        assert isinstance(action["runArgv"], list)
    if report["platform"] != "macos":
        assert report["diskAccess"]["applicable"] is False


def test_privileged_preview_and_run_are_typed_single_use_and_audited(tmp_path, monkeypatch):
    import cleanup_lab.privilege as privilege_module

    plan = privilege_module.PrivilegedPreview(
        platform="linux", action_id="privileged.linux.apt-cache", risk="low",
        preview_argv=None, run_argv=("apt-get", "clean"), elevation="pkexec",
        elevation_argv=("pkexec", "--disable-internal-agent", "apt-get", "clean"),
        digest="d" * 64, count=7, total_bytes=1234, created_at=time.time(),
    )
    material = {"count": 7, "totalBytes": 1234, "notes": [], "missing": False}
    monkeypatch.setattr(privilege_module, "preview", lambda *args, **kwargs: (plan, material))
    monkeypatch.setattr(privilege_module, "execute", lambda *args, **kwargs: {
        "actionId": plan.action_id, "platform": "linux", "status": "completed",
        "candidateCount": 7,
        "command": ["pkexec", "--disable-internal-agent", "apt-get", "clean"],
        "elevation": "pkexec", "output": "ok", "bytesRemoved": None,
    })
    api = cleanup_api.CleanupAPI(REPO_ROOT)
    for body in ({"nope": 1}, {"actionId": ""}, {"actionId": 3}):
        with pytest.raises(cleanup_api.CleanupError) as raised:
            api.post("/api/cleanup/privileged/preview", body)
        assert raised.value.status == 400
    with pytest.raises(cleanup_api.CleanupError) as raised:
        api.post("/api/cleanup/privileged/run", {"previewId": "nope"})
    assert raised.value.status == 404

    preview = api.post("/api/cleanup/privileged/preview", {"actionId": "privileged.linux.apt-cache"})
    assert preview["previewId"]
    assert preview["candidateCount"] == 7
    assert preview["totalBytes"] == 1234
    assert preview["command"] == ["pkexec", "--disable-internal-agent", "apt-get", "clean"]

    job = api.post("/api/cleanup/privileged/run", {"previewId": preview["previewId"]})
    wait_for(job, "done")
    assert job.kind == "privileged-run"
    assert job.result["status"] == "completed"
    assert job.error is None
    assert job.finishedAt is not None

    with pytest.raises(cleanup_api.CleanupError) as raised:
        api.post("/api/cleanup/privileged/run", {"previewId": preview["previewId"]})
    assert raised.value.status == 409
