# Source Lab

Source Lab provides local source/package analysis through a namespaced Python engine and [[labctl]]. It needs no VM, KVM, Docker or Node for static detection.

The console reports native Python readiness. Retained file-backed analysis views
and documentation are available; [[source-lab/AUDIT.md]] records scope and limits.

## Detection

[[source-lab/engine/source_lab/cli/run_detection.py#main]] selects browser-extension, Windows, macOS, Android or iOS analysis and writes V2 findings/coverage, an H1-H5 scorecard, JSON, SARIF, Markdown and STIX reports.

[[source-lab/engine/source_lab/analyzers]] contains the source and binary parsers and rule families. Findings distinguish capabilities and static leads from runtime observations. [[source-lab/engine/source_lab/paths.py#Paths]] configures resource and private-state roots without absolute developer paths.

## Contracts

[[source-lab/engine/source_lab/contracts.py#schema_document]] exports JSON Schema from the Python models and engine envelopes. [[source-lab/engine/source_lab/contracts.py#typescript]] generates [[dashboard/src/lib/source-contracts.ts]].

[[source-lab/engine/source_lab/contracts.py#validate]] checks the emitted schema vocabulary, including versions, evidence states, coverage and finite confidence. `labctl source contracts` exports JSON or TypeScript and can validate a local artifact. [[source-lab/contracts/schema.json]] is the committed schema snapshot.

## Runtime evidence

[[source-lab/engine/source_lab/evidence/session.py]] signs and verifies session bundles. [[source-lab/engine/source_lab/collectors]] provides the browser canary and four platform telemetry importer libraries.
[[source-lab/COLLECTORS.md]] documents input provenance, synthetic mode and
explicitly unavailable native collection workflows.

[[source-lab/engine/source_lab/cli/run_detection.py#_verified_events]] excludes synthetic sessions and target/platform mismatches from correlation. Missing keys or failed integrity leave the static findings and an explicit coverage limitation. Explicit console verification uses a previewed runtime job. Signed manifests must
cover both metadata and events; unsafe paths, missing signatures and oversized
bundles fail closed. Key material stays in the worker environment/private file.

Live canary collection requires operator-installed Playwright and Chromium; setup does not install them.

## Read-only artifact API

[[console/source_artifacts.py#SourceArtifacts]] serves existing findings, coverage, session metadata/events and five allowlisted report formats through [[android-lab/lab/web_ui.py#LabHttpHandler#_source_get]]. It never imports or starts the engine.

`GET /api/source/evidence` lists target summaries or reads `slug` detail and an
optional `session` timeline. `GET /api/source/evidence/report` downloads an
allowlisted report named by `slug` and `file`. The existing localhost Host guard
still applies; responses are no-store and nosniff. Unknown routes and duplicate
or unexpected parameters fail explicitly.

Reads reject symlinks and nonregular files. Limits are 5 MB per JSON/events file,
10 MB per report, 16 MB aggregate, 100 targets/sessions and 500 returned events.
Descriptor-relative no-follow traversal is used where supported, with checked
paths on other hosts. Session integrity is labeled not verified by this reader;
signature verification remains the engine's responsibility. No key or session
seal is downloadable. STIX remains CLI-only.

## Pipeline

[[source-lab/engine/source_lab/pipeline]] contains the crawler, extension merger and CSV joiner. [[source-lab/run.py#main]] supplies storage defaults for the crawler and merger; the CSV CLI writes joined catalogs into mutable storage.

Crawling and source acquisition can contact GitHub only when the operator invokes them. Targets and catalogs are operator-supplied; no upstream archive or dataset is bundled. Merge output is for authorized testing in disposable lab browser profiles.

## Structural maps

[[source-lab/engine/source_lab/sourcemap]] maps source trees through a read-only disk/archive VFS and exports JSON, Markdown and DOT. [[source-lab/engine/source_lab/sourcemap/__main__.py#main]] supports generate and query commands.

Adapters cover Python, JS/TS, PHP, Rust, Swift, Objective-C, Kotlin, Java and markup. Optional grammars fall back to scanners; binary-only applicability and parser limitations stay explicit. A structural map is navigation data, not evidence of behavior.

## Launcher and state

[[source-lab/run.py#main]] exposes status, doctor, setup, detect, map, crawl, merge and merge-csvs. [[source-lab/run.py#status]] probes readiness without writing state. Explicit setup creates private directories without downloads.

`SOURCE_LAB_STORAGE` defaults to `source-lab/storage`; `SOURCE_LAB_RESOURCES` defaults to its `resources` child. Resource directories are not created automatically. Detection defaults to separate per-target folders; CLI output overrides remain explicit. `.env` examples are not evaluated as shell code.

## Publication boundary

[[source-lab/IMPORT_POLICY.md]] records the owner's authorization and exclusions. [[source-lab/PROVENANCE.json]] maps reviewed first-party imports to their source and current hashes; [[source-lab/UPSTREAM-MANIFEST.csv]] retains the historical extraction metadata.

No third-party archives, datasets or binaries are imported. Skills, database
integration and OpenAPI are outside the requested migration scope; artifact
readers and engine contracts remain file-backed. The Python package is
`source_lab`, so its modules do not shadow the existing Android engine. Mutations
use shared previews/jobs; remote deployment remains outside this integration.

## Regression tests

[[source-tests]] preserves the engine's bound test specifications, including generated binary fixtures and launcher/evidence regressions. Run `python3 -m pytest -q` in [[source-lab/engine]].

[[source-lab/engine/tests/fixture_workspace.py#build_workspace]] generates an
owned, offline workspace for detection, crawl/merge, map, synthetic signed session
and future UI tests. Generated output and signing keys are never committed.

The repository test runner executes this suite in a separate Python process from Android tests. Static analysis remains usable without optional browser, grammar or VM dependencies.

## Console readiness

[[console/source_control.py#lab_status]] probes the selected Python interpreter in
an isolated process and reports core storage/Python requirements separately from
optional Git, Node, grammar and browser tools.

[[console/oslab.py#provider_for]]
selects native Python on Linux, macOS and Windows, without WSL or virtualization.
The dashboard lab types and localized readiness routes include Source Lab.

## Console operations

[[console/source_api.py#SourceAPI]] adapts retained file-backed endpoints to
bounded artifact readers and the shared job service. [[console/source_control.py#build_plan]]
validates typed options and produces exact previews.

[[console/source_jobs.py]] journals Source jobs privately and locks all Source
writes across console processes. [[console/source_worker.py]] supervises engine
children and stops the process group if the console connection closes.


[[source-lab/API.md]] records all retained methods and intentional contract
adaptations. [[android-lab/lab/tests/test_source_console.py]] exercises real
engine jobs, guards, credential handling, conflicts and interrupted recovery.

## Crawler input boundaries

[[source-lab/list_inputs.py]] parses bounded operator CSV/TXT/XLSX lists offline
in a separate process.

Console previews normalize only GitHub identifiers or available private
directories. Typed retry/wait/file/map caps bound worker work.
Catalog joins reuse the confirmed jobs service and write private output, keeping
operator resource catalogs unchanged.

## Pipeline reference

[[console/source_pipeline.json]] contains pinned first-party architecture
descriptors with an explicit import date, not repository results or a live run.

[[dashboard/src/views/source/pipeline.tsx]] renders stage flow and details,
network requests, signatures, risk rules, manifest candidates and flow steps.
An operator snapshot takes precedence; provenance stays visible in either case.

## Authorized legacy import

[[source-lab/engine/source_lab/import_legacy.py]] supplies an opt-in dry run,
hash-bound copy, private backups/journal and conflict-protected rollback.

[[source-lab/IMPORT.md]] documents positive artifact allowlists, signed-session
verification, root relocation and excluded archives/datasets/binaries/keys.
Original inputs remain unchanged; copy shares the Source job lock.
