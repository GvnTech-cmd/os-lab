# Source Lab TODO

This is the implementation queue for [PLAN.md](PLAN.md), measured against
[INVENTORY.md](INVENTORY.md). Completed engine foundation tasks are marked below. Check a task only
when its acceptance evidence is linked in the implementation PR or this ledger.
Implementation was merged in PR #103; the public Pages deployment fix is PR #105.
Version 0.3.0 is published. Acceptance evidence and open bonus verification
limits are recorded in [VALIDATION.md](VALIDATION.md).

## Scope

The owner excludes Skills/agent catalogs, database-backed repository management
(including sync, taxonomy and notes), and OpenAPI/API-reference integration.
Engine JSON Schema/generated TypeScript, file-backed target and bundle browsing,
and ordinary project documentation remain in scope. The owner also skips further
merger UI/parity work (SRC-042); the merger engine and console API already
implemented in this PR remain available. Excluded items are neither
open tasks nor completed implementation. Stable task IDs are preserved.

## Planning baseline

These completed tasks describe this planning PR only, not delivered runtime.

- [x] PLAN-01: Fetch latest os-lab master and create a standalone worktree/branch.
- [x] PLAN-02: Read os-lab architecture/contribution/readiness guidance and source rules/graph.
- [x] PLAN-03: Pin source commit and inventory all pages, HTTP methods and engine capabilities.
- [x] PLAN-04: Record phased architecture, dependencies, known gaps and validation requirements.

## Slice 0: Import decisions

Finish these before copying the affected source code or data.

- [x] SRC-001 (no dependency): Resolve source code license and archive redistribution rights; list permitted/excluded assets and dependency notices. Accept: documented origin/license evidence compatible with os-lab, with unlicensed material held out pending resolution.
- [x] SRC-002 (no dependency): Reconcile inventory with source at import time, including seven pages, docs/API, every method, shell and Brain subviews. Accept: pinned revision, upstream-to-destination parity ledger and explicit dispositions for stubs and unavailable data.
- [x] SRC-003 (SRC-001, SRC-002): Create sanitized detection/crawler/merge/map/session/UI fixtures and provenance/relocation manifest. Accept: reproducible fixtures without proprietary media, keys or personal metadata; checksums and upstream file mapping retained.

## Slice 1: Portable engine and lab foundation

Establish a usable static analysis path independently of optional runtime tools.

- [x] SRC-010 (SRC-003): Import analyzers/binfmt/evidence/collectors/CLI/tests under `source-lab/engine/`, isolate imports from existing Android modules and retain provenance. Accept: retained suite passes in its documented environment and importing either lab cannot shadow the other.
- [x] SRC-011 (SRC-010): Configure resource/work roots and gitignored storage, fixtures, `.env.example` and portable launchers. Accept: clean checkout operates with explicit paths and no `/home/pod` dependency; generated data never pollutes code/catalog inputs.
- [x] SRC-012 (SRC-010): Export V2 evidence and structural-map schemas; add validation/generated frontend contracts and format compatibility fixtures. Accept: unsupported versions/errors are visible; no hand-maintained duplicate schema.
- [x] SRC-013 (SRC-011): Add Makefile/preflight/setup and `labctl source` dispatch, supported verbs, doctor/status and `all` handling. Accept: static runs need Python/storage only; unsupported VM verbs give a useful error and existing lab dispatch still works.
- [x] SRC-014 (SRC-010, SRC-011): Verify auto/explicit detection on browser/userscript, Windows/Electron, macOS, Android and iOS fixtures; preserve rule families/H1-H5 and all CLI reports including STIX. Accept: expected evidence/coverage artifacts for every platform, including parser failures/caps.
- [x] SRC-015 (SRC-010, SRC-011): Import sourcemap CLI/VFS/adapters/resolver/filter/rank/export functions. Accept: disk/ASAR, supported languages, generate/query, JSON/Markdown/DOT, fallback parsers and binary-only not-applicable tests pass.

## Slice 2: Console and contracts

Integrate with the existing console protections, readiness model and jobs.

