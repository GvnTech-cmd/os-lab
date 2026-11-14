# Cleanup Lab status

Maintainer ledger for the CLN roadmap. The task text is
[`../dashboard/src/views/cleanup-lab-tasks.tsx`](../dashboard/src/views/cleanup-lab-tasks.tsx),
the contract is [`README.md`](README.md), the evidence is [`VERIFY.md`](VERIFY.md).
One row per task; the row is updated in the next task's PR (or in a final docs PR
when the last task lands).

## Work split (decided 2026-11-13)

This Run owns the **engine layer**: `cleanup-lab/` (engine, catalog, PARITY,
VERIFY, this file), `console/cleanup_api.py`, `labctl`, the tests and `lat.md/`.
It does **not** write anything under `dashboard/` — not `api.ts`, not pages or
views, not the seven locale catalogs, not the rebuilt `dist`.

The **dashboard layer** is handed to Claude Code. Each task below carries a
"Dashboard handoff" section with the endpoint contract, the UI states and every
user-visible English string; that section is also in the PR body.

Why: the workspace write guard in this build rejects any file whose *existing*
content matches its credential-assignment heuristic (`assertWriteCarriesNoCredential`
runs on the whole content, with no path allowlist and `materializeArtifacts`
defaulting to true). `dashboard/src/lib/api.ts` contains TypeScript annotations
named `token` and every locale catalog contains UI copy mentioning passwords, so
those eight files cannot be written here. Nothing was worked around: the attempts,
the finding and the decision are in the session log.

## Ledger

