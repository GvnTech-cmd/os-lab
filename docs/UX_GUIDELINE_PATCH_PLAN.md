# Plan: os-lab UX guideline patch

## Working rules and owner request

The owner's request: "i mean best ux guideline patch for os-lab repo not qlar" and "regarding my prompts i asked in plan of qlar ux guidelinepatchs consider im asking same style prompts best fffor os-lab and regarding that analyze and create todo for its ux parts detailed which and agent can patch by reading plan and todo with smallest code read." This draft PR is the plan/todo home. It does not authorize claims that untested host or device behavior works.

- The owner subsequently asked to patch all code-backed findings in commits on this draft PR. That instruction supersedes the proposed split-PR sequence for points A–C and I–M. Keep the [todo](UX_GUIDELINE_PATCH_TODO.md) current, and keep the PR draft while evidence-first reviews and physical host/device acceptance remain open. New findings from D–H or N should still become focused follow-up PRs when verified.
- Before a slice, read its **First read** paths and the matching test, then inspect only direct callers/types needed for the change. Read [AGENTS.md](../AGENTS.md), [UX readiness](UX_READINESS.md), and [the UX graph node](../lat.md/ux-readiness.md) for shared rules. The broad inventory is a reconciliation task, not a reason to read the whole repository before each fix.
- Preserve working actions, Source Lab destinations, downloads, locale routes, and local/public separation. The [Source inventory](../source-lab/INVENTORY.md) records retained and excluded features; the [Source TODO](../source-lab/TODO.md) has completed UI work. Do not revive excluded integrations or treat an older sentence in the Source plan as current implementation status.
- The guideline update is **standard plus enforcement**: write measurable rules into `UX_READINESS.md`, then patch verified violations. Do not style-churn a working page merely to satisfy an abstract rule. Record a reproduction or code-level failure before changing behavior.
- For subsequent feature work, the owner chose a behavior-first sequence: types, stores, API calls, and plain functional pages/controls; verify those flows; then make a focused visual design pass. Keep existing UX work. Functional pages still need honest readiness, errors, confirmation, and basic accessibility. A backend-only draft is a handoff, not feature completion.
- Cleanup Lab batches remain sequential work with **one PR per CLN task**. Never bundle several CLN tasks into one PR; record the functional and visual gates on each task's own PR.
- Update the relevant `lat.md/` node when behavior changes. Rebuild committed `dashboard/dist/` for dashboard source changes. PR bodies report checks run, concrete before/after evidence, and untested host/device paths.

## Grounded baseline

`docs/UX_READINESS.md` already covers host-derived readiness, required versus optional setup, exact action previews, configured endpoints, secrets, public Pages separation, feedback, and core checks. This PR corrects one concrete drift: it said seven locale catalogs, while `dashboard/src/firewall/locale.ts` declares eight (`en`, `tr`, `de`, `fr`, `es`, `it`, `fa`, `ar`). Derive coverage from the active catalog list.

Current code also exposes these focused candidates:

| ID | Evidence in `master` | Required outcome |
| --- | --- | --- |
| A | `dashboard/src/views/jobs-page.tsx`, `JobLog` cancel handler awaits `api.cancel()` with no catch or visible error; a failed request leaves the user with no adjacent explanation. | Show submit/cancel progress, failure beside Cancel, and a safe retry; keep server state authoritative. |
| B | `dashboard/src/views/public-home.tsx` silently swallows latest-release fetch errors and `Copy` calls `navigator.clipboard.writeText()` without a result state. | Make lookup failure and clipboard success/failure understandable, with a working manual next step. Do not claim a specific installer asset exists when lookup failed. |
| C | `dashboard/src/styles/iux.css` sets `.iux-btn` and icon buttons to 32 px; shared shell buttons use it in `dashboard/src/shell/app-shell.tsx`. `dashboard/src/views/firewall-page.tsx` has a small text-only alternatives toggle. | On coarse pointers, give interactive controls a usable target (44×44 CSS px where feasible), without inflating desktop layout; verify dense cases and adjacent-target separation. |
| D | `dashboard/src/views/source/brain.tsx` implements keyboard-selectable SVG nodes and URL state, while Source routes are defined in `dashboard/src/views/source/pages.tsx`. This is existing functionality, not a defect claim. | Audit focus, readable graph alternative, query/deep-link preservation, and no clipping; patch only reproduced failures. |
| E | `dashboard/src/views/lab-page.tsx` already previews actions and reports poll/cancel failures; `dashboard/src/views/source/action.tsx` has an exact-preview workflow. | Reconcile the same failure/recovery contract across host, lab, Source, and Android without duplicating good behavior. |
| F | `dashboard/src/shell/app-shell.tsx` uses native dialogs for the mobile drawer; `dashboard/src/shell/spotlight.tsx` has search semantics. | Check the complete keyboard/focus/return path, sticky bar, mobile width, theme, and RTL on representative routes; patch reproduced gaps. |
| G | `dashboard/README.md` says public deployment filters Astro output into `dashboard/build-pages/`; `lat.md/ux-readiness.md` requires Source and How-to-use smoke on that final artifact. | Acceptance must inspect the filtered artifact, not just the raw Pages build. |

