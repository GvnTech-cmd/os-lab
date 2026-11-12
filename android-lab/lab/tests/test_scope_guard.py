"""Scope guard (console/scope_guard.py): manifest validation and allow/deny of hosts, apps, devices and paths."""
import datetime
import json
import os
import sys

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "console"))

import scope_guard  # noqa: E402
from scope_guard import ScopeError, ScopeManifestError  # noqa: E402

TODAY = datetime.date(2026, 11, 12)


def manifest(**changes):
    data = {
        "version": 1,
        "name": "unit-test lab",
        "authorization": "Owned test fixtures only",
        "expires": "2026-12-31",
        "hosts": ["127.0.0.0/8", "::1", "localhost", "10.25.130.0/24", "fd00:1ab::/64",
                  "srv.lab.internal", "*.lab.internal"],
        "packages": ["com.testlab.vulnerable", "com.oslab.*"],
        "devices": ["emulator-*", "127.0.0.1:5555", "R58M12ABCDE"],
        "paths": ["artifacts"],
    }
    data.update(changes)
    return {key: value for key, value in data.items() if value is not None}


@pytest.fixture
def scope(tmp_path):
    (tmp_path / "artifacts").mkdir()
    return scope_guard.parse_scope(manifest(), source=str(tmp_path / "scope.json"))


def allowed(scope, kind, target):
    return scope_guard.check(kind, target, scope, today=TODAY).allowed


# @lat: [[tooling#Scope guard#Hosts]]
@pytest.mark.parametrize("target", [
    "127.0.0.1", "127.8.9.10", "::1", "[::1]", "[::1]:8080", "localhost", "LOCALHOST", "localhost.",
    "10.25.130.14", "10.25.130.14:22", "http://10.25.130.14:8080/login?next=/", "ssh://root@10.25.130.14",
    "::ffff:10.25.130.14", "fd00:1ab::17", "srv.lab.internal", "a.b.lab.internal", "https://App.Lab.Internal/",
])
def test_lab_hosts_are_in_scope(scope, target):
    assert allowed(scope, "host", target)


# @lat: [[tooling#Scope guard#Hosts]]
@pytest.mark.parametrize("target", [
    "8.8.8.8", "10.25.131.14", "10.25.13.14", "192.168.1.1", "2001:4860:4860::8888", "fd00:1ac::17",
    "example.com", "lab.internal", "evil-lab.internal", "lab.internal.evil.com", "srv.lab.internal.evil.com",
    "localhost.evil.com", "notlocalhost",
])
def test_hosts_outside_the_lab_are_refused(scope, target):
    decision = scope_guard.check("host", target, scope, today=TODAY)
    assert not decision.allowed
    assert "outside" in decision.reason and "unit-test lab" in decision.reason


# @lat: [[tooling#Scope guard#Hosts]]
@pytest.mark.parametrize("target", [
    "http://localhost@evil.com/",            # user info is not the host
    "http://evil.com#@localhost",            # nor is the fragment
    "http://evil.com/?h=localhost",
    "http://localhost\\@evil.com/",
    "127.1", "2130706433", "0x7f.0.0.1", "0x7f000001", "017700000001",   # inet_aton spellings
    "lоcalhost",                             # Cyrillic "о"
    "local host", "localhost\n", "localhost\r\nevil.com", "", "   ", "http://", "localhost:port", "a..b",
    " localhost", "localhost ", " 127.0.0.1",                    # the tool would use the padded value
    "file://localhost/etc/passwd", "FILE://localhost/C:/Windows/win.ini",    # a path, not a network host
    "[::1", "::1]", "[[::1]]", "[127.0.0.1]", "[localhost]",     # brackets are for IPv6 only, and in pairs
])
def test_disguised_or_malformed_hosts_are_refused(scope, target):
    assert not allowed(scope, "host", target)


# @lat: [[tooling#Scope guard#Hosts]]
def test_interface_zones_are_refused(tmp_path):
    scope = scope_guard.parse_scope(manifest(hosts=["fe80::/10"]), source=str(tmp_path / "scope.json"))
    assert allowed(scope, "host", "fe80::1") and allowed(scope, "host", "[fe80::1]:22")
    for target in ("fe80::1%eth0", "[fe80::1%eth0]", "[fe80::1%25eth0]:22", "http://[fe80::1%25eth0]/"):
        decision = scope_guard.check("host", target, scope, today=TODAY)
        assert not decision.allowed, target


