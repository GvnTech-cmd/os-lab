# Repository tooling

Cross-cutting process, tests and conventions for the monorepo: CI, the android
test suite, contribution flow and the project's security/licensing stance.

## Local test runner

The local runner complements enabled browser/content and Linux/macOS package
workflows. Windows review builds do not imply permission to publish without
Authenticode; its workflow requires SignPath or explicit unsigned-release approval.

[[scripts/run-tests.sh]] is the CI replacement. It prepares a Python
environment (a `.venv-test` unless `--no-venv`), runs the pytest suite in
[[android-lab/lab/tests]], runs a sample-analysis smoke test, checks every
shell script with `bash -n`, runs `lat check` when `lat` is installed, and,
when `dashboard/node_modules` exists, typechecks the [[dashboard]] and fails if
the committed `dashboard/dist` differs from a fresh build.
`--quick` runs only the unit tests. The dormant workflow file
[[.github/workflows/mobile-sec-scan.yml]] is kept for reference but is disabled.

## Tests

Android and Source Lab have independent automated test suites.

It lives in [[android-lab/lab/tests]] (analyzer, reporter, MobSF client, secret
scanner, patcher, flow parser, agentic engine, web UI, the host engine in
[[console/oslab.py]] and the [[tooling#Scope guard]]). Shell scripts across the
VM labs are kept `bash -n` clean and use `set -euo pipefail`.
The [[source-lab]] engine tests run in their own process from
[[source-lab/engine]] so their imports cannot collide with Android tests.

## Firewall rule renderer

[[firewall-lab/vm/scripts/render-rules.py]] turns a company's abstract rules into UFW
commands, an nftables ruleset or a vendor-neutral table, so the same ordered policy
can be loaded in the disposable firewall guest.

Port handling follows the declared rule exactly. A comma list becomes an nft
anonymous set (`dport { 22, 443 }`) and stays a UFW multiport list. `proto: any`
with a port means TCP or UDP to those ports (`meta l4proto { tcp, udp } th dport`
in nft, one tcp and one udp command in UFW), never all traffic. A port on `icmp`
is ignored by both backends. Items that are not ports or ascending ranges in
1–65535 (`esp`, `80,,443`, `500:400`) are skipped with a comment and a stderr
warning. Notes and names are flattened to one line before they go into comments.
[[.github/workflows/firewall-lab.yml]] renders every branch of every company and
checks the output with `nft -c` and `bash -n`, and rejects duplicate branch ids.

## Scope guard

[[console/scope_guard.py]] turns the authorization-only rule into code: a lab
tool names the target it is about to touch and is refused unless the declared
lab scope covers it.

A tool calls [[console/scope_guard.py#assert_in_scope]] with a kind (`host`,
`package`, `device` or `path`) and the target, and gets a decision naming the
manifest rule that allowed it, or a `ScopeError` whose message says why it was
refused. [[console/scope_guard.py#check]] returns the same decision without
raising. The module uses only the standard library, never resolves DNS and never
opens a connection, so a decision is the same offline and in tests.

### Manifest

The scope is a JSON file listing the hosts, app ids, device serials and folders
that may be tested, with who authorized it and an optional end date.

[[console/scope_guard.py#load_scope]] reads the `path` argument, then
`$OSLAB_SCOPE_FILE`, then `scope.json` in the checkout (git-ignored;
[[console/scope.example.json]] is the starting point). Validation is strict:
unknown fields, wrong types, a missing `authorization` text and more than 512
entries per list are errors, so a typo cannot silently widen or empty a scope.
A scope must name its targets: `*`, `0.0.0.0/0`, `::/0`, `*.com` and `com.*` are
rejected. Address ranges must be loopback, private or link-local unless the
manifest sets `allowPublic`, which is the written-authorization case.

### Hosts

A host target may be an address, a name, `host:port` or a URL; only its host
part is matched, against addresses, CIDR ranges, exact names and `*.suffix`.

A wildcard covers subdomains at any depth but not the bare domain, and whole
top-level domains are accepted only for reserved lab names such as `.test` and
`.local`. An IPv4-mapped IPv6 address is matched as its IPv4 address. Targets
that could hide another host are refused before matching: user info and
fragments in URLs are not the host, `inet_aton` spellings such as `127.1` or
`2130706433` are not names, and non-ASCII names must be written in punycode.
Names are matched as text, so a tool that connects by name should also check
the address it resolved.

### Apps and devices

App ids and device serials are case-sensitive and match exactly or by a
trailing wildcard: `com.vendor.*` for ids, `emulator-*` for serials.

An id wildcard matches whole dotted parts, so `com.oslab.*` covers
`com.oslab.demo` but not `com.oslabs.demo` or `com.oslab` itself. Anything that
is not a plain id or serial (spaces, shell characters, extra arguments) is
refused rather than matched.

### Paths

A path is in scope when its real location is inside a declared folder; manifest
folders are relative to the manifest, targets to the working directory.

Targets are resolved the way the operating system would open them, with links
followed, so `..`, a sibling folder that shares a name prefix and a link that
leaves the lab folder are all refused. A filesystem root cannot be declared.

### Refusal

The guard fails closed: no manifest, an unreadable or invalid manifest, an
expired scope, an unknown kind or a malformed target are refusals, never passes.

Each refusal states the target, the scope name and the declared rules of that
kind, so the operator can see whether the target or the manifest is wrong.
Control characters are rejected before any trimming because the tool would use
the raw value. A scope is valid through its `expires` date and refuses
everything after it.

### Console and command line

The declared scope is visible without reading the file: `GET /api/scope` on the
local console and `python3 console/scope_guard.py show`.

[[console/oslab.py#scope_status]] reports whether a scope is declared and valid,
its name, authorization, expiry and rule counts; [[android-lab/lab/web_ui.py]]
serves it read-only. The command line checks one target and exits 0 in scope,
1 refused and 2 for a usage or manifest error, with `--json` for agents and
scripts. The tests are in [[android-lab/lab/tests/test_scope_guard.py]].

## Community and contribution

Contribution flow, coding conventions and the authorization stance.

They are in [[CONTRIBUTING.md]], step by step from setup to pull request, and
the [[dashboard]] renders the same file at `/contribute/`. Contributions must not
add vendor binaries or proprietary media (see [[legal#Google platform-tools]]).
The Source Lab migration is tracked in [[source-lab/README.md]], with its plan,
task queue and pinned source inventory. [[source-lab]] records the implemented
engine, console and file-backed dashboard workflows. Remaining native/live
verification and patches are open Source bonus tasks in [[CONTRIBUTING.md]].

Issue and PR templates are in
[[.github/ISSUE_TEMPLATE]] and [[.github/PULL_REQUEST_TEMPLATE.md]]; behavior
expectations in [[CODE_OF_CONDUCT.md]].

## Security and licensing

Private vulnerability reporting and the authorization-only scope.

These are defined in [[SECURITY.md]]; the project is Apache-2.0 ([[LICENSE]]).
The VM base images (`dockur/windows`, `qemux/qemu`, `dockurr/macos`) are MIT and
do not distribute OS media; users are responsible for valid licences.

[[dashboard/scripts/source-brain-model.test.mjs]] validates provider paths, graph
limits/windows and bounded revision diff without a browser.
[[source-lab/RUNBOOK.md]] records the portable release/rollback workflow.