These are code observations. A, B, and C support immediate scoped implementation; the audit below adds further code-backed fixes. D–G require a short evidence pass before code changes. Keep verified pass results in the todo, rather than opening redundant PRs.

### Dashboard page and component audit (static review)

This pass inventoried `dashboard/src/pages/`, the corresponding `views/`, `shell/`, `components/ui.tsx`, and the three dashboard E2E specs. It is a **source audit**, not a browser/device pass. The route groups below tell the next agent where to start. “Verify” rows are acceptance checks, not asserted bugs.

| Routes / component | Code-backed gap or verification target | Best scoped treatment |
| --- | --- | --- |
| `/`, `/labs/<lab>/`, `/jobs/`, `/health/` | Jobs cancel failure lacks a catch; the lab-page cancel path already has a local error pattern. Health's `role=tablist` platform controls use tab roles without arrow-key handling or a tab/panel relationship. | Fix Jobs cancel locally; implement a complete tab interaction in Health (or use ordinary grouped buttons if tab semantics are unnecessary). Verify ready/setup/unavailable and job recovery with existing health E2E fixtures. |
| Shared `CopyButton` in `components/ui.tsx` | `navigator.clipboard?.writeText()` rejection is swallowed, yet the check icon appears; the button is `size-7` (28 px). | Show copied only after success, expose failure and a selectable/manual route; let the shared coarse-pointer rule enlarge the hit area. Test denied clipboard on a page using this component. |
| `/android/*` workbench | `ConsolePage` Clear awaits `api.clearLogs()` without catch or pending state; Stop catches errors. `RunButton` already reports errors beside actions. | Add local pending/error state for Clear, disable conflicting repeat clicks, preserve logs if clearing fails, and refresh from the server after success. Keep existing RunButton behavior. |
| `/source/*` | Existing Source E2E covers destinations, previews, cancellation, evidence states, Brain, mobile drawer, and theme. `brain.tsx` draws keyboard-selectable graph nodes in an internally scrollable SVG. | Run a focused zoom/keyboard/screen-reader and narrow/RTL pass before changing Source. Preserve graph/export/deep links and label any proven issue with fixture and route. |
| `/firewall/`, `/firewall/<company>/` | `ContributeModal` and `GapModal` focus their container and restore focus, but use non-native `role=dialog` overlays without trapping focus or making the background inert. Company Network/Gaps has `role=tablist` and tab roles without arrow-key/roving-tabindex behavior. Small text toggles also bypass `.iux-btn`. | Prefer native modal dialog semantics or equivalent focus trap/inert handling, retaining Escape/backdrop/return focus. Complete tab semantics or use ordinary buttons. Apply coarse-pointer sizing to text-only controls. |
| `/contribute/` | `copyToClipboard()` swallows failure and sets `copiedId` unconditionally. The task data in `cleanup-lab-tasks.tsx` repeats “all seven locale catalogs” three times. | Reuse a truthful clipboard-result pattern with selectable fallback; correct task copy to “all active locales” without hard-coding a count. Preserve reservation/branch commands. |
| Public `/` | Release lookup failure and setup-command Copy lack result states (finding B). | Distinguish loading from lookup failure; keep release-page fallback and add copy/manual-select feedback. |
| `/how-to-use/`, `/feedback/`, `/legal/*`, `/content/`, `404` | How-to-use already handles clipboard rejection and manual selection. Feedback has distinct bug/feature/discussion/private-security links. Legal/content use locale-aware links and static English legal text. The 404 briefly renders nothing while resolving an unprerendered Firewall company. | Keep existing working behavior. Verify keyboard, locale/base routing, final Pages artifact, and 404 loading/unknown-company result; patch a failed check only. |
| App/content update panels | `app-update-panel.tsx` retains last progress if polling fails, without a visible stale-connection cue; this may leave a downloading phase on screen until polling recovers. | Reproduce with a mocked polling failure before patching; if stale progress persists, label it as last known and provide retry/status guidance without falsely claiming completion. |

Existing tests cover many Source and readiness cases; add tests for the **new** failure paths and interactions above, rather than cloning current assertions. The todo gives one checklist item per fix or evidence pass.