# @lat: [[tooling#Scope guard#Hosts]]
def test_mapped_ipv6_rules_match_like_their_ipv4_address(tmp_path):
    scope = scope_guard.parse_scope(manifest(hosts=["::ffff:10.9.8.7", "::ffff:10.7.0.0/112"]),
                                    source=str(tmp_path / "scope.json"))
    for target in ("10.9.8.7", "::ffff:10.9.8.7", "[::ffff:10.9.8.7]:443", "10.7.0.5", "::ffff:10.7.255.255"):
        assert allowed(scope, "host", target), target
    for target in ("10.9.8.8", "10.8.0.1", "::ffff:10.8.0.1"):
        assert not allowed(scope, "host", target), target


# @lat: [[tooling#Scope guard#Apps and devices]]
def test_packages_match_exactly_or_by_dotted_prefix(scope):
    for package in ("com.testlab.vulnerable", "com.oslab.demo", "com.oslab.demo.debug"):
        assert allowed(scope, "package", package)
    for package in ("com.testlab.vulnerable2", "com.testlab", "com.oslabs.demo", "com.oslab", "com.OSLAB.demo",
                    "com.whatsapp", "org.com.oslab.demo", "com.oslab.demo; rm -rf /", "singleword", "", "com..oslab",
                    " com.testlab.vulnerable", "com.testlab.vulnerable "):
        assert not allowed(scope, "package", package)


# @lat: [[tooling#Scope guard#Apps and devices]]
def test_device_serials_match_exactly_or_by_prefix(scope):
    for serial in ("emulator-5554", "emulator-5556", "127.0.0.1:5555", "R58M12ABCDE"):
        assert allowed(scope, "device", serial)
    for serial in ("R58M12ABCDF", "r58m12abcde", "R58M12ABCDE1", "192.168.1.20:5555", "127.0.0.1:5556",
                   "emulator", "xemulator-5554", "emulator-5554 -s other", "", "*", " emulator-5554", "emulator-5554 "):
        assert not allowed(scope, "device", serial)


# @lat: [[tooling#Scope guard#Paths]]
def test_paths_must_stay_inside_a_declared_folder(scope, tmp_path, monkeypatch):
    inside = tmp_path / "artifacts"
    (tmp_path / "other").mkdir()
    (tmp_path / "artifacts-private").mkdir()
    assert allowed(scope, "path", str(inside))
    assert allowed(scope, "path", str(inside / "run-1" / "report.json"))        # need not exist yet
    assert not allowed(scope, "path", str(tmp_path / "other" / "report.json"))
    assert not allowed(scope, "path", str(tmp_path / "artifacts-private" / "x"))  # a name prefix is not a folder
    assert not allowed(scope, "path", str(inside / ".." / "other" / "x"))
    assert not allowed(scope, "path", str(tmp_path))
    assert not allowed(scope, "path", "")
    assert not allowed(scope, "path", "artifacts\0/x")
    assert not allowed(scope, "path", " " + str(inside / "x.json"))       # open() would use the padded name
    assert not allowed(scope, "path", str(inside / "x.json") + " ")
    # a relative target is resolved against the working directory, as the tool's open() would
    monkeypatch.chdir(tmp_path)
    assert allowed(scope, "path", os.path.join("artifacts", "x.json"))
    monkeypatch.chdir(tmp_path / "other")
    assert not allowed(scope, "path", os.path.join("artifacts", "x.json"))


