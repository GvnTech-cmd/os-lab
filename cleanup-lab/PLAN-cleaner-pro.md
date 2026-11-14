# Cleaner Pro — plan (draft PR #214)

Planning document for the `feat/cleaner-pro` workstream on the Cleanup Lab.
Tasks are appended here (and to the PR body) as the maintainer dictates them;
**no implementation starts until they say so.** Each task lands as its own
commit on this branch once approved; a task that outgrows the branch splits
into a stacked PR per the "each Cleanup Lab task in its own PR" rule.

Task series: `CLNP-01…` (Cleaner Lab Pro). The existing roadmap covers
`CLN-01…CLN-29`; new ids join the dashboard Contribute → Roadmap page at
implementation time with the seven-locale translations.

---

## Task 1 — Optional permission checks and grants (CLNP-01 … CLNP-05)

Add an optional, read-only permission surface so the cleaner can say exactly
which macOS privacy grants (Full Disk Access, hidden/TCC-protected roots)
unlock which catalog entries — with grant guidance — and the honest
equivalents on Windows and Linux. Permissions never block readiness; they are
an optional capability, like `privileged-actions`.

### Current state (grounded in the code)

- `cleanup_lab/privilege.py::disk_access()` (CLN-20) already ports a read-only
  macOS FDA probe: `os.listdir` on `~/Library/Safari` and `~/Library/Mail`,
  returning `{applicable, granted, paths[], guidance}` with
  `applicable: False` elsewhere. It rides inside `privilege.capabilities()`
  as `diskAccess` and reaches the console only through
  `GET /api/cleanup/privileged`.
- `readiness.py` reports required checks (deciding `ready` / `needs-setup` /
  `unavailable`) plus optional capabilities that never block.
- The scan job reports unreadable paths under `unreadable` with a reason, but
  does not classify *permission denied* (a grant would fix it) against
  *not present / other errors*.
- `labctl cleanup doctor` prints readiness checks, paths and hints — no
  disk-access or permission lines.
- The dashboard renders no permission state; `diskAccess` appears only as
  roadmap text in `dashboard/src/views/cleanup-lab-tasks.tsx`.

### Design rules (from README safety rules + architecture contract)

1. **Read-only probes only** — `os.listdir` / `lstat` on fixed probe paths;
   no shell, no subprocess, no paths accepted from the page.
2. **Optional capability** — a missing or denied permission never flips
   readiness away from `ready`; it is surfaced as a capability with guidance.
3. **Typed payloads** — stable JSON shapes, unknown query parameters or keys
   → `400`, missing engine → `501`, no command strings.
4. **Grant affordance is guidance, not action** — the engine never opens
   System Settings or spawns anything. The dashboard renders the hint plus a
   plain client-side `x-apple.systempreferences:` link; `labctl doctor`
   prints the hint text.
5. **Proactive probes stay non-intrusive** — only FDA probe paths
   (`~/Library/Safari`, `~/Library/Mail`) are touched proactively; they fail
   silently under TCC without raising a macOS consent dialog. Desktop /
   Documents / Downloads TCC folders are *not* probed up front — probing them
   can trigger the system consent dialog — so they are classified reactively
   from scan-time permission errors instead.

### Permission set

| id | scope | how it is decided | grant hint |
| --- | --- | --- | --- |
| `macos-full-disk-access` | macOS | proactive probe of `~/Library/Safari`, `~/Library/Mail` (listdir; deny → `granted: false`) | System Settings → Privacy & Security → Full Disk Access + deep link `x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles` |
| `macos-desktop-folder` / `macos-documents-folder` / `macos-downloads-folder` | macOS | reactive: scan-time `PermissionError` on a root inside that folder classifies as needs-grant (`granted: null` until evidence) | System Settings → Privacy & Security → Files and Folders (or the named folder pane) |
| `hidden-roots` | all | read-only readability classification of hidden catalog roots (dot-directories, `~/Library`, `%APPDATA%` equivalents) per scan: `readable` / `permission-denied` / `not-present` | macOS: FDA hint (Library roots are TCC-protected); Windows: WindowsApps ACL note (report-only); Linux: owner/permission note |
| OneDrive placeholders | Windows | report-only `lstat` reparse-point classification on cloud-provider roots so the scan can say "online-only file, not measured" | none (informational) |
| TCC equivalents | Windows / Linux | every macOS permission reports `applicable: false` | — (existing `disk_access` shape already handles this) |

