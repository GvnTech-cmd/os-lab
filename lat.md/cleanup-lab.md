# Cleanup Lab

A disk-cleanup lab: measure reclaimable space, show every item with its size and
risk, and clean only through a confirmed plan. The behaviour is ported from
Qleaner; its code, styling and known bugs are not.

## Layers

The engine is a standard-library Python package; the console and `labctl` are thin
typed layers over it.

The package lives in [[cleanup-lab/engine/cleanup_lab]]. `readiness`, `paths`, the
catalog loader (CLN-02), the scan job (CLN-03), the safety guard (CLN-12) and the
plan → clean executor (CLN-13) and audit history (CLN-15) exist now. `safety.py`
guards filesystem deletion and moves; CLN-08's daemon prune actions use a
separate typed, single-use preview guard.

Target paths are data, never code: every platform path, risk class, owning process
and privilege flag belongs in `cleanup-lab/catalog/*.json` (CLN-02). Per-OS
resolution comes from [[cleanup-lab/engine/cleanup_lab/paths.py]].

[[console/cleanup_api.py]] answers `/api/cleanup/...` with typed, validated calls
and never accepts a command string or a free-form path list from the page.
[[android-lab/lab/web_ui.py]] routes the namespace before the static dashboard
fallthrough. Long work becomes a console job with preview, progress and cancel.

`labctl cleanup status|doctor|history [--json]` runs the same engine through
`cleanup_lab.cli`: exit `0` when ready, `1` when a required check fails, `2` for a
usage error, matching [[lat.md/labctl.md]].

## Catalog

CLN-05 adds [[cleanup-lab/catalog/browser.json]] for Chrome, Edge, Brave,
Opera, Vivaldi, Firefox and Safari.

The `profile-glob` detector expands every matching profile path from catalog
data. Chrome history and extension traces carry `privacy` risk and are never
pre-selected; every browser names its owning process for the running-app guard.

CLN-06 adds [[cleanup-lab/catalog/developers.json]] with per-OS developer cache
defaults, credentials and toolchains.

The catalog reports binary presence through `shutil.which` without a shell.
Shell functions are tracked by their directories. Credential entries are never
pre-selected; toolchains and local clusters have `cleanable: false` and the
plan skips them. CLN-25 resolves developer caches from an environment variable,
an allowlisted fixed-argument tool probe (five-second timeout), or the catalog
default. Invalid probe output falls back safely. The catalog, scan, plan and
result records identify the chosen source for each path.
The cleanup results and plan pages display that source beside the resolved path.


Target paths are data. One JSON file per family under `cleanup-lab/catalog`, validated
against `schema.json`.

[[cleanup-lab/engine/cleanup_lab/catalog.py]] loads it: unique ids, a family prefix,
the known risk classes, and `defaultSelected` refused for `high`, `credentials` and
`privacy`. Templates (`~`, `{cache}`, `${VAR}`, `${VAR:-fallback}`, `%VAR%`) expand per
operating system; an unset variable yields `path: null` plus a reason instead of a
guess. [[cleanup-lab/PARITY.md]] maps every Qleaner detector id to a catalog id or to
why it was dropped, and [[cleanup-lab/catalog/README.md]] documents the format.

## Scan job

CLN-08 offers container and VM detection through typed console endpoints.

[[cleanup-lab/engine/cleanup_lab/containers.py]] reports a responsive Docker
engine or falls back to Podman. It loads fixed preview/prune argv from
[[cleanup-lab/catalog/actions/containers.json]], checks those arguments against
an allowlist, and hides actions when neither engine responds. A preview records
candidate JSON and expires after ten minutes; execution re-previews and refuses
changed candidates. `POST /api/cleanup/containers/prune` accepts only a single-use
preview id, runs as a job and appends its result to the signed audit history.
Volumes are high risk and never pre-selected. `bytesRemoved` remains null when
the engine does not provide a trustworthy byte count.

[[cleanup-lab/engine/cleanup_lab/vms.py]] inventories configured VirtualBox,
VMware, Parallels and UTM locations from [[cleanup-lab/catalog/actions/vms.json]].
Each found bundle is measured read-only and marked `reportOnly`; the API has no
VM deletion action.
[[dashboard/src/views/cleanup/extra-tools.tsx]] shows only actions offered by
the live container engine. It requires a candidate preview before confirmation,
shows risk, command and errors, and reports VM bundles without a delete control.
Public Pages does not request these endpoints.

