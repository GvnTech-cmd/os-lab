# Source Lab operator and release runbook

Static engine, guarded console workflows and the retained file-backed dashboard
views are implemented. The owner moved remaining native/live verification and
required patches into open Source Lab bonus contributions, SRC-B01–SRC-B06 in
[Contributing](../CONTRIBUTING.md). Portable checks do not establish native manual
acceptance. Package signing/verification remains required for release publication.

## Start and configure

Use Python 3.11+. From os-lab:

```bash
./labctl source doctor
./labctl source setup
./labctl ui
```

Without Bash, run `python source-lab/run.py doctor`, then
`python android-lab/lab/web_ui.py 5050`. The console listens on localhost.
`SOURCE_LAB_PYTHON` selects the console interpreter; `SOURCE_LAB_STORAGE` and
`SOURCE_LAB_RESOURCES` select private state and operator inputs. `.env` examples
are not executed. No third-party archive, dataset or binary is bundled.

Put authorized directories/packages under private `targets/`, or use existing
`cloned-repos/`. Input catalogs belong under configured `resources/sources/`.
No input upload, arbitrary-path browser endpoint or external deployment is added.

## Dashboard workflows

| Page | Use |
|---|---|
| Readiness | Required Python/storage and optional Git/parsers/browser tooling. |
| Overview / Sources | Manifest/background/dependency/permission comparison, inspectors, catalogs and downloads. |
| Crawler | Explicit repositories/source lists, limits, preview/confirmation, logs and cancellation. |
| Evidence | Target/platform detection, findings and coverage, H1-H5 scorecard, sessions/events and reports. |
| Runtime settings | Key status/generation/acknowledged rotation, configured canary URL and signed-session verification. |
| Deep analysis | Bundles, source/AST browsing, structural maps and selected local-target reanalysis. |
| Pipeline | Pinned architecture reference or dated operator snapshot; no live-run claim. |
| Brain | Authorized graph/provider snapshots, bounded graph views, metrics, history/diff and export. |

A browser action first previews its exact command/effects/timeout. Review it,
then confirm. One Source mutation holds the shared lock. Progress follows actual
logs. Failures, cancellation, timeouts and interrupted-on-restart jobs remain
visible. Partial outputs and retained artifacts from earlier runs require review
before reuse; selecting fewer stages does not establish that old artifacts are
fresh. Compare artifact timestamps or use a separate private workspace.

Static capability/lead findings are not live proof. Session browsing does not
verify a signature; use the explicit verification action. Synthetic or failed
collections cannot confirm behavior, and correlation needs matching platform and
target. A structural map describes source structure, not runtime evidence.
Native telemetry importers do not launch native collectors. Live stress testing
has no configured application provider. See [Collectors](COLLECTORS.md) and
[Brain providers](BRAIN.md).

## Optional tools

Static analysis uses the standard library and works without Node/VMs/containers.
Git supports acquisition. Operator-installed tree-sitter grammars can improve
parsing; fallback and coverage limitations stay visible. Playwright and Chromium
are separately installed for live browser canary runs against authorized test
URLs. The software never installs these automatically. Environment-owned keys
are changed outside the dashboard; managed keys never appear in the UI.

## Import and rollback

[Legacy import](IMPORT.md) defaults to a no-copy dry run, requires reviewed hashes
and explicit authorization to copy, and retains private backups/journals.
Do not import private browser profiles or unsigned/mismatched sessions. Keep the
original key for older sessions; rotation does not rewrite signatures.

## Verify before release

Run `bash scripts/run-tests.sh`, then the dashboard translation and browser
checks. Verify local app routes and a Pages build below `/os-lab/`, including
non-English switching and absence of public engine requests/actions. Check
provenance, legal retention/network descriptions and the retained inventory.

The portable owned-fixture check can run on this checkout or an installed runtime:

```bash
python source-lab/acceptance.py --out source-acceptance.json
python source-lab/acceptance.py --root /path/to/installed/runtime --installed-only --out source-acceptance.json
```

It runs all five static analyzers with site packages disabled and an empty PATH,
checks no false runtime claims, and emits counts/fingerprints without private
paths or keys. It does not establish GUI/installer/live-collector acceptance.

On native macOS and Windows, verify a fresh packaged/minimal install, restart,
update with existing private state, Python 3.11+ readiness, static detection,
previews/jobs/cancellation, report/source browsing and the documented optional
fallbacks. Parse the Windows installer with both PowerShell 5.1 and 7; preserve
its UTF-8 BOM. Record host/interpreter/app revision and results without private
targets, keys, personal paths or session artifacts. Native acceptance remains
open under SRC-B01/SRC-B05; live browser checks are SRC-B02. The owner deferred
these checks from the integration merge into bonus work. This is a documented
exception to the initial plan, not a passed native test.

## Operation recovery

Restarted unfinished jobs become `interrupted`; they are not reported as success.
Preserve partial artifacts for review. Import rollback refuses newer edits and
retains its backups/journal. A desktop update preserves private `storage/`; it
updates code/dashboard, not user inputs. If reverting the application, restore
reviewed prior code/build assets and keep private storage backed up separately.
There is no automatic data deletion, remote upload, deployment or release action.
