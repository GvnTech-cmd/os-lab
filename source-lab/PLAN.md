# Source Lab integration plan

Bring the in-scope engine capabilities and user-facing pages in the pinned
[parity inventory](INVENTORY.md) into os-lab as `source-lab`, with navigation in
the existing dashboard and operations through the existing local console.
The engine/CLI and read-only evidence routes are implemented; other console
routes and the UI remain planned.
See README and the task queue for current behavior.

## Scope and rules

The baseline is the inspected iQ-SourceContol commit recorded in the inventory,
not its unfinished roadmap. Preserve Overview, Evidence, Deep analysis, Pipeline
and Brain, the five analyzers, crawler/merger, structural maps, signed runtime
sessions, reports and artifact-based navigation/search. Each retained inventory
item needs a tested destination.

The owner excludes Skills and agent/implementation-catalog integration, database
integration (including the SQLite/Prisma repository manager, sync, taxonomy and
notes), and OpenAPI/API-reference generation and pages. Their source routes are
recorded as excluded, not pending work. Repository selection and file/bundle
browsing in Deep analysis remain file-backed. Keep the engine JSON Schema and
generated TypeScript contracts; these validate artifacts and do not add OpenAPI
integration. This scope replaces the original all-pages parity target.

Follow `AGENTS.md`, `CONTRIBUTING.md`, `lat.md/lat.md`, `lat.md/overview.md`,
`lat.md/dashboard.md`, `lat.md/labctl.md`, `lat.md/setup.md`,
`lat.md/tooling.md`, `lat.md/ux-readiness.md` and `docs/UX_READINESS.md`.
Use conventional commits, scoped PRs and authorized fixtures. Reserve an existing
curated task only if a later implementation PR actually claims its task ID.

Source rules to carry over: Python and frontend code remain separate, data paths
are explicit, static leads never imply observed behavior, imported files retain
provenance, and known gaps remain visible. Future design stays here; graph nodes
should describe implemented behavior when each slice ships.

## Proposed architecture

Port the Next.js pages into Astro pages and React islands in `dashboard/`.
Move server-side logic from Next route handlers to Python console modules, using
the existing job/planning machinery for operations. Node remains a build-time
dependency of the dashboard, with optional Node syntax checks for the merger;
Bun, Next.js and Prisma are not required by the core installed console.

This choice preserves os-lab's current static distribution and minimal installer.
Prototype the Brain port before the bulk migration; document any
necessary architecture revision before importing their callers.

| Proposed location | Responsibility |
|---|---|
| `source-lab/engine/` | Namespaced Python analyzers, evidence, collectors, pipeline, sourcemap, CLIs and retained tests. Keep the CLI working-directory boundary and test import isolation. |
| `source-lab/scripts/`, `Makefile`, `.env.example` | Idempotent preflight/setup, capability discovery, CLI entry points and supported lifecycle/data maintenance operations. |
| `source-lab/doc/resources/` | Audited redistributable reference catalogs and research; optional external archive root for large/restricted source resources. |
| `source-lab/storage/` | Gitignored writable analyses, clone workspace, staged targets, merged outputs, sessions and key/settings. Separate curated inputs from generated data and imported legacy snapshots. |
| `console/source_lab/` | Proposed Python adapter: paths, validated API dispatch, job execution, file-backed artifact readers and runtime settings. |
| `dashboard/src/views/source/` | Ported React views and source-specific components/Brain store; reuse the os-lab shell, theme, Spotlight and components where practical. |
| `dashboard/src/pages/source/`, locale route generation | Retained static routes in the inventory, project docs and public capability descriptions. |
| `dashboard/src/lib/` | Namespaced typed API client generated from/validated against engine contracts; capability and job-store integration. |

Use canonical lab id `source`, directory `source-lab`, page root `/source/`,
readiness page `/labs/source/`, and API root `/api/source`. Update all LabId maps,
console lab metadata/order, navigation, icon/availability maps, locale route
lists and CLI dispatch together. Source Lab is a local analysis service, not a
new VM: static operation must not require Docker, KVM or mobile devices.

Add `labctl source` verbs appropriate to analysis, status, diagnostics and data
maintenance; state clearly which generic VM actions are unsupported. Make
`labctl all status` include Source Lab without blindly passing boot/resize/shell
to it. Expose supported actions as capabilities rather than offering inert buttons.

