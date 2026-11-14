# Source Lab scope and release audit

Reviewed on 2026-11-09 against the pinned [inventory](INVENTORY.md), owner scope
decisions and [import policy](IMPORT_POLICY.md). This records implementation,
not a claim that every native host or live collector has been exercised.

## Retained surfaces

| Inventory surface | Delivered behavior and evidence |
|---|---|
| Overview | Property/background/dependency/permission matrices, migration annotations, filters, inspector, CSV/JSON exports; operator catalogs, counts, downloads and previewed catalog joining. No bundled dataset. |
| Crawler | Explicit repositories, bounded CSV/TXT/XLSX lists or available private directories; workers/depth/retry/rate/tree/AST/map controls, exact previews, real logs, conflicts and cancellation. |
| Evidence | Five-platform detection, state/severity/text filters, confidence/spans/hypotheses/alternatives/remediation, coverage, scorecards, sessions/timelines and five HTTP reports. STIX remains available through CLI. |
| Runtime | Managed key generation/acknowledged rotation, environment ownership, configured canary URL, static/canary/selected-session modes and explicit integrity verification. Readers never present browsing as verification. |
| Deep analysis | Bundle selection, source/manifest/threat/dependency/metadata/indexed AST, repo/file deep links; paged map roles/languages/stats/targets/coverage/symbols/imports/entrypoints; bound local reanalysis. Further merger UI is skipped by owner; backend remains. |
| Pipeline | Interactive stages, inputs/outputs/network/requests/signatures/risk/candidates/flow, pinned first-party reference or operator snapshot with visible provenance. No automatic regeneration claim. |
| Brain | Tabs, bounded graph windows, filters/legend/keyboard/sidebar, usages/source/history/diff/flow/sequence/static AI-rules/recorded complexity and risk/full JSON export. Providers are optional private JSON; absent providers and live stress are explicitly unavailable. |
| Shell and docs | Existing sidebar/mobile/theme/Spotlight, readiness, loading/empty/errors, local and Pages locale/base/query navigation, five first-party workflow guides. Public routes have no engine requests or operation controls. |

The five original retained app pages are implemented; os-lab adds separate
crawler, catalog, runtime, readiness and guide destinations. All 13 retained
API routes/19 methods have guarded adapters; catalog joining adds one POST.
[API.md](API.md) enumerates every method and intentional contract adaptation.
The hello-world stub is retired. Database/repository manager, Skills and
OpenAPI/API-reference routes remain excluded, rather than unfinished endpoints.

## Engine and operational boundaries

The portable engine retains five analyzers and parser families, V2 evidence and
H1–H5, signed sessions, browser canary, four telemetry importer libraries, all
CLI report formats, crawler/merger/catalog joins and structural-map adapters,
queries and JSON/Markdown/DOT exports. Optional grammars/browser tools remain
operator-installed. Native importer libraries accept supplied telemetry; they
do not launch native collection. Synthetic events, structural relationships and
snapshot metrics do not establish observed behavior.

Artifact reads, source/list inputs, graph rendering and diff work have explicit
caps. Large workspaces can return a visible limit error rather than complete
coverage. Cross-process locking, exact-option tokens, private paths, symlink and
Windows reparse-point guards, bounded logs, redaction, interruption recovery and
conflict-protected import rollback are tested with owned temporary inputs.
Native GUI/process/filesystem acceptance remains a separately recorded check.

## Publication and legal review

The owner authorized publication of first-party iQ-SourceContol code under
os-lab's Apache-2.0 license. [PROVENANCE.json](PROVENANCE.json) contains 110
imported/derived file rows, source revisions and current hashes. New integration
code uses the existing dashboard dependencies and Python standard library;
no new production dependency or third-party asset was introduced.

The staged changes were reviewed against CONTRIBUTING.md, SECURITY.md and all
four legal documents. Terms describe Source Lab; privacy describes intentional
GitHub/canary connections, private storage, key/session/import backup retention,
and browser URL selections. Notices identify first-party code and architecture
metadata. No archives, datasets, binaries, private reports, keys, environment
files, source deployment registrations or original working-tree changes are
imported. Tests construct binary samples instead of shipping executables.

## Acceptance and release status

[VALIDATION.md](VALIDATION.md) records commands, counts and limits.
[RUNBOOK.md](RUNBOOK.md) describes installed operation, optional tools, portable
acceptance, native verification and recovery. Portable checks exercise all five
platforms with an empty PATH and disabled site packages; this is distinct from
native installation or live collection acceptance. Follow-up work must retain
these distinctions and the owner's explicit exclusions.

The owner subsequently moved remaining native/live verification and required
patches to open bonus contributions SRC-B01–SRC-B06 in
[Contributing](../CONTRIBUTING.md). They are visible in the dashboard task list
and are not marked complete. This supersedes the initial native pre-merge gate;
it does not waive package signatures or claim native manual verification.
