# Source Lab validation and review

This file records review evidence for the public migration PR. It distinguishes
implemented behavior from the remaining task queue.

## Planning commit

Commit `7c6b81a` adds original planning documents only. It includes no copied
engine/UI code, third-party archives, datasets, binaries, credentials or reports.
The source inventory was checked against seven pages and 29 API routes exposing
41 HTTP methods; local Markdown links, task references and `lat check` passed.

## Engine foundation

The first implementation slice imports the owner's authorized first-party
engine and synthetic source fixtures, with namespaced imports and full relocation
hashes. Original source data, deployment settings and third-party material are
excluded. The input snapshot remains the revision pinned in PROVENANCE.json;
its page and API census is unchanged.

Review covers `CONTRIBUTING.md`, `SECURITY.md`, acceptable use, terms, privacy
and third-party notices. The import policy records the owner's explicit public
Apache-2.0 publication authorization. No credentials or personal data are present
in new fixtures; binary parser samples are generated in temporary directories.
The legal pages describe local storage and user-triggered network workflows.
No console listener, request protection or public live action has been added.

Implemented acceptance checks cover SRC-001/002/010/011/013/014/015: retained
engine tests plus portable launcher, independent target outputs, five-platform
reports, namespace isolation, synthetic evidence rejection, standalone PE input
and resource/output separation. SRC-003 remains open for session/UI
migration fixtures, and SRC-012 is completed in the subsequent contracts milestone.
CLI pipeline modules are retained, but their console/UI workflows remain open.

Validation commands and final results are recorded in the PR after the complete
check run. Source historical test counts are not used as fresh verification.

The engine foundation validation completed on 2026-11-09:

- `scripts/run-tests.sh --no-venv`: 7 stages passed, no failures; Android 104
  passed/2 skipped and Source Lab 133 passed; sample smoke, shell syntax,
  graph, dashboard types and committed-build freshness passed.
- Dashboard `npm run check`, `npm run test:i18n` (1933 keys across seven locales),
  `npm run build` (337 pages), and `npm run test:e2e` (15 passed) completed.
- Fresh-checkout checks initially needed Astro's generated types; the repository
  runner now runs `astro sync` before typechecking. The first browser attempt
  needed the matching Chromium test runtime, installed in the local cache only.
- Local fixture crawler, map generation and merge-plan smoke checks passed.
- `python3 source-lab/scripts/check-import.py` verified 108 provenance hashes
  and no tracked excluded assets. The staged credential scanner found no
  credential signatures (synthetic test/example paths are skipped by that tool
  and were reviewed separately). `git diff --cached --check` passes.
- The separate Pages build and browser smoke rendered all 12 English/Turkish
  legal routes without hydration errors, but found that Markdown cross-links
  escaped the Pages base. That check was initially recorded as passing before
  its final result returned. The following navigation fix adds regression
  coverage and reruns this check before publication.

Console endpoints and Source Lab UI pages are not implemented by this milestone;
their tasks remain open. No claim of full migration parity is made.

## Legal navigation follow-up

The follow-up fixes Markdown cross-links and legal navigation to preserve locale
and Pages base paths. It changes navigation only; the legal terms are unchanged.
Regression tests cover English/Turkish document links and following a terms link.
The initial Turkish assertion used an English label that the UI translates; the
assertion now uses the active-link semantics while still checking its exact URL.

Follow-up results: dashboard check, translation check and local build pass; all
17 browser tests pass. The separate Pages build passes. Browser smoke verifies
12 English/Turkish local/Pages legal routes, both language-switch directions,
following the terms link, correct Pages prefixes and no hydration errors.

## Generated contracts milestone

The next slice completes SRC-012: exported V2 evidence/V1 structural-map schemas,
engine-vocabulary validation and generated frontend types. All 141 engine tests
pass, including actual report/map compatibility, invalid versions/states,
non-finite/out-of-range confidence and regeneration freshness. Dashboard type and
translation checks pass; the generated file is unused by current runtime pages,
so it does not change the built assets. `lat check`, provenance/exclusion checks
and staged whitespace checks pass. The existing Android suite and browser
checks were unchanged since the preceding validated milestones.

This slice is original standard-library code and generated contracts, reviewed
against the same contribution/security/legal rules. It adds no dependency,
network activity, archive, dataset, binary or private fixture.

## Scope reduction