## Contracts, operations and access

Preserve the engine's V2 finding/coverage contract and structural-map V1 contract.
Export a machine-readable schema and generate frontend types or validate payloads
against it; do not add another hand-maintained schema mirror. Golden fixtures must
cover report contents, not volatile IDs/timestamps. Retain legacy AST links while
clients still depend on them.

Map retained inventoried HTTP methods to `/api/source`. Do not add the
excluded database, Skills/catalog or OpenAPI endpoints. The generic `/api` hello-world
stub is deliberately retired in favor of os-lab health. Bind handlers to the
console's localhost Host and mutation-header protections; no unauthenticated
remote exposure is introduced. Keep arbitrary commands and unrestricted paths
out of browser requests. Validate repository ids, source lists, URLs, platform
values, workers/depth/caps, artifact names and session ids. Reject traversal,
symlinks and files outside configured roots; keep bounded reads and responses.

Mutating runs receive a validated preview with effects, downloads and privileges
before execution, then a background job with polling/logs, redaction, timeouts,
conflict handling and process-tree cancellation. Preserve source 400/404/409/413/
503 error semantics where applicable and show errors beside the initiating action.
Tie previews to the exact target/options, so stale or altered execution is rejected.
A restarted console must report interrupted jobs accurately and retain artifacts;
source process-memory state must not produce a false running/success state.

Keep tokens in environment or protected server-side settings, never arguments,
URLs, artifacts, generated docs or logs. HMAC key status exposes metadata only;
managed keys use mode 0600. Preserve environment ownership, key precedence and
explicit rotation consequences for existing bundles. Trust runtime bundles only
after hash and signature verification. Record live versus synthetic collection,
missing tools, partial scans and not-applicable maps clearly. Scope browser test
URLs and network acquisition to authorized targets; new capabilities must not
silently expand target scope.

Read analysis bundles, targets, maps and sessions directly from validated local
files. No database, ORM, repository-index sync, taxonomy or notes store is part
of Source Lab. Existing JSON artifacts and generated contracts remain the
engine/UI boundary.

## Data, licensing and portability

The owner authorized first-party publication under os-lab's Apache-2.0 rules;
retain the grant and exclusions in IMPORT_POLICY.md. For permitted code, record origin commit,
original path, upstream/local hashes and modifications; retain source manifests
and add a relocation manifest. Update legal notices for actually imported code
and dependencies. Review catalogs, own-repository metadata and research for
personal data; exclude secrets, proprietary binaries/media and nested checkouts.

Provide an explicit, opt-in legacy import accepting an operator-supplied root.
Dry-run first: inventory counts/hashes/bytes, schema versions, duplicates and
unsupported items; produce an old-to-new path mapping. Copy into new storage
without mutating `/home/pod/iQ-SourceContol`; preserve originals and manual edits.
Import authorized first-party analysis, AST/maps, sessions and settings only;
do not import repository databases, taxonomy/notes or skill catalogs. Verify
counts/hashes and signature usability before switching. Keep file/settings
backup and rollback instructions. Third-party archives, datasets and binaries
remain excluded from public distribution.

Replace hardcoded `/i-vs`, source-checkout paths, port numbers, platform gate
hostnames and systemd names with os-lab configuration. Preserve useful setup,
service and project-docs workflows through os-lab tools; legacy remote deployment
registrations remain reference-only. Do not edit iQ-iUX or iQ-Bridge for this port.
Audit shared-component provenance without importing their cross-repo sync policy.

## UI parity and environment behavior

Use the page and subfeature tables in the inventory as acceptance criteria.
Source Lab appears in host/lab readiness and in the existing navigation with
Overview, Evidence, Deep analysis, Pipeline and Brain routes.
Preserve deep-link query parameters, report downloads, mobile navigation,
keyboard Spotlight records, theme, focus behavior and all usable Brain subviews.
Inspect Brain hooks for actual data/provider support; absent data gets an honest
unavailable/empty state, while working upstream behavior must be reproduced.
Label imported snapshot dates and provenance on Brain and Pipeline.