# @lat: [[tooling#Scope guard#Paths]]
def test_a_link_out_of_the_lab_folder_is_refused(scope, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "artifacts" / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available to this user")
    assert not allowed(scope, "path", str(link / "secret.txt"))


# @lat: [[tooling#Scope guard#Refusal]]
def test_assert_in_scope_raises_with_the_reason(scope):
    decision = scope_guard.assert_in_scope("host", "10.25.130.14:22", scope, today=TODAY)
    assert decision.allowed and decision.target == "10.25.130.14" and decision.rule == "10.25.130.0/24"
    with pytest.raises(ScopeError) as caught:
        scope_guard.assert_in_scope("host", "https://example.com/", scope, today=TODAY)
    assert isinstance(caught.value, PermissionError)
    assert caught.value.kind == "host" and caught.value.target == "example.com"
    assert "example.com is outside" in str(caught.value) and "10.25.130.0/24" in str(caught.value)


# @lat: [[tooling#Scope guard#Refusal]]
def test_unknown_kinds_and_non_string_targets_are_refused(scope):
    for kind, target in (("url", "localhost"), ("host", None), ("host", 2130706433), ("host", ["localhost"]),
                         ("host", "a" * 5000), (None, "localhost")):
        assert not scope_guard.check(kind, target, scope, today=TODAY).allowed


# @lat: [[tooling#Scope guard#Refusal]]
def test_an_expired_scope_refuses_everything(scope):
    assert allowed(scope, "host", "127.0.0.1")
    assert scope_guard.check("host", "127.0.0.1", scope, today=datetime.date(2026, 12, 31)).allowed
    late = scope_guard.check("host", "127.0.0.1", scope, today=datetime.date(2027, 1, 1))
    assert not late.allowed and "expired on 2026-12-31" in late.reason


# @lat: [[tooling#Scope guard#Refusal]]
def test_no_manifest_means_nothing_is_in_scope(tmp_path, monkeypatch):
    monkeypatch.setenv(scope_guard.SCOPE_ENV, str(tmp_path / "missing.json"))
    decision = scope_guard.check("host", "127.0.0.1")
    assert not decision.allowed and "No lab scope is declared" in decision.reason
    assert not scope_guard.in_scope("device", "emulator-5554")
    with pytest.raises(ScopeError):
        scope_guard.assert_in_scope("package", "com.testlab.vulnerable")
    with pytest.raises(ScopeManifestError):
        scope_guard.load_scope()


# @lat: [[tooling#Scope guard#Refusal]]
def test_a_broken_manifest_refuses_instead_of_falling_open(tmp_path, monkeypatch):
    path = tmp_path / "scope.json"
    monkeypatch.setenv(scope_guard.SCOPE_ENV, str(path))
    for text in ("", "{not json", "[]", '"hosts"', json.dumps(manifest(hosts="127.0.0.1"))):
        path.write_text(text, encoding="utf-8")
        assert not scope_guard.in_scope("host", "127.0.0.1")
    path.write_text(json.dumps(manifest()), encoding="utf-8")
    assert scope_guard.in_scope("host", "127.0.0.1")
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(manifest()).encode())    # a Notepad BOM is fine
    assert scope_guard.in_scope("host", "127.0.0.1")
    path.write_text(" " * (scope_guard.MAX_MANIFEST_BYTES + 1), encoding="utf-8")
    assert not scope_guard.in_scope("host", "127.0.0.1")
    path.write_text("[" * 100000, encoding="utf-8")                       # deeper than the JSON decoder goes
    refused = scope_guard.check("host", "127.0.0.1")
    assert not refused.allowed and "nested too deeply" in refused.reason
    # a repeated field would silently replace the first one
    text = json.dumps(manifest(hosts=["8.8.8.8"], allowPublic=True))[:-1] + ', "hosts": ["127.0.0.1"]}'
    path.write_text(text, encoding="utf-8")
    refused = scope_guard.check("host", "127.0.0.1")
    assert not refused.allowed and '"hosts" appears more than once' in refused.reason
    monkeypatch.setenv(scope_guard.SCOPE_ENV, str(tmp_path))              # a folder is not a manifest
    refused = scope_guard.check("host", "127.0.0.1")
    assert not refused.allowed and "not a regular file" in refused.reason