The owner removed Skills/agent catalogs, database integration (including the
repository manager and sync/taxonomy/notes), and OpenAPI/API-reference integration.
SRC-050/051/052/053/060/061 are retired as exclusions, not marked implemented.
Their dependencies are removed from active tasks. Five app pages and 13 source
API routes (19 methods) remain migration targets; the full source census stays
in the inventory with explicit dispositions. Engine schemas/generated types and
file-backed analysis browsing remain required. No runtime implementation was
removed, because these integrations had not been added.

This update changes planning documents only. Validation covers Markdown links,
task/dependency references, scope counts, `lat check`, provenance/exclusion checks
and whitespace. Previous runtime test results above are historical; they are not
reported as rerun for this scope-only update.

## Reusable workspace fixtures

SRC-003 is complete: the owned browser fixture now generates detection reports,
a crawler bundle, structural map, planned/built MV3 merge, a signed synthetic
session, UI response data and output SHA-256 manifest in a fresh temporary root.
No third-party data is acquired, no generated binaries/archives are committed,
and the ephemeral session key is supplied explicitly rather than stored. Existing
workspace files are preserved by refusing an existing destination. Validation:
143 engine tests, graph, import/exclusion and whitespace checks pass.

## Read-only evidence endpoints

SRC-026 is complete: the existing localhost console serves evidence summaries,
detail, bounded session timelines and the five planned report download formats.
The reader is standard-library code and never imports or starts the engine.
Session integrity is explicitly not verified by this display endpoint; the
reader does not expose keys or session seals. CLI-only STIX remains unchanged.

This also completes the evidence GET subset of SRC-021 and the read-only path,
size, Host and response-header subset of SRC-023; those broader tasks remain
open for the remaining routes/mutations. The tests cover generated workspace
responses, five-format downloads, foreign Host headers, traversal/duplicate/
unknown parameters, excluded endpoints, symlinks, named pipes, malformed data,
unsupported versions, per-file/aggregate byte budgets and event/directory caps.

Publication review: no new dependencies, outbound requests, hosted listeners,
third-party data, binaries or credentials are added. Existing privacy/terms
already describe these local reports and the localhost console. No dashboard
source or legal-page content changes, so dashboard rebuild/browser checks are
not required for this backend patch.

Final backend patch results on Linux: `scripts/run-tests.sh --no-venv` passes
with Android 112 passed/2 skipped, Source Lab 143 passed, sample-analysis smoke,
shell syntax and graph checks. Dashboard checking is skipped by that runner
because dependencies are absent in this worktree; no dashboard files changed.
The eight focused artifact API tests, import/exclusion check, staged secret scan
and whitespace checks pass. Windows fallback host coverage remains part of the
platform/distribution tasks rather than a claim of this Linux test run.

## Console readiness (SRC-020)

Native Python readiness, optional tools and unavailable interpreter coverage were
added to the console suite. Source Lab has a readiness route in every locale and
a capability entry; static detection does not depend on Docker, KVM or WSL.

Validation: console/web tests 46 passed, 1 skipped; dashboard type and i18n checks
passed; local build 345 pages; browser suite 17 passed.

## Console handlers, guards and jobs (SRC-021/022/023)

All 13 retained namespaced routes / 19 methods now have adapters. [API.md](API.md)
records the preview/job envelope, bounded option set, normalized file-backed DTOs,
absent snapshot behavior and deliberate departures from the source application's
memory-only API. Rich UI parity and deeper crawler controls remain separate tasks.

Linux validation for this milestone:

- Repository runner: all **7 stages passed**; Android/console **143 passed, 2 skipped**,
  Source engine **143 passed**, generated sample reports, 70 shell scripts, graph,
  dashboard types and committed-build freshness. Subsequent Source boundary
  checks cover the final HTTP report redaction/read-budget refinements.
- New Source console suite: **30 passed**, including real detection, both offline
  crawler POST adapters, merger planning/build/download, managed settings jobs,
  credential redaction, private ZIP refusal, typed hostile options, exact-preview
  binding, cross-console conflicts, cancellation, timeout escalation and a real
  abrupt-console-crash test proving the engine stops and its job is interrupted.
- Together with the existing artifact reader tests: **38 passed**.
- Dashboard type check and **1937 keys across seven locale catalogs** pass. Local
  build: **345 pages**; browser suite: **19 passed**, including native Source
  readiness with missing optional tooling and interrupted-job display.
