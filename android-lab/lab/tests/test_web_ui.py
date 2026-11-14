import os
import json
import threading
import time
import urllib.error
import urllib.request
import pytest
from http.server import HTTPServer
from web_ui import LabHttpHandler


@pytest.fixture(scope="module")
def web_server():
    server = HTTPServer(("127.0.0.1", 5059), LabHttpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)
    yield "http://127.0.0.1:5059"
    server.shutdown()


def test_web_ui_health_endpoint(web_server):
    url = f"{web_server}/api/health"
    req = urllib.request.urlopen(url)
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert data["status"] == "ok"
    assert data["app"] == "android-lab"


def test_web_ui_dashboard_page(web_server):
    url = f"{web_server}/"
    req = urllib.request.urlopen(url)
    assert req.status == 200
    body = req.read().decode("utf-8")
    assert "os-lab" in body


def test_web_ui_classic_console(web_server):
    body = urllib.request.urlopen(f"{web_server}/classic/").read().decode("utf-8")
    assert "android-lab" in body
    assert "Mobile Security Console" in body


def test_web_ui_logs_and_reports_endpoints(web_server):
    # Logs endpoint
    req_logs = urllib.request.urlopen(f"{web_server}/api/logs")
    assert req_logs.status == 200
    logs_data = json.loads(req_logs.read().decode("utf-8"))
    assert "logs" in logs_data

    # Reports endpoint
    req_reports = urllib.request.urlopen(f"{web_server}/api/reports")
    assert req_reports.status == 200
    reports_data = json.loads(req_reports.read().decode("utf-8"))
    assert "reports" in reports_data


def test_web_ui_upload_endpoint(web_server):
    boundary = "----TestBoundary12345"
    file_bytes = b"PK\x03\x04mock_apk_content"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="apk"; filename="uploaded-sample.apk"\r\n'
        f"Content-Type: application/vnd.android.package-archive\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{web_server}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-OSLab": "1"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "success"
        assert data["filename"] == "uploaded-sample.apk"
        assert data["size"] == len(file_bytes)
        assert data["path"].endswith("uploaded-sample.apk")



def _post(url, payload, headers=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def test_post_requires_oslab_header(web_server):
    status, data = _post(f"{web_server}/api/run", {"action": "preflight"})
    assert status == 403
    assert "X-OSLab" in data["error"]


def test_foreign_host_header_is_refused(web_server):
    req = urllib.request.Request(f"{web_server}/api/health", headers={"Host": "evil.example"})
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req)
    assert err.value.code == 403


def test_artifacts_cannot_escape_folder(web_server):
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", 5059)
    conn.request("GET", "/artifacts/../web_ui.py")
    assert conn.getresponse().status == 404


def test_host_reports_every_lab(web_server):
    data = json.loads(urllib.request.urlopen(f"{web_server}/api/host").read().decode("utf-8"))
    assert data["host"]["os"]
    assert [lab["id"] for lab in data["labs"]] == ["android", "windows", "linux", "ios", "macos", "source"]
    for lab in data["labs"]:
        assert lab["state"] in ("ready", "needs-setup", "unavailable")


def test_health_capabilities_are_served_by_console(web_server):
    data = json.loads(urllib.request.urlopen(f"{web_server}/api/capabilities").read().decode("utf-8"))
    assert len(data["platforms"]) == 3
    assert any(item.get("lab") == "ios" for group in data["groups"] for item in group["items"])


def test_lab_start_requires_a_previewed_plan(web_server):
    status, data = _post(f"{web_server}/api/labs/start",
                         {"request": {"lab": "android", "action": "status"}, "token": "forged"},
                         {"X-OSLab": "1"})
    assert status == 409


def test_lab_plan_rejects_injection(web_server):
    status, data = _post(f"{web_server}/api/labs/plan",
                         {"request": {"lab": "android", "action": "start", "profile": "../../etc"}},
                         {"X-OSLab": "1"})
    assert status == 400


def _content_post(url, body=b"{}", headers=None):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers or {})
    try:
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        return e


def test_content_status_and_bundled_companies(web_server):
    status = json.load(urllib.request.urlopen(f"{web_server}/api/content/status"))
    assert status["installed"] is False and status["offline"] is True
    data = json.load(urllib.request.urlopen(f"{web_server}/api/content/companies"))
    assert data["source"] == "bundled" and len(data["companies"]) >= 1
    assert all(c["slug"] and isinstance(c["branches"], list) for c in data["companies"])


def test_content_file_is_limited_to_content_paths(web_server):
    ok = urllib.request.urlopen(f"{web_server}/api/content/file?path=docs/legal/PRIVACY.md")
    assert ok.status == 200 and b"Privacy" in ok.read()
    for bad in ("labctl", "../../etc/passwd", "android-lab/lab/web_ui.py", "docs/legal/../../labctl"):
        try:
            urllib.request.urlopen(f"{web_server}/api/content/file?path={bad}")
            raise AssertionError(f"{bad} was served")
        except urllib.error.HTTPError as e:
            assert e.code == 404


def test_content_posts_need_the_oslab_header_and_respect_the_offline_switch(web_server):
    assert _content_post(f"{web_server}/api/content/update").code == 403
    resp = _content_post(f"{web_server}/api/content/check", headers={"X-OSLab": "1"})
    assert resp.code == 400 and b"switched off" in resp.read()


def test_app_update_status_is_reported_without_network(web_server):
    data = json.load(urllib.request.urlopen(f"{web_server}/api/app/update"))
    assert "supported" in data and "updateAvailable" in data
    assert data["install"] is None

