"""Unit tests for console/oslab.py: host-dependent lab availability, typed plans, signing and jobs."""
import copy
import os
import sys
import time

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "console"))

import oslab  # noqa: E402


def make_host(os_name="linux", arch="x86_64", kvm=True, runtime="docker", tools=(), distros=(), xcode=None):
    found = set(tools) | {"bash"}
    if runtime:
        found.add(runtime)
    return {
        "os": os_name, "arch": arch, "root": REPO_ROOT,
        "kvm": {"present": kvm, "usable": kvm},
        "wsl": {"guest": False, "distributions": list(distros)},
        "runtime": runtime,
        "xcode": xcode if xcode is not None else ({"installed": True, "iosRuntime": True, "iosDevice": True} if os_name == "macos" else None),
        "tools": [{"id": t, "label": label, "found": t in found, "path": None} for t, label in oslab.TOOLS],
    }


def states(host):
    return {lab["id"]: lab["state"] for lab in oslab.lab_catalog(REPO_ROOT, host)["labs"]}


def test_linux_kvm_host_runs_container_labs_but_not_native_mac():
    assert states(make_host()) == {
        "android": "ready", "windows": "ready", "linux": "ready", "ios": "ready", "macos": "unavailable", "source": "ready",
    }


def test_missing_kvm_needs_setup_except_android_static():
    s = states(make_host(kvm=False))
    assert s["android"] == "ready"
    assert s["windows"] == s["linux"] == s["ios"] == "needs-setup"
    android = oslab.lab_status("android", make_host(kvm=False))
    assert any("static" in note for note in android["notes"])


def test_arm_linux_cannot_run_x86_guests():
    s = states(make_host(arch="aarch64"))
    assert s["windows"] == "unavailable"
    assert s["ios"] == "unavailable"
    assert s["linux"] == "ready"


def test_macos_offers_native_simulator_and_static_android_only():
    host = make_host(os_name="macos", kvm=False, tools=("xcrun", "brew"))
    s = states(host)
    assert s["ios"] == "ready" and s["macos"] == "ready"
    assert s["windows"] == "unavailable" and s["linux"] == "unavailable"
    android = oslab.lab_status("android", host)
    assert android["provider"] == "macos-containers"
    assert not any(a["privileged"] for a in android["actions"])
    assert not any(r["id"] == "kvm" for r in android["requirements"])
    assert len([n for n in android["notes"] if "Linux/KVM" in n]) == 1
    for lab in ("ios", "macos"):
        status = oslab.lab_status(lab, host)
        assert status["state"] == "ready"
        assert any("Appium automation needs" in note for note in status["notes"])
        assert all(not action["privileged"] for action in status["actions"])


def test_native_macos_needs_full_xcode_and_available_ios_simulator():
    for missing in ("installed", "iosRuntime", "iosDevice"):
        xcode = {"installed": True, "iosRuntime": True, "iosDevice": True}
        xcode[missing] = False
        host = make_host(os_name="macos", kvm=False, tools=("xcrun", "brew"), xcode=xcode)
        for lab in ("ios", "macos"):
            status = oslab.lab_status(lab, host)
            assert status["state"] == "needs-setup"
            assert any(r["required"] and not r["found"] for r in status["requirements"])


def test_container_engine_requires_reachable_api_and_compose(monkeypatch):
    monkeypatch.setattr(oslab, "_which", lambda name: f"/usr/bin/{name}" if name in ("docker", "podman") else None)
    calls = []
    def fake_capture(args, timeout=5, decode="utf-8"):
        calls.append(args)
        if args[0] == "docker" and args[1] == "info":
            return 1, "engine stopped"
        return 0, "ok"
    monkeypatch.setattr(oslab, "_capture", fake_capture)
    assert oslab.container_runtime() == "podman"
    assert ["docker", "compose", "version"] not in calls
    assert ["podman", "compose", "version"] in calls