- Separate Pages build under `/os-lab`: English/Turkish Source readiness pages,
  switching locale both ways, internal base paths, no API polling/run controls or
  hydration errors. Twelve local/Pages legal routes and legal locale links pass.
- `lat check`, whitespace, all **108** original import hashes/exclusion checks and
  a staged credential-signature review pass. First-party adapter code only; no
  external catalog, Brain dataset, binary, credential or generated output added.

Source job retention is documented in the privacy page. Runtime API foundations
now exist, but SRC-024/025 remain open for full integrity/settings/importer workflow
acceptance. Five analysis UI pages and native Windows/macOS host verification
remain outside this P0 milestone. Linux tests exercise portable validation and
POSIX lifecycle behavior; they do not establish native Windows host acceptance.

## Owner scope update: skip remaining merger work

SRC-042 is explicitly skipped, removed from release dependencies and listed with
owner-excluded work. Existing merger engine/API functionality is retained. The
remaining active queue has 18 tasks; this skip is not recorded as completed work.
This ledger-only change uses Markdown/graph/whitespace checks; runtime validation
above applies to the preceding implementation milestone.

## Next batch: SRC-024 runtime acceptance

Managed generation/rotation/default URL and explicit `verify-session` jobs are
implemented. Existing mode 0600, ownership and ambiguous-key checks remain. The
engine now requires signed metadata/events and refuses traversal, symlinks,
missing signatures, invalid manifests and wrong keys with bounded reads.

Validation: focused console runtime tests **5 passed**; engine session/collector
tests **20 passed**. Fixtures use temporary keys and owned generated inputs only.
No browser installation, third-party assets or credentials were published.

## Next batch: SRC-025 collector acceptance

All four native importer libraries now accept explicit synthetic labeling and
record that they do not launch native collectors. Browser collection failure
excludes partial events from correlation. Owned, generated telemetry exercises
signed review and matching-target correlation for all four platforms; synthetic
and target-mismatched events are rejected. Browser simulation stays synthetic.

Validation: session/collector suite **29 passed**. Actual native collection and
live browser tooling are not claimed; see [COLLECTORS.md](COLLECTORS.md).

## Next batch: SRC-030 navigation acceptance

Eight Source destinations plus the existing readiness route use the shared
sidebar/mobile drawer, themes and locale helpers. Local Spotlight searches
file-backed target records with debouncing, cancellation and error feedback.
Future Evidence/Deep/Pipeline/Brain/settings views are explicit placeholders.

Validation: dashboard typecheck, 1,951-key/seven-locale check, 409-page local and
Pages builds; existing/browser navigation suite 21 passed initially and the
hydration-timing correction for Spotlight passed its focused rerun. Public smoke
checks 16 EN/TR destinations, locale/query/base links and absence of engine
requests/actions. No private artifact or third-party dataset enters the build.

## Next batch: SRC-031 Overview acceptance

The Overview compares properties, background execution, dependencies, permissions
and target inspectors. Filters, pinned migration annotations, per-target counts,
source catalog browsing and CSV/JSON downloads use private file-backed API data.
Property annotations were extracted from the authorized pinned first-party route;
provenance records the source hash and transformed JSON hash. No catalogs copied.

Validation includes a console fixture for flattened crawler manifests and nested
package dependency sections, deduplicated counts, background groups, high-risk
permissions and annotated CSV export. Browser tests cover matrix tabs/keyboard,
filters, inspector notes/deep links, loading, empty and error states.

SRC-031 results: dashboard typecheck and seven-locale catalog check passed; local
and Pages builds each emitted 409 routes. Source-focused browser checks **7
passed** after updating navigation mocks to return the new Overview DTO; the
other 17 checks in the full run passed. Public smoke again passed all 16 EN/TR
Source routes without engine requests. Combined Source console/artifact tests
**40 passed**; full engine suite **158 passed**.

## Next batch: SRC-032 crawler acceptance

The crawler page offers operator source lists or up to 100 explicit GitHub slugs,
workers/depth and AST/metadata/resume/workspace options. Source readiness and Git
gate actions. Exact previews are invalidated by edits; confirmation starts a
shared Source job. Logs, conflicts, cancellation, failures and completed summaries
remain visible, with H1–H5 weights labeled as review heuristics rather than proof.

Source-list discovery caps scanned entries/results, accepts only supported file
types and never follows links. The public build stays informational. The owner
requested ignoring `dashboard/.check-source-pages/`; the rule was verified with
`git check-ignore`, and no generated files under that directory are tracked.