### Copy sweep candidates (review before editing)

| Location | Current effect | Recommendation |
| --- | --- | --- |
| `host-page.tsx` `MinimalistHero.description` | The dynamic ready count is followed by two standing sentences explaining setup and preview, also shown by the cards/actions. | Keep the dynamic count; shorten the standing guidance to one concise next-step phrase if a user check confirms the duplication. |
| `jobs-page.tsx` `PageHead.description` | “Source Lab keeps private restart records…” is a Source-specific implementation detail on the general Jobs landing page. | Keep the 50-job limit; move restart/interruption detail next to an interrupted Source job or help detail. |
| `content-panel.tsx` when an update is available | “A newer content pack is available” appears both in the main line and an Advanced badge. | Keep one visible update status and the version; retain hooks and signed-content consequences. |
| `source/pages.tsx` public Source intro | Section description and body both say the public page needs a local console and has no local engine. | Consolidate into one short explanation plus a clear install next step; preserve the no-private-targets promise. |
| `cleanup-lab-tasks.tsx` | Three visible task deliverables specify seven catalogs. | Correct to “all active locales” as UX-M, independently of any broader copy sweep. |

These are candidates, except the factual locale correction. UX-H records the final keep/change choice and an exact before/after string before a copy PR.

## UX contract to add to the guideline

1. **Action truth.** A visible action is backed by a current capability and host report. Required and optional prerequisites are separate. The preview identifies target/options, command/effects, privileges, and downloads; changed options invalidate confirmation. An unavailable control gives a reason and a manual or retry path where one exists.
2. **Job recovery.** Submission, polling, cancellation, and refresh failures appear beside the initiating control or job. Pending/running/succeeded/failed/cancelled/interrupted states come from the backend. A lost connection or cancelled request never becomes a false success. Duplicate or conflicting submission is prevented while still allowing safe retry after failure.
3. **Evidence truth.** Configured addresses are not observed services. Imported/synthetic/partial Source results are labeled with provenance and time where relevant; missing optional tooling and empty coverage do not imply a clean live target. Private artifacts and secrets stay out of public Pages.
4. **Native-feeling web UX.** Navigation and overlays have clear focus order and return focus, keyboard/Escape behavior, visible focus, and usable coarse-pointer targets. Shared controls work at narrow width, text zoom, light/dark themes, and Arabic/Persian RTL. A dense data table may scroll inside its own region; the whole page should not pan sideways because of one child.
5. **Public truth.** Pages under `/os-lab/` offer information and browser-only features without local engine polling or inert local controls. Locale/base links, deep-link queries, feedback/legal/security routes, release lookup, and copy actions have understandable success/failure states. Visible copy is complete in every active catalog.
6. **Concise copy.** Show dynamic warnings and consequences where they matter. Avoid repeating a standing “ready” statement or a paragraph that duplicates the control itself. Keep setup, security, and irreversible-action warnings intact; move secondary detail into a discoverable location.
7. **Behavior before polish.** For new features, establish types, state/store, API calls, and plain accessible pages or components; prove real success and failure flows; then design their visual treatment in one focused pass. Existing working UX stays. Keep one Cleanup Lab task per PR and mark unfinished page or design work explicitly.

## Stable points and acceptance