def test_windows_host_uses_wsl2():
    without = states(make_host(os_name="windows", kvm=False, runtime=None, tools=("wsl",)))
    assert without["windows"] == "needs-setup"
    host = make_host(os_name="windows", kvm=False, runtime=None, tools=("wsl",), distros=("Ubuntu",))
    assert states(host)["windows"] == "ready"
    assert states(host)["macos"] == "unavailable"
    assert oslab.lab_status("linux", host)["provider"] == "wsl2"


def test_only_unsupported_labs_are_unavailable_across_hosts():
    expected = {
        "linux": {"macos"},
        "windows": {"macos"},
        "macos": {"windows", "linux"},
    }
    for os_name, unavailable in expected.items():
        host = make_host(os_name=os_name, kvm=os_name == "linux", distros=("Ubuntu",) if os_name == "windows" else ())
        labs = oslab.lab_catalog(REPO_ROOT, host)["labs"]
        assert {lab["id"] for lab in labs if lab["state"] == "unavailable"} == unavailable
        assert all(any(action["id"] == "setup" for action in lab["actions"])
                   for lab in labs if lab["state"] == "needs-setup")


def test_capability_catalog_uses_lab_provider_rules():
    catalog = oslab.capability_catalog()
    assert {p["id"] for p in catalog["platforms"]} == {"macos", "windows", "linux"}
    labs = {item["lab"]: item for group in catalog["groups"] for item in group["items"] if item.get("lab")}
    assert set(labs) == set(oslab.LAB_ORDER)
    for lab, item in labs.items():
        for platform in ("macos", "windows", "linux"):
            provider = oslab.provider_for(lab, platform)
            assert (item["support"][platform]["level"] == "none") == (provider is None)


def test_job_failure_before_process_start_is_reported(monkeypatch):
    def fail(_root):
        raise RuntimeError("cannot read configuration")
    monkeypatch.setattr(oslab, "secret_values", fail)
    service = oslab.JobService(REPO_ROOT)
    plan = {"program": sys.executable, "args": ["-c", "pass"], "timeoutSec": 5, "display": "test"}
    job = oslab.Job("Test setup", "macos", "setup", plan)
    service._run(job, plan)
    assert job.state == "failed"
    assert job.error == "cannot read configuration"
    assert job.finished_at is not None


def test_job_nonzero_exit_reports_error():
    service = oslab.JobService(REPO_ROOT)
    plan = {"program": sys.executable, "args": ["-c", "import sys;sys.exit(7)"], "timeoutSec": 5, "display": "test"}
    job = oslab.Job("Test setup", "macos", "setup", plan)
    service._run(job, plan)
    assert job.state == "failed"
    assert job.exit_code == 7
    assert job.error == "Command exited with status 7. See output below."


def test_job_worker_start_failure_does_not_leave_running_job(monkeypatch):
    def fail(_thread):
        raise RuntimeError("thread unavailable")
    monkeypatch.setattr(oslab.threading.Thread, "start", fail)
    service = oslab.JobService(REPO_ROOT)
    plan = {"lab": "macos", "action": "setup", "program": sys.executable,
            "args": ["-c", "pass"], "timeoutSec": 5, "display": "test", "runnable": True}
    job = service.start(plan)
    assert job.state == "failed"
    assert job.error == "Could not start the job worker: thread unavailable"
    assert job.finished_at is not None


def test_plan_builds_typed_labctl_command():
    p = oslab.plan(REPO_ROOT, {"lab": "windows", "action": "start"}, make_host())
    assert p["program"] == "bash"
    assert p["args"][0].endswith("/labctl")
    assert p["args"][1:] == ["win", "start"]
    assert p["runnable"] and not p["privileged"]


def test_every_advertised_local_action_resolves_to_a_bundled_entry_point():
    for host in (make_host(), make_host(os_name="macos", kvm=False, tools=("xcrun", "brew"))):
        for lab in oslab.LAB_ORDER:
            status = oslab.lab_status(lab, host)
            for action in status["actions"]:
                request = {"lab": lab, "action": action["id"]}
                if action["id"] == "profile" or (host["os"] == "macos" and lab == "android" and action["id"] in ("start", "restart")):
                    request["profile"] = "lightweight"
                if action["id"] == "resize":
                    request["cpus"] = "2"
                plan = oslab.plan(REPO_ROOT, request, host)
                if plan["program"] == "bash":
                    assert os.path.isfile(plan["args"][0]), (lab, action["id"], plan["args"][0])


