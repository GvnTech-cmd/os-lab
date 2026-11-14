#!/usr/bin/env python3
"""os-lab scope guard: refuse any target that is not inside the declared lab scope.

The project rule is "authorization only, lab only" (docs/legal/ACCEPTABLE_USE.md). This module
enforces that rule in code instead of leaving it to a README: a lab tool declares what it is
about to touch and the guard either returns a decision or raises with a clear reason.

    import scope_guard
    scope_guard.assert_in_scope("host", "10.25.130.14")        # raises ScopeError if outside
    scope_guard.assert_in_scope("package", "com.testlab.vulnerable")
    scope_guard.assert_in_scope("device", "emulator-5554")
    scope_guard.assert_in_scope("path", "android-lab/lab/artifacts/report.json")

- ``load_scope()``        reads and strictly validates the scope manifest (JSON).
- ``check()``             returns a ``Decision`` (allowed or not, the reason, the matching rule).
- ``assert_in_scope()``   the same, but raises ``ScopeError`` when the target is refused.
- ``scope_status()``      a summary of the declared scope for the console and for agents.

The guard fails closed. No manifest, an unreadable or invalid manifest, an expired manifest or a
malformed target are all refusals. It never resolves DNS and never touches the network: a host
name is matched by name only, so a tool that connects by name should also check the address it
actually resolved.

A decision describes the target at the moment of the check. Use ``decision.target`` (the
normalized host, or the resolved path) for the operation that follows, and keep lab folders
writable only by the operator: the guard cannot stop another process from swapping a folder for
a link between the check and the tool's own open().

The manifest is looked up in this order: the ``path`` argument, ``$OSLAB_SCOPE_FILE``, then
``scope.json`` in the os-lab checkout. Start from ``console/scope.example.json``.

Command line (exit 0 in scope, 1 refused, 2 usage or manifest error):

    python3 console/scope_guard.py check host 10.25.130.14
    python3 console/scope_guard.py check --json package com.example.bank
    python3 console/scope_guard.py show

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import ipaddress
import json
import os
import re
import stat
import sys
import urllib.parse
from dataclasses import dataclass, field

KINDS = ("host", "package", "device", "path")
SCOPE_ENV = "OSLAB_SCOPE_FILE"
DEFAULT_NAME = "scope.json"
MANIFEST_VERSION = 1
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ENTRIES = 512
MAX_TARGET = 4096

_ALLOWED_KEYS = {"version", "name", "authorization", "expires", "allowPublic",
                 "hosts", "packages", "devices", "paths"}
_LABEL = r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?"
_HOSTNAME = re.compile(rf"^{_LABEL}(?:\.{_LABEL})*$")
_PACKAGE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$")
_DEVICE = re.compile(r"^[A-Za-z0-9._:\-\[\]]{1,128}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# inet_aton() also accepts "127.1", "2130706433" and "0x7f.0.0.1" as addresses. They are not
# valid host names for the guard: refusing them stops an IP hiding behind a name rule.
_NUMERIC_LABEL = re.compile(r"^(?:0x[0-9a-f]*|[0-9]+)$")
# Special-use names that never resolve on the public internet (RFC 6761, RFC 6762, ICANN .internal).
_LAB_TLDS = {"test", "local", "localhost", "internal", "example", "invalid"}
_MAPPED = ipaddress.ip_network("::ffff:0:0/96")


class ScopeError(PermissionError):
    """The target is refused: outside the scope, or no usable scope is declared."""

    def __init__(self, reason: str, kind: str | None = None, target: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.kind = kind
        self.target = target


class ScopeManifestError(ValueError):
    """The scope manifest is missing, unreadable or invalid."""


@dataclass(frozen=True)
class Decision:
    """The outcome of one check. ``rule`` is the manifest entry that allowed the target."""
    allowed: bool
    kind: str
    target: str
    reason: str
    rule: str | None = None

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "kind": self.kind, "target": self.target,
                "reason": self.reason, "rule": self.rule}


@dataclass(frozen=True)
class Scope:
    """A validated scope manifest. Build it with ``load_scope()`` or ``parse_scope()``."""
    name: str
    authorization: str
    expires: _dt.date | None
    networks: tuple = ()        # (rule text, ip_network)
    hostnames: tuple = ()       # (rule text, exact name or ".suffix" for a wildcard)
    packages: tuple = ()        # rule text: exact id or "prefix.*"
    devices: tuple = ()         # rule text: exact serial or "prefix*"
    paths: tuple = ()           # (rule text, resolved absolute folder)
    source: str | None = None
    rules: dict = field(default_factory=dict, compare=False)   # the manifest lists, as written

    def expired(self, today: _dt.date | None = None) -> bool:
        return self.expires is not None and (today or _dt.date.today()) > self.expires


# ── Manifest ─────────────────────────────────────────────────────────────────

def default_root() -> str:
    """The os-lab checkout this file lives in."""
    return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def manifest_path(path: str | None = None, root: str | None = None, env=None) -> str:
    """Where the manifest is expected: explicit path, then $OSLAB_SCOPE_FILE, then <root>/scope.json."""
    env = os.environ if env is None else env
    chosen = path or env.get(SCOPE_ENV) or os.path.join(root or default_root(), DEFAULT_NAME)
    return os.path.abspath(chosen)


def _strings(data: dict, key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ScopeManifestError(f'"{key}" must be a list of strings')
    if len(value) > MAX_ENTRIES:
        raise ScopeManifestError(f'"{key}" has more than {MAX_ENTRIES} entries')
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 512 or _has_control(item):
            raise ScopeManifestError(f'"{key}" entries must be non-empty single-line strings')
        out.append(item.strip())
    return out


def _has_control(text: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in text)


def _unmapped(address):
    """An IPv4-mapped IPv6 address is the IPv4 address it carries."""
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped if mapped is not None else address


def _host_rule(entry: str, allow_public: bool):
    """One "hosts" entry as ("network", ip_network) or ("name", exact-or-.suffix)."""
    text = entry.lower()
    try:
        network = ipaddress.ip_network(text, strict=True)
    except ValueError:
        network = None
        try:
            widened = ipaddress.ip_network(text, strict=False)
        except ValueError:
            widened = None
        if widened is not None:              # 10.25.130.14/24 would silently cover the whole /24
            raise ScopeManifestError(
                f'hosts: "{entry}" has address bits beyond its prefix; write "{widened}" for the range '
                "or the address alone for one host") from None
    if network is not None:
        if network.version == 6 and network.subnet_of(_MAPPED):    # targets are matched unmapped
            network = ipaddress.IPv4Network((int(network.network_address) & 0xFFFFFFFF, network.prefixlen - 96))
        if network.prefixlen == 0:
            raise ScopeManifestError(f'hosts: "{entry}" matches every address; a scope must name its targets')
        if not allow_public and not network.is_loopback and not network.is_private and not network.is_link_local:
            raise ScopeManifestError(
                f'hosts: "{entry}" is a public range. Lab scopes are loopback or private addresses; '
                'set "allowPublic": true only with written authorization for that range')
        return "network", network
    wildcard = text.startswith("*.")
    name = text[2:] if wildcard else text
    name = name[:-1] if name.endswith(".") else name
    labels = name.split(".")
    if "*" in name or not _HOSTNAME.match(name) or len(name) > 253:
        raise ScopeManifestError(
            f'hosts: "{entry}" is not an address, a CIDR range, a host name or a "*.suffix" wildcard')
    if all(_NUMERIC_LABEL.match(label) for label in labels):
        raise ScopeManifestError(f'hosts: "{entry}" is not a valid address or CIDR range')
    if wildcard and len(labels) < 2 and name not in _LAB_TLDS:
        raise ScopeManifestError(f'hosts: "{entry}" covers a whole top-level domain; name the lab domain')
    return "name", ("." + name) if wildcard else name


def _package_rule(entry: str) -> str:
    wildcard = entry.endswith(".*")
    base = entry[:-2] if wildcard else entry
    if not _PACKAGE.match(base):
        raise ScopeManifestError(
            f'packages: "{entry}" is not an app id; use "com.vendor.app" or "com.vendor.*" '
            "(a wildcard needs at least two fixed parts)")
    return entry


def _device_rule(entry: str) -> str:
    base = entry[:-1] if entry.endswith("*") else entry
    if not base or "*" in base or not _DEVICE.match(base):
        raise ScopeManifestError(
            f'devices: "{entry}" is not a device serial; use the exact serial or a prefix such as "emulator-*"')
    return entry


def parse_scope(data, source: str | None = None, base_dir: str | None = None) -> Scope:
    """Validate a decoded manifest. Raises ScopeManifestError naming the first problem."""
    if not isinstance(data, dict):
        raise ScopeManifestError("The scope manifest must be a JSON object")
    unknown = set(data) - _ALLOWED_KEYS
    if unknown:
        raise ScopeManifestError("Unknown scope fields: " + ", ".join(sorted(map(str, unknown))))
    if data.get("version") != MANIFEST_VERSION or isinstance(data.get("version"), bool):
        raise ScopeManifestError(f'"version" must be {MANIFEST_VERSION}')
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or _has_control(name):
        raise ScopeManifestError('"name" must be a short single-line label for this scope')
    authorization = data.get("authorization")
    if not isinstance(authorization, str) or not authorization.strip() or len(authorization) > 2000:
        raise ScopeManifestError(
            '"authorization" must say who authorized testing these targets (you own them, or written permission)')
    allow_public = data.get("allowPublic", False)
    if not isinstance(allow_public, bool):
        raise ScopeManifestError('"allowPublic" must be true or false')

    expires = None
    if data.get("expires") is not None:
        raw = data["expires"]
        if not isinstance(raw, str) or not _DATE.match(raw):
            raise ScopeManifestError('"expires" must be a date written as YYYY-MM-DD')
        try:
            expires = _dt.date.fromisoformat(raw)
        except ValueError:
            raise ScopeManifestError(f'"expires" is not a real date: {raw}') from None

    rules = {key: _strings(data, key) for key in ("hosts", "packages", "devices", "paths")}
    networks, hostnames = [], []
    for entry in rules["hosts"]:
        kind, value = _host_rule(entry, allow_public)
        (networks if kind == "network" else hostnames).append((entry, value))
    packages = [_package_rule(e) for e in rules["packages"]]
    devices = [_device_rule(e) for e in rules["devices"]]

    base = os.path.realpath(base_dir or (os.path.dirname(source) if source else os.getcwd()))
    paths = []
    for entry in rules["paths"]:
        resolved = os.path.realpath(os.path.join(base, os.path.expanduser(entry)))
        if os.path.dirname(resolved) == resolved:
            raise ScopeManifestError(f'paths: "{entry}" is a filesystem root; name the lab folder')
        paths.append((entry, resolved))

    return Scope(name=name.strip(), authorization=authorization.strip(), expires=expires,
                 networks=tuple(networks), hostnames=tuple(hostnames), packages=tuple(packages),
                 devices=tuple(devices), paths=tuple(paths), source=source, rules=rules)


def _unique_fields(pairs):
    """json keeps the last of two equal keys; a second "hosts" list must not replace the first unnoticed."""
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ScopeManifestError(f'Scope field "{key}" appears more than once')
        fields[key] = value
    return fields


def load_scope(path: str | None = None, root: str | None = None, env=None) -> Scope:
    """Read and validate the scope manifest. Raises ScopeManifestError; never returns a partial scope."""
    source = manifest_path(path, root, env)
    try:
        if not stat.S_ISREG(os.stat(source).st_mode):
            raise ScopeManifestError(f"Scope manifest is not a regular file: {source}")
        with open(source, "rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)     # the limit applies to what is actually read
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ScopeManifestError(f"Scope manifest is larger than {MAX_MANIFEST_BYTES} bytes: {source}")
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_fields)
    except FileNotFoundError:
        raise ScopeManifestError(
            f"No lab scope is declared ({source} does not exist). Copy console/scope.example.json to "
            f"scope.json, or point ${SCOPE_ENV} at your manifest, and list only targets you may test") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ScopeManifestError(f"Scope manifest cannot be read: {source} ({exc})") from None
    except json.JSONDecodeError as exc:
        raise ScopeManifestError(f"Scope manifest is not valid JSON: {source} (line {exc.lineno})") from None
    except RecursionError:
        raise ScopeManifestError(f"Scope manifest is nested too deeply: {source}") from None
    return parse_scope(data, source=source)


# ── Targets ──────────────────────────────────────────────────────────────────

def _address(text: str) -> str | None:
    """An IP literal in its normalized form, or None when ``text`` is not one. Raises ValueError for a zone."""
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if getattr(address, "scope_id", None):
        # fe80::1%eth0 and fe80::1%wlan0 can be different machines; rules carry no interface
        raise ValueError("the address carries an interface zone (%...), which the scope cannot express")
    return str(_unmapped(address)).lower()


def normalize_host(target: str) -> str:
    """The bare host of an address, host name, host:port or URL, lower-cased. Raises ValueError."""
    text = target.strip()
    if not text or _has_control(text) or any(c.isspace() for c in text):
        raise ValueError("the host is empty or contains whitespace or control characters")
    if "\\" in text:
        raise ValueError("the host contains a backslash")
    if not text.isascii():
        raise ValueError("the host is not ASCII; write internationalized names in punycode (xn--)")
    bracketed = text.startswith("[") and text.endswith("]")
    bare = text[1:-1] if bracketed else text
    if bracketed and ":" not in bare:
        raise ValueError("square brackets are only for IPv6 addresses")
    if "[" not in bare and "]" not in bare:  # a bare address, including unbracketed IPv6
        address = _address(bare)
        if address:
            return address
    try:
        parts = urllib.parse.urlsplit(text if "://" in text else "//" + text)
        host = parts.hostname
        parts.port                           # raises ValueError for a port that is not a number
    except ValueError as exc:
        raise ValueError(f"the host cannot be parsed ({exc})") from None
    if parts.scheme == "file":
        raise ValueError("a file URL names a local path, not a network host; check it as a path")
    if not host:
        raise ValueError("no host was found in the target")
    host = host[:-1] if host.endswith(".") else host
    address = _address(host)
    if address:
        return address
    if not _HOSTNAME.match(host) or len(host) > 253:
        raise ValueError("the host is not a valid address or host name")
    if all(_NUMERIC_LABEL.match(label) for label in host.split(".")):
        raise ValueError("the host is a non-standard numeric address; write it as a dotted IPv4 address")
    return host


def _match_host(scope: Scope, target: str):
    host = normalize_host(target)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        for rule, network in scope.networks:
            if address.version == network.version and address in network:
                return host, rule
        return host, None
    for rule, name in scope.hostnames:
        if host == name or (name.startswith(".") and host.endswith(name) and len(host) > len(name)):
            return host, rule
    return host, None


def _match_package(scope: Scope, target: str):
    package = target.strip()
    if not _PACKAGE.match(package) or len(package) > 255:
        raise ValueError("the app id is not a valid package or bundle identifier")
    for rule in scope.packages:
        if package == rule or (rule.endswith(".*") and package.startswith(rule[:-1])):
            return package, rule
    return package, None


def _match_device(scope: Scope, target: str):
    serial = target.strip()
    if not _DEVICE.match(serial):
        raise ValueError("the device serial is empty or contains unexpected characters")
    for rule in scope.devices:
        if serial == rule or (rule.endswith("*") and serial.startswith(rule[:-1])):
            return serial, rule
    return serial, None


def _match_path(scope: Scope, target: str, base_dir: str | None = None):
    text = target.strip()
    if not text or "\0" in text:
        raise ValueError("the path is empty or contains a NUL byte")
    # Resolved the way the operating system would open it: relative to the working directory,
    # no "~" expansion. realpath follows links, so a link in the lab folder that points outside is refused.
    resolved = os.path.realpath(os.path.join(base_dir or os.getcwd(), text))
    probe = os.path.normcase(resolved)
    for rule, folder in scope.paths:
        allowed = os.path.normcase(folder)
        try:
            if os.path.commonpath([allowed, probe]) == allowed:
                return resolved, rule
        except ValueError:                   # different drives on Windows
            continue
    return resolved, None


_MATCHERS = {"host": _match_host, "package": _match_package, "device": _match_device, "path": _match_path}
_LABELS = {"host": "host", "package": "app", "device": "device", "path": "path"}
_RULE_KEYS = {"host": "hosts", "package": "packages", "device": "devices", "path": "paths"}


def check(kind: str, target, scope: Scope | None = None, *, today: _dt.date | None = None) -> Decision:
    """Decide whether ``target`` is in scope. Never raises for a refused or malformed target.

    With no ``scope`` the manifest is loaded from its default location; a missing or invalid
    manifest is a refusal, not an error.
    """
    shown = target if isinstance(target, str) else repr(target)
    shown = shown if len(shown) <= 200 else shown[:200] + "..."
    if kind not in KINDS:
        return Decision(False, str(kind), shown, f"Refused: unknown target kind {kind!r}; use one of {', '.join(KINDS)}")
    if not isinstance(target, str) or len(target) > MAX_TARGET:
        return Decision(False, kind, shown, f"Refused: the {_LABELS[kind]} must be a string of at most {MAX_TARGET} characters")
    if _has_control(target):                 # the tool would use the raw value, not a cleaned-up copy
        return Decision(False, kind, repr(shown), f"Refused: the {_LABELS[kind]} contains control characters")
    if target != target.strip():
        return Decision(False, kind, repr(shown), f"Refused: the {_LABELS[kind]} has leading or trailing whitespace")
    if scope is None:
        try:
            scope = load_scope()
        except ScopeManifestError as exc:
            return Decision(False, kind, shown, f"Refused: {exc}")
    where = f'the lab scope "{scope.name}"'
    if scope.expired(today):
        return Decision(False, kind, shown,
                        f"Refused: {where} expired on {scope.expires.isoformat()}; renew the authorization before testing")
    try:
        normalized, rule = _MATCHERS[kind](scope, target)
    except ValueError as exc:
        return Decision(False, kind, shown, f"Refused: {exc}")
    if rule is not None:
        return Decision(True, kind, normalized, f'In scope: {_LABELS[kind]} {normalized} matches "{rule}" in {where}', rule)
    declared = scope.rules.get(_RULE_KEYS[kind]) or []
    listed = ", ".join(declared[:8]) + (" ..." if len(declared) > 8 else "") if declared else "none declared"
    return Decision(False, kind, normalized,
                    f"Refused: {_LABELS[kind]} {normalized} is outside {where}. "
                    f"Allowed {_RULE_KEYS[kind]}: {listed}. Only test targets you own or are authorized to assess")


def assert_in_scope(kind: str, target, scope: Scope | None = None, *, today: _dt.date | None = None) -> Decision:
    """Return the decision for an in-scope target; raise ScopeError with the reason otherwise."""
    decision = check(kind, target, scope, today=today)
    if not decision.allowed:
        raise ScopeError(decision.reason, decision.kind, decision.target)
    return decision


def in_scope(kind: str, target, scope: Scope | None = None) -> bool:
    return check(kind, target, scope).allowed


def scope_status(root: str | None = None, path: str | None = None, env=None,
                 today: _dt.date | None = None) -> dict:
    """What the console shows: whether a scope is declared, its counts and why it is unusable."""
    source = manifest_path(path, root, env)
    try:
        scope = load_scope(path, root, env)
    except ScopeManifestError as exc:
        return {"declared": os.path.isfile(source), "valid": False, "source": source, "error": str(exc)}
    expired = scope.expired(today)
    return {
        "declared": True, "valid": True, "source": source,
        "name": scope.name, "authorization": scope.authorization,
        "expires": scope.expires.isoformat() if scope.expires else None, "expired": expired,
        "counts": {key: len(scope.rules[key]) for key in ("hosts", "packages", "devices", "paths")},
        "rules": scope.rules,
        "error": f"The scope expired on {scope.expires.isoformat()}" if expired else None,
    }


# ── Command line ─────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scope_guard.py", description="Check a target against the declared os-lab scope.")
    parser.add_argument("--scope", metavar="FILE", help=f"scope manifest (default: ${SCOPE_ENV} or scope.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("check", help="exit 0 if the target is in scope, 1 if it is refused")
    one.add_argument("--json", action="store_true", help="print the decision as JSON")
    one.add_argument("kind", choices=KINDS)
    one.add_argument("target")
    show = sub.add_parser("show", help="print the declared scope; exit 2 if it is missing or invalid")
    show.add_argument("--json", action="store_true", help="print the status as JSON")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    for stream in (sys.stdout, sys.stderr):      # a refused target may not fit the console encoding
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")

    if args.command == "show":
        status = scope_status(path=args.scope)
        if args.json:
            print(json.dumps(status, indent=2, ensure_ascii=False))
        elif not status["valid"]:
            print(status["error"], file=sys.stderr)
        else:
            print(f'{status["name"]}  ({status["source"]})')
            print(f'authorization: {status["authorization"]}')
            print(f'expires: {status["expires"] or "no end date"}' + ("  EXPIRED" if status["expired"] else ""))
            for key, entries in status["rules"].items():
                print(f'{key}: {", ".join(entries) if entries else "none"}')
        return 0 if status["valid"] and not status["expired"] else 2

    try:
        scope = load_scope(args.scope)
    except ScopeManifestError as exc:
        if args.json:
            print(json.dumps(Decision(False, args.kind, args.target, f"Refused: {exc}").to_dict(), ensure_ascii=False))
        else:
            print(f"Refused: {exc}", file=sys.stderr)
        return 2
    decision = check(args.kind, args.target, scope)
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False))
    else:
        print(decision.reason, file=sys.stdout if decision.allowed else sys.stderr)
    return 0 if decision.allowed else 1


if __name__ == "__main__":
    sys.exit(main())
