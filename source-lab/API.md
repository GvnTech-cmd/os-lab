# Source Lab console API

The installed localhost console serves these routes. GET requests never launch
engine jobs. POST and DELETE require a localhost `Host` and `X-OSLab: 1`.
Third-party archives/datasets/binaries, Skills, databases and OpenAPI remain
excluded. No source data, Brain export or external catalog is bundled here.

## Confirmation and jobs

For any operation below, POST `{"options": {...}, "preview": true}` to receive
`{plan, token}`. Review the exact supervisor command, engine arguments, effects,
network access and timeout. POST the same options with `token` to start the job;
the response is HTTP 202 `{job}`. Changed options or configured paths/interpreter
invalidate the token. The token is a confirmation capability, never an engine
credential. Tokens from a previous console process are invalid.

Poll `/api/jobs/{id}` for state, bounded logs, line count and truncation, or use
`/api/jobs`. Progress follows actual engine output; no invented percentage is
reported. `/api/jobs/{id}/cancel` accepts the existing console POST contract.
Source jobs share one lock across actions and console processes. Conflicts return
409. A job remains exclusive through process cleanup. Timeouts and cancellation
terminate the process tree, escalating on POSIX after two seconds. Engine
supervisors stop their process group when the console's input pipe closes.

Source records are journaled privately under `control/jobs.json`, with up to 50
records and a 4 MB journal cap. Unfinished records with no live lock become
`interrupted` on restart; partial engine outputs require review before retrying.
A second live console can inspect another console's job but cannot cancel it.
Source logs are limited to 4,000 lines and 1 MB; individual lines over 8 KB are
omitted. Other labs retain their existing in-memory lifecycle.

## Retained methods

| Route under `/api/source` | Methods | Contract |
|---|---|---|
| `/detection` | GET | Available private `targets/` and `cloned-repos/` candidates, runner readiness and latest `run`. |
| `/detection` | POST | `target` candidate key, optional `platform` (auto or five platform IDs), `runCanary`, `testUrl`, `session`. Output uses the candidate's fixed analysis slug. |
| `/detection` | DELETE | `{jobId}` cancels a matching Source detection job. |
| `/evidence` | GET | Existing target summaries, `slug` detail or `slug` + `session` events. Session integrity remains explicitly unverified by the reader. |
| `/evidence/report` | GET | `slug`, `file`: the five allowlisted formats; STIX remains CLI-only. JSON downloads are parsed and scrubbed before serialization. |
| `/analyzer` | GET | Latest crawl `run`, report, CSV summary count and first 50 rows; available `sourceFiles` and `sourceFilesTruncated`. Source-list discovery is capped at 100 files/1,000 scanned entries and refuses symlinks. |
| `/analyzer` | POST | `sourceFile` basename from configured resources/sources or explicit `repos` owner/repo list. Optional `workers` (1–8), `depth` (1–10), `noAst`, `noMetadata`, `resume`, `keepWorkspace`. |
| `/analyzer/merged` | GET | File-backed extension bundles, property/dependency/permission matrices and background groups; `export=json` or `csv`. |
| `/deep-analysis` | GET | Available and analyzed bundles; `repo=owner/name` or slug selects a bundle; optional `file` reads bounded UTF-8 workspace source. |
| `/deep-analysis` | POST | Same bounded crawler options as analyzer; no client-chosen workspace or credential fields. |
| `/deep-analysis/merge` | GET | Jobs and output reports; `download=folder` downloads an inspected ZIP; `plan=1&slugs=a__b,...` returns an exact read-only job preview, without launching the engine. |
| `/deep-analysis/merge` | POST | Explicit `slugs`, optional `name` (60 chars), `includeFlagged`, `allowClone` (default false), `mv` (2/3), `plan` (manifest-only background check). |
| `/settings/runtime` | GET | Key source/configuration/problem, default canary URL, optional Playwright availability and rotation warning. Never returns a key. |
| `/settings/runtime` | POST | Options `action=generate-key` with explicit `rotate=true` to replace an existing managed key, or `action=set-canary` and `testUrl`. These use preview/confirmation jobs. `action=verify-session`, `slug`, `session` verifies signed bundle integrity in a background job. |
| `/sources` | GET | Three operator-provided CSV catalogs with counts and actual available files. `download` names one of those catalogs. No hardcoded dataset counts. |
| `/brain` | GET | Operator-supplied `storage/brain-data/manifest.json`, with namespaced graph links. Missing data returns 404. |
| `/brain/files/{path}` | GET | Bounded JSON under that Brain root. |
| `/pipeline` | GET | Operator `storage/snapshots/pipeline.json` or the pinned first-party architecture reference. `source`, `date`, `revision` identify provenance; neither is a live run. |
| `/spotlight` | GET | `q`, optional `section` (evidence/deep-analysis/sources), `limit` (1–25); file-backed results only. |