Focused console/artifact regression: **41 passed**, including real offline
crawler jobs from the earlier P0 suite and source-list discovery boundaries.

Final batch results:

- Repository runner: **7 passed, 0 failed, 0 skipped** stages; Android/console
  **146 passed, 2 skipped**, Source engine **158 passed**, sample analysis,
  **70** shell scripts, graph, dashboard typecheck and committed-build freshness.
- Dashboard: typecheck, **2,010** catalog keys across seven locales, local and
  Pages **409-route** builds, and full browser suite **27 passed**.
- Public browser smoke: **16** EN/TR Source destinations, preserved locale/base/
  query links, no local API requests, operation buttons or hydration errors.
- Real localhost console smoke: generated owned fixture Overview and inspector,
  crawler exact preview, and no job started by preview.
- Provenance: **109** current file hashes verified. Secret-signature review of
  **40** changed text files found only three intentional invalid-auth URL test
  fixtures; no production credentials. No third-party assets or new dependencies.

SRC-024/025/030/031/032 are complete. **13** active implementation tasks and four
upstream follow-ups remain; SRC-042 stays explicitly skipped. Actual native
collection, remaining analysis UIs and distribution acceptance are still pending.

## SRC-033: Evidence dashboard

Implemented target/platform detection previews, jobs/logs/cancellation, evidence
state/severity/text filters, confidence, source/binary spans, alternatives,
verification tests, remediation, coverage, scorecard, sessions and event timelines,
and allowlisted report links. Browsing never asserts signature verification.

Dashboard typecheck/i18n/build passed; full browser suite **32 passed**, including
five platform journeys with partial coverage and preserved evidence states. Local
and Pages builds emitted 409 routes; public smoke preserves EN/TR routes without
engine calls. Existing engine five-platform tests supply parser acceptance.

## SRC-034: Runtime controls

Runtime settings expose status only, managed key actions, rotation acknowledgement
plus command confirmation, configured URL and explicit verification jobs.
Environment-owned keys cannot be changed. Evidence runner modes gate session
matching and explain optional Playwright/synthetic behavior. Refresh retains
verification results and logs.

Typecheck, **2,041**-key/seven-locale check, 409-route local/Pages builds, public
EN/TR smoke and full browser suite **33 passed**. Rotation/environment/invalid-URL
controls have a dedicated browser check; existing console tests verify actual key
writes, modes, signatures and precedence. No secret is delivered to the UI.

## SRC-040: Crawler controls and joins

Added typed retry/time/rate-wait/tree/AST/map bounds, offline bounded list parsing
with selected-workspace and credential guards, and previewed private CSV joins.
Catalog browsing distinguishes resource inputs from generated output.

Source console **35 passed**; list/retry/stop/stage-failure engine checks **5
passed**, plus both existing CSV tests. The fault injection preserves unrelated
manifest/tree artifacts. Dashboard types, **2,051**-key locales and both builds
passed. Browser run: 32 passed plus an unrelated Persian hydration check that
passed its focused rerun; public 16-route EN/TR smoke passed. No data imported.

## SRC-041: Deep analysis

Added bundle/manifest/threat/dependency/metadata/file browsing, repo/file deep
links, legacy AST-index reads, a structural map dialog with stats, roles, targets,
coverage, symbols/imports and entrypoints, and selected private-target crawling.
AST reads require an index match and retain private-path/read-budget guards.

Dashboard types, **2,067**-key locales, local/Pages builds and **34 browser tests**
passed. Source console suite **36 passed**; the AST/local-target test was rerun
after the private-name guard. Public EN/TR smoke passed without engine calls.

## SRC-070: Distribution implementation; native acceptance pending

The app staging/required-runtime lists include Source engine, adapters, schema,
probe and list parser. Private Source state/resources and archive/binary inputs
are excluded. Update tests preserve Source settings. Minimal installers skip
pip upgrades and call download-free doctor. Unsupported Python cannot appear
ready. PowerShell's UTF-8 BOM is preserved.

Validation: **6 Node staging tests**, **5 Rust runtime tests** (a temporary Cargo
harness imports the actual module with its existing serde dependency), shell
syntax and supported-interpreter console test passed. Staged **441 tracked
runtime files** plus current dashboard were exercised outside a checkout using
`python -S`: readiness and owned-fixture detection passed without site packages,
Node or virtualization. No app build/publication was performed.