def test_plan_profile_and_resize_validation():
    host = make_host()
    p = oslab.plan(REPO_ROOT, {"lab": "linux", "action": "profile", "profile": "lightweight"}, host)
    assert p["args"][1:] == ["linux", "profile", "use", "lightweight"]
    p = oslab.plan(REPO_ROOT, {"lab": "windows", "action": "resize", "cpus": "4", "ram": "8G", "disk": "128G"}, host)
    assert p["args"][2:] == ["resize", "--cpus", "4", "--ram", "8G", "--disk", "128G"]
    for bad in (
        {"lab": "windows", "action": "resize", "ram": "8G;rm -rf /"},
        {"lab": "windows", "action": "resize", "cpus": "999"},
        {"lab": "linux", "action": "resize", "disk": "64G"},
        {"lab": "windows", "action": "resize"},
        {"lab": "windows", "action": "start", "profile": "../../etc/passwd"},
        {"lab": "windows", "action": "start", "profile": "-x"},
        {"lab": "windows", "action": "start", "ram": "8G"},
        {"lab": "windows", "action": "shell"},
        {"lab": "windows", "action": "start", "command": "id"},
        {"lab": "nope", "action": "start"},
        {"lab": "macos", "action": "status"},
    ):
        with pytest.raises(oslab.PlanError):
            oslab.plan(REPO_ROOT, bad, host)