- [x] SRC-020 (SRC-012, SRC-013): Add `source` to console lab metadata/order, host reports, capability/action models and frontend LabId maps. Accept: required/optional readiness and unavailable hosts are correct without KVM/Docker.
- [x] SRC-021 (SRC-020): Implement namespaced handler adapters for each retained inventory API method, query/body and response/error contract. Accept: method-by-method contract tests and intentional deviations documented; hello-world stub retired explicitly. Acceptance: all retained methods have adapters and tested intentional contract adaptations in [API.md](API.md).
- [x] SRC-022 (SRC-021): Integrate exact-option previews, background logs/progress, conflict handling, timeout/cancel/process-tree cleanup and interrupted-on-restart reporting. Accept: two runs cannot corrupt the same output and cancelled/interrupted jobs cannot show success.
- [x] SRC-023 (SRC-021): Enforce localhost/mutation guards, allowlisted target/resource/session paths, symlink/traversal rejection, read caps and secret redaction. Accept: hostile-request regression tests pass and logs/responses disclose no credentials. Acceptance: mutation framing/Host/header, typed options, private input/output roots, symlink rejection, bounded reads/logs and credential redaction are covered by the console suite.
- [x] SRC-024 (SRC-021, SRC-023): Port managed runtime settings/key generation/rotation/default canary URL and integrity verification. Accept: environment ownership/precedence, mode 0600, rotation warnings and tampered/missing-signature cases tested; key values never reach UI.
- [x] SRC-025 (SRC-024): Preserve browser canary and all four native importer libraries. Accept: signed sessions can be reviewed/correlated, synthetic events are clearly marked and cannot masquerade as live proof; absent native collector workflows stay explicit.
- [x] SRC-026 (SRC-012, SRC-013): Serve bounded findings/coverage/events and allowlisted report downloads. Accept: source five HTTP formats work, CLI STIX remains available, and adding HTTP STIX is tracked explicitly if chosen.

## Slice 3: Dashboard shell, overview and evidence

Use os-lab's static pages, existing shell and locale/base-path helpers.

- [x] SRC-030 (SRC-020): Add `/labs/source/`, `/source/` and nested routes, sidebar/icon/availability, mobile navigation, theme and record Spotlight. Accept: all retained inventory destinations and query links resolve locally, with accessible keyboard/focus behavior.
- [x] SRC-031 (SRC-021, SRC-030): Port Overview matrices (properties/backgrounds/dependencies/permissions), inspector, annotations, counts, filters, sources and CSV downloads. Accept: fixture results match the source UI and all tabs have loading/empty/error states.
- [x] SRC-032 (SRC-022, SRC-031): Port source-list crawler runner/options/progress/logs and H1-H5 reference. Accept: configured inputs validated, preview/run/cancel workflow works and failures render beside actions.
- [x] SRC-033 (SRC-025, SRC-026, SRC-030): Port Evidence findings/state/severity/scorecard/spans/coverage/verification, target/platform runner, polling/cancel, session list/timeline and reports. Accept: five-platform fixture journeys preserve evidence levels and explain partial coverage.
- [x] SRC-034 (SRC-024, SRC-033): Port runtime key controls, two-step rotation, canary URL/default/toggle, Playwright warning and session selection. Accept: missing-required versus optional tooling, synthetic mode and environment-owned keys render correctly.

## Slice 4: Deep analysis, pipeline, merger and Brain

Keep structural maps distinct from evidence and expose snapshot provenance.

- [x] SRC-040 (SRC-011, SRC-022): Import crawler/list parsing/CSV merge and route adapters, worker/depth/cap/resume/rate-limit controls. Accept: fault-isolated stages, interrupt artifacts and selected-target workspace/token guards pass tests.
- [x] SRC-041 (SRC-015, SRC-030, SRC-040): Port Deep analysis bundle/source/AST browsing and Map dialog (stats/roles/targets/coverage/symbols/imports/entrypoints). Accept: `?repo=`/`&file=` deep links and legacy AST behavior work; missing artifacts show useful states.
**SRC-042 — skipped by owner.** Do not implement further merger planning/run/
cancel/download UI or require merger UI parity for release. Existing engine/API
functionality is retained; this task is neither open nor completed.
- [x] SRC-043 (SRC-030, SRC-040): Port Pipeline API/flowchart/stages/network/heuristics/candidates and bundled fallback. Accept: stage details match the pinned snapshot and its date is visible; no claim of automatic regeneration.
- [x] SRC-044 (SRC-003, SRC-030): Prototype Brain's data/provider hooks and React/Astro embedding. Accept: documented feasibility for each inventory subview, dependency licenses checked and snapshot/API roots portable.
- [x] SRC-045 (SRC-044): Port Brain graph/tabs/filter/legend/usages/source/history/diff/flowchart/sequence/AI-rules/complexity/risk/stress/export and virtual store behavior. Accept: each usable upstream view has a fixture-backed check; absent providers show explicit unavailable states.

