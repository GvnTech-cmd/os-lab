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
