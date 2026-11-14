# Qleaner → Cleanup Lab parity

Every detector id Qleaner can emit, mapped to the catalog entry that replaces it or
to a written reason for dropping it. Read from `src-tauri/src/cleaner/detectors.rs`
and `commands.rs` on Qleaner's default branch on 2026-11-13.

* **Catalog id** — the entry id the task adds. Families are files: `system.json`,
  `browser.json`, `developers.json`, `projects.json`, `containers.json`,
  `vms.json`, `simulators.json`, `leftovers.json`, `packages.json`.
* **Task** — the CLN task that adds the entry. `catalog/system.json` already ships
  the three CLN-02 seeds.
* **Instance ids** — Qleaner builds one item per folder or volume
  (`crash_{name}`, `tmp_{base}_{name}`, `container_{name}` …). One catalog entry
  covers the detector; the scan creates the items, so they are listed once, under
  the detector that emits them.

Qleaner's known bugs and the "Do not port" tables are in
[`README.md`](README.md); this file records coverage, not behaviour.

## Safety translations

| Qleaner check | Cleanup Lab | Why |
|---|---|---|
| `path.contains("..")` | `safety.canonical` + resolved containment | the old test rejected valid names like `a..b` and never resolved a symlink |
| `path.contains("system")` | `protected_roots` + `system_roots` per OS | the substring blocked `~/.cache/systemd` and protected nothing else |
| Chrome and Firefox only, by substring | the entry's `owningProcesses`, whole name from the process table | every entry names its own apps; `Slack` does not match `slackd` |
| `is_owned_by_user` (uid compare) | `safety.owned_by_user` | kept; Qleaner called it on macOS only |
| `is_process_running` (two names) | `safety.running_processes` | now fed by the catalog, with injected process lists in tests |

## Scan job translations

| Qleaner function | Cleanup Lab | Notes |
|---|---|---|
| `start_scan` | `scan.scan_catalog` + a console job | Scans the catalog's resolved paths for this OS; the request names entry ids, never paths. |
| `get_scan_results` | `GET /api/cleanup/jobs/<id>` (`result`) | Per-path report plus entry and scan totals. |
| `cancel_scan` | `POST /api/cleanup/jobs/<id>/cancel` → `threading.Event` | Returns the partial counters with `cancelled: true`; no error and no invented bytes. |
| `get_directory_size` | `scan.measure_path` | `lstat` only; symlinks never followed; sockets/FIFOs/devices not measured. |
| (none) | progress callback | Throttled to 120 ms and polled between entries; `GET /api/cleanup/jobs/<id>` returns it. |

Unlike Qleaner's scan, a path the engine cannot read is reported in `unreadable`
instead of aborting or being silently skipped, and one directory worker never
follows a symlink out of its top-level path.

## Plan → clean translations

| Qleaner function | Cleanup Lab | Notes |
|---|---|---|
| `clean_items` / `clean_leftovers` | `clean.build_plan` + `clean.execute_plan` + console jobs | Guard → measure → fingerprint → confirm. The request names catalog ids, never paths. |
| Trash fallback to `remove_dir_all` | `clean._run_trash` | **Not ported.** A failed Trash move is a failed item; permanent delete only when the plan says `mode: "delete"`. |
| `retry_remove` | `clean.retry` | Retries `EBUSY`, `ETXTBSY`, `EAGAIN`, `EWOULDBLOCK`, `EINTR`, `ENOTEMPTY` three times; the final error is reported, never swallowed. |
| (none) | `clean.fingerprint_path` + `clean.verify_plan` | A plan is single-use and expires after ten minutes or when an item's fingerprint changes. |
| (none) | per-item result | `trashed` / `deleted` / `skipped` (stable code + reason) / `failed` (error); bytes counted only after the original is gone. |
| streaming progress | progress callback | `itemsDone`, `itemsTotal`, `bytesRemoved`, `currentPath`; the job is polled through `GET /api/cleanup/jobs/<id>`. |