Native macOS/Windows fresh install/update and PowerShell parser acceptance are
not verified on this Linux host; SRC-070 stays unchecked until that evidence is
available. The implementation is committed for review and later host testing.

## SRC-043: Pipeline reference

Ported the authorized first-party Pipeline architecture descriptors (12 stages,
3 request descriptions, 9 signatures) from pinned source code, with provenance
and fixed import date. These are code metadata, not third-party datasets or
private generated outputs. Stage flow/details, inputs/outputs/network/failures,
heuristics/candidates/dependencies and flow steps are available. Operator snapshots
take precedence and are validated; neither source claims live regeneration.

Dashboard types, **2,078**-key locales, local/Pages builds and **35 browser tests**
passed; two console tests cover fallback provenance and invalid/operator
snapshots. Public EN/TR smoke passed. Source packaging requires the metadata.

Native macOS/Windows installer acceptance is explicitly **on hold by owner until
the last step**; remaining implementation continues before requesting those runs.

## SRC-044: Brain feasibility and provider prototype

The existing React/Astro shell embeds a file-backed Brain tab prototype.
BRAIN.md maps all retained subviews to snapshot data or explicitly absent
providers, with no new dependencies. Source/history/flow/sequence/AI-rule provider
paths and unique tab IDs are guarded; graphs reject duplicate/oversized nodes
and report dangling edges. Virtual windows bound rendering to at most 200 nodes.

Three model tests, two manifest/API guard tests, dashboard types/i18n/build,
**36 browser tests** and public EN/TR smoke passed. All graph fixtures are owned
and generated in tests; no upstream graph export or application data was copied.

## SRC-045: Brain viewer

Implemented graph tabs/windowing/filters/legend/sidebar/keyboard selection,
snapshot usages, file-backed source/history and bounded LCS side-by-side diff,
flow/sequence views, static AI-rules dialog, complexity/risk ranking and full JSON
export. Live stress has no configured application provider and is explicitly
unavailable; it never returns simulated success or calls the upstream backend.

Four model tests, types, **2,106**-key locales, local/Pages builds and a full
**37-test** browser run passed. Three focused Brain journeys additionally cover
every available subview, missing providers, keyboard selection and a 250-node
owned snapshot: only 100 nodes render, while the download contains all 250.
Public EN/TR smoke passed. No graph/provider dataset or new dependency imported.

## SRC-071: Authorized legacy import

Added CLI dry-run/default preview, explicit root/slug mapping, fingerprint-bound
`--copy --authorized`, positive artifact/settings allowlists, contract/hash/HMAC
checks, private backups/journals and conflict-protected rollback. Existing signed
session IDs cannot be overwritten; private/binary-containing bundles are held
out whole. Keys, databases, Skills, catalogs/datasets, archives and app binaries
are excluded. Originals are unchanged; import never contacts a network service.

Eleven import tests cover no-write dry run, copy/backups/hashes, changed inputs,
rollback conflicts, signed/tampered sessions, exclusions, settings, job locks,
CLI attestation and injected partial failure. A legacy Windows CRLF-signature
regression is fixed without weakening event hash checks. Full engine: **175
passed**. Dashboard types/i18n/build, **38 browser tests**, Pages build and public
EN/TR smoke passed after updating privacy retention/URL-history disclosure.
Six staging tests and 12 launcher foundation checks passed. No real legacy data
was imported; all tests used owned temporary fixtures.

## SRC-062: Workflow documentation and graph

Added the operator/release runbook and local/public `/source/docs/` guide,
collectors, Brain providers, import and runbook routes. Trusted English technical
prose is labeled; UI navigation and internal guide/legal links preserve locale
and base paths. No OpenAPI/API-reference integration or private output is added.
README and setup/labctl/dashboard/overview/tooling graph nodes describe implemented
workflows and the held native platform gates.

Dashboard types, **2,112**-key locales, **457-route** local/Pages builds, **39 browser
tests**, four graph-model tests, public EN/TR smoke and `lat check` passed. A
dedicated browser test checks local guide links and Turkish navigation while
retaining the English article language.

## SRC-072: Locales and Pages acceptance

All active catalogs contain **2,122** matching keys. Overview summaries/background
groups/catalog tabs now use readable translated labels; preview privilege flags
are explicit. Technical artifact data and English first-party guide prose remain
identified as such. No private snapshot is in the public build.

