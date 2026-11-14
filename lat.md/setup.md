# One-command setup

Three self-contained installers bring a fresh machine to a running os-lab web
console in a single command, one per host family. They are the supported way to
bootstrap and to update a checkout.

## Installers

One script per host, each runnable via `curl | bash` / `irm | iex` or directly
from a checkout.

[[scripts/setup/install.sh]] targets Linux, [[scripts/setup/install-macos.sh]]
targets macOS, and [[scripts/setup/install.ps1]] targets Windows PowerShell
(saved UTF-8 with a BOM for 5.1). Usage, options and one-liners are documented
in [[scripts/setup/README.md]].

## Stages

Every installer runs the same seven stages and is idempotent, so re-running is
the update path.

Detect host and provider (native-linux / wsl2 / native-macos / native-windows);
report host tools with path and version; install core prerequisites (git,
python, venv) via the host package manager; fetch or update the checkout
without switching a developer's branch; provision a `.venv` from
[[android-lab/lab/requirements.txt]]; prepare the [[dashboard]]; then launch the
web console.

## Device report

The report stage mirrors the host-tool and provider discovery used by the qLar
desktop port, so a user can see capability before committing to a lab.

It prints OS, architecture, CPU, memory, disk and virtualization (KVM on Linux,
Hyper-V/WSL2 on Windows), then a tool table. `--report-only` stops after this
and changes nothing. VM labs ([[win-lab]], [[linux-lab]]) need a KVM host; the
report steers macOS and bare-Windows users to the Android and iOS tooling.

## Web console

The launched UI is the android-lab interactive console served locally by the
orchestrator.

The installer runs [[android-lab/lab/orchestrator.py]] `ui --port 5050`, which
serves [[android-lab/lab/web_ui.py]] on `127.0.0.1` and opens the browser. In
`--minimal` mode the console runs on the Python standard library with no extra
dependencies.

Before launching, the installers rebuild the [[dashboard]] into the untracked
`dashboard/build` when Node.js 22+ is present; otherwise, or with `--minimal`
or `OSLAB_DASHBOARD_BUILD=0`, the committed `dashboard/dist` is used.

## Source Lab distribution

[[app/scripts/stage-runtime.mjs]] includes Source engine/adapters and the Cleanup
Lab engine/catalog. It refuses private resource/storage/archive inputs. Desktop
updates preserve private state.

Minimal installers skip pip package upgrades and report Source readiness through
Python. Static Source detection needs no Node, VM or optional parser/browser
installation. Native installer acceptance is tracked in [[source-lab/VALIDATION.md]].