CLN-04 adds system temp, crash, font and Spotlight catalog entries on the
applicable operating systems. The regular scan remains read-only.

Temp roots enumerate immediate candidates after filtering locks, small files
and symlinks. Spotlight expands indexes on mounted macOS volumes. Shared temp
and Spotlight entries require a later privileged clean flow.

CLN-11 adds read-only package review suggestions.

[[cleanup-lab/engine/cleanup_lab/packages.py]] powers `POST /api/cleanup/packages/scan`, which
accepts no argv or paths and returns a job. Homebrew's `autoremove --dry-run`
identifies unneeded dependencies; pip's `list --not-required --format=json`
and RubyGems' local list identify top-level packages for review. Each result
includes an exact uninstall argv as a preview, but this API has no uninstall
execution endpoint. Missing tools are hidden and parser errors are reported.

CLN-09 adds read-only macOS leftover signatures and a typed scan job.

CLN-10 extends the same identity rules to Linux and Windows. On Linux,
[[cleanup-lab/engine/cleanup_lab/leftovers_cross.py]] queries available dpkg,
rpm, Flatpak and Snap inventories with fixed argv and scans configured XDG
config/share/cache roots. On Windows, it reads uninstall registry keys without
launching a command and scans Roaming and Local AppData. The roots are in
[[cleanup-lab/catalog/signatures/cross-platform-leftovers.json]]. If an inventory
fails, unmatched candidates remain `unknown`; all findings are report-only.
`POST /api/cleanup/leftovers/scan` dispatches by host OS and accepts no paths.
On Linux and Windows, [[dashboard/src/views/cleanup/cross-leftovers.tsx]] uses
that typed job from the leftovers page. It shows inventory sources and errors,
confidence, paths and unreadable items without offering a delete action.

[[cleanup-lab/engine/cleanup_lab/leftovers_macos.py]] reads installed app bundle
ids and optional team ids from `Info.plist` with `plistlib`. It checks candidate
folders under the configured [[cleanup-lab/catalog/signatures/macos-leftovers.json]]
roots by exact bundle id or dotted child, whole team prefix, or normalized app
name. It reports confidence and evidence for potential orphans, hidden apps and
large app data; an empty app inventory produces `unknown` instead of an orphan
claim. `POST /api/cleanup/leftovers/macos/scan` accepts no paths and returns a
job. Every finding is report-only; the endpoint cannot clean it.

CLN-07 adds a read-only project sweep and an Xcode simulator inventory.

[[cleanup-lab/deep-roots.json]] defines selectable root ids; the console accepts
only those ids through `POST /api/cleanup/deep-scan`, with an optional
`minIdleDays` filter, and exposes availability through `GET /api/cleanup/deep-roots`.
The engine stops descending
at a proved `node_modules` or Rust/Maven `target`, measures it without following
links, and reports ecosystem, regeneration hint and project directory age.
`GET /api/cleanup/simulators` reads Xcode's JSON device list with fixed argv,
flags unavailable devices and measures each device directory under the configured
[[cleanup-lab/simulator-roots.json]] root. These are detection results, not
cleanup targets. CLN-24 replaces the first three project checks with marker-verified
signatures from [[cleanup-lab/catalog/signatures/projects.json]].
[[cleanup-lab/engine/cleanup_lab/artifacts.py]] validates the signature data,
refuses symlink markers, checks `CACHEDIR.TAG`, and reports the project's newest
marker age with the ecosystem and regeneration hint.

[[cleanup-lab/engine/cleanup_lab/scan.py]] measures the catalog's resolved paths
read-only, with progress and cancel.

Sizes come from `lstat`; a symlink is never followed or recursed into, a hard link
is counted once per scan by `(device, inode)`, and an unreadable path is reported in
`unreadable` instead of failing the scan. Apparent and on-disk sizes are separate
(on-disk may be `null`). One worker measures one top-level path, at most 16; the
callback is throttled, and a cancel returns the partial counters with
`"cancelled": true`.

## Plan → clean

[[cleanup-lab/engine/cleanup_lab/clean.py]] previews and runs destructive work; only a confirmed, unexpired plan can move a file.