### Sub-tasks

#### CLNP-01 — Engine: typed `permissions` module
- [ ] New `cleanup-lab/engine/cleanup_lab/permissions.py` owning the
      permission model: one typed record per permission —
      `{id, name, applicable, granted (true/false/null), probePaths[],
      results[{path, readable, reason}], guidance, grantUrl|null}`.
- [ ] Move the CLN-20 FDA probe here; keep `privilege.disk_access()`
      delegating to it so the `GET /api/cleanup/privileged` payload shape
      stays byte-compatible for existing consumers.
- [ ] Reactive classification helper: given a scan's `unreadable` entries,
      map each to a permission id + guidance (FDA / Files-and-Folders /
      hidden-roots), leaving unmatched entries unclassified — no guessing.
- [ ] OneDrive/WindowsApps reparse + ACL classification is report-only and
      never blocks a scan.

#### CLNP-02 — Readiness and doctor
- [ ] `readiness.py` gains the optional `permissions` capability (present
      whenever the engine can answer the permission payload) — missing it
      never blocks `ready`.
- [ ] `labctl cleanup doctor` prints each permission: applicable / granted /
      probe results / guidance, and the deep-link hint text on macOS; exit
      codes unchanged (optional capability).

#### CLNP-03 — Console API
- [ ] `GET /api/cleanup/permissions` — typed, read-only; merges proactive
      probe results with the latest scan's reactive classification when one
      exists in the console process. Unknown query parameters → `400`;
      missing engine → `501`.
- [ ] Scan job payloads keep `unreadable` as-is; the *classification* joins
      through the permissions endpoint, not by widening the scan schema.

#### CLNP-04 — Dashboard
- [ ] `/cleanup/` gains a permissions card (readiness-probe section): state
      chip per permission (granted / denied / unknown / not applicable),
      probe paths with per-path reasons, guidance text, and — on macOS — a
      plain link to `x-apple.systempreferences:…` (client-side only, no
      engine call, no polling).
- [ ] Scan page: unreadable items show "which grant would unlock this" via
      the classified permission id.
- [ ] Seven-locale translations; Public Pages renders the card as
      documentation only, no engine calls, per `lat.md/ux-readiness.md`.

#### CLNP-05 — Tests, docs, knowledge graph
- [ ] `unittest` with fake probers: `PermissionError` / `FileNotFoundError` /
      other `OSError` / not-applicable / partial results; delegation keeps
      the CLN-20 payload shape stable.
- [ ] Console contract cases in `android-lab/lab/tests/test_cleanup_console.py`
      (400/501/typed payload).
- [ ] Update `cleanup-lab/README.md`, `cleanup-lab/STATUS.md`,
      `cleanup-lab/VERIFY.md`, `lat.md/cleanup-lab.md`; add `CLNP-01…05` to
      the Contribute → Roadmap page with translations; `lat check` passes.
- [ ] `scripts/run-tests.sh` suite green.

### Open questions (decide at implementation start)
- Should `macos-full-disk-access` gain more probe paths (e.g.
  `~/Library/Messages`)? Default: keep Safari + Mail unless a catalog root
  proves unreadable under FDA.
- Roadmap ids `CLNP-…` vs continuing `CLN-30…` on the Contribute page —
  default `CLNP-…` for workstream separation (WINMIR precedent).

---

## Task 2 — In-place tabs: no reload on tab change (CLNP-06 … CLNP-08)

Make the five Cleanup Lab tabs (Dashboard / Advanced scan / Results /
Leftovers / History, screenshot 2026-11-14) load **in place**: tab change
updates the URL and swaps content client-side with live data fetches — the
feel of a static Astro app — while the scan session, selection and running
jobs stay alive across tab switches.

### Current state (grounded in the code)

- Five static routes: `dashboard/src/pages/cleanup/[...page].astro` (English)
  and the localized catch-all `dashboard/src/pages/[locale]/[...rest].astro`
  (which also serves source, jobs, labs, android, legal pages). Each renders
  `<CleanupPage page={page} client:only="react" />` from
  `dashboard/src/views/cleanup/pages.tsx`.
- Tabs are plain `<a href>` anchors (`pages.tsx:266`); every tab change is a
  full HTML navigation, the island unmounts and remounts, and all React state
  is lost (selection, preset, mode, sort order, confirm dialog, in-flight job
  polling). Scan results only survive because the island refetches the
  console's recent jobs on mount.