# @lat: [[tooling#Scope guard#Manifest]]
def test_manifest_lookup_order(tmp_path):
    env = {scope_guard.SCOPE_ENV: str(tmp_path / "env.json")}
    assert scope_guard.manifest_path(str(tmp_path / "arg.json"), str(tmp_path), env) == str(tmp_path / "arg.json")
    assert scope_guard.manifest_path(None, str(tmp_path), env) == str(tmp_path / "env.json")
    assert scope_guard.manifest_path(None, str(tmp_path), {}) == str(tmp_path / "scope.json")
    assert scope_guard.manifest_path(None, None, {}) == os.path.join(REPO_ROOT, "scope.json")


# @lat: [[tooling#Scope guard#Manifest]]
@pytest.mark.parametrize("changes", [
    {"version": 2}, {"version": "1"}, {"version": True}, {"version": None},
    {"name": ""}, {"name": None}, {"name": "two\nlines"},
    {"authorization": ""}, {"authorization": None}, {"authorization": 5},
    {"expires": "31.12.2026"}, {"expires": "2026-02-30"}, {"expires": 20261231},
    {"allowPublic": "yes"},
    {"targets": ["127.0.0.1"]},                                  # unknown field
    {"hosts": "127.0.0.1"}, {"hosts": [5]}, {"hosts": [""]}, {"hosts": ["a\nb"]},
    {"hosts": ["*"]}, {"hosts": ["0.0.0.0/0"]}, {"hosts": ["::/0"]}, {"hosts": ["*.com"]},
    {"hosts": ["lab.*.internal"]}, {"hosts": ["*lab.internal"]}, {"hosts": ["http://localhost"]},
    {"hosts": ["127.1"]}, {"hosts": ["10.0.0.0/33"]},
    {"hosts": ["10.25.130.14/24"]}, {"hosts": ["fd00:1ab::17/64"]},        # host bits would widen to the range
    {"hosts": ["::ffff:0:0/96"]}, {"hosts": ["::ffff:8.8.8.8"]},           # mapped "everything" / mapped public
    {"hosts": ["8.8.8.8"]}, {"hosts": ["0.0.0.0/1"]}, {"hosts": ["192.168.0.0/15"]}, {"hosts": ["2001:db8::/16"]},
    {"packages": ["*"]}, {"packages": ["com.*"]}, {"packages": ["com.oslab*"]}, {"packages": ["com.*.app"]},
    {"devices": ["*"]}, {"devices": ["emu*lator"]}, {"devices": ["a b"]},
    {"paths": ["/"]}, {"paths": [7]},
    {"hosts": ["127.0.0.1"] * (scope_guard.MAX_ENTRIES + 1)},
])
def test_invalid_or_over_broad_manifests_are_rejected(changes, tmp_path):
    with pytest.raises(ScopeManifestError):
        scope_guard.parse_scope(manifest(**changes), source=str(tmp_path / "scope.json"))


# @lat: [[tooling#Scope guard#Manifest]]
def test_a_range_with_host_bits_names_the_fix(tmp_path):
    with pytest.raises(ScopeManifestError, match=r'write "10\.25\.130\.0/24" for the range'):
        scope_guard.parse_scope(manifest(hosts=["10.25.130.14/24"]), source=str(tmp_path / "scope.json"))


# @lat: [[tooling#Scope guard#Manifest]]
def test_public_ranges_need_an_explicit_opt_in(tmp_path):
    source = str(tmp_path / "scope.json")
    with pytest.raises(ScopeManifestError, match="public range"):
        scope_guard.parse_scope(manifest(hosts=["203.0.114.7"]), source=source)
    opted = scope_guard.parse_scope(manifest(hosts=["203.0.114.7"], allowPublic=True), source=source)
    assert allowed(opted, "host", "203.0.114.7") and not allowed(opted, "host", "203.0.114.8")
    with pytest.raises(ScopeManifestError):                      # the opt-in never covers "everything"
        scope_guard.parse_scope(manifest(hosts=["0.0.0.0/0"], allowPublic=True), source=source)