## System

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `user_caches` | `system.user-caches` | CLN-02 (seed) | Qleaner pushes it twice (macOS branch and Linux branch). One entry, per-OS paths: `~/Library/Caches`, `${XDG_CACHE_HOME:-~/.cache}`. Windows has no equivalent in Qleaner. |
| `system_logs` | `system.user-logs` | CLN-02 (seed) | `~/Library/Logs` only in Qleaner. CLN-04 adds the Linux and Windows equivalents. |
| `trash` | `system.trash` | CLN-02 (seed) | Never pre-selected: emptying the Trash is permanent. Qleaner scans `~/.Trash`, `~/.local/share/Trash/files` and `C:\$Recycle.Bin`; the Windows path needs a privileged read (CLN-20), so it gets its own entry there. |
| `temp_files` | `system.temp` | CLN-04 | `std::env::temp_dir()`; Qleaner only emits it on Windows. |
| `local_temp` | `system.local-temp` | CLN-04 | `%LOCALAPPDATA%\Temp`. |
| `tmp_{base}_{name}` (instance) | `system.temp` / `system.shared-temp` | CLN-04 | From `detect_temp_data`: `$TMPDIR`, `/private/tmp`, `/private/var/folders`, `~/.tmp`, `~/tmp`; skips `.lock`, `.sock`, `.pid` and regular files under 1 KiB. Shared roots are never pre-selected and cleaning needs a privileged plan. |
| `crash_{name}` (instance) | `system.crash-reports` | CLN-04 | `~/Library/Logs/DiagnosticReports`, `~/Library/Logs/CrashReporter`, `~/.local/share/apport`. |
| `font_cache_{name}` (instance) | `system.font-caches` | CLN-04 | `~/Library/Caches/com.apple.ATS`, `~/.cache/fontconfig`. |
| `spotlight_{vol_name}` (instance) | `system.spotlight-index` | CLN-04 | `.Spotlight-V100` per volume; `needsPrivilege: true` on macOS (CLN-20 rebuilds it). |

## Browsers

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `chrome_cache` | `browser.chrome.cache` | CLN-05 | Qleaner reads only the `Default` profile; CLN-05 enumerates every profile. |
| `chrome_history` | `browser.chrome.history` | CLN-05 | Privacy class, never pre-selected. Qleaner already sets `selected: false`. |
| `chrome_extensions_telemetry` | `browser.chrome.extension-traces` | CLN-05 | Privacy class. **Qleaner pre-selects it** (`selected: true`); the catalog will not, and the loader rejects a credential/privacy entry that is pre-selected. |
| `edge_cache` | `browser.edge.cache` | CLN-05 | |
| `brave_cache` | `browser.brave.cache` | CLN-05 | |
| `opera_cache` | `browser.opera.cache` | CLN-05 | |
| `vivaldi_cache` | `browser.vivaldi.cache` | CLN-05 | |
| `firefox_cache` | `browser.firefox.cache` | CLN-05 | |
| `safari_cache` | `browser.safari.cache` | CLN-05 | macOS only (Qleaner leaves the Linux path empty). |

Every browser entry names its owning process (`Google Chrome`, `Microsoft Edge`,
`Brave Browser`, `Opera`, `Vivaldi`, `firefox`, `Safari`) so the CLN-12 lock skips
it with a reason while the browser runs. Qleaner checks only Chrome and Firefox,
by substring.

## Developer tools

