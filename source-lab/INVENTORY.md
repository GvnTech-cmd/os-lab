# Source Lab migration inventory

This records the source snapshot and the retained migration scope for Source Lab. Paths in this document
refer to the source repository unless explicitly described as os-lab destinations.
No entry here claims the migration is implemented.

## Snapshot and evidence

The inventory was inspected on 2026-11-09 from `/home/pod/iQ-SourceContol` at
commit `51ce20b6210ab5a98a2dd2653b230bdf2282f93c` ([source repository](https://github.com/keyvanarasteh/iQ-SourceContol)).
The local checkout has an unrelated `.gitignore` modification; it is excluded.
The os-lab base is fetched `origin/master` at
`9b971c44596a4636dfe5230daab1abeb9568c04d`.

Read source `AGENTS.md`, `engine/AGENTS.md`, `lat.md/lat.md`, `architecture.md`,
`status.md`, `ui.md`, `repos.md`, `analyzers.md`, `repo-map.md`, `pipeline.md`,
`evidence-model.md`, `runtime-sessions.md`, `correlation.md`, `reports.md`,
`cli.md`, `deployment.md`, `archive.md`, and `TODO.md` alongside the route handlers.
Source `lat check` passes. Historical test counts in source status are claims
from its October snapshot, not tests rerun for this planning PR.

## Scope disposition

The owner excludes Skills/agent catalogs, database integration and OpenAPI.
The database-backed repository manager, its sync/taxonomy/notes APIs, the Skills
page and implementation catalog, and the OpenAPI/API-reference surfaces will
not be ported. Retained browsing and search use local analysis artifacts.
Engine JSON Schema and generated TypeScript contracts remain in scope.

The original census stays intact for provenance: seven app pages, 29 API routes
and 41 HTTP methods. The current target retains five app pages and 13 API routes
(19 methods), excludes two app pages and 15 API routes (21 methods), and retires
the remaining hello-world API route (one method).

## App pages

The five retained `page.tsx` routes have destinations in the existing dashboard;
the other two source pages are explicitly excluded.
The route names below are logical paths; locale and Pages base prefixes must be
applied through os-lab's path helpers.

| Source route | Proposed os-lab route | Source file |
|---|---|---|
| `/brain` | `/source/brain/` | `ui/src/app/brain/page.tsx` |
| `/deep-analysis` | `/source/deep-analysis/` | `ui/src/app/deep-analysis/page.tsx` |
| `/evidence` | `/source/evidence/` | `ui/src/app/evidence/page.tsx` |
| `/` | `/source/` | `ui/src/app/page.tsx` |
| `/pipeline` | `/source/pipeline/` | `ui/src/app/pipeline/page.tsx` |
| `/repos` | Excluded: database-backed repository manager | `ui/src/app/repos/page.tsx` |
| `/skills` | Excluded: Skills integration | `ui/src/app/skills/page.tsx` |

Additional surfaces: `/docs/[[...path]]` maps to `/source/docs/` and nested
document routes for ordinary project documentation. `/api-docs` and its spec
download are excluded with OpenAPI. `/labs/source/` is the new os-lab
readiness/lifecycle page, beyond the five retained source pages.

| Page or shared surface | Required parity |
|---|---|
| Overview | Merged manifest property matrix and CSV export, MV2/MV3 migration annotations, background/service-worker matrix and filters, dependencies, permissions, extension inspector; curated/monitored source catalogs and downloads; source-list crawler runner, workers/options, progress/logs; H1-H5 signature reference. |
| Evidence | Target/platform selection, run/poll/cancel, state/severity filters, confidence, source/binary spans, hypothesis, alternatives, remediation, coverage and limitations; H1-H5 scorecard and decisive tests; runtime key status/generate/two-step rotate, canary URL/default/toggle, Playwright readiness, prior-session selection and event timeline; existing report downloads. |
| Deep analysis | Repository selection/search, bundle status, manifest/threat/dependency/file/metadata views, AST and source browsing with `?repo=` and `&file=` links; repo-map stats, roles, targets, coverage, symbols/imports and entrypoints; selected-target crawler options/logs/cancel; merge preview, exclusions, flagged override, run/cancel and folder/ZIP/report results. |
| Pipeline | Stage flowchart, inputs/outputs, network calls, GitHub requests, signatures, risk rules, manifest candidates and flow steps; explicit bundled-data fallback. |
| Brain | Tabs, graph/filter/legend/sidebar, usages, source, file history, side-by-side diff, flowchart and sequence views, AI-rules dialog, complexity/riskiest-files/stress panels, export, theme and virtual graph. Distinguish available snapshot data from controls whose data/provider is absent. |
| Shell | Source Lab navigation inside the existing os-lab sidebar, grouped analysis links, mobile behavior, keyboard Spotlight with section/record search, light/dark theme, project-docs links, accessible focus and loading/empty/error states. |

## HTTP route census

This table is generated from all source `api/**/route.ts` exported HTTP handlers.
Retained rows are the implementation checklist; excluded rows are not future
endpoints. Internal clients use the namespaced API. Preserve retained query,
body, status, file download and cancellation semantics or document an intentional
change and add a contract test.

| Source route | Methods | Proposed destination |
|---|---|---|
| `/api/analyzer/merged` | GET | `/api/source/analyzer/merged` |
| `/api/analyzer` | GET, POST | `/api/source/analyzer` |
| `/api/brain/files/[...path]` | GET | `/api/source/brain/files/[...path]` |
| `/api/brain` | GET | `/api/source/brain` |
| `/api/deep-analysis/merge` | GET, POST | `/api/source/deep-analysis/merge` |
| `/api/deep-analysis` | GET, POST | `/api/source/deep-analysis` |
| `/api/detection` | GET, POST, DELETE | `/api/source/detection` |
| `/api/evidence/report` | GET | `/api/source/evidence/report` |
| `/api/evidence` | GET | `/api/source/evidence` |
| `/api/implementations` | GET | Excluded: Skills/implementation catalog |
| `/api/openapi` | GET | Excluded: OpenAPI integration |
| `/api/pipeline` | GET | `/api/source/pipeline` |
| `/api/repo-categories/[key]` | PATCH, DELETE | Excluded: database-backed repository management |
| `/api/repo-categories` | GET, POST | Excluded: database-backed repository management |
| `/api/repo-tags/[key]` | PATCH, DELETE | Excluded: database-backed repository management |
| `/api/repo-tags` | GET, POST | Excluded: database-backed repository management |
| `/api/repos/[owner]/[name]/analysis` | GET | Excluded: database-backed repository management |
| `/api/repos/[owner]/[name]/dependencies` | GET | Excluded: database-backed repository management |
| `/api/repos/[owner]/[name]/evidence` | GET | Excluded: database-backed repository management |
| `/api/repos/[owner]/[name]/files` | GET | Excluded: database-backed repository management |
| `/api/repos/[owner]/[name]` | GET, PATCH | Excluded: database-backed repository management |
| `/api/repos` | GET | Excluded: database-backed repository management |
| `/api/repos/sync` | GET, POST | Excluded: database-backed repository management |
| `/api` | GET | Retire hello-world stub; use os-lab health |
| `/api/settings/runtime` | GET, POST | `/api/source/settings/runtime` |
| `/api/skills/generate` | GET | Excluded: Skills/implementation catalog |
| `/api/skills` | GET | Excluded: Skills/implementation catalog |
| `/api/sources` | GET | `/api/source/sources` |
| `/api/spotlight` | GET | `/api/source/spotlight` |

## Engine and artifact capabilities

The core detection path uses Python 3.11+ standard library modules; optional
collectors and parsers have separate requirements.

| Area | Baseline to preserve | Source anchors |
|---|---|---|
| Detection | Auto/explicit browser-extension, windows-app, macos-app, android-app, ios-app; browser/userscript rules, PE imports/exports/DLL proxy/CLR and Electron/WebView2/ASAR/fuses, Mach-O signatures/entitlements/dyld/ObjC, Android XML/DEX/ELF/APK signing, iOS IPA/provisioning/frameworks/WKWebView. | `engine/analyzers/`, `cli/run_detection.py`, `lat.md/analyzers.md` |
| Evidence | V2 findings/coverage, five states, six severities, target identity, H1-H5 scoring, verification tests, correlation and confidence, replay-script library helper. | `engine/evidence/`, `lat.md/evidence-model.md`, `correlation.md` |
| Runtime | Signed session metadata/events/artifacts/manifests; HMAC resolution/verification; browser canary; Windows/macOS/Android/iOS telemetry importer libraries. | `engine/collectors/`, `evidence/session.py` |
| Reports | `analysis-v2.json`, `findings.json`, `coverage.json`, `report.sarif`, `summary.md`, `report.stix.json`; all CLI output-format options. | `engine/evidence/report.py`, `lat.md/reports.md` |
| Crawler | Single/list/CSV/XLSX/scan-dir inputs, acquisition/resume/retries/rate limits/workers/depth/caps, manifest score and priority, threat/dependency/tree/metadata/AST/map stages, partial failures and interruption artifacts. | `engine/pipeline/ext_repo_analyzer.py` |
| Merger and datasets | MV2/MV3 eligibility, flagged override, service-worker checks, shims/namespacing/manifest folding, Node syntax check when available, overwrite marker guard, ZIP/report/hub output; source CSV joining/enrichment. | `engine/pipeline/ext_merger.py`, `merge_csvs.py` |
| Structural maps | Disk/ASAR/overlay read-only VFS; Python/JS/TS/PHP/Rust/Swift/ObjC/Kotlin/Java/markup/XML/plist adapters; symbols/types/import resolution/roles/rank/cycles/targets/filters; JSON/Markdown/DOT generate/query CLI. | `engine/sourcemap/`, `lat.md/repo-map.md` |
| Repository index (excluded) | The SQLite/Prisma repository manager, database sync and taxonomy/notes are excluded by owner scope. | `ui/prisma/schema.prisma`, `ui/src/lib/repo-*.ts` |
| Resources and provenance | Operator-supplied local inputs and outputs; original extraction manifests, hashes and attributions; portable setup and project-docs workflows. Third-party archives/datasets/binaries and database/skill catalogs remain excluded. | `engine/MANIFEST.csv`, `ui/MANIFEST.csv`, `ops/` |

## Limits and follow-ups

Preserve accurate labels for these limits; do not silently turn them into claims
of implemented live capability.

- Upstream `lat.md/ui.md` says six pages but the actual tree has seven, including
  Skills. The sidebar also includes Repositories. This inventory follows code.
- The source deployment relies on external iBone/core-api gates and absolute-path
  environment settings. It has no in-app authentication and stores run state in
  process memory. Those remote hosts, service names and gates are not portable.
- Without Playwright/extension input, the browser runner can emit synthetic events.
  The migration must label or exclude synthetic evidence from live confirmations.
- Native importers accept already-parsed telemetry through library entry points;
  the source CLI does not launch native collectors. Research-only memory checks
  remain future work.
- Brain and Pipeline use hand-maintained snapshots; no regeneration pipeline exists.
  Optional tree-sitter applies to TS/JS, PHP and Rust; newer language adapters use
  fallback scanners. Binary-only structural maps may be `not_applicable`.
- The engine exports STIX but the existing report HTTP allowlist has five files
  and excludes STIX. Preserve CLI STIX; exposing it in UI is an explicit addition.
- Source `TODO.md` proposes platform-specific navigation/crawlers, MCP targets and
  broader datasets. Preserve that backlog separately from shipped parity; do not
  mark unchecked upstream aspirations as migrated features.
- The inspected source had no top-level license file. The owner subsequently
  authorized the first-party port into public os-lab; IMPORT_POLICY.md records
  that authorization. Third-party archives/datasets/binaries remain excluded,
  and new third-party dependencies require their own license/notices review.