# @lat: [[tooling#Scope guard#Manifest]]
def test_reserved_lab_domains_and_optional_fields(tmp_path):
    scope = scope_guard.parse_scope(
        manifest(hosts=["*.test", "*.local"], expires=None, packages=None, devices=None, paths=None),
        source=str(tmp_path / "scope.json"))
    assert scope.expires is None and not scope.expired(datetime.date(2099, 1, 1))
    assert allowed(scope, "host", "dvwa.test") and allowed(scope, "host", "printer.local")
    assert not allowed(scope, "host", "test") and not allowed(scope, "host", "dvwa.test.com")
    refused = scope_guard.check("package", "com.testlab.vulnerable", scope, today=TODAY)
    assert not refused.allowed and "none declared" in refused.reason


# @lat: [[tooling#Scope guard#Manifest]]
def test_the_example_manifest_is_valid():
    example = os.path.join(REPO_ROOT, "console", "scope.example.json")
    scope = scope_guard.load_scope(example)
    assert scope.source == example
    assert scope_guard.check("package", "com.testlab.vulnerable", scope, today=datetime.date(2026, 11, 12)).allowed
    assert scope_guard.check("device", "emulator-5554", scope, today=datetime.date(2026, 11, 12)).allowed
    assert not scope_guard.check("host", "example.com", scope, today=datetime.date(2026, 11, 12)).allowed


# @lat: [[tooling#Scope guard#Console and command line]]
def test_scope_status_reports_the_declared_scope(tmp_path):
    path = tmp_path / "scope.json"
    missing = scope_guard.scope_status(path=str(path))
    assert missing == {"declared": False, "valid": False, "source": str(path), "error": missing["error"]}
    assert "No lab scope is declared" in missing["error"]

    path.write_text("{", encoding="utf-8")
    broken = scope_guard.scope_status(path=str(path))
    assert broken["declared"] and not broken["valid"] and "not valid JSON" in broken["error"]

    path.write_text(json.dumps(manifest()), encoding="utf-8")
    status = scope_guard.scope_status(path=str(path), today=TODAY)
    assert status["valid"] and not status["expired"] and status["error"] is None
    assert status["name"] == "unit-test lab" and status["expires"] == "2026-12-31"
    assert status["counts"] == {"hosts": 7, "packages": 2, "devices": 3, "paths": 1}
    assert status["rules"]["devices"] == ["emulator-*", "127.0.0.1:5555", "R58M12ABCDE"]
    expired = scope_guard.scope_status(path=str(path), today=datetime.date(2027, 6, 1))
    assert expired["valid"] and expired["expired"] and "expired" in expired["error"]


# @lat: [[tooling#Scope guard#Console and command line]]
def test_command_line_exit_codes(tmp_path, capsys):
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(manifest(expires=None)), encoding="utf-8")
    base = ["--scope", str(path)]

    assert scope_guard.main(base + ["check", "host", "10.25.130.14"]) == 0
    assert "In scope" in capsys.readouterr().out

    assert scope_guard.main(base + ["check", "host", "8.8.8.8"]) == 1
    out = capsys.readouterr()
    assert out.out == "" and "Refused: host 8.8.8.8 is outside" in out.err

    assert scope_guard.main(base + ["check", "--json", "package", "com.whatsapp"]) == 1
    decision = json.loads(capsys.readouterr().out)
    assert decision == {"allowed": False, "kind": "package", "target": "com.whatsapp",
                        "reason": decision["reason"], "rule": None}

    assert scope_guard.main(base + ["check", "--json", "device", "emulator-5554"]) == 0
    assert json.loads(capsys.readouterr().out)["rule"] == "emulator-*"

    assert scope_guard.main(base + ["show"]) == 0
    assert "unit-test lab" in capsys.readouterr().out
    assert scope_guard.main(base + ["show", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["hosts"] == 7

    missing = ["--scope", str(tmp_path / "missing.json")]
    assert scope_guard.main(missing + ["check", "host", "127.0.0.1"]) == 2
    assert "No lab scope is declared" in capsys.readouterr().err
    assert scope_guard.main(missing + ["check", "--json", "host", "127.0.0.1"]) == 2
    assert json.loads(capsys.readouterr().out)["allowed"] is False
    assert scope_guard.main(missing + ["show"]) == 2
    capsys.readouterr()
    assert scope_guard.main(base + ["check", "planet", "mars"]) == 2
    assert scope_guard.main([]) == 2
    capsys.readouterr()