Dashboard types/i18n/build passed, local/Pages builds each produced **457 routes**,
and the **39-test** browser suite passed with one worker. The committed reusable
`source-pages-smoke.mjs` verified **112** Source/guide routes across English plus
all seven catalogs, locale/base/query links and language switches, with **zero
engine API requests, operation buttons or hydration errors**. New npm commands
expose model and Pages acceptance checks.

## SRC-073: Portable final regression

`bash scripts/run-tests.sh` passed all seven required stages: **153 Android/console
tests passed, two optional tests skipped**, **176 Source engine tests passed**,
sample analysis/report smoke, shell parsing, graph validation, dashboard types
and committed build freshness. Shell discovery included the ignored staged runtime.
The actual Rust runtime module passed **five** offline Cargo tests, including
private Source state preservation; staging/Python helper tests passed **seven**.
The Brain model suite passed **four**.

`python source-lab/acceptance.py` passed read-only status/setup and all five
owned-fixture analyzers with PATH empty and Python site packages disabled:
zero runtime/correlated claims. Its portable JSON report exposes counts and a
source fingerprint, without private paths or keys. A staged-runtime invocation
can require that same fingerprint with `--installed-only`.

Path review adds Windows reparse-point/junction rejection to console targets,
artifact reads and legacy imports, and key/session reads. Twenty focused
path/import regressions passed. These portable tests do not replace native
Windows filesystem/process/installer or macOS GUI acceptance.

Dashboard types/i18n and local/Pages builds passed (**457 routes**). All **39**
browser tests passed with one worker; reusable public smoke verified **112**
Source/guide routes across all eight locales, no API calls/actions/hydration
errors. Real localhost console smoke used the owned workspace for Overview,
inspector and exact crawler preview; preview started no job/acquisition.
The staged runtime passed all six portable checks with the identical source
fingerprint and no checkout marker. Native GUI/install checks remain unclaimed.

## SRC-074: Inventory and publication audit

[AUDIT.md](AUDIT.md) accounts for every retained page/subview and all 13
routes/19 upstream methods plus catalog-join POST, including absent providers,
CLI-only STIX, skipped merger UI and explicit Skills/database/OpenAPI exclusions.
All 110 provenance hashes match. First-party manifest/Pipeline metadata notices
and stale intermediate UI status text were corrected. No new production
dependency, third-party archive/dataset/binary, actual session or key is added.
The import policy, Terms, Acceptable Use, Privacy, notices, contribution/security
rules and staged paths were reviewed; `lat check` and `git diff --check` passed.

## Finalization and owner deferral

The app version is now **0.3.0** in Tauri, npm and Cargo manifests/locks.
The integration was rebased onto master `5d823f5b`; its firewall/catalog and
reservation changes are preserved. The owner directed remaining verification
steps and required patches to bonus contributions before merge/release.
SRC-B01–SRC-B06 are open and reservable in Contribute, with priorities and
acceptance results. Native/manual/live checks remain unverified; no test result
is inferred from that deferral. Release signatures and platform build checks
are still required. No actual legacy data was imported.

After rebase and bonus integration: all seven repository stages passed again
(**153 + 176 tests**, two optional Android skips), dashboard types and **2,135**
matching locale keys passed, local/Pages builds produced **457 routes**, **39**
browser tests and the **112-route** public smoke passed. All six bonus cards
were confirmed available with their exact reservation links and no hydration
errors. Rust runtime **5**, staging/helper **7**, model **4** and portable
acceptance **6** checks passed. `lat check` and whitespace checks passed.

## Published 0.3.0

PR #103 merged at `687893e3`; immutable tag `app-v0.3.0` points to that commit.
All tagged Linux, macOS and Windows builds passed. All ten packages and their
20 SHA-256/signature sidecars were verified; the macOS job additionally passed
Developer ID signing, notarization/stapling and platform verification. Windows
MSI install/launch/uninstall passed, with Authenticode status `NotSigned`. The
owner explicitly approved publishing these Windows installers with valid Tauri
updater signatures and the SmartScreen limitation stated in the release notes.

The release and verified five-platform updater feed were published on 2026-11-09.
PR #105 fixes post-build Pages filtering; its final artifact passed all 112
Source/guide routes across eight locales, with no engine requests/actions or
hydration errors. Both integration PRs passed all platform and browser checks.
Native/manual/live Source acceptance remains open in SRC-B01–SRC-B06.