- All five pages already render from **one** component and one fetch layer —
  the only thing page-scoped is the `page` prop and the two `useEffect`s
  keyed on it (core fetch on `[page]`, history fetch on `[page]`).
- The codebase already anticipates client-side navigation:
  `dashboard/src/shell/theme.ts:105` listens for `astro:after-swap` /
  `astro:page-load`, and `dashboard/src/i18n/client.ts` re-translates swapped
  DOM through a `MutationObserver` — so in-place re-renders are translated
  and themed without extra work.
- All cleanup tabs share the same document title ("Cleanup Lab · os-lab");
  links are built with `localePath` (`dashboard/src/i18n/paths.ts`), keeping
  locale prefixes and the Public Pages base path.

### Design decision

**Primary: island-internal client router** — `CleanupPage` owns navigation:
intercept tab and in-page cleanup links, `history.pushState` the same
`localePath` URL, render the new page from internal state, re-derive on
`popstate`. No layout or route changes; every locale and Public Pages get it
for free; deep links still land on the static routes.

Deferred alternative (recorded, not planned): Astro `ClientRouter` +
`transition:persist` on the cleanup-serving templates. Rejected for now
because the localized catch-all `[...rest].astro` shares its template with
~40 unrelated page kinds, and a persisted island freezes its props (the
location-derived page state would still be required). Revisit only if
cross-page in-place navigation (cleanup → other labs) is wanted.

### Rules

1. **URLs stay real** — every tab keeps its static route and trailing-slash
   URL shape via `localePath`; `pushState` pushes exactly what the anchor's
   `href` was. Deep links, refresh, and Public Pages URLs unchanged.
2. **Progressive enhancement** — anchors keep real `href`s; interception is
   an enhancement. With JavaScript disabled, navigation falls back to the
   existing full-page loads.
3. **Session state survives tab changes** — selection, preset, mode, sort
   order, plan review and the running-job poller persist; the confirm dialog
   closes on tab change (a plan review is re-opened from the page that owns
   it).
4. **Live fetch per tab, never idle polling** — core data (status, catalog,
   jobs) is fetched once per island session; entering a tab live-fetches what
   it shows: jobs on Dashboard/Results/Leftovers, audit history on History.
   The running-job poller keeps its 650 ms cadence only while a job runs,
   per `lat.md/ux-readiness.md`.
5. **Errors stay per-surface** — a failed tab fetch renders that tab's error
   status without discarding the session state.

### Sub-tasks

#### CLNP-06 — Island client router in `pages.tsx`
- [ ] Active page becomes internal state derived from
      `localeFromPath(window.location.pathname)` + the `/cleanup/…` suffix,
      not the (per-route) `page` prop; the prop stays as the initial value
      and the SSR/Public fallback.
- [ ] Tab anchors and in-page cleanup anchors ("View results", "Choose
      individual items", "View leftovers", "History", "Full scan report")
      are intercepted: `preventDefault` + `pushState` + state update +
      scroll-to-top; `popstate` re-derives the page. Links to other labs or
      locales are never intercepted.
- [ ] `aria-current="page"` follows the live page; AppShell `activeId`
      mapping (`cleanup-${page || "scan"}`) is preserved for the live page;
      the confirm dialog closes on page change.
- [ ] Public Pages (`PUBLIC_SITE_MODE`): same in-place tab swap, zero engine
      calls (the "Local app required" section swaps in place).

#### CLNP-07 — Live fetch semantics
- [ ] Split the `[page]` effects: core fetch (status + catalog + jobs) once
      per session with a session ref; per-tab live fetches keyed on the
      internal page (jobs refetch on Dashboard/Results/Leftovers entry;
      `api.cleanupHistory()` on History entry, keeping the existing
      once-per-entry behaviour).
- [ ] No reset of selection/preset/mode/order on tab change; first-load
      skeleton (`loading` + `role="status"`) only for the initial session
      fetch; per-tab fetches degrade to stale content + error status.
- [ ] Keep the job poller tied to a running job only; no new intervals.

#### CLNP-08 — Verification and docs
- [ ] Playwright e2e (`dashboard/tests`, `npm run test:e2e`): tab click does
      not reload (a `window` marker set before the click survives), URL
      updates, `aria-current` moves, browser back/forward re-derives the
      page, direct deep link still loads the right tab, running job keeps
      polling across a tab change.
- [ ] `npm run check`, `npm run test:i18n`, `npm run build`; regenerate
      `dashboard/dist` (committed); verify the local console routes and the
      Public Pages routes per `docs/UX_READINESS.md`.
- [ ] Docs: `lat.md/cleanup-lab.md` (Dashboard pages section), the
      cleanup-lab README page list, and `cleanup-lab/STATUS.md`.

### Open questions (decide at implementation start)
- Prefetch on tab hover/focus (Astro `prefetch` needs ClientRouter; with the
  island router, an idle-time `fetch` of the next tab's data is possible but
  adds code — default: skip, tab data is already local except History).
- Should the Advanced scan ↔ Dashboard presets stay in sync when navigating
  in place (they already share one island, so yes — no action).

---

## Task 3 — Optional background runner: disk free-space warnings (CLNP-09 … CLNP-13)

An optional, opt-in background runner that periodically checks disk free
space and raises a visible warning when a volume crosses its configured
free-space threshold. Built as a **trigger registry** so the maintainer's
next prompts can add more triggers (they announced further trigger kinds)
without touching the runner.

### Current state (grounded in the code)

- `cleanup_lab/volumes.py::inventory()` (CLN-28) already reports every local
  volume's mount point, capacity, kind, the home volume and a static >90%
  pressure note; it is read-only and typed (`GET /api/cleanup/volumes`,
  `labctl cleanup volumes`).
- The console process already owns long-lived work as daemon threads
  (`console/cleanup_api.py:207` `_spawn`), with locks around shared state.
- The engine's private state folder (`paths.state_dir`, overridable via
  `OSLAB_CLEANUP_STATE`) already persists the audit history SQLite store;
  config can persist there the same way.