Building is read-only: the guard checks each catalog path, one `lstat` walk records
its size and a fingerprint, and the plan lists every item as ready or skipped with a
reason. `POST /api/cleanup/plan` names catalog ids and an optional mode; `POST
/api/cleanup/clean {planId}` verifies the fingerprints, runs once, and reports
`trashed` / `deleted` / `skipped` / `failed`. Trash is the default; a failed Trash
is a failed item, never a silent delete, and bytes are counted only when the
original is gone.

## Readiness

`readiness.py` reports what the engine can do on this host without writing anything.

[[cleanup-lab/engine/cleanup_lab/readiness.py]] checks the operating system, the
interpreter, the home folder, the Trash target and the private state folder; those
decide `ready`, `needs-setup` or `unavailable`. The detector catalog, the native
scan backend and the tools on `PATH` are optional capabilities, so a missing one
never blocks a scan.

The desktop launcher selects Python 3.11 or newer to satisfy Cleanup Lab. If the
host has only an older interpreter, its Get Python action installs an app-managed
Python 3.12 before the local console starts.

`/cleanup/` renders that probe in the dashboard shell, with scan, plan and clean
actions only when the engine is ready. Public Pages has no engine, so the page
explains local installation without polling, per
[[lat.md/ux-readiness.md]].

## Volumes

CLN-28 adds a read-only volume inventory: [[cleanup-lab/engine/cleanup_lab/volumes.py]]
answers `GET /api/cleanup/volumes` and `labctl cleanup volumes`.

Every local volume is reported with its mount point, filesystem, capacity and
kind (`root` / `internal` / `removable` / `unknown`), the volume holding the
home folder is marked, and usage above 90% raises a pressure warning. Network
and pseudo filesystems are filtered before any capacity call; Windows
enumerates drives through kernel32, Linux reads `/proc/self/mountinfo`, and
macOS parses the fixed `mount` probe plus an optional fixed `diskutil info
-plist` probe. An unreadable volume carries an `error` instead of failing the
probe. The `/cleanup/` volumes card is the dashboard layer's part.

## Privileged actions

CLN-20 adds typed privileged actions: [[cleanup-lab/engine/cleanup_lab/privilege.py]]
previews and runs root-level maintenance through the desktop's own elevation.

System maintenance — `apt-get clean`, a journald vacuum, `apt-get autoremove
--purge`, the Spotlight index rebuild, DISM's component store cleanup — is
never a plan → clean path item: an elevated `rm` would bypass the Trash rules,
so the cleaning happens inside the tool itself, behind the CLN-08 pattern
(fixed argv from a validated allowlist mirrored by
[[cleanup-lab/catalog/actions/privileged.json]], a fingerprinted preview, a
single-use preview id, a fresh candidate check and an audited run). The page
sends an action id and a preview id, never a command string. `GET
/api/cleanup/privileged`, `POST /api/cleanup/privileged/preview` and `POST
/api/cleanup/privileged/run` follow the container contract; readiness gains an
optional `privileged-actions` capability; `system.shared-font-caches` joins
the catalog as a scanned, privilege-flagged Linux path.
`privilege.disk_access()` ports the read-only macOS Full Disk Access probe
with guidance and reports `applicable: False` elsewhere. The `/cleanup/`
privileged card is the dashboard layer's part.

## Relocation

CLN-27 relocates a catalog entry to another volume behind a symlink:
[[cleanup-lab/engine/cleanup_lab/relocation.py]] classifies seven link states
and plans move, restore, relink and resume.

