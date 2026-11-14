# Source Lab

Source Lab brings iQ-SourceContol into os-lab. The Python engine, CLI and guarded console API are implemented. The local
dashboard provides Overview, crawler, Evidence/runtime, Deep analysis, Pipeline
and Brain snapshot views. Distribution code is implemented; native platform
acceptance remains separately tracked; [AUDIT.md](AUDIT.md) records the final scope review.
Only first-party source code and synthetic fixtures are included. Third-party
archives, datasets and binaries are excluded. Skills, database-backed repository
management, and OpenAPI integration are also outside the requested scope.
Analysis and browsing remain file-backed; engine schemas and generated types stay.

- [Plan](PLAN.md): integration design, sequence, migration and release criteria.
- [TODO](TODO.md): ordered tasks, dependencies and completion evidence.
- [Scope audit](AUDIT.md): delivered surfaces, exclusions and verification limits.
- [Inventory](INVENTORY.md): pinned source snapshot, every page/API route and
  engine/data capabilities, with known gaps separated from shipped features.

Start with os-lab's [architecture graph](../lat.md/lat.md),
[contribution guide](../CONTRIBUTING.md) and
[UX readiness rules](../docs/UX_READINESS.md). The design keeps the existing
static dashboard and local Python console as the user-facing runtime.

## Run locally

Use Python 3.11+; no Node, Docker or KVM is needed for static analysis.

```bash
./labctl source doctor
./labctl source setup
./labctl source detect /path/to/authorized/target
./labctl source detect /path/to/authorized/target --platform android-app --format sarif
./labctl source map --root /path/to/authorized/source --out /path/to/private/repo-map.json
./labctl source crawl --help
./labctl source merge --help
```

Status/doctor are read-only. Setup creates private, gitignored storage and does
not install packages or download resources. Export `SOURCE_LAB_STORAGE` or
`SOURCE_LAB_RESOURCES` to use other locations; `.env` is never evaluated by the
launcher. On Windows, invoke `python source-lab/run.py` directly.

Detection writes reports into separate per-target folders under storage unless
`--output` is supplied. Static runs make no network requests. Explicit crawling,
merge acquisition and live browser canary tests may contact the operator's
chosen repositories or targets. Use merged extensions only in disposable lab
profiles on authorized targets. Synthetic canary fallback is labeled and excluded
from runtime correlation. Native importers remain library entry points.

Read [import/publication policy](IMPORT_POLICY.md) for authorization, exclusions
and the checks required before each public commit. Retained tests run with
`make -C source-lab test` in a Python environment containing pytest.

## Engine contracts

`./labctl source contracts` prints the engine JSON Schema; `--format typescript`
prints frontend types generated from the same models. Regenerate committed files:

```bash
./labctl source contracts --out source-lab/contracts/schema.json
./labctl source contracts --format typescript --out dashboard/src/lib/source-contracts.ts
./labctl source contracts --check /path/to/analysis-v2.json --kind AnalysisV2
./labctl source contracts --check /path/to/repo-map.json --kind RepoMapV1
```

The validator supports the schema vocabulary emitted by this engine, including
unsupported-version rejection; it is not a general-purpose JSON Schema library.

## Review local artifacts

With `./labctl ui` running, read-only console routes expose existing outputs:

- `/api/source/evidence` lists bounded target summaries.
- `/api/source/evidence?slug=owner__target` returns findings, coverage and sessions.
- `/api/source/evidence?slug=owner__target&session=ses_id` returns up to 500 events.
- `/api/source/evidence/report?slug=owner__target&file=summary.md` downloads an
  allowlisted report (JSON artifacts, Markdown or SARIF; STIX stays CLI-only).

They do not start analyses or expose keys/seals. Session integrity is explicitly
unverified in these read-only responses. Errors distinguish missing, malformed
and oversized data; responses are not cached. Target files stay under the
configured private storage root, with symlink and path-traversal checks.

The installed console now provides all retained namespaced route adapters, exact
previews and shared Source jobs. See [API.md](API.md) for methods, bounds, explicit
contract adaptations and restart/cancellation behavior.

The local dashboard includes Overview matrices/inspectors, catalogs and crawler,
Evidence/runtime settings and verification, Deep analysis/source/maps, Pipeline
reference and bounded Brain snapshot views. See [AUDIT.md](AUDIT.md) for each
retained surface and its limits. Public Source routes are informational and
never read local targets or start jobs.

## Workflow documentation

- [Operator/release runbook](RUNBOOK.md) covers readiness, operation, recovery and release gates.
- [Collectors](COLLECTORS.md) distinguishes imported/synthetic sessions from live proof.
- [Brain providers](BRAIN.md) describes bounded snapshots and unavailable application providers.
- [Legacy import](IMPORT.md) documents opt-in dry runs, exclusions, hashes and rollback.

The installed and public dashboard documentation routes render these first-party
guides. They do not expose private output or integrate an OpenAPI reference.