- The dashboard polls only while a job runs (`lat.md/ux-readiness.md`);
  there is no periodic monitor today.

### Design

**Runner** — a daemon thread inside the local console process (same lifetime
as the console: alive while the local app's console runs, gone with it —
documented honestly). Off by default; the user activates it once from the
dashboard and the console auto-starts it on every boot while enabled
(persisted in the private state folder as atomic JSON, like history's store).

**Trigger registry** — each trigger is a typed record:
`{id, name, applicable(platform), configSchema, evaluate(context) -> [events]}`.
The runner evaluates only enabled, applicable triggers on its interval and
records events with timestamps. The first trigger:

- **`disk-free-space`** — per-volume thresholds chosen from the live CLN-28
  inventory (selection by mount point id, never a free-form path). Config per
  volume: warn when free space falls below an absolute floor and/or a percent
  floor. **Re-arm semantics** (hysteresis): a warning fires once on crossing
  below the threshold and re-arms only after free space recovers above the
  threshold plus a margin — no repeated alerts while space stays low; a
  cooldown guards flapping volumes. Default config (prefilled, disabled
  until activation): home volume, warn below 10 % free or 10 GiB free,
  300 s interval (configurable 60–3600 s).
- Evaluation is a **pure function** over `(volumes snapshot, config, previous
  state, now)` — unit-testable with an injected clock and usage fn; the
  runner thread only schedules and persists.

**Warning surface** — the warning "shows up" as a banner at the top of the
`/cleanup/` page (volume, free space, threshold, which cleanup tab helps,
deep link) plus a recent-events list on the monitor card. The runner is
read-only: it never cleans by itself — a warning links to the existing
plan → confirm → clean flow.

**Why console-thread, not a system daemon** — a launchd/systemd/Task
Scheduler runner with OS notifications is a separate product layer (the
desktop app owns process lifetime); recorded as deferred scope, not this
task. Honest limitation: no monitoring while the console is closed.

### Rules

1. **Read-only probes only** — the runner calls the same engine volume
   probes as CLN-28 (`shutil.disk_usage`-family, fixed `mount`/`diskutil`
   argv); no scans, no shell strings, no writes outside the state folder.
2. **Typed config, validated twice** — dashboard → console request is typed
   and validated (`unknown keys → 400`, free-form paths refused; volume ids
   validated against the live inventory); the engine re-validates the config
   schema when loading it from disk. Corrupt config → monitor starts
   disabled with the corruption reported, never a guess.
3. **Optional and quiet** — disabled by default; no polling, no warnings,
   no endpoints doing work while disabled beyond reporting its state.
4. **One evaluation at a time** — the runner thread skips a tick if the
   previous evaluation is still running (volumes probes can block on
   `diskutil`); evaluation results and errors are recorded, an unreadable
   volume yields a per-volume error event, not a runner failure.
5. **Warnings are events with history** — every warning, recovery and error
   is recorded with a timestamp in the monitor state (bounded, e.g. last
   100), so the card can show what happened while the page was closed.

### Sub-tasks

#### CLNP-09 — Engine: `monitor.py` trigger registry + disk-free-space trigger
- [ ] Typed trigger registry (id, name, applicable, config schema, pure
      `evaluate`), first trigger `disk-free-space` with per-volume
      absolute/percent thresholds, re-arm margin, cooldown.
- [ ] Monitor config + event store in the private state folder (atomic
      JSON, bounded event list); engine-side schema validation on load;
      corrupt config → disabled + reported.
- [ ] `unittest` with injected usage fn + clock: crossing, re-arm,
      cooldown, flapping, unreadable volume, disabled/applicable-false
      triggers, config validation.

#### CLNP-10 — Console runner + API
- [ ] Daemon runner thread in the console process: starts on boot when
      enabled; `GET /api/cleanup/monitor` (enabled/running, interval, per
      -trigger config, last evaluation, active warnings, recent events);
      typed config endpoint to enable/disable, set interval and edit
      trigger configs (400/501 contract; volume ids checked against the
      live inventory); on-demand "evaluate now" action.
- [ ] Thread skips ticks while an evaluation runs; errors recorded, never
      crash the runner; console contract tests in
      `android-lab/lab/tests/test_cleanup_console.py`.

#### CLNP-11 — Dashboard monitor card + warning banner
- [ ] `/cleanup/` gains a "Background monitor" card: activation toggle,
      interval, per-volume threshold editor (volume picker from CLN-28
      inventory, absolute/percent inputs), recent events list; a warning
      banner above the page content when a trigger is active, with a deep
      link to the relevant cleanup tab.
- [ ] Poll cadence: only while the runner is enabled (light, e.g. 15 s on
      the monitor card) — no polling when disabled or on Public Pages;
      seven-locale translations; Public Pages renders the card as
      documentation only.

#### CLNP-12 — labctl
- [ ] `labctl cleanup monitor [--json]` — engine-backed read-only status
      (enabled, running per config, last evaluation, active warnings),
      following the `labctl.md` exit-code contract (`0` ready, `1` check
      failed, `2` usage error).

#### CLNP-13 — Tests, docs, knowledge graph
- [ ] `scripts/run-tests.sh` green; console contract cases added;
      `cleanup-lab/README.md`, `STATUS.md`, `VERIFY.md` and
      `lat.md/cleanup-lab.md` updated; `CLNP-09…13` joined to the
      Contribute → Roadmap page with seven-locale translations;
      `lat check` passes.

### Open questions (decide at implementation start)
- OS-level notifications (macOS/Windows/Linux notification center) via the
  desktop app — deferred; needs the app layer's notification plumbing.
- Whether activation should also live in `labctl` (`monitor enable/disable`)
  or stay dashboard-only — default dashboard-only.
- Trigger id namespace for the maintainer's upcoming triggers — registry
  ids are open (`monitor.triggers` config keyed by id); record their ids in
  this plan as they arrive.

---

## Task 4 — Bookmarks: prioritize, quick-clean, hooks and size alerts (CLNP-14 … CLNP-19)

Let the user bookmark cleanup items (from history cleanups or anything the
detections support), order them by priority, configure per-bookmark
behaviour — include in quick cleanup, auto-clean when the free-space hook
fires, notify above a size threshold — and act on them with one click.

### Current state (grounded in the code)

- Every clean result item already carries its catalog `entryId`
  (`cleanup_lab/clean.py:325`, mirrored into the history records), and scan
  results are catalog entries — so "mark from history or detections" can be
  fully typed without accepting free-form paths.
- The plan → clean executor accepts catalog ids only
  (`clean.py:397`: "entryIds must be a non-empty list of detector ids");
  the catalog refuses `defaultSelected` for `high`, `privacy` and
  `credentials` risk classes — the same refusal will govern bookmarks that
  clean automatically.
- Task 3's monitor (CLNP-09/10) owns the trigger registry, the event store
  and the warning banner — the size alert and the free-space hook extend
  that registry instead of inventing a second scheduler.
- The dashboard's scan cards, results rows and history items are the
  surfaces where a bookmark affordance attaches.

### Design

**Bookmarks are catalog-entry references, never raw paths.** A bookmark
record: `{id, entryId, createdAt, priority (1 = first), quickClean: bool,
autoCleanHook: {enabled, lastRunAt, cooldownUntil} | disabled,
sizeAlert: {thresholdBytes, armed} | disabled}`. `entryId` is validated
against the live catalog on every write; resolved paths display from the
catalog (CLNP-01's permission classification applies here too). A history
or detection item whose entry no longer exists in the catalog cannot be
bookmarked (reported, not guessed).

**Quick clean** — a one-click action that builds a plan from every bookmark
with `quickClean: true`, ordered by priority, then runs the *existing*
plan → confirm → run flow (Trash default, confirmation still required —
quick ≠ unattended). The plan review names the bookmark order.

**Auto-clean hook (free-space)** — per-bookmark hook: when the Task 3
`disk-free-space` trigger crosses its threshold, the runner builds a plan
from hooked bookmarks (priority order) and runs it **Trash-only, without a
per-run confirmation click**. This is a deliberate, scoped exception to the
confirm step, guarded by: the user explicitly enabling the hook per
bookmark; Trash mode only (permanent delete is never available to hooks);
`high`/`privacy`/`credentials` entries refused; the existing safety guard,
plan fingerprinting and owning-app check still applying; a hook cooldown
(no re-run until the trigger re-arms); engine-ready preconditions; no
overlapping job; audit history records marked `"automated": true`; and a
post-run dashboard banner naming exactly what the hook moved to Trash.

**Size alert** — a new registry trigger `bookmark-size`: on its own cadence
the monitor measures hooked bookmarked entries with an entry-scoped,
read-only scan (the existing scan machinery, entry ids only) and raises a
monitor event when a bookmark's size crosses its threshold. Re-arm shares
Task 3's hysteresis (re-arm on falling back under threshold − margin). The
dashboard notification offers cleanup actions: "Clean this bookmark now"
(builds a confirmable plan) and — when the auto-clean hook is enabled —
adds it to the hook set.

### Rules

1. **Typed end to end** — bookmark writes take `entryId`s only; unknown or
   no-longer-catalogued ids are `400`/`410` with a reason; no command
   strings, no paths from the page.
2. **Automation is Trash-only and visible** — hooks never permanently
   delete, never touch high/privacy/credentials, never run while another
   job is active or the engine is not ready, and every automated run is
   audited and announced.
3. **One scheduler** — hooks and alerts live in the Task 3 monitor
   (registry entries + per-trigger cadences); no second timer stack.
4. **Persistence matches history's store** — bookmarks live in the private
   state folder as atomic JSON with engine-side schema validation; corrupt
   store → bookmarks disabled + reported, never guessed.
5. **Priority is honest** — the plan review and quick-clean dialog show the
   priority order; the audit record lists items in execution order.

### Sub-tasks

#### CLNP-14 — Engine: bookmarks store (`bookmarks.py`)
- [ ] Typed bookmark records with priority, `quickClean` flag,
      `autoCleanHook` and `sizeAlert` config; catalog validation on read
      and write; atomic JSON store in the state folder; bounded ordering
      helpers (move up/down, dedupe).
- [ ] Plan-builder helper: bookmarks → ordered `entryIds` filtered by flag
      (quick-clean or hook), refusing refused-risk classes with reasons.
- [ ] `unittest` with temp state folder and fake catalog: validation,
      ordering, flag filtering, corrupt-store recovery.

#### CLNP-15 — Quick clean from bookmarks (console + dashboard)
- [ ] Console: `POST /api/cleanup/bookmarks/quick-clean` starts the normal
      plan → confirm → run flow over `quickClean` bookmarks in priority
      order (typed job, existing 400/409/410 contract).
- [ ] Dashboard: "Quick clean" action with a review dialog listing the
      bookmark order, sizes and skipped reasons.

#### CLNP-16 — Auto-clean hook on the free-space trigger
- [ ] Monitor extension: on `disk-free-space` crossing, evaluate hooked
      bookmarks (priority order) → build plan → run Trash-only → record
      `automated: true` audit entry → emit monitor event; cooldown,
      engine-ready and no-overlapping-job guards; failure recorded, never
      silently retried.
- [ ] Dashboard: hook toggle per bookmark with the Trash-only/risk-class
      guardrail text inline; post-run banner naming what was cleaned.

#### CLNP-17 — `bookmark-size` trigger (registry)
- [ ] New registry trigger measuring hooked bookmarked entries on a
      per-trigger cadence (read-only, entry-scoped scan); threshold config
      per bookmark; events with size evidence (measured bytes, threshold,
      path resolution source); re-arm hysteresis shared with Task 3.
- [ ] Console events surface through `GET /api/cleanup/monitor` (no new
      endpoint); dashboard alert card offers the cleanup actions.

#### CLNP-18 — Dashboard bookmarks UI
- [ ] Bookmark affordances on scan cards, results rows and history items
      (via `entryId`); a Bookmarks section on `/cleanup/` (or its own tab —
      decide at implementation) with priority up/down, quick-clean
      checkmark, hook and size-alert configuration, resolved paths and
      last-run/last-alert info.
- [ ] Seven-locale translations; Public Pages renders the section as
      documentation only.

#### CLNP-19 — labctl, tests, docs
- [ ] `labctl cleanup bookmarks [--json]` (read-only list with resolved
      paths and flags); engine unittests, console contract cases,
      `scripts/run-tests.sh`; README/STATUS/VERIFY + `lat.md/cleanup-lab.md`
      updates; roadmap entries with translations; `lat check`.

### Open questions (decide at implementation start)
- Bookmarks as a section on `/cleanup/` vs a sixth tab — default: section
  on the dashboard, tab only if the card outgrows it.
- Hook evaluation timing: only on the `disk-free-space` warning crossing,
  or also re-evaluated on a cadence while space stays low (default:
  crossing-only, per re-arm semantics).
- Whether "notify" should later include OS notifications — stays on the
  Task 3 deferral (desktop app plumbing).
- Confirm dialog for quick clean stays mandatory (default); a "trusted
  quick clean" without confirmation would need its own explicit ask.

---

## Task 5 — Custom paths, overview-style dashboard, Space Explorer (CLNP-20 … CLNP-23)

Three connected pieces: let the user bookmark **custom paths** (safely), redesign the
Cleanup Lab dashboard into an **overview page** in the maintainer's reference
style (screenshot 2026-11-14: storage hero card, review CTA, grouped card
grids) covering every ability the lab has, and add a **Space Explorer** tab
that visualizes disk usage like the `dua` tool.

### Part A — Custom-path bookmarks (CLNP-20)

Task 4's rule was "bookmarks are catalog-entry references, never raw paths".
Custom paths join the same system by becoming **user-defined catalog
entries** in a per-install catalog overlay, so every existing safeguard
(roots containment, protected-root refusal, owning-app check, fingerprinted
plans) applies unchanged.

- [ ] **Overlay catalog** in the private state folder, validated against the
      shipped `schema.json`: family prefix `custom`, one entry per user
      path (display name, per-OS path templates expanded like shipped
      entries), risk restricted to `low`/`medium`, `defaultSelected: false`,
      `needsPrivilege: false`, merged after the shipped catalog by the
      CLN-02 loader (shipped ids win on collision; overlay corruption →
      overlay ignored + reported, never guessed).
- [ ] Typed console endpoints to add / update / remove custom entries — the
      raw path appears exactly once, as a validated field of the create
      request (absolute, `lstat`-resolvable, refused when it classifies as
      a protected or system root via the existing read-only guard
      classification); after that, only entry ids travel through the API.
- [ ] Bookmarks (CLNP-14) accept custom entry ids like any other; the
      bookmarks UI gains "Add custom path" (name + path + optional size
      alert / hook config in one dialog); scan and advanced-scan lists
      include custom entries with a "custom" source marker; removing a
      custom entry clears its bookmark, hook and alert records.
- [ ] Tests: overlay load/merge/corruption, path validation refusals,
      scan/plan behaviour over custom entries, bookmark lifecycle.

### Part B — Overview-style dashboard (CLNP-21, CLNP-22)

Redesign the `/cleanup/` Dashboard tab into an overview page following the
reference screenshot's **layout** (Overview header + status chip; storage
hero card with segmented used/available bar and legend; "Review cleanup"
CTA card; two-column grids of icon cards with title, one-line description
and chevron). The lab's own design tokens stay (brand orange, iux
variables, dark/light) — behaviour is ported, code, styling and known bugs
are not (`lat.md/cleanup-lab.md`).

