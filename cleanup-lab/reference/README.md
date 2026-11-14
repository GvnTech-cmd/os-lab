# Cleanup Lab reference code

Working code for the Cleanup Lab roadmap, contributed by the maintainer from
private projects. Those projects stay private; what is here is a cleaned-up,
self-contained copy, licensed with the rest of os-lab under **Apache-2.0**
(see [`LICENSE`](../../LICENSE)). You don't need access to anything else to
use it.

Both parts here are **read-only**: they measure, search, classify, plan and score.
None of them deletes, moves or writes user files. Wiring them into the engine,
console and dashboard is the job of the tasks `CLN-21` … `CLN-29`, and every
path they hand over is validated again by the engine's safety guard (CLN-12)
and the plan → confirm → clean flow (CLN-13).

| Part | What it is | Tasks |
|---|---|---|
| [`qrust-scan/`](qrust-scan/) | Rust crate: parallel disk-usage scan with allocated size, hard-link de-duplication, a parent-summed size tree, sort modes, hotspot descent, glob seek, cleanup-name candidates, `.gitignore` view, progress and cooperative cancel. macOS, Linux, Windows. | CLN-21, CLN-22, CLN-23 |
| [`python/cleanup_ref/`](python/cleanup_ref/) | Python standard-library modules: path policy, marker-verified artifact signatures, tool-reported cache locations, relocation planner, cleaned-items ledger and learned profile. | CLN-24 … CLN-27 (and CLN-12, CLN-23) |

## Status

These are **references, not wired features**. Nothing in `console/`, `labctl`
or the dashboard imports them yet. A task PR may move a module into
`cleanup-lab/engine/` (or add the crate to `app/src-tauri` as a path
dependency), adapting it to the contract in [`../README.md`](../README.md).
Keep the tests passing when you do.

## qrust-scan

The scan/seek algorithms follow [dua-cli](https://github.com/Byron/dua-cli)'s
design. They are reimplemented, not taken from dua's source.

| Module | Behaviour |
|---|---|
| `walk` | `jwalk` parallel walk on a dedicated Rayon pool. Sizes come from `symlink_metadata` (never follows links). Allocated size by default (`st_blocks × 512` / `GetCompressedFileSizeW`) and apparent size on request. Hard links are counted once by `(dev, inode)` / `(volume serial, file index)`. Optionally stays on one filesystem. A single-pass depth stack rolls child sizes, counts and newest mtime into their parent. Progress is throttled to 120 ms. Cancellation is polled per entry and during the final rollup. |
| `tree` | Flat node array (parent / first child / next sibling). Sort by size, name, count or recursive mtime. `hotspot_descend` follows the biggest child down to a leaf. |
| `glob_search` | In-memory seek over the finished tree, **iterative** (any depth). `*` and `?` never cross `/`; `**` does. Stops descending at a match. |
| `cleanup` | Regenerable build folders among the current view's children, **proved by a marker file** (`node_modules` + `package.json`, `target` + `Cargo.toml`/`pom.xml`, `.venv` + `pyvenv.cfg`, a valid `CACHEDIR.TAG` …). Same signature ids as `python/cleanup_ref/artifacts.py`; keep the two tables in step. |
| `gitignore` | Finds the enclosing repo and flags the current view's children git would ignore: global excludes (`core.excludesFile`), `info/exclude`, and the `.gitignore` of the repo root and every directory down to the view. Deeper files win; nothing below an ignored directory can be re-included. |
| `platform` | The only OS-specific code: allocated size, file identity, default thread count (3 on macOS because of APFS contention, otherwise the machine's parallelism up to 16). |

**Fixed in this copy:** on Windows a directory's identity was read with a
plain `File::open`, which fails on directories. That left the scan root's
volume serial at 0, so `stay_on_filesystem` zeroed the size of every file. The
handle is now opened with `FILE_FLAG_BACKUP_SEMANTICS` and no access rights.

**Closed in CLN-22:** nested `.gitignore`, `.git/info/exclude` and the global
excludes file are read; `glob_search` no longer recurses, so a deep tree cannot
exhaust the stack; cleanup candidates need their project's marker files instead
of a name match (a `target/` without `Cargo.toml` is not reported); a failure to
build the thread pool is a `ScanError::Io` instead of a panic; `entry_count`
saturates at `u32::MAX` and a tree too large to index is an error, not a wrap.

**Still open:** on Windows every entry is opened once to read its identity, even
single-link files (a speed cost, not a correctness one). `cleanup_candidates` and
`gitignored_children` look at the current view only, as designed.

```bash
cd cleanup-lab/reference/qrust-scan
cargo test
cargo clippy --all-targets -- -D warnings
cargo clippy --target x86_64-pc-windows-msvc --all-targets -- -D warnings   # Windows half of `platform`
```

## python/cleanup_ref

| Module | Behaviour | Fixes against the private original |
|---|---|---|
| `path_policy` | Canonical absolute paths, protected roots (`/`, drive roots, home), containment, scan-root, target and copy validation. | Containment is checked on resolved paths and path components, not string prefixes. A target may not be an allowed root itself. |
| `artifacts` | 17 project-artifact signatures (Node, Rust, Maven, Gradle, Python venv/tox/pycache, Next, Nuxt, SvelteKit, JS tool caches, Dart, SwiftPM, Zig, Elixir, Terraform) proved by marker files, plus any directory with a valid `CACHEDIR.TAG`. Iterative sweep: stops at a match, skips VCS and system trees, idle-project filter, cancel. | The original matched `venv`/`target` by name; one port required `Cargo.toml`. Every signature now needs proof. |
| `devcache` | 15 tool cache locations. Each resolves from the tool's env var, then a fixed-argv probe (no shell, 5 s timeout, output validated), then the per-OS default. rustup and Cargo home are `toolchain`, not `cache`. | The original only knew macOS defaults and sometimes probed before reading the environment. |
| `relocation` | Link-status classifier (7 states) and typed plans: move = copy → verify → rename aside → symlink → verify link → remove aside; restore; relink. Also a free-space gate and interrupted-run detection. | The original ran `rm -rf` on the source right after copying, without verifying. It fell back to an elevated shell script built by string interpolation, and its "prepare"/"link" actions `rm -rf`-ed the home path. |
| `learning` | Local cleaned-items ledger (atomic JSON, 90-day window, lifetime totals). Profile score = `frequency × 0.5^(age/30d) × avg bytes × (1 + user-chosen share)`. Also soft pre-selection and Quick Clean seeds. | A corrupt ledger was silently overwritten (lifetime totals lost); it is now moved aside and reported. Pre-selection also skips the `credentials` and `privacy` classes, not only `high`. |

```bash
cd cleanup-lab/reference/python
python3 -m unittest discover -s tests -p 'test_*.py'
```

Both suites also run from `./scripts/run-tests.sh`.

## Not ported on purpose

- Product-specific behaviour: guest scan allowance and sign-in gating, the
  freeware counter, app icons, Dock repair, the Xcode bundle mover.
- The Swift ↔ Rust C ABI and its weak-symbol shim. os-lab calls Rust directly
  from Tauri, so that boundary has no use here.
- Any elevated shell script. Privileged work goes through CLN-20's typed plans.
- Permanent deletion as a purge mode. The original `purgePath` called
  `removeItem` directly, counted apparent size and counted directories as files.
  CLN-13 uses Trash by default and reports honest per-item results.
