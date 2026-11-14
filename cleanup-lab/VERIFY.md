# Cleanup Lab verification record

One section per task: the commands that were run, their real output, and anything
that was not run and why. The checks in
[`README.md`](README.md#definition-of-a-good-pr) and [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
apply; this file is the evidence, not a second contract.

## CLN-01 — skeleton: engine, labctl, readiness endpoint

Branch `feat/cln-01-cleanup-skeleton`. Scope of this PR: engine, console API,
`labctl`, tests, knowledge graph. The dashboard page lives in the handoff section
of `STATUS.md` (this environment cannot write under `dashboard/`; see the session
log there).

### Engine unit tests

```console
$ cd cleanup-lab/engine && ../../.venv-test/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 29 tests in 0.048s
OK
```

Covers: platform mapping, per-OS state and Trash paths, the `OSLAB_CLEANUP_STATE`
override, relative XDG values being ignored, dangling-symlink and non-directory
components, the "never writes the state folder" rule, Python 3.11 exactly (the
`(3, 11, 0) >= (3, 11)` boundary), an unusable Trash, a group-readable state
folder, old-Python and unsupported-OS states, missing home folder, detector
counting, fake `PATH` lookups, the Windows Recycle Bin entry, control-character
escaping in CLI output, and the CLI exit codes (`0` ready / `1` problem / `2` usage).

### CLI

```console
$ ./labctl cleanup status
Cleanup Lab 0.1.0 · macOS · ready
  [ok] Supported operating system       macOS
  [ok] Python 3.11 or newer             3.15.0
  [ok] Home folder readable             /Users/Q
  [ok] Trash available                  /Users/Q/.Trash
  [ok] Private state folder writable    /Users/Q/Library/Application Support/os-lab/cleanup

Capabilities:
  [--] Detector catalog                 No detector catalog yet
  [--] Native scan backend              Reference crate present; not wired into the app yet
  [--] Container engine                 No docker or podman on PATH
  [ok] Package managers                 pip3 at /usr/bin/pip3
  [ok] Simulator tools                  xcrun at /usr/bin/xcrun
$ echo $?
0
```

`./labctl cleanup doctor` adds `Paths:` and a `Hints:` block with every
requirement's hint (failed ones marked `(needs attention)`); `--json` prints the same
payload as the HTTP endpoint. `bash -n labctl` parses.

### Console endpoint

```console
$ .venv/bin/python android-lab/lab/web_ui.py 5099 &
$ curl -sS -i http://127.0.0.1:5099/api/cleanup/status | head -5
HTTP/1.0 200 OK
Server: BaseHTTP Python/3.15.0
Date: Fri, 13 Nov 2026 00:40:46 GMT
Content-Type: application/json

$ curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5099/api/cleanup/nope
404
$ curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:5099/api/cleanup/status?x=1'
400
$ curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5099/health/
200
```

Payload: `engine`, `state` (`ready` / `needs-setup` / `unavailable`), `platform`,
`home`, `stateDir`, `requirements[]`, `capabilities[]`, `reasons[]`, `checkedAt`.
On this Mac: `state: ready`, five requirements found, detector catalog absent
(CLN-02 has not landed), no reasons.

### Repository checks

```console
$ ./scripts/run-tests.sh
...
8 passed, 1 failed, 1 skipped
```

* `[ok] cleanup-lab/engine` — the new stage.
* `[ok] cleanup-lab/reference/python`, `[ok] source-lab/engine test suite`.
* `[ok]` bash -n (499 scripts), `lat check`, dashboard typecheck and
  `dashboard/dist matches the sources`.
* `[fail] android-lab/lab test suite` — **pre-existing on this arm64 Mac**, proved
  by running the same suite on a clean `master` worktree:

  ```console
  # branch feat/cln-01-cleanup-skeleton
  4 failed, 139 passed, 2 skipped, 10 errors in 12.42s
  # master (git worktree add .worktrees/cln01-baseline master)
  5 failed, 138 passed, 2 skipped, 10 errors in 17.47s
  ```

  The failing ids are the same set (three `test_app_update` download cases, one
  `test_web_ui` plan-token case, ten `test_content` OpenSSL signing cases); the
  branch has one fewer because `test_source_console` needs the primary checkout.
  No new failure.
* `[skip] cargo not installed` — `cargo` is only at `~/.cargo/bin`, which is not on
  `PATH` for this shell. This PR changes no Rust code; CLN-21/22 must run it.

```console
$ lat check
All checks passed in 222ms
$ git diff --check
$ echo $?
0
```

### Not run

* `npm run test:e2e` — this PR changes nothing under `dashboard/`, and Playwright
  browsers are not installed on this machine (no `~/Library/Caches/ms-playwright`).
* Dashboard screenshots — same reason, and the page is the handoff, not this PR.

## CLN-02 — detector catalog format, loader and Qleaner parity

Branch `feat/cln-02-catalog`. Scope: catalog data + schema, loader, parity table,
CLI and console endpoint. No dashboard file is touched.

### Engine unit tests

```console
$ cd cleanup-lab/engine && ../../.venv-test/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 47 tests in 0.023s
OK
```

18 new cases: template expansion (`~`, `{home}`, `{cache}`, `${VAR}`,
`${VAR:-fallback}`, `%VAR%`, unavailable context, relative path), per-platform
filtering, duplicate ids across files, a pre-selected `high`/`credentials`/`privacy`
entry refused, nine malformed-entry cases, bad file version, and `path: null` with a
reason instead of a guess. `SchemaTest` asserts the loader's required keys equal
`schema.json`'s and that every catalog file uses only declared fields.

### CLI

```console
$ ./labctl cleanup catalog
Cleanup Lab catalog · macos · 3 entries
  system.user-caches     User caches                low         pre-selected
      /Users/Q/Library/Caches
  system.user-logs       User logs                  low         pre-selected
      /Users/Q/Library/Logs
  system.trash           Trash                      medium      not pre-selected
      /Users/Q/.Trash
$ echo $?
0
```

`--json` prints the same payload as the endpoint.

### Console endpoint

```console
$ python3 -c '…CleanupAPI(".").get("/api/cleanup/catalog", {})…'
entries: 3 platform: macos
query -> 400 Unexpected query parameters
broken -> 500 The detector catalog is invalid: system.json: entry nope is missing name, category, risk,
```

The broken-catalog case uses a generated temp catalog, not the repository one.

### Repository checks

```console
$ ./scripts/run-tests.sh
8 passed, 1 failed, 1 skipped
```

The failure is still the android suite, pre-existing on this arm64 Mac (a clean
`master` worktree: 5 failed + 10 errors; this branch: 5 failed + 10 errors, same ids).
`cargo` is not on `PATH`, so qrust-scan is skipped; this PR changes no Rust.

```console
$ lat check
All checks passed in 538ms
$ git diff --check
(clean)
```

### Not run

`npm run check|test:i18n|build|test:e2e` — no file under `dashboard/` changed, and
Playwright browsers are not installed here.

## CLN-12 — one safety guard for every destructive call

Branch `feat/cln-12-safety-guard`. Scope: `cleanup_lab/safety.py` and its tests; the
modules that will call it are CLN-13 (plan) and CLN-15 (run).

### Engine unit tests

```console
$ cd cleanup-lab/engine && ../../.venv-test/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 69 tests in 0.144s
OK
```

22 new cases: path inside / equal to / outside its catalog root, a sibling with the
same prefix (`caches-old` vs `caches`), the valid name `a..b` that Qleaner's
`contains("..")` rejected, a symlink resolving outside the root, protected roots (`/`
and home), a missing path, a foreign owner (injected `lstat`), a running owning app,
whole-name vs basename process matching, the Windows `tasklist` CSV parser, a failing
process listing, scan-folder validation, copy pairs, the refusal codes, and a check
that every shipped catalog entry resolves to a non-protected path.

### Repository checks

```console
$ ./scripts/run-tests.sh
8 passed, 1 failed, 1 skipped
```

The failure is the android suite, pre-existing on this arm64 Mac (same ids on a clean
`master` worktree); `cargo` is not installed, so qrust-scan is skipped and no Rust
changed.

```console
$ lat check
All checks passed in 318ms
$ git diff --check
(clean)
```

### Not run

`npm` checks — no `dashboard/` file changed. Process matching was exercised with
injected tables on this macOS host; no Windows or Linux host ran the `tasklist` path.

## CLN-22 — harden qrust-scan

Branch `feat/cln-22-qrust-scan-hardening`. Rust only, under `cleanup-lab/reference/qrust-scan/`.

One failing test per gap, written first (`tests/hardening.rs`, `walk::tests`). Before the
fix the four ignore-stack tests failed and the 20 000-deep glob test aborted with
`thread ... has overflowed its stack`. After:

```console
$ cd cleanup-lab/reference/qrust-scan && cargo test
test result: ok. 6 passed   (unit: platform, walk)
test result: ok. 9 passed   (tests/hardening.rs)
test result: ok. 12 passed  (tests/scan.rs)
$ cargo clippy --all-targets -- -D warnings
Finished `dev` profile
$ cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings
Finished `dev` profile
$ cargo fmt --check
(clean)
```

Covers: a nested `.gitignore` applying below its own folder only; a deeper file re-including
what a parent ignored; `.git/info/exclude`; the global excludes file as lowest priority;
no re-inclusion below an ignored folder; a 12 000-deep glob; pre-order and prune-on-match
unchanged; `target/` without `Cargo.toml` rejected; Rust, Maven, Node, venv and
`CACHEDIR.TAG` signatures proved (and a `.venv` without `pyvenv.cfg`, or a tag without the
signature, rejected); thread-pool failure returned as an error; `entry_count` saturating.

### Not run

The Windows target was type-checked and linted only; no Windows host ran the tests. The
Rust and Python signature tables are kept in step by hand (same ids), not by a shared file.

## CLN-03 — scan job: bounded-parallel size scan with progress and cancel

Branch `feat/cln-03-scan-jobs`. Engine, console API, tests and the knowledge graph.
The scan is read-only; no file under `dashboard/` changed (the page is CLN-16, and
the endpoint contract, states and strings are in the CLN-03 handoff in `STATUS.md`).

### Engine unit tests

```console
$ cd cleanup-lab/engine && ../../.venv-test/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 88 tests in 0.149s
OK
```

Covers: apparent and on-disk sizes from a generated tree; a symlink inside the tree
and a top-level symlink never followed; a symlink loop terminating; hard links
counted once across parallel paths (thread-safe inode set); a mode-000 file still
sized because only `lstat` is used; a permission-denied directory reported in
`unreadable` without failing the scan; missing path and unset-variable reasons; a
FIFO not measured; cancel mid-walk and before start (partial counters,
`cancelled: true`, phase `cancelled`); progress keys and totals; one and four
workers agreeing; the shipped catalog against a fake `HOME`.

### Console tests

```console
$ cd android-lab/lab && ../../.venv-test/bin/python -m pytest tests/test_cleanup_console.py -q
5 passed in 0.62s
```

Covers: a real scan job from `POST /api/cleanup/scan` to
`GET /api/cleanup/jobs/<id>`; refusal of a path list, unknown keys, duplicate or
unknown ids, non-string ids and out-of-range workers (`400`); unknown job and
endpoint (`404`); cancel reaching a running scan and mapping to `cancelled`; the
browser route (`X-OSLab`) starting, polling and cancelling a job.

### End to end over HTTP (generated temp `HOME`)

```console
$ curl -sS -X POST -H 'Content-Type: application/json' -H 'X-OSLab: 1' \
    -d '{"entryIds":["system.user-caches"],"workers":1}' \
    http://127.0.0.1:5098/api/cleanup/scan
HTTP/1.0 202 Accepted
{"id":"2b8cc9ba670f","kind":"scan","state":"running",...}

$ curl -sS http://127.0.0.1:5098/api/cleanup/jobs/2b8cc9ba670f
{
  "id": "2b8cc9ba670f",
  "kind": "scan",
  "state": "done",
  "progress": {"phase": "done", "pathsDone": 1, "pathsTotal": 1,
               "bytesSeen": 40960, "filesSeen": 1, "currentPath": ".../Library/Caches/demo"},
  "error": null
}
totals: {'sizeBytes': 40960, 'sizeOnDiskBytes': 40960, 'files': 1, 'folders': 2,
         'paths': 1, 'unreadable': 0, 'entries': 1}
path:   {'path': '.../Library/Caches', 'measured': True, 'sizeBytes': 40960,
         'files': 1, 'folders': 2, 'unreadable': []}

$ curl -sS -o /dev/null -w '%{http_code}\n' -X POST -H 'X-OSLab: 1' -d '{}' \
    http://127.0.0.1:5098/api/cleanup/jobs/2b8cc9ba670f/cancel
200
$ ... POST /api/cleanup/scan with {"path":"/tmp"}           -> 400
$ ... GET  /api/cleanup/jobs/nope                           -> 404
$ ... GET  '/api/cleanup/jobs?x=1'                          -> 400
```

The server ran with `HOME` pointing at a `mktemp -d` tree; no real user folder was
scanned.

### Repository checks

A completed `./scripts/run-tests.sh` run reported **8 passed, 2 failed, 0 skipped**:

* `[ok] cleanup-lab/reference/python`, `[ok] cleanup-lab/engine`,
  `[ok] cleanup-lab/reference/qrust-scan`, `[ok]` sample smoke, `[ok]` `bash -n`
  (125 scripts), `[ok]` dashboard typecheck, `[ok]` `dashboard/dist matches the
  sources`.
* `[fail] android-lab/lab test suite` — **pre-existing**, proved by running the
  same six failing ids on a clean `master` worktree:
  `6 failed, 56 passed, 1 skipped` (three `test_app_update` download cases,
  `test_jadx_decompiler_on_real_dex`, `test_source_console` mutation guards,
  `test_web_ui` plan preview). The branch's full-suite result was
  `6 failed, 153 passed, 1 skipped`; no new failure. The new
  `test_cleanup_console.py` passes.
* `[fail] lat check` in that run — the CLN-03 section summary exceeded the
  250-character lead limit. Shortened; re-run:

```console
$ lat check
All checks passed in 146ms
```

The full suite was not re-run after that one-line documentation fix (maintainer
instruction). No code changed.

### Not run

`npm run test:e2e` and dashboard screenshots — nothing under `dashboard/` changed
and this PR adds no page. `cargo clippy`/`fmt` — no Rust changed. No Windows host
ran the POSIX permission and FIFO tests; they are skipped there by design.

## CLN-13 — plan → confirm → clean, Trash by default, honest results

Branch `feat/cln-13-plan-confirm-clean`. Engine, console API, tests and the
knowledge graph. No file under `dashboard/` changed; the page and its confirm step
are CLN-16 and the contract is in the CLN-13 handoff in `STATUS.md`.

### Engine unit tests

```console
$ cd cleanup-lab/engine && ../../.venv-test/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 112 tests in 1.059s

OK
```

The 24 new tests cover: a read-only plan that lists sizes and marks ready items;
the safety guard skipping running apps and privileged entries; duplicate and nested
paths yielding to the first item; a FIFO planned as not cleanable; a cancelled plan
build making no plan; the Trash never being moved into itself; planning leaving
mtimes untouched; Trash by default with collision names; a **failed Trash staying a
failure** (the original remains, no bytes counted); transient `EBUSY` retries with
backoff; partial failure across two entries; cancel between items; cross-volume copy
verified before removing the source; a failed source removal keeping the verified
copy; the freedesktop `.trashinfo` sidecar on Linux; explicit delete mode; changed,
added and vanished items expiring the plan; the TTL clock; planned skips carrying
reasons and zero bytes; and invalid requests/worker bounds.

### Console tests

```console
$ cd android-lab/lab && ../../.venv-test/bin/python -m pytest tests/test_cleanup_console.py -q
..........                                                               [100%]
10 passed in 1.21s
```

Covers: a real plan job previewed and cleaned from the console (job kinds, ready
size, Trash move, counted bytes, Trash path, recent jobs); typed refusal of a path,
command, unknown key, empty/duplicate/unknown ids, bad mode/workers and bad
`planId`; a changed item failing the clean with nothing removed; a plan being
single-use (`409`) and expiring (`410`); and the browser route starting both a
plan and a clean with `202`, polling to `done`.

### Repository checks

```console
$ PATH=.../.venv-test/bin:$PATH CARGO_TARGET_DIR=/Volumes/Projects/iQ/.cargo-target-cln13 \
    ./scripts/run-tests.sh --no-venv
...
6 failed, 158 passed, 1 skipped in 21.50s
[fail] android-lab/lab test suite
[ok]   source-lab/engine test suite         176 passed
[ok]   cleanup-lab/reference/python          35 tests, OK
[ok]   cleanup-lab/engine                    112 tests, OK
[ok]   cleanup-lab/reference/qrust-scan      27 tests, OK
[ok]   sample analysis + report generated
[ok]   all 70 shell scripts parse
[ok]   lat check
[skip] dashboard dependencies not installed
7 passed, 1 failed, 1 skipped
```

The only failure is the known android stage: the same six ids as `master`
(`test_app_update` ×3, `test_jadx_decompiler_on_real_dex`, the
`test_source_console` mutation guard, the `test_web_ui` plan preview), with the
suite at `158 passed` thanks to the ten console tests. The dashboard stage was
skipped because this worktree has no `node_modules`; nothing under `dashboard/`
changed. `lat check` also ran clean on its own:

```console
$ lat check
All checks passed in 456ms
$ git diff --check
(clean)
$ python -m py_compile cleanup-lab/engine/cleanup_lab/clean.py console/cleanup_api.py \
    android-lab/lab/web_ui.py android-lab/lab/tests/test_cleanup_console.py
(ok)
```

### Not run

`npm run check` / `build` / `test:e2e` and dashboard screenshots — no dashboard
file changed and this worktree has no Node dependencies; the page is CLN-16. Rust
`fmt`/`clippy` — no Rust changed. No Windows host ran the cross-volume and
freedesktop-Trash paths; those use injected tests.

## CLN-16 — cleanup dashboard pages

Branch `codex/cln-16-cleanup-dashboard` from master `6656ed55`, independent of
CLN-15 PR #140. Adds `/cleanup/`, `/cleanup/results/`, `/cleanup/leftovers/` and
`/cleanup/history/` in all eight route sets, with local typed API calls and a
read-only public Pages view. The history route expects CLN-15 to merge first.

`npm run check`, `npm run test:i18n`, and `npm run build` passed. The new mocked
API e2e passed for scan, plan, confirm, clean, results, leftovers and history.
A Pages build under `/os-lab` passed the Turkish route e2e with no API calls or
clean controls. `scripts/deploy-page.sh --dry-run` retained all 32 cleanup routes.
`lat check` and `git diff --check` passed.

The generated How to use command inventory needed the existing Cleanup Lab
`labctl` help text; it was refreshed with `build-how-to-use-reference.py` and
the dashboard was rebuilt. The full `npm run test:e2e` run then passed with
44 passed, 1 skipped.

## CLN-05 — browser caches and privacy data

Branch `codex/cln-05-browser-caches` from master `6656ed55`. The catalog
includes Chrome, Edge, Brave, Opera, Vivaldi, Firefox and Safari caches on
their applicable operating systems. Chrome history and extension traces are
privacy-class entries and never pre-selected. Browser process names feed the
existing running-app lock. `profile-glob` expands all matching local profiles;
the guard refuses a candidate whose symlink resolves outside the catalog root.

Disposable-home fixtures cover Chrome Default, numbered and guest profiles,
Firefox profiles, process locks, symlink escape, privacy defaults and per-OS
template expansion. The engine suite passed 116 tests. Native Windows browser
profile scanning was not run on this macOS host.

## CLN-04, CLN-06 … CLN-29

## CLN-04 — system detections

Branch `codex/cln-04-system-caches` from master `6656ed55`. The system catalog
now has per-OS paths for account caches and logs, per-item temporary data,
crash reports, font caches and macOS Spotlight indexes. A temp detector
enumerates immediate children of catalog roots while omitting symlinks, lock,
socket and pid names, and regular files below 1 KiB. Spotlight expands indexes
on mounted volumes. Shared temp and Spotlight are privileged and never
pre-selected; the current unprivileged plan reports them as skipped.

Generated-tree fixtures cover macOS and Linux temp scanning, Windows path
expansion, and multiple macOS Spotlight volumes. The engine suite passed 115
tests. `lat check`, JSON parsing and `git diff --check` passed. Native Windows
scanning was not run on this macOS host.

## CLN-05 … CLN-29

## CLN-06 — developer tool and package-manager caches

Branch `codex/cln-06-developer-caches` from master `6656ed55`. Adds 47
developer entries with per-OS defaults, credential risk and non-cleanable
toolchain/local-cluster entries. Optional binary presence uses `shutil.which`
with the supplied `PATH`, never `sh -c`; nvm and virtualenvwrapper use their
directories because they may be shell functions. CLN-25 adds dynamic cache
resolution from environment and fixed-argv probes.

Generated-home tests cover XDG/macOS/Windows paths, a fake npm binary, absent
pnpm, credential defaults and plan refusal for toolchains. The engine suite
passed 115 tests. Native Windows scanning was not run on this macOS host.

## CLN-25 — dynamic developer cache locations

Branch `codex/cln-25-dynamic-cache-paths` builds on CLN-06. Catalog metadata
allows an environment cache root or a fixed, allowlisted tool probe before the
per-OS default. Probes use no shell, have a five-second timeout and accept only
one absolute, non-root, non-home path. The path source is carried through
catalog, scan, plan and result records. Fake environment/probe tests cover
precedence, fallback, path rejection, toolchain exclusion and the probe runner.
The CLN-16 results and plan pages show the resolved path source; the dashboard
browser test exercises the source label with a typed scan, plan and clean job.

## CLN-04, CLN-05, CLN-07 … CLN-29

## CLN-11 — package review suggestions

Fixed-argv Homebrew, pip3 and gem inventory calls are read-only and use a
15-second timeout. Captured-style output fixtures verify Homebrew dry-run
formulae, pip JSON and RubyGems local names, plus malformed pip output and
missing tools. Each result carries a typed uninstall argv without running it;
names beginning with options are rejected. Console tests reject caller-supplied
argv and return a job. Pip and gem candidates are for review, not proven
orphans.

## CLN-09 — macOS leftover signatures

The scanner reads `Info.plist` with `plistlib` and scans catalog roots without
following symlinks. Exact bundle ids and dotted children, whole team-id prefix,
and normalized app name are separate evidence rules. A generated tree verifies
that `com.acme.editor2` and `Acme Editor Pro` do not match `com.acme.editor` or
`Acme Editor`. Fixtures also cover hidden apps, large app data, symlink skips,
and an empty installed inventory returning `unknown`. The console endpoint
rejects free-form paths and returns a job. All findings are report-only.

## CLN-10 — Linux and Windows leftover signatures

Linux inventory uses fixed argv for dpkg, rpm, Flatpak and Snap and scans
configured XDG config, share and cache roots. Windows inventory reads uninstall
registry keys and scans configured AppData roots. Both use CLN-09's confidence
rules and return report-only findings. Generated fixtures prove exact `firefox`
and Flatpak id matches, a `firefox-old` near miss, an inventory failure yielding
`unknown`, and Windows `Acme Editor` versus `Acme Editor Pro`. Console tests
reject free-form paths on the general typed scan endpoint.
After merging master, the engine suite passed 154 tests and the console
contract passed 16. The Linux/Windows dashboard panel shows report-only
findings and inventory uncertainty; its browser test checks the typed request,
unknown status and absence of a delete action. Dashboard type, translation,
build and browser checks pass with all seven translated catalogs updated.

## CLN-07 — deep project sweep and Xcode simulators

The sweep accepts configured root ids, scans read-only, checks project marker
files and stops below matched artifacts. A generated tree test covers valid
Node and Rust projects, false `target`/`node_modules` names, a nested artifact
and a symlink loop. Console tests reject paths, unknown ids and malformed age
filters. A fake `xcrun simctl list -j devices` checks fixed argv, timeout,
unavailable devices and measured size. Engine suite: 115 passed; console
contract suite: 11 passed via `uv run --with pytest`. Native Xcode was not
available on this host.

## CLN-24 — proved project artifact signatures

The signature catalog in `catalog/signatures/projects.json` defines 18 project
artifact kinds. The engine validates it and requires regular marker files or a
valid `CACHEDIR.TAG` before reporting a directory. A false `target`, symlink
marker, unmarked virtualenv and invalid cache tag are excluded. A fixture checks
ecosystem, regeneration hint and marker-based idle age. After merging master,
the engine suite passed 146 tests and the console contract passed 13 tests.
No dashboard source changed.

## CLN-15 — private audit history

Branch `codex/cln-15-audit-history` from master `6656ed55`. A clean request
checks that a private state folder, 32-byte per-install key and SQLite store are
usable before claiming the plan. Completed clean results are recorded with their
paths, mode, counted bytes and outcomes. Rows and the chain head have HMAC-SHA256
signatures; `labctl cleanup history --verify` and `GET /api/cleanup/history`
verify the full chain. Changed or removed rows fail verification. Like any local
integrity scheme, restoring an older complete snapshot of both database and key
cannot be distinguished without an external trusted anchor.

```console
$ cd cleanup-lab/engine && ../../.venv-test/bin/python -m unittest discover -s tests -p 'test_*.py'
Ran 118 tests — OK
$ cd android-lab/lab && ../../.venv-test/bin/python -m pytest tests/test_cleanup_console.py -q
10 passed
$ lat check
All checks passed
```

`./scripts/run-tests.sh --no-venv` passed the cleanup engine, reference Python,
Rust, Source Lab, shell syntax, knowledge graph and dashboard typecheck/build
stages. Its Android stage had the same six host or baseline failures recorded for
CLN-13 (three AppImage architecture expectations, invalid `JAVA_HOME` for JADX,
source console mutation guard, and web UI preview status): 6 failed, 158 passed,
1 skipped. No dashboard files changed; CLN-16 owns the history view.

## CLN-08 — container actions and report-only VMs

The container catalog defines four Docker prune scopes and three Podman fallback
scopes. The engine checks every preview/prune argv against a fixed allowlist,
detects a responding engine, hides actions when neither responds, fingerprints
candidate JSON, and re-previews before a single-use action. Volumes are high
risk and never pre-selected. The console prepares signed audit history before
claiming a preview and appends every result. VM bundles are measured read-only
from catalog roots and have no delete endpoint.

A fake Docker executable verifies preview, execution and stale refusal; a fake
Podman verifies fallback. Console tests verify request keys, a successful
single-use prune with history verification, and VM report-only inventory.
After merging master, the engine suite passed 151 tests and the console
contract passed 15. The dashboard client and plain cleanup controls show live
capabilities, candidate previews, risk, command, confirmed prune result and
report-only VM inventory; the browser test covers the typed requests. Dashboard
type, translation, build and browser checks pass with all seven catalogs updated.

## CLN-28 — volumes overview and disk pressure

Branch `feat/cln-28`. Scope: the engine volume inventory, `GET
/api/cleanup/volumes`, `labctl cleanup volumes`, tests, docs. The `/cleanup/`
volumes card is the dashboard layer's part (handoff in `STATUS.md`).
## CLN-20 — privileged targets and disk-access check

Branch `feat/cln-20`. Scope: the privileged-action engine module, the action
catalog, the console endpoints, the readiness capability, the macOS Full Disk
Access probe, tests and docs. The `/cleanup/` privileged card is the dashboard
layer's part (handoff in `STATUS.md`).

### Engine unit tests

```console
$ cd cleanup-lab/engine && python -m unittest discover -s tests -p 'test_*.py'
Ran 178 tests in 1.120s
FAILED (failures=49, errors=37, skipped=4)
```

Baseline discipline: this Windows host fails the same suite on a clean master
worktree **before** any change, with the same counts — the suite carries
platform-specific expectations (macOS path templates, POSIX-only fixtures) that
do not hold on Windows:

```console
# clean origin/master worktree, before this branch's changes
Ran 154 tests in 3.032s
FAILED (failures=49, errors=37, skipped=4)
```

The failing test ids were captured on both runs (`unittest -v` lines starting
with `FAIL:`/`ERROR:`) and compared: 86 ids before, 86 after, diff 0 — **no new
failure**. The 24 new `test_volumes.py` tests (fake mount tables and fake
disks only, per README rule 8) and the existing `test_cli.py` suite (10 tests)
pass on this host.
Ran 180 tests in 1.350s
FAILED (failures=49, errors=37, skipped=4)
```

Same discipline as CLN-28: a clean `origin/master` worktree on this Windows
host fails the same suite before any change (154 tests, failures=49,
errors=37, skipped=4 — platform-specific expectations, pre-existing). The
failing test ids were captured on both runs: **86 ids before, 86 after, diff 0
— no new failure**. The 26 new `test_privilege.py` tests (fake runners, fake
`which`, injected executors — no real sudo/pkexec/osascript/UAC, per rule 8)
pass; the catalog inventory assertion was updated deliberately from 65 to 66
entries for the new `system.shared-font-caches` path and the updated test
passes.

### Console contract

```console
$ python -m pytest android-lab/lab/tests/test_cleanup_console.py -q
1 failed, 10 passed, 7 skipped in 0.89s
```

The failure (`test_container_prune_requires_single_use_preview_and_audits`) is
pre-existing on this host at the baseline (the fake docker binary fixture is
POSIX-shaped); the two new volumes tests pass.

### CLI on this host (real, read-only run)

```console
$ python -c "import sys; sys.path.insert(0, 'cleanup-lab/engine'); from cleanup_lab import cli; print('exit', cli.main(['volumes']))"
Cleanup Lab volumes · windows · 1 volume
  [ok] C:\                          NTFS     root       86% used · home
exit 0
```
1 failed, 10 passed, 7 skipped in 1.18s
```

The failure is the same single pre-existing Windows one recorded at the
baseline (fake docker binary fixture); the two new privileged-endpoint tests
pass.

### Knowledge graph

```console
$ lat check
All checks passed in 950ms
All checks passed
```

### Not run

* `./scripts/run-tests.sh` — this host has no usable bash (the `bash` on PATH is
  the WSL launcher without distributions), so the repo runner cannot start here;
  the targeted suites above are the same stages it would run for this change.
* `npm run check` / `test:i18n` / `build` / `test:e2e` — no dashboard file
  changed; the volumes card is the dashboard-layer handoff.
* Live macOS and Linux collector runs — covered here by the injected
  fake-table tests; on-host confirmation is pending.
* `./scripts/run-tests.sh` — no usable bash on this host (WSL launcher without
  distributions), as recorded for CLN-28; the targeted suites above are the
  stages this change needs.
* Live elevated runs of every action (`apt-get clean` on Linux, `mdutil -E /`
  on macOS, DISM on Windows) — deliberately not executed from a test or agent;
  execution is covered by the injected-executor tests, and the real elevation
  prompts belong to the user, not to CI. The `GET /api/cleanup/privileged`
  capabilities call is safe and returns this host's actions without running
  any of them.
* Dashboard checks — no dashboard file changed; the card is the handoff.

## CLN-27 — relocate caches to another volume behind a symlink

Branch `feat/cln-27`, stacked on `feat/cln-28` (destinations come from the
CLN-28 volume inventory). Scope: the relocation engine module, the console
endpoints, tests and docs. The `/cleanup/` relocation card is the dashboard
layer's part (handoff in `STATUS.md`).

### Engine unit tests

```console
$ cd cleanup-lab/engine && python -m unittest discover -s tests -p 'test_*.py'
Ran 202 tests in 1.634s
FAILED (failures=49, errors=37, skipped=11)
```

The 11 skips are the 4 pre-existing ones plus 7 honest symlinks skips: this
Windows host cannot create symlinks without Developer Mode or a privilege
(WinError 1314), so the executor tests that need a real link skip with that
reason and pass on macOS/Linux hosts. The symlink-failure refusal itself is
tested everywhere by simulating the error. Baseline discipline: a clean
`origin/master` worktree on this host fails the same suite before any change
(154 tests, failures=49, errors=37, skipped=4 — pre-existing,
platform-specific). Failing test ids captured on both runs: **86 before, 86
after, diff 0 — no new failure**. The 24 new `test_relocation.py` tests pass
(including the fake-catalog integration through `build_plan`/`execute`).

### Console contract

```console
$ python -m pytest android-lab/lab/tests/test_cleanup_console.py -q
1 failed, 12 passed, 7 skipped in 0.98s
```

The failure is the same single pre-existing Windows one recorded at the
baseline; the two new relocation-endpoint tests pass.

### Knowledge graph

```console
$ lat check
All checks passed
```

### Not run

* `./scripts/run-tests.sh` — no usable bash on this host (WSL launcher without
  distributions), as recorded for CLN-28/CLN-20.
* Live relocation of a real cache — rule 8: the executor is covered by
  generated-tree tests; a real move belongs to the user, on a host where
  symlinks are available.
* Dashboard checks — no dashboard file changed; the relocation card is the
  handoff.

## CLN-04 … CLN-29

Each task appends its own section when it lands.