- [ ] **CLNP-21 — Overview page**: page head with readiness chip
      (`Ready` / setup needed) and last-scan note ("No scan run yet" /
      latest scan time + measured total); storage hero card (home volume
      by default, volume picker when CLN-28 finds several, refresh action)
      with Used / Purgeable / Available segmented bar — purgeable legend
      only where a fixed probe proves it, omitted elsewhere; "Review
      cleanup" CTA card opening the existing scan flow; grouped card grids
      covering every ability, each card a link with icon + one-line
      description, **dimmed or hidden with a reason when its capability is
      not live on this host** per `lat.md/ux-readiness.md`:
      *Storage & cleanup*: Quick cleanup, Advanced scan, Results, Leftovers,
      History, Bookmarks, Space Explorer;
      *System & maintenance*: Background monitor, Permissions (CLNP-01),
      Privileged actions, Containers & VMs, Packages review, Projects deep
      scan, Simulators, Volumes, Relocation.
- [ ] Existing dashboard sections (quick cleanup, suggested cleanup, latest
      clean report) fold into the overview: the CTA card + results chips
      replace them, the confirm dialog and plan state keep working
      unchanged (preserve working UX; Task 2's in-place routing gains
      `space` in its tab list).
- [ ] **CLNP-22 — Overview data**: storage card reads the CLN-28 volumes
      inventory (typed, cached per session like other core fetches);
      optional `volumes.py` extension probing macOS purgeable space through
      the existing fixed `diskutil info -plist` probe and reporting it only
      when present (`null` + omitted legend elsewhere, Windows/Linux);
      scan-status summary from the jobs list.