def test_privileged_setup_without_graphical_agent_is_manual(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    p = oslab.plan(REPO_ROOT, {"lab": "windows", "action": "setup"}, make_host())
    assert p["privileged"] and not p["runnable"]
    assert p["manualCommand"].startswith("sudo ")
    assert p["manualCommand"].endswith("win-lab/scripts/setup-ubuntu.sh")
    assert p["setup"]["guestDisk"]
    assert "authorization" in p["setup"]["privileges"]


def test_macos_android_start_requires_static_profile():
    host = make_host(os_name="macos", kvm=False, tools=("xcrun", "brew"))
    mode = oslab.env_entries(open(os.path.join(REPO_ROOT, "android-lab/lab/.env"), encoding="utf-8").read()).get("LAB_MODE") \
        if os.path.isfile(os.path.join(REPO_ROOT, "android-lab/lab/.env")) else None
    if mode == "static":
        pytest.skip("this checkout already uses the static Android profile")
    with pytest.raises(oslab.PlanError):
        oslab.plan(REPO_ROOT, {"lab": "android", "action": "start"}, host)


def test_plan_signer_binds_the_exact_request():
    signer = oslab.PlanSigner()
    req = {"lab": "linux", "action": "start"}
    token = signer.sign(req)
    assert signer.verify(copy.deepcopy(req), token)
    assert not signer.verify({"lab": "linux", "action": "stop"}, token)
    assert not signer.verify(req, "0" * 64)
    assert not oslab.PlanSigner().verify(req, token)


def test_env_parsing_and_secret_masking(tmp_path):
    text = "# comment\nexport WEB_PORT=9000\nUSER_PASSWORD='hunter22'\nBAD LINE\nAPI_TOKEN=\n"
    entries = oslab.env_entries(text)
    assert entries == {"WEB_PORT": "9000", "USER_PASSWORD": "hunter22", "API_TOKEN": ""}
    assert oslab.is_secret("USER_PASSWORD") and not oslab.is_secret("WEB_PORT")
    assert oslab.endpoints("windows", entries)[0]["address"] == "http://127.0.0.1:9000/"


def test_lab_config_masks_secrets():
    cfg = oslab.lab_config(REPO_ROOT, "windows")
    assert cfg["path"] == "win-lab/.env"
    for field in cfg["fields"]:
        if oslab.is_secret(field["key"]) and field["value"]:
            assert field["value"] == "••••••"


def test_job_service_runs_redacts_and_reports(monkeypatch):
    monkeypatch.setattr(oslab, "secret_values", lambda root: ["s3cr3t-value"])
    jobs = oslab.JobService(REPO_ROOT)
    plan = {"lab": "linux", "action": "status", "program": sys.executable, "runnable": True, "timeoutSec": 30,
            "display": "python -c ...",
            "args": ["-c", "print('token=s3cr3t-value'); print('\\x1b[32mok\\x1b[0m'); raise SystemExit(3)"]}
    job = jobs.start(plan)
    with pytest.raises(oslab.PlanError):
        jobs.start(plan)  # one running job per lab
    deadline = time.time() + 10
    while job.state == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert job.state == "failed" and job.exit_code == 3
    assert job.lines == ["token=[redacted]", "ok"]
    assert jobs.list()[0]["id"] == job.id


def test_job_service_cancel():
    jobs = oslab.JobService(REPO_ROOT)
    plan = {"lab": "ios", "action": "start", "program": sys.executable, "runnable": True, "timeoutSec": 30,
            "display": "sleep", "args": ["-c", "import time; print('up', flush=True); time.sleep(30)"]}
    job = jobs.start(plan)
    deadline = time.time() + 5
    while job.proc is None and time.time() < deadline:
        time.sleep(0.02)
    jobs.cancel(job.id)
    deadline = time.time() + 10
    while job.state == "running" and time.time() < deadline:
        time.sleep(0.05)
    assert job.state == "cancelled"


def test_manual_plans_never_start():
    jobs = oslab.JobService(REPO_ROOT)
    with pytest.raises(oslab.PlanError):
        jobs.start({"lab": "windows", "action": "setup", "runnable": False, "manualCommand": "sudo bash x"})


def test_monitor_without_runtime():
    host = make_host(runtime=None)
    assert oslab.monitor(REPO_ROOT, "windows", host)["state"] == "no-runtime"
    assert oslab.monitor(REPO_ROOT, "macos", host)["containers"] == []


def test_appium_install_is_a_user_level_native_macos_action():
    host = make_host(os_name="macos", kvm=False, tools=("xcrun", "brew"))
    for lab in ("ios", "macos"):
        status = oslab.lab_status(lab, host)
        action = next(a for a in status["actions"] if a["id"] == "appium-install")
        assert not action["privileged"]
        plan = oslab.plan(REPO_ROOT, {"lab": lab, "action": "appium-install"}, host)
        assert plan["program"] == "bash" and plan["args"][0].endswith("/ios-lab/mac/appium.sh")
        assert plan["args"][1:] == ["install"] and plan["runnable"] and not plan["privileged"]
    assert "appium-install" not in {a["id"] for a in oslab.lab_status("android", host)["actions"]}


def test_native_macos_actions_follow_whether_appium_is_installed():
    missing = oslab.lab_status("macos", make_host(os_name="macos", kvm=False, tools=("xcrun", "brew")))
    ids = {a["id"] for a in missing["actions"]}
    assert "appium-install" in ids and not ids & {"appium-start", "appium-stop"}
    present = oslab.lab_status("macos", make_host(os_name="macos", kvm=False, tools=("xcrun", "brew", "appium")))
    ids = {a["id"] for a in present["actions"]}
    assert {"appium-start", "appium-stop"} <= ids and "appium-install" not in ids
    labels = {a["id"]: a["label"] for a in present["actions"]}
    assert labels["start"] == "Start iOS Simulator" and labels["stop"] == "Stop iOS Simulator"
    # Linux/container labs keep their own wording
    assert {a["id"]: a["label"] for a in oslab.lab_status("windows", make_host())["actions"]}["start"] == "Start"


def test_managed_appium_counts_as_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("OSLAB_APPIUM_HOME", str(tmp_path))
    monkeypatch.setattr(oslab.shutil, "which", lambda name: None)
    assert oslab._which("appium") is None
    binary = tmp_path / "node_modules" / ".bin" / "appium"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    assert oslab._which("appium") == str(binary)


@pytest.mark.skipif(sys.platform != "darwin", reason="appium.sh is macOS only")
def test_appium_install_stops_clearly_without_node_or_homebrew(tmp_path):
    import subprocess
    script = os.path.join(REPO_ROOT, "ios-lab", "mac", "appium.sh")
    done = subprocess.run(["/bin/bash", script, "install"], capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "OSLAB_APPIUM_HOME": str(tmp_path / "a")})
    assert done.returncode != 0
    assert "##PROGRESS 1/5 Checking Node.js" in done.stdout
    assert "Node.js 20.19+" in done.stderr and "Homebrew" in done.stderr
    assert not (tmp_path / "a" / "node_modules").exists()