From `detect_cli_tool_data` (36 ids) and the cache list. All of them are
`category: developer`; the credential stores carry `risk: credentials` and are
never pre-selected (rule 5). Toolchains carry `risk: high` and are relocate-only
(CLN-27), never offered as cache (CLN-25).

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `gradle_caches` | `developers.gradle` | CLN-06 | |
| `maven_repo` | `developers.maven` | CLN-06 | |
| `ivy2_cache` | `developers.ivy2` | CLN-06 | |
| `coursier_cache` | `developers.coursier` | CLN-06 | |
| `poetry_cache` | `developers.poetry` | CLN-06 | |
| `pip_cache` | `developers.pip` | CLN-06 | Resolved by `devcache` in CLN-25 (`PIP_CACHE_DIR`, then `pip3 cache dir`). |
| `composer_cache` | `developers.composer` | CLN-06 | |
| `go_mod_cache` | `developers.go-mod` | CLN-06 | |
| `rubygems_cache` | `developers.rubygems-cache` | CLN-06 | `.gem/specs` only, as Qleaner has it. |
| `ansible_tmp` | `developers.ansible` | CLN-06 | |
| `terraform_cache` | `developers.terraform` | CLN-06 | |
| `pulumi_cache` | `developers.pulumi` | CLN-06 | |
| `k9s_cache` | `developers.k9s` | CLN-06 | **`risk: credentials`** — `.k9s` holds cluster config and screen dumps. Qleaner calls it a medium cache. |
| `helm_cache` | `developers.helm` | CLN-06 | |
| `gh_hosts` | `developers.gh` | CLN-06 | **`risk: credentials`** — `.config/gh` holds auth tokens. |
| `aws_cli_cache` | `developers.aws` | CLN-06 | **`risk: credentials`** — STS tokens. |
| `gcloud_cache` | `developers.gcloud` | CLN-06 | **`risk: credentials`** — `.config/gcloud` holds credentials. |
| `azure_cli_cache` | `developers.azure` | CLN-06 | **`risk: credentials`** — `.azure` holds tokens. |
| `kubectl_cache` | `developers.kubectl` | CLN-06 | |
| `minikube_data` | `developers.minikube` | CLN-06 | `risk: high` — deleting it loses every local cluster. |
| `venv_dirs` | `developers.virtualenvwrapper` | CLN-06 | `risk: high`; honours `WORKON_HOME` (CLN-25). Qleaner probes `workon`, a shell function it can never find. |
| `pyenv_versions` | `developers.pyenv` | CLN-06 | `risk: high`; installed interpreters are not a cache. |
| `nvm_cache` | `developers.nvm` | CLN-06 | `risk: high`; `NVM_DIR`, not a `command -v nvm` shell probe (Qleaner's never matches). |
| `rbenv_versions` | `developers.rbenv` | CLN-06 | `risk: high`. |
| `rustup_toolchains` | `developers.rustup` | CLN-06 | `risk: high`, class `toolchain`; relocate only (CLN-27). |
| `rustup_tmp` | `developers.rustup-tmp` | CLN-06 | Partial downloads; safe. |
| `bun_cache` | `developers.bun` | CLN-06 | |
| `deno_cache` | `developers.deno` | CLN-06 | |
| `wasm_pack_cache` | `developers.wasm-pack` | CLN-06 | |
| `sccache_data` | `developers.sccache` | CLN-06 | |
| `ccache_data` | `developers.ccache` | CLN-06 | |
| `jest_cache` | `developers.jest` | CLN-06 | |
| `eslint_cache` | `developers.eslint` | CLN-06 | |
| `prettier_cache` | `developers.prettier` | CLN-06 | |
| `turbo_cache` | `developers.turbo` | CLN-06 | |
| `nx_cache` | `developers.nx` | CLN-06 | |
| `npm_cache` | `developers.npm` | CLN-06/25 | Qleaner hardcodes `~/.npm` on every OS; CLN-25 resolves env → probe → per-OS default. |
| `pnpm_store` | `developers.pnpm` | CLN-06/25 | |
| `yarn_cache` | `developers.yarn` | CLN-06/25 | |
| `cargo_registry` | `developers.cargo-registry` | CLN-06/25 | |
| `cargo_git` | `developers.cargo-git` | CLN-06/25 | |
| `discord_cache` | `developers.discord` | CLN-06 | Owning process `Discord`. |
| `slack_cache` | `developers.slack` | CLN-06 | Owning process `Slack`. |
| `xcode_derived_data` | `developers.xcode-derived-data` | CLN-07 | Xcode build output; the owning process is `Xcode`. |

## Projects

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `deep_node_modules` | `projects.node-modules` | CLN-07, CLN-24 | Matched by marker files (`package.json`), not by name. Qleaner matches the folder name only. |
| `deep_rust_targets` | `projects.rust-target` | CLN-07, CLN-24 | Requires `Cargo.toml`; a folder called `target` without one is not offered. |
| Maven `target` | `projects.maven-target` | CLN-24 | Requires `pom.xml`. |
| Gradle `.gradle` | `projects.gradle-cache` | CLN-24 | Requires Gradle build/settings marker. |
| Gradle `build` | `projects.gradle-build` | CLN-24 | Requires Gradle build marker. |
| Python virtualenv | `projects.python-venv` | CLN-24 | Requires inner `pyvenv.cfg`. |
| Python tox | `projects.python-tox` | CLN-24 | Requires tox or Python project marker. |
| Python bytecode | `projects.python-pycache` | CLN-24 | Requires Python project marker. |
| Next.js build | `projects.next-build` | CLN-24 | Requires `package.json`. |
| Nuxt build | `projects.nuxt-build` | CLN-24 | Requires Nuxt config. |
| SvelteKit build | `projects.svelte-kit` | CLN-24 | Requires Svelte config. |
| JS tool cache | `projects.js-tool-cache` | CLN-24 | Requires `package.json`. |
| Dart tool cache | `projects.dart-tool` | CLN-24 | Requires `pubspec.yaml`. |
| SwiftPM build | `projects.swiftpm-build` | CLN-24 | Requires `Package.swift`. |
| Zig build | `projects.zig-cache` | CLN-24 | Requires `build.zig`. |
| Elixir build | `projects.elixir-build` | CLN-24 | Requires `mix.exs`. |
| Terraform providers | `projects.terraform-providers` | CLN-24 | Requires Terraform source marker. |
| Tagged cache | `projects.cachedir-tag` | CLN-24 | Requires valid `CACHEDIR.TAG` signature. |

Roots come from the console as validated ids (CLN-07), never as free-form paths.

## Containers and VMs

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `docker_build_cache` | `containers.docker.build-cache` | CLN-08 | Typed `docker builder prune` argv, previewed. |
| `docker_dangling_images` | `containers.docker.dangling-images` | CLN-08 | `docker image prune`, argv only. |
| `docker_stopped_containers` | `containers.docker.stopped-containers` | CLN-08 | |
| `docker_dangling_volumes` | `containers.docker.dangling-volumes` | CLN-08 | Never pre-selected: volumes can hold data. |
| `parallels_vms` | `vms.parallels` | CLN-08 | Report-only by default. |
| `vmware_vms` | `vms.vmware` | CLN-08 | |
| `vbox_vms` | `vms.virtualbox` | CLN-08 | |
| `utm_vms` | `vms.utm` | CLN-08 | |
| `{vm_id}_{name}` (instance) | the four entries above | CLN-08 | `detect_virtual_machines` emits one item per VM bundle; no extra detector. |

`docker info` gates the family, as in Qleaner, but with a Podman fallback and no
shell (`argv` lists). The family is hidden when neither engine answers.

## Simulators

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `xcode_simulators` | `simulators.xcode.devices` | CLN-07 | Device list with sizes; unavailable devices flagged. |
| `xcode_devicesupport_{name}` (instance) | `simulators.xcode.device-support` | CLN-29 | Legacy `DeviceSupport` folders. |

## macOS leftovers

All from `detect_*_orphans`. Confidence comes from the CLN-09 signature module
(bundle id from `Info.plist`, team-id prefix, inferred app name), not from
Qleaner's substring comparisons.

| Qleaner id | Catalog id | Task |
|---|---|---|
| `container_{name}` (instance) | `leftovers.macos.container` | CLN-09 |
| `group_container_{name}` (instance) | `leftovers.macos.group-container` | CLN-09 |
| `pref_{name}` (instance) | `leftovers.macos.preference` | CLN-09 |
| `appsupport_{name}` (instance) | `leftovers.macos.app-support` | CLN-09 |
| `launchagent_{name}` (instance) | `leftovers.macos.launch-agent` | CLN-09 |
| `cache_{name}` (instance) | `leftovers.macos.cache` | CLN-09 |
| `lib_{stem}` (instance) | `leftovers.macos.library` | CLN-09 |
| `hidden_app_{bundle_id}` (instance) | `leftovers.macos.hidden-app` | CLN-09 |
| `appdata_{name}` (instance) | `leftovers.macos.large-app-data` | CLN-09 |

Linux and Windows have no Qleaner equivalent (its scan returns immediately there);
CLN-10 adds `leftovers.linux.*` and `leftovers.windows.*` with the same
confidence model.

| Platform | Catalog ids | Inventory evidence |
|---|---|---|
| Linux | `leftovers.linux.config`, `.share`, `.cache` | dpkg, rpm, Flatpak and Snap package/application names |
| Windows | `leftovers.windows.appdata`, `.localappdata` | Read-only uninstall registry display names and keys |

## Packages

| Qleaner id | Catalog id | Task | Notes |
|---|---|---|---|
| `brew_orphan_{formula}` (instance) | `packages.homebrew-orphans` | CLN-11 | Report-and-suggest: the exact `brew uninstall` argv is in the preview. |
| `pip_sitepackages_{name}` (instance) | `packages.pip-global` | CLN-11 | |
| `gem_{name}` (instance) | `packages.gem-global` | CLN-11 | |

## Dropped

| Qleaner id | Where | Why |
|---|---|---|
| `app_{bundle_id}` | `detect_installed_apps` | This is an inventory of installed applications with no bytes to reclaim, not a cleanup target. The same bundle-id set is the input to the CLN-09 orphan checks, where it is read from `Info.plist` with `plistlib` instead of Qleaner's inferred names. |

Everything else is ported. Qleaner behaviour that is **not** reproduced is listed
in the "Do not port" tables of [`README.md`](README.md): silent permanent delete
when Trash fails, substring traversal and "system" guards, Chrome/Firefox-only
lock, macOS paths on every OS, `sh -c "command -v …"` tool detection, single
Chrome profile, credentials listed as cache, shredder ignoring errors, hardcoded
HMAC key, and an Ignore Rules page nothing enforces.