- [ ] Seven-locale translations; Public Pages renders the overview as
      static documentation (no engine calls); responsive: single column on
      narrow viewports; e2e for the overview render + card navigation.

### Part C — Space Explorer, the dua-like tab (CLNP-23)

A new tab visualizing disk usage like the `dua` tool: sorted size bars per
folder, drill-down navigation, breadcrumbs. Read-only — the explorer never
deletes; it links cleaning to the existing plan / bookmark flows.

- [ ] **Engine size-tree walker** (new `explorer.py`, semantics ported from
      the CLN-21/23 `qrust-scan` reference): read-only `lstat` walk with
      parent-summed apparent sizes, symlinks never followed, hard links
      counted once per `(device, inode)`, one filesystem, progress +
      cancel, depth/node budgets so a huge tree stays responsive; works
      over the **root-id registry** — `deep-roots.json` ids (`home-projects`,
      `home-code`, `home-documents`, `home-desktop`) plus custom overlay
      entries — the console never accepts a free-form path (same rule as
      deep-scan).
- [ ] Console: `POST /api/cleanup/explorer/scan {rootId}` as a typed job
      (progress, cancel), subtree re-walk on drill-down with budgets;
      results carry per-node size, file/folder counts and newest-age.
- [ ] Dashboard tab: dua-style view — folder rows with proportional size
      bars sorted largest-first (sort modes: size / items / name), click to
      descend, breadcrumb + up navigation, collapsed subtrees with
      "measure" affordance, report-only rows with a "how to clean" hint
      linking to the plan flow or bookmarking for catalog-owned paths.
      Optional treemap mode built in-house (squarified layout component,
      no new dependencies). In-place tab navigation via Task 2.