def test_host_report_leaves_out_tools_and_providers_from_other_platforms(monkeypatch):
    monkeypatch.setattr(oslab, "host_os", lambda: "macos")
    monkeypatch.setattr(oslab, "host_arch", lambda: "arm64")
    mac = oslab.host_info(REPO_ROOT)
    ids = {t["id"] for t in mac["tools"]}
    assert {"xcrun", "brew"} <= ids and not ids & {"wsl", "apt-get", "pkexec"}
    assert all(p["candidate"] for p in mac["providers"])
    assert {p["id"] for p in mac["providers"]} == {"android-container", "native-macos", "native-python"}
    assert oslab.tools_for_host("windows") and {t for t, _ in oslab.tools_for_host("windows")} >= {"wsl", "docker", "bash"}
    win = {t for t, _ in oslab.tools_for_host("windows")}
    assert not win & {"xcrun", "brew", "apt-get", "pkexec", "sudo"}
    linux = {t for t, _ in oslab.tools_for_host("linux")}
    assert {"apt-get", "pkexec", "sudo"} <= linux and not linux & {"xcrun", "brew", "wsl"}


def test_a_lab_with_missing_requirements_offers_only_ways_to_fix_or_diagnose_it():
    blocked = make_host(os_name="macos", kvm=False, runtime=None, tools=("xcrun", "brew", "adb"))
    status = oslab.lab_status("android", blocked)
    assert status["state"] == "needs-setup"
    assert {a["id"] for a in status["actions"]} <= oslab.SETUP_STATE_ACTIONS
    for hidden in ("start", "stop", "restart", "resize", "logs", "urls", "monitor", "status"):
        assert hidden not in {a["id"] for a in status["actions"]}
        with pytest.raises(oslab.PlanError):
            oslab.plan(REPO_ROOT, {"lab": "android", "action": hidden, **({"profile": "lightweight"} if hidden in ("start", "restart") else {}), **({"cpus": "2"} if hidden == "resize" else {})}, blocked)
    # Linux without a container engine: same rule for the VM labs
    linux = oslab.lab_status("windows", make_host(runtime=None))
    assert linux["state"] == "needs-setup" and {a["id"] for a in linux["actions"]} <= oslab.SETUP_STATE_ACTIONS
    # Once the requirements are met the full set is back
    ready = oslab.lab_status("windows", make_host())
    assert ready["state"] == "ready" and {"start", "stop", "resize", "logs"} <= {a["id"] for a in ready["actions"]}
    # Native macOS without Xcode: no simulator start/stop until it is installed
    mac = oslab.lab_status("ios", make_host(os_name="macos", kvm=False, tools=("xcrun", "brew"),
                                            xcode={"installed": False, "iosRuntime": False, "iosDevice": False}))
    assert mac["state"] == "needs-setup" and not {"start", "stop"} & {a["id"] for a in mac["actions"]}


def test_source_is_native_without_vm_dependencies(monkeypatch):
    import source_control
    monkeypatch.setattr(source_control, "readiness", lambda root: {
        "python": {"version": "3.11"}, "storage": {"writable": True}, "optional": {},
        "capabilities": ["static-detection"]})
    for system in ("linux", "macos", "windows"):
        source = oslab.lab_status("source", make_host(system, kvm=False, runtime=None))
        assert source["state"] == "ready"
        assert source["provider"] == "native-python"
        assert not any(r["id"] in ("kvm", "runtime", "wsl") for r in source["requirements"])
        assert all(not a["privileged"] for a in source["actions"])
    monkeypatch.setattr(source_control, "readiness", lambda root: {})
    assert oslab.lab_status("source", make_host())["state"] == "unavailable"