Show required Python and writable-storage readiness separately from optional
Playwright/Chromium, tree-sitter, Git/GitHub credentials, native telemetry tools
and merger Node checks. A missing optional component must not block static
analysis. An endpoint is configured until a live probe establishes availability.
Keep endpoint/configuration details collapsed; show requirements and primary
actions. Never treat empty coverage as proof a target is clean.

Local routes use the console. Public Pages routes under `/os-lab/` provide
readable documentation, reference/sample content and a clear local-install next
step; live runs, keys, merge and local records are unavailable there.
Do not poll a nonexistent engine or ship real private findings/sessions into the
public build. Build links with locale/base helpers and update every active locale
catalog (the current readiness guide requires seven). Verify the actual supported
locale set during implementation rather than relying on a copied count.

## Delivery sequence

Ship reviewable vertical slices, with existing labs usable after every step.
The corresponding task IDs and explicit dependencies are in [TODO](TODO.md).

| Slice | Scope | Exit evidence |
|---|---|---|
| 0. Baseline and rights | Confirm snapshot/census, clean fixtures, import rights and dependency licenses. | Reconciled parity ledger and permitted import list; unresolved rights block copying affected assets. |
| 1. Foundation | Namespaced engine import, portable paths/storage, schemas, CLI/preflight and static detection. | Retained engine tests, all five fixture platforms, all output formats, no-KVM/no-Node static run. |
| 2. Console integration | Lab registry, typed APIs, previews/jobs/cancellation, runtime settings/artifact guards. | Readiness and API contract tests, process cancellation/restart checks, signature/secret/path boundary tests. |
| 3. Evidence and overview | Static routes/shell/Spotlight; evidence/session controls/reports; matrices/catalogs. | Fixture-backed local user journeys, optional-tool states, migrated query links and source download parity. |
| 4. Analysis | Crawler/deep bundles/AST/map, merge preview/run/download, Pipeline and complete Brain viewer. | Crawl-to-map-to-evidence journey, merge output smoke, Brain views and explicit snapshot states. |
| 6. Project docs | Document implemented analysis workflows and configuration. | Retained workflow docs, graph links and search links resolve; excluded integrations are absent. |
| 7. Distribution | Install/update/minimal mode, optional extras, legacy data import, local/public routing and notices. | Fresh install and update checks on supported hosts; full relevant checks and signed-off parity ledger. |

Slice 5 and the Skills/OpenAPI tasks from slice 6 are excluded by the owner's
scope change; their IDs are retained only as exclusion records. Brain feasibility
is checked before slice 4. Keep upstream future target classes and research-only collectors in a
separate backlog so they do not obscure parity completion.

## Validation and completion

For this documentation PR: run `git diff --check`, `lat check`, check relative
Markdown links, and reconcile the inventory against every source page and route.
Do not report source historical test baselines as fresh execution.

For implementation slices: retain and run imported engine tests (the source
status reports 121 historical passes; discover the current suite), add focused
console/contract tests for new behavior, and exercise detection/reporting on
benign fixtures for all five platforms. Check signature failure, missing keys,
synthetic/live distinction, limits, traversal/symlinks, conflicting runs and
cancellation. Test crawler partial failures/resume and merger eligibility/output.
Verify file-backed artifact reads and target selection against sanitized fixtures.

For dashboard changes run all required commands from `dashboard/`:

```bash
npm run check
npm run test:i18n
npm run build
npm run test:e2e
```

Check all new page types for hydration, loading/empty/errors, disabled actions
and ready/missing-required/missing-optional/unavailable states. Build Pages with
`PUBLIC_SITE_MODE=pages SITE_BASE=/os-lab`, then verify routes, English and
non-English language switching, deep links and downloads in a browser.
Commit refreshed `dashboard/dist` with UI changes as required by contribution
rules. Run relevant console pytest and shell syntax checks, and the repository
runner from `lat.md/tooling.md` when shared runtime/installers change. Preserve
PowerShell 5.1/7 compatibility and UTF-8 BOM if Windows installer files change.

Update relevant implemented-state graph nodes for each shipped slice and run
`lat check`. Completion requires every retained inventory item and active TODO acceptance check
to have evidence, migration rollback to work, existing labs to pass regression
checks, and a clean minimal install without an external iQ checkout.