- [ ] Seven-locale translations; Public Pages documentation-only; e2e:
      scan a fixture tree, descend, breadcrumb, no-reload behaviour.

### Rules
1. **No free-form paths anywhere in the API** — explorer roots and custom
   entries both resolve through typed registries; the raw path exists only
   inside the create-custom-entry request.
2. **Read-only first** — the explorer measures; deletion always happens
   through plan → confirm → run, and automated hooks stay Trash-only
   (Task 4).
3. **Honest numbers** — apparent sizes from `lstat`, on-disk size where the
   platform proves it (`null` otherwise); purgeable shown only when
   probed; every capability card reflects live readiness.
4. **Own tokens** — the overview layout is ported, Qleaner's colours,
   code and known bugs are not.

### Sub-task order
`CLNP-20 → CLNP-22 → CLNP-21 → CLNP-23` (overlay + data first, redesign
consumes them, explorer last). Verification and docs fold into each part;
`lat.md/cleanup-lab.md`, README/STATUS/VERIFY and roadmap entries update
with them, `lat check` + `scripts/run-tests.sh` at the end.

### Open questions (decide at implementation start)
- Explorer budget defaults (max nodes/depth per walk) and whether on-disk
  size is worth a second stat pass (default: apparent size only, v1).
- Treemap in v1 or bar-list first (default: bar-list first, treemap behind
  the same data once the walker is proven).
- Whether the Bookmarks open question (section vs tab) resolves to a tab
  now that the overview grids exist (default stays: section).