The fixed order — copy → verify (file count + bytes) → rename the original
aside → symlink → verify the link → remove the set-aside original — leaves
either the original or a verified copy at every step. The page sends a catalog
entry id and a destination volume from CLN-28's inventory (`GET
/api/cleanup/relocation` lists both); the store is
`<volume>/oslab-caches/<entry id>`, the pair passes `safety.validate_copy`, the
owning application must not be running, and there is no elevated fallback. An
interrupted move is flagged in the status and continued by a typed resume that
re-verifies the store copy before touching the aside. `POST
/api/cleanup/relocation/plan` and `POST /api/cleanup/relocation/run` follow the
typed preview → single-use job pattern and are audited. The `/cleanup/`
relocation card is the dashboard layer's part.

## Dashboard pages

[[dashboard/src/views/cleanup/pages.tsx]] renders the compact default dashboard at
`/cleanup/`: one read-only catalog scan, measured suggestions, plan review,
confirmation, progress and a result summary. Its confirmation opens the shared
native dialog (focus containment, Escape/backdrop close, focus return) that
lists ready items with sizes and skipped items with their reasons.

The recommended preset uses default-selected, nonprivileged entries outside
high/privacy/credentials risk. The extended preset adds other low/medium risk
entries. Both use the same expiring Trash plan. Detailed catalog selection and
delete mode remain at `/cleanup/scan/`, where entries are selectable cards
carrying only decision info — category icon, risk badge, measured size and a
relative size bar — sorted largest-first once a scan exists or safest-first
(default-selected, then low to high risk) otherwise. Hints, impacts, resolved
paths, sources and the privilege requirement live in the hover/focus popover
from [[dashboard/src/views/cleanup/info-popover.tsx]]; shared formatting and
ordering live in [[dashboard/src/views/cleanup/format.ts]]. The scan page adds
a "Measured space" summary with a stacked bar by risk class, and selection or
mode changes invalidate the plan.

The page renders
category results at `/cleanup/results/`, skipped/failed and unreadable items at
`/cleanup/leftovers/`, and verified audit records at `/cleanup/history/`.

The typed client is in [[dashboard/src/lib/api.ts]]. Each action shows its own
error; the confirm step names the planned item count, size and mode, and a
changed selection, expired plan or used plan requires a new preview. Trash is
the default.

The local app polls only while a job runs. Public Pages renders the routes without
engine calls or destructive controls. All eight route sets are built, including
the seven translated locales.

## Console API

`console/cleanup_api.py` answers `/api/cleanup/...`; the web console routes that prefix
before the static dashboard fallthrough.

`GET /api/cleanup/status`, `GET /api/cleanup/catalog` and `GET /api/cleanup/volumes` are read-only.
`POST /api/cleanup/scan`, `POST /api/cleanup/plan` and `POST /api/cleanup/clean
{planId}` start jobs whose requests carry catalog ids, an optional worker count or
mode, and a plan id only. `GET /api/cleanup/jobs/<id>` returns progress and result;
`POST /api/cleanup/jobs/<id>/cancel` cancels. A request carries no command string and
no free-form path list: an unknown path is `404`, unexpected or duplicate query
parameters, unknown keys or unknown ids are `400`, and a missing engine is `501`.
A stale, expired or already-used plan is `409`/`410` with nothing removed. The job
lives in the console process, and its worker always ends in `done`, `cancelled` or
`failed` — never `running`. `GET /api/cleanup/history` returns the latest 100
verified runs from the private SQLite store. The store writes each completed
clean result with path, bytes, mode and outcome, chaining records with
HMAC-SHA256 and a random per-install key. `labctl cleanup history --verify`
checks the full chain and exits 1 on tampering. History is durable across console
restarts. Later tasks add ignore rules (CLN-17) and
runtimes (CLN-29) here, each typed and validated again by the
engine.

## Safety

The eight rules in the README are the acceptance criteria for every task.

Every destructive call passes through [[cleanup-lab/engine/cleanup_lab/safety.py]]:
the target is resolved with its symlinks and must stay inside its catalog entry's
roots; it is refused when it is a protected or system root, when it is owned by
another account, or when an owning application is running (whole-name match against
the process table, not a Chrome/Firefox substring). `check_target()` returns a
verdict with a stable `code` and an English reason; `assert_safe_target()` raises
the same pair. Scans stay read-only (`lstat`, symlinks never followed). Cleaning is
plan → confirm → run with Trash by default, and a failed Trash never becomes a silent
permanent delete. Credentials and privacy data are never pre-selected. Bytes are
counted only when removed, every skip and failure carries a reason, and every run is
written to the audit history. Tests use generated temp trees and fake binaries,
never real user files.

## Tests

The engine tests run under `unittest` from the engine folder.

`cd cleanup-lab/engine && python3 -m unittest discover -s tests -p 'test_*.py'`
covers the probe, the catalog, the scan, plan → clean (guard, fingerprints,
Trash by default, honest failures), the path rules, the CLI exit codes, the
volume inventory, the privileged actions and the relocation executor.
Tests live in [[cleanup-lab/engine/tests]]; the console's typed job contract is
covered by [[android-lab/lab/tests/test_cleanup_console.py]]. [[scripts/run-tests.sh]]
runs the same suites next to the reference code tests, the Android suite, `bash -n`,
`lat check` and the dashboard build check.