POST analyzer/deep-analysis/merge may also use `{action: "cancel", jobId}`;
`stop` is accepted as a cancellation alias. Unknown routes, unsupported methods,
fields, query parameters and duplicate query parameters fail explicitly. Body
size is capped at 64 KB. Artifact reads retain the per-file and 16 MB aggregate
limits documented in README. Private workspace files and binary source display
are refused. ZIP downloads are bounded, inspected for private filenames and
configured credentials, and refused when credential review is required.

## Intentional adaptations from the source application

All 13 retained routes and 19 methods have adapters. The original memory-only run
objects become shared os-lab jobs; errors and cancellation use job IDs. Mutations
require the additional explicit preview round trip. GET merge planning returns a
command preview; execute `options.plan=true` through POST to run the manifest
check and read its JSON from the job log. Defaults prohibit clone during merge.

Private data roots replace deployment paths and fixture fallbacks. Input keys
are stable relative candidates; the API never accepts arbitrary absolute paths,
client tokens, output roots or workspace overrides. Credentials come only from
operator environment/private key storage. URLs cannot contain credentials,
queries or fragments. Environment keys and key files are checked for conflicting
values; managed key changes are refused when the environment owns the key.

Collections and matrices use normalized `{name, slugs, count}` entries and raw
file-backed bundles. Overview adds pinned migration annotations, dependency categories/sections,
MV2/MV3 counts, background grouping and permission risk labels. Counts deduplicate
a target within each matrix row. CSV includes annotations and protects formula cells.
Annotations describe the imported snapshot; check vendor guidance before migration.
Additional bounded crawler tuning is documented below. Pipeline reference and
optional file-backed Brain views are available. No database or Skills-backed Spotlight search is retained. The
hello-world stub remains retired. Explicit session verification uses a confirmed runtime job; read endpoints continue to label integrity as unverified.

Runtime settings writes are atomic, use private modes where supported and never
contact the configured URL. Rotation warns during preview that earlier sessions
need the original key. No keys, journals or generated outputs are committed.

## Crawler tuning and catalog joins

Crawl options also accept bounded `retries` (1–5), `cloneTimeout` (1–600 seconds),
`apiMaxWait` (1–120 seconds), `maxTreeEntries` (1–50,000), `maxAstFiles` (1–1,000),
`noMap`, `mapDetail` (files/symbols/full), `mapMaxFiles` (1–10,000) and
`mapBudgetMs` (1–120,000). Source lists are parsed offline with size/workbook caps
before preview; only clean GitHub repository identifiers and available private
directories are accepted. The plan binds the normalized targets.

A new `POST /api/source/sources` uses the ordinary preview/confirmation envelope
with empty options to join the two operator catalogs and analysis metadata into
private `catalogs/`. Inputs remain unchanged. This adds one method beyond the
19 retained upstream adapters. GET sources accepts `origin=resources|generated`
for browsing/downloads. No catalog is bundled or fetched by this action.

Deep analysis GET accepts `view=ast` with `repo` and `file`. Only the matching
AST-index entry under that bundle's `ast/` directory can be read; source/private
path and read-cap protections still apply. Missing AST artifacts return 404.
Crawl adapters additionally accept `target`, an available private directory key,
instead of repositories or a source list. Local runs use the CLI's `local__`
output naming and do not clone repositories.