| Point | Smallest scope and first read | Acceptance evidence |
| --- | --- | --- |
| 0. Guideline text | `docs/UX_READINESS.md`, `lat.md/ux-readiness.md` | Add the six contracts above as reviewable rules; keep current working rules; `lat check` after graph edits. |
| A. Jobs cancel feedback | `dashboard/src/views/jobs-page.tsx` (`JobLog`), `dashboard/src/views/lab-page.tsx` (`JobCard` as reference), `dashboard/e2e/health-and-content.spec.ts` | Rejected cancel request is visible at the job, button does not double-submit, retry remains possible, success refreshes server state. |
| B. Public home async feedback | `dashboard/src/views/public-home.tsx`, `dashboard/e2e/health-and-content.spec.ts` | Release lookup failure shows an honest fallback; copy success and clipboard rejection have accessible status and manual-copy route; no permanent “checking” label. |
| C. Coarse-pointer controls | `dashboard/src/styles/iux.css`, `dashboard/src/shell/app-shell.tsx`, `dashboard/src/views/firewall-page.tsx` | Representative shell, action, dialog, and Firewall controls have usable hit areas on coarse pointer; desktop density, focus ring, and narrow/RTL layout remain sound. |
| I. Shared clipboard truth | `dashboard/src/components/ui.tsx` `CopyButton`, `dashboard/src/views/contribute-page.tsx` `copyToClipboard`, `dashboard/src/views/how-to-use-page.tsx` as reference | Denied clipboard never displays “Copied”; success is announced; manual selection remains available. |
| J. Android Clear feedback | `dashboard/src/views/android/pages.tsx` `ConsolePage`, `dashboard/src/views/android/common.tsx` | Rejected Clear is visible, current logs remain, repeat clicks are blocked while pending, success refreshes server logs. |
| K. Firewall dialog focus | `dashboard/src/views/{contribute-modal,gap-modal}.tsx`, `dashboard/src/styles/firewall-contribute.css` | Tab/Shift+Tab cannot reach background controls while modal is open; Escape/backdrop/close and return focus work at mobile/RTL widths. |
| L. Tab semantics | `dashboard/src/views/health-page.tsx` `PlatformTabs`, `dashboard/src/views/firewall-company-page.tsx` Network/Gaps, `dashboard/src/views/source/overview.tsx` as reference | Arrow/Home/End navigation or ordinary-button semantics are internally consistent; active panel/control is correctly identified to assistive tech. |
| M. Contributor locale copy | `dashboard/src/views/cleanup-lab-tasks.tsx`, `dashboard/src/firewall/locale.ts` | All three stale “seven locale” task strings say “all active locales” or reflect the actual list; no changed task meaning. |
| D. Local action parity | `dashboard/src/views/host-page.tsx`, `lab-page.tsx`, `source/action.tsx`, `android/common.tsx`, `jobs-page.tsx` | Matrix records exact-preview, required/optional, busy/conflict, cancel/poll error, retry and manual guidance for each; patch only failed cells. |
| E. Shell and Source navigation | `dashboard/src/shell/{app-shell,sidebar,spotlight,top-bar}.tsx`, `dashboard/src/views/source/{pages,brain}.tsx`, `dashboard/e2e/source.spec.ts` | Mobile drawer/Spotlight focus and Escape, deep-link queries, graph selection, sticky header, zoom/narrow/RTL pass or have focused fixes. |
| F. Source evidence | `dashboard/src/views/source/{evidence,pipeline,brain,overview}.tsx`, `source-lab/INVENTORY.md`, `dashboard/e2e/source.spec.ts` | Live/synthetic/imported/partial/unavailable and empty-coverage wording remain truthful; retained reports/downloads/routes still work. |
| G. Public Pages and locale | `dashboard/src/views/{public-home,how-to-use-page,firewall-page,feedback-page,legal-page}.tsx`, `dashboard/src/i18n/paths.ts`, `dashboard/src/firewall/locale.ts` | Final filtered artifact has all active locale routes, browser-only features, base-aware links, non-English query-preserving switch, RTL/mobile, and no private/local operations. |
| H. Copy sweep | `dashboard/src/views/{host-page,lab-page,jobs-page}.tsx`, `dashboard/src/views/source/*.tsx` | List exact repetitive/ambiguous copy with replacement/removal proposal; patch selected candidates in small surface PRs while retaining safety and operational guidance. |
| N. Stale update/404 states | `dashboard/src/views/{app-update-panel,not-found-page}.tsx` | Mock slow/failed update polling and dynamic-company lookup; show truthful last-known/loading state only if current UI misleads or goes blank. |

Points D–H and N are review gates. If a point passes, close it with test or manual evidence and no code PR. Do not infer missing features from this table.

The owner chose to bundle the code-backed fixes in this draft PR. D–H and N remain evidence passes; re-check fresh `master` before later follow-up work because another PR may have fixed a candidate.

## Verification and completion

For each dashboard code PR, run in `dashboard/`: `npm run check`, `npm run test:i18n`, `npm run build`, and scoped `npm run test:e2e -- <spec>`; use the full E2E suite when shared shell or public routing changes. Run relevant console tests and `scripts/run-tests.sh` when contracts or committed distribution output change. `git diff --check` is required. Run `lat check` after graph changes. Record pre-existing failures separately from introduced failures.

For public Pages, build with `PUBLIC_SITE_MODE=pages SITE_BASE=/os-lab`, run `scripts/deploy-page.sh --dry-run`, and smoke the **filtered** `dashboard/build-pages/` artifact with `node dashboard/scripts/source-pages-smoke.mjs dashboard/build-pages` and `node dashboard/scripts/how-to-use-pages-smoke.mjs dashboard/build-pages` when their routes are involved. Check English and non-English deep links, Arabic/Persian RTL, mobile drawer, feedback/legal links, and absence of local API calls/private outputs. Do not call a raw Astro build the deployed artifact.

Automated tests do not prove native host and physical-device behavior. Record platform, device, viewport, actual route/state exercised, and remaining limits. Keep this tracker draft until required manual acceptance is recorded or the owner explicitly accepts the limits.