| ID | Status | PR | Merge commit | Deliverables not done | Deviations | Student reservations / PRs |
|---|---|---|---|---|---|---|
| CLN-01 | merged | [#134](https://github.com/keyvanarasteh/os-lab/pull/134) | d04941f6 | — | dashboard layer landed in CLN-16 | none |
| CLN-02 | merged | [#135](https://github.com/keyvanarasteh/os-lab/pull/135) | 39ea0f1f | — | — | none |
| CLN-03 | merged | [#138](https://github.com/keyvanarasteh/os-lab/pull/138) | c253cf34 | — | dashboard layer landed in CLN-16 | none |
| CLN-04 | merged | [#143](https://github.com/keyvanarasteh/os-lab/pull/143) | 673d6853 | — | — | none |
| CLN-05 | merged | [#144](https://github.com/keyvanarasteh/os-lab/pull/144) | e02bc47d | — | — | none |
| CLN-06 | merged | [#145](https://github.com/keyvanarasteh/os-lab/pull/145) | 01a08055 | — | — | none |
| CLN-07 | merged | [#147](https://github.com/keyvanarasteh/os-lab/pull/147) | fcf2929a | project sweep UI and simulator action | read-only detection only | none |
| CLN-08 | merged | [#149](https://github.com/keyvanarasteh/os-lab/pull/149) | 72e2b635 | — | typed controls added after CLN-16 | none |
| CLN-09 | merged | [#150](https://github.com/keyvanarasteh/os-lab/pull/150) | 8503ef58 | frontend client/state still due | logic and API first | none |
| CLN-10 | in review (this PR) | [#151](https://github.com/keyvanarasteh/os-lab/pull/151) | — | — | typed Linux/Windows results view added after CLN-16 | none |
| CLN-11 | merged | [#152](https://github.com/keyvanarasteh/os-lab/pull/152) | ef1d2f1a | frontend client/state still due | report-and-suggest only | none |
| CLN-12 | merged | [#136](https://github.com/keyvanarasteh/os-lab/pull/136) | 3d5ab866 | — | — | none |
| CLN-13 | merged | [#139](https://github.com/keyvanarasteh/os-lab/pull/139) | 6656ed55 | — | dashboard layer landed in CLN-16 | none |
| CLN-14 | pending | — | — | — | — | none |
| CLN-15 | merged | [#140](https://github.com/keyvanarasteh/os-lab/pull/140) | 310f7d19 | — | history view landed in CLN-16 | none |
| CLN-16 | merged | [#141](https://github.com/keyvanarasteh/os-lab/pull/141) | b06db079 | — | — | none |
| CLN-17 | pending | — | — | — | — | none |
| CLN-18 | pending | — | — | — | — | none |
| CLN-19 | pending | — | — | — | — | none |
| CLN-20 | merged | [#171](https://github.com/keyvanarasteh/os-lab/pull/171) | ee7a45a3 | `/cleanup/` privileged card (dashboard layer) | action model, not elevated path deletion (see handoff) | none |
| CLN-21 | pending | — | — | — | — | none |
| CLN-22 | merged | [#137](https://github.com/keyvanarasteh/os-lab/pull/137) | a3133e76 | — | done ahead of order by Claude Code at the maintainer's request; engine and dashboard untouched | none |
| CLN-23 | pending | — | — | Disk Explorer page | console side only | none |
| CLN-24 | merged | [#148](https://github.com/keyvanarasteh/os-lab/pull/148) | 547f0a92 | — | catalog signatures behind CLN-07 sweep | none |
| CLN-25 | merged | [#146](https://github.com/keyvanarasteh/os-lab/pull/146) | e5dfac27 | source label wired into cleanup results | engine and dashboard payloads ready | none |
| CLN-26 | pending | — | — | — | — | none |
| CLN-27 | in review (this PR) | [#172](https://github.com/keyvanarasteh/os-lab/pull/172) | — | `/cleanup/` relocation card (dashboard layer) | stacked on CLN-28 (uses its volume inventory) | none |
| CLN-28 | merged | [#170](https://github.com/keyvanarasteh/os-lab/pull/170) | c10d5ad9 | `/cleanup/` volumes card (dashboard layer) | console + engine landed per the layer split | none |
| CLN-29 | pending | — | — | — | — | none |

No CLN task has a student reservation or open student PR: `grep -rl CLN-
reservations/` matches only `README.md` and `_schema.json`, and no open PR title or
branch names a CLN id.

## Dashboard handoff — CLN-13

### Console endpoints (live on this branch)

`POST /api/cleanup/plan` — header `X-OSLab: 1`, JSON body:

```json
{ "entryIds": ["system.user-caches"], "workers": 4, "mode": "trash" }
```

`entryIds` is **required** (catalog ids from `GET /api/cleanup/catalog`); `workers`
is `1`–`16`; `mode` is `trash` (default) or `delete`. A path, a command, any other
key, an empty/duplicate/unknown id list, a bad worker count and any other mode are
`400`. The answer is `202` with a job whose `kind` is `plan`:

```json
{
  "id": "9e1c0a7b3d21", "kind": "plan", "state": "running",
  "request": { "entryIds": ["system.user-caches"], "workers": 4, "mode": "trash" },
  "progress": { "phase": "planning", "pathsDone": 0, "pathsTotal": 1,
                "bytesSeen": 0, "filesSeen": 0, "currentPath": "" },
  "result": null, "error": null,
  "startedAt": 0, "finishedAt": null
}
```

Poll `GET /api/cleanup/jobs/<id>`. When `state` is `done`, `result` is the plan:

```json
{
  "planId": "8c1f2a9b0d44", "createdAt": 0, "expiresAt": 0, "ttlSeconds": 600,
  "mode": "trash", "platform": "macos",
  "items": [
    {
      "entryId": "system.user-caches", "entryName": "User caches", "risk": "low",
      "template": "~/Library/Caches", "path": "/Users/me/Library/Caches",
      "status": "ready", "code": "", "reason": "",
      "privileged": false, "mode": "trash",
      "sizeBytes": 40960, "sizeOnDiskBytes": 40960, "files": 3, "folders": 4
    }
  ],
  "totals": { "items": 1, "ready": 1, "skipped": 0, "bytes": 40960,
              "files": 3, "folders": 4 }
}
```

`POST /api/cleanup/clean` — header `X-OSLab: 1`, body `{ "planId": "8c1f2a9b0d44" }`,
no other key → `202` job `kind: "clean"`. Errors are answered before a job starts:
`404` unknown plan, `410` expired, `409` already used. A plan is **single-use** and
expires after ten minutes **or** when any item's fingerprint changed; the change is
re-checked inside the job, which ends `failed` with that message and removes nothing.

Clean progress: `phase` `queued`/`cleaning`/`done`/`cancelled`, `itemsDone`,
`itemsTotal`, `bytesRemoved`, `currentPath`. When finished:

```json
{
  "planId": "8c1f2a9b0d44", "mode": "trash", "platform": "macos",
  "startedAt": 0, "finishedAt": 0, "durationMs": 0, "cancelled": false,
  "results": [
    {
      "entryId": "system.user-caches", "entryName": "User caches",
      "template": "~/Library/Caches", "path": "/Users/me/Library/Caches",
      "mode": "trash", "status": "trashed",
      "code": "", "reason": "", "error": null,
      "bytes": 40960, "files": 3, "folders": 4,
      "trashPath": "/Users/me/.Trash/Caches"
    }
  ],
  "progress": { "phase": "done", "itemsDone": 1, "itemsTotal": 1,
                "bytesRemoved": 40960, "currentPath": "" },
  "totals": { "items": 1, "trashed": 1, "deleted": 0,
              "skipped": 0, "failed": 0, "bytes": 40960,
              "files": 3, "folders": 4 }
}
```

Statuses are exactly `trashed`, `deleted`, `skipped` and `failed`. A skipped item
has a stable `code` plus an English `reason`: `no-path`, `privileged`,
`app-running`, `foreign-owner`, `protected`, `system-root`, `outside-root`,
`missing`, `unreadable`, `not-cleanable`, `duplicate`, `nested`, `trash-nesting`,
`cancelled`. A failed item has an `error`; a failed Trash is **failed, not
deleted** — the original is still there. `bytes`/`files`/`folders` are this run's
measurement and only counted after the item is really gone; a failed/skipped item
counts 0. `trashPath` is `null` for `delete`, skips and failures. **Do not sum the
plan's estimate**; show `result.totals.bytes` and say “moved to Trash” (or “deleted”
only in delete mode).

`mode: "delete"` is permanent and only happens when the plan names it; never make it
the default, never fall back to it, and warn in the confirm step. There is no audit
history yet (CLN-15) and no undo beyond the user's own Trash. Privileged items are
planned as skipped and must offer no clean action.

### What the page does with it

CLN-16 owns the page. The scan section stays; add a plan/confirm section with:

| State | What the page shows |
|---|---|
| idle | selected catalog entries, **Build plan**; Trash is the default and delete is a deliberate second choice with a warning |
| planning | `pathsDone / pathsTotal`, `bytesSeen`, `filesSeen`, `currentPath`; **Cancel** |
| plan ready | every item with `status`, `code`/`reason`, size, files, folders; **N items ready**, byte total; **Confirm clean** disabled when `totals.ready` is 0; “Expires in 10 minutes” |
| expired / stale / used | that sentence verbatim plus **Build a new plan**; never retry the same `planId` |
| cleaning | `itemsDone / itemsTotal`, `bytesRemoved`, `currentPath`; **Cancel** |
| done | one row per item with its status, reason/error and (for Trash) `trashPath`; the counted `totals.bytes`; say space was **moved to Trash**, not “freed” |
| cancelled | “Clean cancelled” and the partial rows; remaining items are skipped with reason `cancelled`; a new plan is needed |
| failed | `error`; for a stale plan explicitly “nothing was removed”; if some rows exist, show them |
| public Pages | no plan/clean action: “The Cleanup Lab runs in the local app.” |

Keep the confirm action behind an explicit dialog that names the item count, the
byte total and the mode (Trash default / delete permanent). Never pre-select a
`credentials`/`privacy` entry, and never expose a free-form path or command field.

### Visible strings (English; these are the i18n keys)

`Build plan` · `Confirm clean` · `Trash (default)` · `Delete permanently` ·
`Planning…` · `Plan ready` · `Nothing to clean` · `items ready` · `Cleaning…` ·
`Clean cancelled` · `Clean failed` · `Moved to Trash` · `Deleted permanently` ·
`Skipped` · `Failed` · `Moved to Trash, not freed` ·
`This plan expired because an item changed. Build a new plan.` ·
`This plan was already run. Build a new plan.` ·
`This plan expired. Build a new plan.` ·
`The item could not be moved to Trash and was left in place.` ·
`Deleting permanently cannot be undone.` ·
`The cleanup engine could not start the job.` ·
`No answer from the cleanup engine. Start os-lab from a terminal, then try again.` ·
`The Cleanup Lab runs in the local app.`

Dynamic strings (`entryName`, `template`, `path`, `reason`, `error`, `trashPath`)
come from the engine/API in English, like every other lab payload; they are not
translated client-side.

## Dashboard handoff — CLN-03

### Console endpoints (live on this branch)

`POST /api/cleanup/scan` — header `X-OSLab: 1`, JSON body:

```json
{ "entryIds": ["system.user-caches"], "workers": 4 }
```

Both keys are optional; `entryIds` is a list of catalog ids (`GET
/api/cleanup/catalog`), `workers` is `1`–`16`. A path, a command, any other key, a
duplicate or unknown id, an empty id list and a bad worker count are `400`. The
answer is `202` with the same job object as below. The scan is read-only and runs
on a console thread; there is no command string and no path list from the page.

`GET /api/cleanup/jobs/<id>` → `200` job, `404` unknown id. `GET
/api/cleanup/jobs` → `{ "jobs": [ … ] }`, newest first, at most the recent 20
finished jobs plus any running one. `POST /api/cleanup/jobs/<id>/cancel` — header
`X-OSLab: 1`, empty object body → `200` job; the cancel flag is set immediately and
the worker finishes with `state: "cancelled"` after its current listing. A
non-empty body is `400`, an unknown id `404`.

```json
{
  "id": "2b8cc9ba670f",
  "kind": "scan",
  "state": "running",
  "request": { "entryIds": ["system.user-caches"], "workers": 4 },
  "progress": {
    "phase": "scanning",
    "pathsDone": 1, "pathsTotal": 3,
    "bytesSeen": 40960, "filesSeen": 1,
    "currentPath": "/Users/me/Library/Logs"
  },
  "result": null,
  "error": null,
  "startedAt": 1794536063.8,
  "finishedAt": null
}
```

`state` is `running`, `done`, `cancelled` or `failed`; `failed` carries a string
`error` and no result. `progress.phase` is `queued`, `scanning`, `done` or
`cancelled`; `pathsTotal` is the number of top-level paths that can be measured.
When finished, `result` is:

```json
{
  "startedAt": 0, "finishedAt": 0, "durationMs": 0, "platform": "macos",
  "cancelled": false,
  "entries": [
    {
      "id": "system.user-caches", "name": "User caches", "family": "system",
      "category": "system", "risk": "low", "hint": "…", "impact": "…",
      "defaultSelected": true, "needsPrivilege": false,
      "owningProcesses": [], "detector": "paths",
      "paths": [
        {
          "template": "~/Library/Caches", "path": "/Users/me/Library/Caches",
          "reason": "", "missing": false, "symlink": false,
          "sizeBytes": 40960, "sizeOnDiskBytes": 40960,
          "files": 1, "folders": 2, "unreadable": [], "error": null,
          "measured": true
        }
      ],
      "sizeBytes": 40960, "sizeOnDiskBytes": 40960,
      "files": 1, "folders": 2, "unreadable": [], "missing": false
    }
  ],
  "progress": { "phase": "done", "pathsDone": 3, "pathsTotal": 3, "…": "…" },
  "totals": {
    "sizeBytes": 0, "sizeOnDiskBytes": 0, "files": 0, "folders": 0,
    "paths": 0, "unreadable": 0, "entries": 0
  }
}
```

Honest fields: `sizeOnDiskBytes` is `null` where the OS does not expose a block
count; a path with `path: null` has a `reason`; `missing`/`symlink` paths carry a
`reason` and zero bytes; `unreadable` lists paths under this path that could not be
read; `measured: false` means the walk was cancelled (partial counters are still
real). Totals exclude unmeasured and unreadable bytes — never invent them. Jobs are
in-process only, so a console restart loses them; do not persist or promise them.

Errors on the namespace: `400` bad query/key/id/worker, `404` unknown path or job,
`403` missing `X-OSLab` on POST, `500` malformed catalog, `501` engine missing.

### What the page does with it

CLN-16 owns the page. A scan section offers exactly one action, **Start scan**
(disabled while a job is running), then **Cancel scan**; no clean/delete action
until CLN-13. Poll `GET /api/cleanup/jobs/<id>` every ~500–750 ms while `running`;
stop polling on `done`, `cancelled` or `failed`.

| State | What the page shows |
|---|---|
| idle | Start scan, the catalog's entry count, and a sentence that scanning is read-only. Never say space was freed. |
| running | progress bar from `pathsDone / pathsTotal`, `bytesSeen`/`filesSeen` and `currentPath`; Cancel scan |
| done | totals plus one row per entry and per path: apparent size, on-disk size when not null, files, folders; risk and `needsPrivilege` from the entry |
| done with zero bytes | the entry stays visible with its `reason` (`missing`, symlink, nothing to measure) — never hidden |
| cancelled | a neutral “Scan cancelled” badge and the partial rows; offer Start scan again |
| failed | `error` next to the action; no results card |
| request failed | the existing offline sentence; do not poll |
| public Pages | no polling, no scan action: “The Cleanup Lab runs in the local app.” |

`unreadable` is a list, shown under the path (“N paths could not be read”) with the
paths in a collapsed detail; it is not an error. A privileged entry
(`needsPrivilege`) can be scanned but must not offer cleaning.

### Visible strings (English; these are the i18n keys)

`Start scan` · `Cancel scan` · `Scanning…` · `Scan cancelled` · `Scan failed` ·
`Scan results` · `Reclaimable space` · `Apparent size` · `On disk` · `Files` ·
`Folders` · `Unreadable paths` · `Missing` · `Symlink not followed` ·
`Nothing to measure` · `Scanning is read-only. Nothing is removed.` ·
`Scanning runs on this computer. Cleaning arrives in a later task.` ·
`The cleanup engine could not start the scan.` ·
`No answer from the cleanup engine. Start os-lab from a terminal, then try again.` ·
`The Cleanup Lab runs in the local app.`

Dynamic strings (`name`, `hint`, `impact`, `risk`, `reason`, `error`, `currentPath`)
come from the engine/API in English, like every other lab payload; they are not
translated client-side.

## Dashboard handoff — CLN-12

### Console endpoint

None. The guard is engine-internal: CLN-13's plan and CLN-15's run will return a
`reason` and `reasonCode` per item from `safety.check_target()`.

### What the page shows per item

`Ok` items carry the resolved path. A refused item must show its translated code and
keep the entry visible — never silently drop it. Codes:

| Code | Meaning | English fallback |
|---|---|---|
| `empty` | empty path in a request | A filesystem path cannot be empty. |
| `nul` | NUL byte in a path | A filesystem path cannot contain NUL bytes. |
| `relative` | not absolute and not `~/…` | Filesystem paths must be absolute: `<path>` |
| `protected` | `/`, the home folder or a drive root | Refusing to operate on protected root `<path>`. |
| `system-root` | `/System`, `/usr`, `C:\Windows` … | Refusing to operate on system directory `<path>`. |
| `missing` | vanished since the scan | Path no longer exists. |
| `no-path` | entry has no path for this OS | This entry has no path for this system. |
| `outside-root` | symlink resolved outside the entry's root | Path resolves outside its catalog root (symlink escape). |
| `foreign-owner` | owned by another account | Owned by another user account; a privileged plan is required. |
| `app-running` | an owning app is running | The owning application is running: `<apps>`. |

Also refused, for CLN-23 and CLN-27: `missing` / `not-a-folder` / `unreadable` when
choosing a scan folder, `outside-roots` for a target outside every allowed root,
`same-path` / `nested` / `destination-outside` for a copy.

### Suggested UI strings

`Skipped` · `Could not be cleaned` · `Some items were skipped` — the reasons themselves
come from the payload. A privileged entry shows `Needs administrator rights` and stays
unselected.

## Dashboard handoff — CLN-02

### Console endpoint (already live)

`GET /api/cleanup/catalog` → `200 application/json`

```json
{
  "platform": "macos",
  "entries": [
    {
      "id": "system.user-caches",
      "name": "User caches",
      "family": "system",
      "category": "system",
      "risk": "low",
      "hint": "Application caches for the current user. They speed up loading.",
      "impact": "Apps rebuild these; the first launch after cleaning is slower.",
      "defaultSelected": true,
      "needsPrivilege": false,
      "owningProcesses": [],
      "detector": "paths",
      "note": "",
      "paths": [
        { "template": "~/Library/Caches", "path": "/Users/Q/Library/Caches", "reason": "" }
      ]
    }
  ]
}
```

`risk` is `low` / `medium` / `high` / `credentials` / `privacy`; the last three are
never pre-selected. `paths[].path` is `null` when the template could not be resolved
(e.g. an unset `XDG_CACHE_HOME`), and `paths[].reason` then says why. Errors: `400`
unexpected or duplicate query parameters, `404` unknown path, `500` malformed catalog
(the message names the file). No POST, no jobs.

### UI

CLN-02 adds no page. When a later page lists detectors (CLN-16), it reads this
endpoint; a path with `path: null` must show its `reason`, not be hidden. Suggested
strings, if such a list is built: `Detector catalog` · `No detector catalog` ·
`Could not resolve this path`. Everything else comes from `name`, `hint`, `impact`
and `risk` in the payload.

## Dashboard handoff — CLN-01

### Console endpoint (already live)

`GET /api/cleanup/status` → `200 application/json`

```json
{
  "engine": { "name": "cleanup-lab", "version": "0.1.0", "python": "3.15.0", "mode": "stdlib" },
  "state": "ready",
  "platform": { "id": "macos", "label": "macOS", "supported": true },
  "home": "/Users/Q",
  "stateDir": "/Users/Q/Library/Application Support/os-lab/cleanup",
  "requirements": [
    { "id": "platform", "label": "Supported operating system", "found": true, "required": true, "hint": "Cleanup Lab runs on macOS, Linux and Windows.", "detail": "macOS" },
    { "id": "python", "label": "Python 3.11 or newer", "found": true, "required": true, "hint": "labctl cleanup prefers the checkout's .venv; install Python 3.11 or newer.", "detail": "3.15.0" },
    { "id": "home", "label": "Home folder readable", "found": true, "required": true, "hint": "The scan targets live under this folder; make it readable by your user.", "detail": "/Users/Q" },
    { "id": "trash", "label": "Trash available", "found": true, "required": true, "hint": "Cleaning moves items to the Trash; a platform without one cannot clean.", "detail": "/Users/Q/.Trash" },
    { "id": "state", "label": "Private state folder writable", "found": true, "required": true, "hint": "The audit history and the learned profile live here. Set OSLAB_CLEANUP_STATE to a writable folder.", "detail": "/Users/Q/Library/Application Support/os-lab/cleanup" }
  ],
  "capabilities": [
    { "id": "detectors", "label": "Detector catalog", "found": false, "detail": "No detector catalog yet" },
    { "id": "native-scan", "label": "Native scan backend", "found": false, "detail": "Reference crate present; not wired into the app yet" },
    { "id": "containers", "label": "Container engine", "found": false, "detail": "No docker or podman on PATH" },
    { "id": "package-managers", "label": "Package managers", "found": true, "detail": "pip3 at /usr/bin/pip3" },
    { "id": "simulators", "label": "Simulator tools", "found": true, "detail": "xcrun at /usr/bin/xcrun" }
  ],
  "reasons": [],
  "checkedAt": 1794530446.947456
}
```

`state` is `ready` / `needs-setup` / `unavailable`. `reasons` lists the `hint` of
every required requirement that failed. Errors: `404` unknown `/api/cleanup/...`
path, `400` unexpected or duplicate query parameters, `501` when
`console/cleanup_api.py` or `cleanup-lab/engine` is missing. No POST, no jobs, no
progress or cancel in this task.

### UI states

| State | What the page shows |
|---|---|
| loading | skeleton rows, headline "Checking this computer…" |
| ready | success badge, "Ready on this computer", every requirement row ticked |
| needs-setup | warning badge, "Needs setup on this computer", the failed row's `hint` under it, plus the `reasons` list |
| unavailable | neutral badge, "Not available on this computer", unsupported-platform sentence |
| request failed | empty state with "No answer from the cleanup engine. Start os-lab from a terminal, then press Re-check." |
| public Pages | no polling: "The Cleanup Lab runs in the local app." |

Actions: exactly one, Re-check (re-fetch). No scan/clean button until CLN-03/13.

### Files to add (dashboard layer)

* `dashboard/src/pages/cleanup/index.astro` — `<Base title="Cleanup Lab" …>` +
  `<CleanupPage client:only="react" />`.
* `dashboard/src/views/cleanup/cleanup-page.tsx` — `AppShell activeId="cleanup"`,
  `TopBar`, `PageHead`, two `Section`s (Readiness, Capabilities), a collapsed
  "Technical details" block with engine version, Python, home and state paths.
* `dashboard/src/lib/api.ts` — `CleanupRequirement`, `CleanupCapability`,
  `CleanupStatus` types and `cleanupStatus: () => call<CleanupStatus>("/api/cleanup/status")`.
* `dashboard/src/shell/app-shell.tsx` — `sectionHref("cleanup")` → `/cleanup/`,
  a "Cleanup Lab" item in the **OS Lab** group (local mode only), Spotlight meta.
* `dashboard/src/pages/[locale]/[...rest].astro` — add `cleanup` to `routes` and
  render the page for `rest === "cleanup"`, otherwise language switching 404s.

### Visible strings (English; these are the i18n keys)

`Cleanup Lab` · `Find reclaimable disk space, inspect every item, and clean only what you confirm.` ·
`Checking this computer…` · `Ready on this computer` · `Needs setup on this computer` ·
`Not available on this computer` · `Every required check answered. Nothing has been scanned or removed.` ·
`The engine is installed but a required check below did not answer.` ·
`This operating system is not supported by the Cleanup Lab engine.` · `Asking the local cleanup engine…` ·
`Re-check` · `Readiness` · `Checks the local engine answers before it scans anything. Nothing on this page changes your system.` ·
`Capabilities` · `Optional tools and detectors this build can use. A missing one never blocks a scan.` ·
`Technical details` · `Engine version` · `Python` · `Home folder` · `Private state` ·
`No answer from the cleanup engine. Start os-lab from a terminal, then press Re-check.` ·
`This build reports readiness only. Scanning, planning and cleaning arrive in later tasks.` ·
`The Cleanup Lab runs in the local app.` ·
`The public site describes the lab. Scanning and cleaning need the engine on your own computer.`

Dynamic strings from the API (`label`, `detail`, `hint`, `reasons`) are English
server-side, like every other lab label; they are not translated client-side.

## Dashboard handoff — CLN-28

### Console endpoint (live on this branch)

`GET /api/cleanup/volumes` — no query parameters (an unknown one is `400`); no
POST, no job: the probe is synchronous and read-only.

```json
{
  "platform": "windows",
  "checkedAt": 0,
  "threshold": 0.9,
  "homeVolume": "C:\\\\",
  "error": null,
  "volumes": [
    {
      "mountPoint": "C:\\\\", "name": "Windows", "device": "C:", "filesystem": "NTFS",
      "kind": "root", "totalBytes": 0, "freeBytes": 0, "usedBytes": 0,
      "usage": 0.93, "isHome": true, "pressure": "warning", "error": null
    }
  ],
  "warnings": ["Volume C:\\\\ is 93% full (7.8 GB free)."]
}
```

`kind` is `root` / `internal` / `removable` / `unknown`; `pressure` is `ok` or
`warning` (usage strictly above `threshold`). A volume that could not be
measured carries a non-null `error`, `null` byte fields and `usage` — show the
error, never zero-filled numbers. `homeVolume` is `null` when no mount point
contains the home folder. Byte totals are `shutil.disk_usage` values; never sum
them into a claim of reclaimable space — they are capacity, not cleanup results.

### What the card does (the `/cleanup/` volumes card is this handoff)

| State | What the page shows |
|---|---|
| ready | one row per volume: mount point, kind, filesystem, used/total and a bar; the home volume marked; the `warnings` list under it |
| unreadable volume | the row stays visible with its `error` text and no numbers — never hidden, never zero-filled |
| probe failed (top-level `error`) | that error text alone; no invented rows |
| public Pages | no engine call: the page explains local installation |

Visible strings (English; these are the i18n keys):
`Volumes` · `Local volumes and disk pressure. Read-only; nothing is scanned or removed.` ·
`Home` · `Root volume` · `Internal` · `Removable` · `Unknown` · `{percent}% used` ·
`Usage unknown` · `Could not measure this volume`. Dynamic strings (`mountPoint`,
`name`, `filesystem`, `error`, `warnings[]`) come from the engine in English,
like every other lab payload; they are not translated client-side.
## Dashboard handoff — CLN-20

### Console endpoints (live on this branch)

`GET /api/cleanup/privileged` — no query parameters (an unknown one is `400`):

```json
{
  "platform": "linux",
  "applicable": true,
  "elevation": "pkexec",
  "actions": [
    {"id": "privileged.linux.apt-cache", "name": "APT package cache", "risk": "low",
     "impact": "…", "previewMode": "files", "previewArgv": null,
     "runArgv": ["apt-get", "clean"]}
  ],
  "diskAccess": {"applicable": false, "granted": null, "paths": [],
                  "guidance": "", "reason": "Full Disk Access is a macOS privacy setting."}
}
```

`elevation` is `pkexec` / `sudo` / `osascript` / `uac`, or `null` when the
desktop offers none — hide the actions then. `POST
/api/cleanup/privileged/preview` carries only `{"actionId": "privileged.linux.apt-cache"}`
(unknown keys are `400`, an unknown action is `400`) and answers the preview id,
the candidate material (`count`, `totalBytes` for files; `output` for tool text;
`candidates` for package lists), the elevated command and `expiresAt`. `POST
/api/cleanup/privileged/run` carries only `{"previewId": …}` — `404` unknown,
`409` used, `410` expired — and starts job kind `privileged-run`; the result is
appended to the signed audit history with `bytesRemoved: null` (the tool does
not report trustworthy bytes — never invent them).

`diskAccess` is macOS-only: `granted` is `true` / `false` / `null` (unknown),
with `paths[]` evidence and, on `false`, the `guidance` sentence.

### What the page does with it

| State | What the page shows |
|---|---|
| no engine section | when `applicable` is `false` or `elevation` is `null`, the card is hidden (readiness hides it too) |
| idle | one row per action: name, risk, impact, preview source; **Preview** |
| previewed | the elevated command, the candidate material, `expiresAt`; **Run** behind an explicit confirm dialog that names the action and says the tool deletes directly (no Trash, no undo) |
| running | job progress; **Cancel** refuses only the poll, the elevated process itself is not cancelled |
| done | the tool's `output` (or the UAC sentence), and the history note |
| failed | the error next to the action |
| public Pages | no engine calls: the page explains local installation |

Never expose a free-form command or path field. A macOS disk-access card shows
`granted` with the probe paths; on other platforms it is hidden.

### Visible strings (English; these are the i18n keys)

`Privileged maintenance` · `System maintenance that needs administrator rights, shown before anything runs.` ·
`Preview` · `Run` · `Elevated command` · `Candidates` · `This action removes data directly; it does not use the Trash and cannot be undone.` ·
`Waiting for the elevation prompt…` · `The elevation prompt was refused.` ·
`Full Disk Access` · `Granted` · `Not granted` · `Unknown` · `Open System Settings` ·
`The Cleanup Lab runs in the local app.` Dynamic strings (`name`, `impact`,
`output`, `error`, `guidance`) come from the engine in English, like every
other lab payload.

## Dashboard handoff — CLN-27

### Console endpoints (live on this branch; stacked on CLN-28)

`GET /api/cleanup/relocation` — no query parameters (an unknown one is `400`):

```json
{
  "platform": "windows",
  "entries": [
    {"entryId": "developers.gradle", "name": "Gradle caches", "path": "C:\\Users\\me\\.gradle",
     "relocatable": true, "interrupted": false}
  ],
  "destinations": [
    {"mountPoint": "D:\\", "freeBytes": 0, "totalBytes": 0, "kind": "internal"}
  ]
}
```

`POST /api/cleanup/relocation/plan` — body `{"action": "move" | "restore" |
"relink" | "resume", "entryId": …, "destination": <mountPoint>}`; anything else
is `400`. The answer is a `relocation-plan` job whose result carries the
`previewId`, the seven-state `state`, `homePath`/`storePath`, `sizeBytes`,
`freeBytes` and the ordered typed `steps`. `POST /api/cleanup/relocation/run`
carries only `{"previewId": …}` — `404` unknown, `409` used, `410` expired —
and starts job kind `relocation-run` with per-step progress
(`{step, stepsDone, stepsTotal}`); the result is appended to the signed audit
history with `bytesRemoved: null` and `bytesRelocated` for a completed move.
A cancelled run reports `cancelled: true` and the remaining step names; the
state is resumable through `action: "resume"`.

### What the card does

| State | What the page shows |
|---|---|
| idle | one row per relocatable entry: name, path, state, interrupted flag; the destination volumes beside it |
| planned | the ordered steps, sizes and free space; **Run** behind an explicit confirm dialog naming the entry, destination and the fact that the original folder becomes a symlink |
| running | `{step, stepsDone, stepsTotal}`; **Cancel** stops between steps and reports what remains |
| done | “Relocated”, the store path and the symlink note; Restore and Relink become available |
| failed | the reason next to the row; the original or a verified copy is still in place — say so, never suggest deleting by hand |
| conflict | `state: "conflict"` blocks plans and must tell the user both copies exist — the user decides, no action is offered |
| public Pages | no engine calls: the page explains local installation |

Never expose a free-form path field: the entry comes from the catalog list, the
destination from the volume list.

### Visible strings (English; these are the i18n keys)

`Relocate caches` · `Move a cache to another volume and link it back into place.` ·
`Move` · `Restore` · `Relink` · `Resume interrupted move` · `Destination` ·
`State: local folder` · `State: linked` · `State: broken link` · `State: conflict` ·
`This replaces the folder with a link to the copy on the destination volume.` ·
`A previous move was interrupted; resume it before starting a new one.` ·
`Cancelled — the original or a verified copy is still in place.` ·
`The Cleanup Lab runs in the local app.` Dynamic strings (`name`, `path`,
`steps`, errors) come from the engine in English.

## Session log

**2026-11-13 — CLN-01.** Read `AGENTS.md`, `CONTRIBUTING.md` §2b,
`docs/UX_READINESS.md`, `lat.md/`, `cleanup-lab/README.md`,
`cleanup-lab/reference/README.md` and the task file. No CLN reservations or open
CLN PRs. Built the `cleanup_lab` package (readiness, paths, CLI), the console
endpoint, the `labctl cleanup` dispatch, the unit suite, `lat.md/cleanup-lab.md`,
the README status/CLI section and the engine stage in `scripts/run-tests.sh`.

Write guard: `dashboard/src/lib/api.ts` and all seven
`dashboard/src/i18n/generated/*.json` were refused (`token`, then `password`
hits) because the guard scans the whole file content and this build exposes no
path allowlist. The maintainer asked for an 8-path allowlist; it did not take
effect in the Run, and the cause was reported. Decision on 2026-11-13: split the
work by layer (engine here, dashboard in a later pass), never work around the
guard, record any further refusal here. A draft `dashboard/src/views/cleanup/`
page written before that decision was removed again; `git status` shows no change
under `dashboard/`.

Baseline: `./scripts/run-tests.sh` reports 8 passed, 1 failed, 1 skipped. The
failure is the android suite, already failing on a clean `master` worktree on this
arm64 Mac (5 failed + 10 errors there, 4 failed + 10 errors on this branch, same
ids, no new failure); `cargo` is not on `PATH`, so the qrust-scan stage is skipped
and this PR changes no Rust.

**2026-11-13 — CLN-01 review round.** Sourcery opened 12 threads; the branch merge
is blocked until they are resolved (`required_conversation_resolution`). Fixed 11:
Python 3.11 is now accepted (a three-element `(3, 11, 0)` compared against
`(3, 11)` was false, so the probe compares the first two components); Trash
readiness checks the target (existing folder writable, otherwise its nearest
existing ancestor, Recycle Bin on Windows); the state folder must be writable
**and** not group/other accessible (`is_private_dir`); relative `XDG_*` values are
ignored instead of resolving against the working directory; `nearest_existing` uses
`lstat`, so a dangling symlink or a permission-blocked component is reported
instead of climbing past it; absolute-path checks use the target platform's path
module; CLI output escapes control characters; `doctor` prints every hint and no
longer claims the engine can scan; README and the knowledge graph say the
`/cleanup/` page is not built yet; the doctor test asserts the hint text. One thread
was declined: absolute home and state paths in the status response — the console
binds `127.0.0.1` only, rejects a foreign Host header, and any local process can
read the home path without it, while the page needs the paths to be useful. Replied
to and resolved every thread.

**2026-11-13 — CLN-02.** Catalog format, loader, seeds and parity. Added
`cleanup-lab/catalog/schema.json` (draft 2020-12), `catalog/system.json` with three
seed entries (user caches, user logs, Trash), `cleanup_lab/catalog.py` (validation,
per-OS template expansion, unresolved paths reported with a reason, pre-selected
risk refused), `cleanup-lab/PARITY.md` mapping every Qleaner detector id read from
`detectors.rs`, `catalog/README.md`, `labctl cleanup catalog` and
`GET /api/cleanup/catalog`. No CLN reservation or open CLN PR existed for this task.

**2026-11-13 — CLN-12.** Safety guard. Added `cleanup_lab/safety.py`: the reference
path policy (canonical/resolved paths, protected and system roots, component
containment, `validate_scan_root`, `validate_target`, `validate_copy`) plus ownership
and a process-table lock matched on whole names from each entry's `owningProcesses`.
`check_target()` returns a verdict with a stable code and an English reason;
`assert_safe_target()` raises both. 22 new tests (69 total), including a check that no
shipped catalog entry points at a protected root. The old `contains("..")` and
`contains("system")` checks are gone; `a..b` is a valid path and `~/.cache/systemd`
is not blocked by a substring.

**2026-11-13 — CLN-03.** Scan job. Added `cleanup_lab/scan.py`: a read-only
`lstat` walk of the catalog's resolved paths, one worker per top-level path (1–16),
throttled progress, hard-link de-duplication by `(device, inode)` across workers,
symlinks never followed, sockets/FIFOs/devices not measured, unreadable paths
reported, and cancel returning the real partial counters. The console exposes
`POST /api/cleanup/scan`, `GET /api/cleanup/jobs/<id>`, `GET /api/cleanup/jobs`
and `POST /api/cleanup/jobs/<id>/cancel`, accepting catalog ids and `workers` only;
a non-empty cancel body and every unknown key/id are refused. Fixed the cancel route
(`/api/cleanup/jobs/<id>/cancel` was parsed as 4 parts) and a web-layer crash where
cancel returned a dict but the route assumed a job object. Added engine tests
(88 total, OK) and `android-lab/lab/tests/test_cleanup_console.py` (5 passed).
`PARITY.md`, `README.md`, `lat.md/cleanup-lab.md` and `VERIFY.md` updated. No CLN-03
reservation or open student PR existed. A completed `./scripts/run-tests.sh` run was
8 passed / 2 failed: the six android failures reproduce on a clean `master`
worktree (no new failure), and the one `lat check` failure (section summary too
long) was fixed and re-checked green. The full suite was not re-run after that
documentation-only fix, per the maintainer's instruction.

**2026-11-13 — CLN-13.** Plan → confirm → clean. Added `cleanup_lab/clean.py`: a
read-only plan build (safety guard, one `lstat` walk, per-item fingerprint), a
single-use ten-minute plan, and an executor that verifies fingerprints first and
then trashes (default) or deletes (explicit) each item. A failed Trash is a failed
item, never a permanent-delete fallback; transient errors retry; cross-volume moves
are copied, verified and only then removed, with the verified copy kept when the
source cannot be removed. Per-item `trashed`/`deleted`/`skipped`/`failed` results
carry reasons, and bytes are counted only when the item is gone from its original
path. The console exposes `POST /api/cleanup/plan`, `POST /api/cleanup/clean
{planId}` and poll/cancel through the shared job store; stale/expired/used plans
answer `409`/`410` and remove nothing. Fixed `_validate_entry_ids` calling
`catalog.load()` without the repo root. Added 24 engine tests (112 total, OK) and
five console tests (10 total, passed) including the real browser route. `README.md`,
`PARITY.md`, `VERIFY.md`, `lat.md/cleanup-lab.md` and this handoff updated. No
CLN-13 reservation or open student PR existed. A full `./scripts/run-tests.sh` run
was 7 passed / 1 failed / 1 skipped: the android stage shows the same six
pre-existing ids as `master` (158 passed), and the dashboard stage skipped because
this worktree has no `node_modules`. Dashboard typecheck/build/e2e were not run —
no dashboard file changed.

**2026-11-13 — CLN-28.** Volumes overview and disk pressure. Added
`cleanup_lab/volumes.py` (kernel32 drive enumeration on Windows,
`/proc/self/mountinfo` on Linux, the fixed `mount` probe plus an optional fixed
`diskutil info -plist` probe on macOS; network and pseudo filesystems filtered
before any capacity query; the home volume marked by longest prefix; pressure
warnings above 90% usage), `GET /api/cleanup/volumes`, `labctl cleanup volumes`
and 24 engine tests over fake mount tables (rule 8: no real volume touched).
The `/cleanup/` volumes card is the dashboard layer's part; the handoff is
above. Baseline note, recorded honestly in VERIFY.md: the engine suite has
pre-existing platform-specific failures on this Windows host (49 failures + 37
errors on a clean master checkout); the failing test set is identical after
this change, and the console contract suite keeps its single pre-existing
Windows failure.

**2026-11-13 — CLN-20.** Privileged targets and the disk-access check. Added
`cleanup_lab/privilege.py` (typed actions for apt cache, journald vacuum,
apt autoremove, Spotlight rebuild and DISM component store cleanup; elevation
through pkexec/sudo/osascript/UAC with no stored password; fingerprinted
single-use previews; the read-only macOS Full Disk Access probe),
`cleanup-lab/catalog/actions/privileged.json` mirrored by the engine allowlist,
`GET /api/cleanup/privileged` + preview/run endpoints, an optional
`privileged-actions` readiness capability and 26 engine tests with fake
runners (rule 8). Design decision, recorded deliberately: privileged
maintenance is the CLN-08 action pattern, not an elevated path deletion — an
elevated `rm` would bypass rule 3's Trash guarantee. The catalog inventory
assertion (`test_catalog.py`) was updated from 65 to 66 entries for the new
`system.shared-font-caches` Linux path. The `/cleanup/` privileged card is the
dashboard layer's part; the handoff is above. Windows host baseline failures
are unchanged (86 identical ids; see VERIFY.md).

**2026-11-13 — CLN-27.** Cache relocation behind a symlink. Ported
`cleanup_ref/relocation.py` into `cleanup_lab/relocation.py` (the seven link
states, the copy → verify → rename aside → symlink → verify → remove order,
`plan_move`/`plan_restore`/`plan_relink`) and added `plan_resume` for the
interrupted states plus the typed step executor with progress and cancel.
Destinations come from CLN-28's volume inventory (this branch is stacked on
`feat/cln-28`); stores are `<volume>/oslab-caches/<entry id>`; the pair passes
`safety.validate_copy` and the CLN-12 running-app lock applies. The console
exposes `GET /api/cleanup/relocation`, a `relocation-plan` job and a single-use
audited `relocation-run` job; the preview store gained a label so container and
relocation refusals are distinguishable. 24 engine tests on generated trees
(rule 8); the symlink-needing ones skip honestly on Windows hosts without
Developer Mode, and the symlink-failure refusal itself is tested everywhere.
Windows host baseline failures are unchanged (86 identical ids; see VERIFY.md).
