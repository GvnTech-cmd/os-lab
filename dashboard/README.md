# os-lab dashboard

The browser console for os-lab: this computer, every lab and the Android Lab
workbench. It is an Astro 7 + React 19 + Tailwind 4 app built from the qLar app
shell (qLar PR #174): the sidebar, Spotlight, theme, iUX tokens and the Android
Lab components are ported from `agents-app/src/shell` and
`agents-app/src/apk-lab`.

The output is static. `android-lab/lab/web_ui.py` serves it and is the only
backend: host detection, lab plans and jobs live in `console/oslab.py`.

## Pages

The GitHub Pages build has a separate public home and retains Firewall Lab,
informational Source Lab/workflow guides, Contribute, feedback and legal routes
in all eight locales. `scripts/deploy-page.sh --dry-run` stages the final filtered
artifact in `build-pages/`; run the Source Pages smoke against that directory,
not only the raw Astro output. Console-backed lab controls remain local.

| Route | What it shows |
|-------|---------------|
| `/` | This computer: OS, CPU, memory, disk, KVM, container runtime, host tools, and which labs can run here (ready / needs setup / unavailable, with reasons) |
| `/labs/<lab>/` | One lab (`android`, `windows`, `linux`, `ios`, `macos`): dependencies with **Install dependencies**, typed actions, plan preview → confirm → run, live job output, container monitor, endpoints, profiles and masked configuration |
| `/jobs/` | Every lab job with its output; cancel running jobs |
| `/firewall/` | Firewall Lab company directory and full manifest details |
| `/firewall/<company>/` | One company's interactive branch composition, VLANs, firewall selections and rule counts |
| `/tr/firewall/` | Turkish Firewall Lab company directory and manifest details |
| `/tr/firewall/<company>/` | Turkish company network visualization; EN/TR links preserve the selected company |
| `/android/…` | Android Lab workbench: overview, code & providers, workflows & DAG, execution & logs, analytics, routes & sitemap |
| `/contribute/` | The contribution steps, compiled from `CONTRIBUTING.md` at build time |
| `/legal/…` | Terms of Use, Acceptable Use, Privacy Notice and Third-Party Notices, compiled from `docs/legal/*.md` at build time |

Every lab action is previewed first: the server returns the exact command, its
effects, setup prerequisites and privileges, and a token that `/api/labs/start`
requires. Pages never send command strings.

## Builds

Two builds can exist; the console serves whichever `index.html` is newer, and
falls back to the classic console (`android-lab/lab/web/`, always at
`/classic/`) when neither exists.

- `dist/` — **committed**, so hosts without Node.js still get the dashboard.
  Rebuild and commit it whenever you change `src/`: `npm run build`.
- `build/` — **local, untracked**. The installers make it with
  `npm run build:local` when Node.js 22+ is present (skip with
  `OSLAB_DASHBOARD_BUILD=0` or `--minimal`), so a local build never dirties the
  checkout.

Tailwind scans only `src/`, so both builds are byte-identical for the same
sources. `scripts/run-tests.sh` rebuilds into a temp folder and fails when the
committed `dist/` is stale.

## Develop

```bash
cd dashboard
npm ci
python3 ../android-lab/lab/web_ui.py 5050 &   # the API
npm run dev                                   # proxies /api to :5050 (OSLAB_API to change)
npm run check                                 # TypeScript
npm run build                                 # refresh dist/ before committing
```

Run the console with `./labctl ui` (or `--port N`).

### How to use

Workspace → **How to use** (`/how-to-use/`, including all locale routes) works
in the local console and public Pages. Describe a task and submit to generate
and copy an LLM-ready prompt with the shipped capability catalog, platform
constraints, workflows and guide/legal links. No LLM API, live host inventory or
request persistence is used. Review the prompt before sharing; clipboard errors
keep a read-only preview available for manual selection or retry.

Verify the final public artifact from the repository root with
`bash scripts/deploy-page.sh --dry-run`, then
`node dashboard/scripts/how-to-use-pages-smoke.mjs dashboard/build-pages`.
Set `HOW_TO_USE_ORIGIN=https://keyvanarasteh.github.io` for the same check on
the live site. Run the existing Source Pages smoke against the same filtered
artifact as well.

The full prompt embeds `docs/HOW_TO_USE_CHEATSHEET.md` (requirements, setup,
workflows, API contracts, endpoints, state, recovery and limitations) and
`docs/HOW_TO_USE_COMMANDS.md` (generated exact CLI/Make/PowerShell syntax,
configuration key names, dependency pins and developer scripts). Every task gets
the complete references; there is no keyword selection or silent truncation.
Neither document reads real `.env` files or private state.

After changing an allowlisted CLI, Makefile, example configuration, dependency
list or npm script, run `python3 scripts/build-how-to-use-reference.py` from the
repository root. Verify freshness with the same command plus `--check`. Review
and update the operational cheatsheet whenever prerequisites or behavior change.