## Slice 6: Project documentation

Document implemented file-backed workflows and configuration without adding
Skills, databases or an OpenAPI reference.

- [x] SRC-062 (SRC-014, SRC-015, SRC-045): Publish portable Source Lab docs and graph links, update README/setup/labctl/dashboard/tooling graph nodes as features ship. Accept: docs describe retained workflows and scope exclusions, links resolve and `lat check` passes.

## Slice 7: Distribution, import and release

SRC-070 implementation is delivered. The owner subsequently moved remaining
native/live acceptance and required patches into open bonus contributions
SRC-B01–SRC-B06 in [CONTRIBUTING.md](../CONTRIBUTING.md). Checking implementation
below does not mark those bonus checks passed. See VALIDATION.md and AUDIT.md.

Release only after both installed-console and public-site behavior is verified.

- [x] SRC-070 (SRC-013, SRC-024): Integrate Linux/macOS/Windows install/update/minimal paths and optional parser/browser tools; adapt useful service/project-docs operations. Portable staged-runtime/update-preservation checks passed. Native fresh install/update acceptance is explicitly deferred by owner to SRC-B01/SRC-B05; it has not passed here.
- [x] SRC-071 (SRC-001, SRC-011, SRC-024): Implement opt-in legacy dry-run/copy/import for authorized first-party artifacts/maps/AST/sessions/settings with path mapping and backups. Accept: counts/hashes/signatures verified; databases, skills and third-party archives/datasets/binaries excluded, originals unchanged and rollback documented/tested.
- [x] SRC-072 (SRC-030, SRC-031, SRC-032, SRC-033, SRC-034, SRC-041, SRC-043, SRC-045, SRC-062): Complete all active locale catalogs and Pages equivalents. Accept: `/os-lab/` links, English/non-English switching, docs/samples/deep routes work; local-only actions/engine polling/private outputs are absent from public build.
- [x] SRC-073 (SRC-070, SRC-071, SRC-072): Run engine/console regression tests and relevant repository checks, shell syntax and installer parse checks; dashboard check/i18n/build/e2e and browser local/Pages smoke. Accept: commands/results recorded, committed `dashboard/dist` current and existing labs pass.
- [x] SRC-074 (SRC-002, SRC-062, SRC-073): Audit every retained inventory row/subfeature and API method, finalize attribution/legal notices and release/runbook/rollback docs. Accept: no silent omissions, all exceptions reviewed and each claimed capability has validation evidence. See [AUDIT.md](AUDIT.md); native acceptance is not claimed.

## Excluded by owner

These task IDs are retired from the active queue rather than marked complete.

| Former task | Excluded work |
|---|---|
| SRC-042 | Further merger UI/parity work; existing engine/API retained. |
| SRC-050 | SQLite compatibility spike. |
| SRC-051 | Database migrations, repository-index sync and automatic classification. |
| SRC-052 | Database-backed repository/taxonomy APIs. |
| SRC-053 | Repository manager page, notes, tags and categories. |
| SRC-060 | Skills, live skill generation and implementation-catalog search. |
| SRC-061 | OpenAPI generation and API-reference page. |

## Follow-up backlog carried from upstream

These items are not already shipped features and must not be confused with parity.

- [ ] NEXT-01: Decide platform-specific overview/targets/evidence navigation and new datasets/crawlers for userscripts, desktop/mobile applications, MCP servers and own repositories.
- [ ] NEXT-02: Add real native collection workflows and the research-only Windows memory/IAT/EAT, Apple IMP/prologue and Android process/ART checks with authorized targets and provenance.
- [ ] NEXT-03: Regenerate Brain/Pipeline data reproducibly or replace snapshots with generated maps.
- [ ] NEXT-04: If remote deployment is requested later, design authenticated access; external upstream gates do not transfer automatically.
