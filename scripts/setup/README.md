# One-command setup

Three self-contained installers that take a fresh machine to a running os-lab
web console in a single command — detect the host, report device status,
install prerequisites, fetch/update the checkout, provision a Python
virtualenv, and launch the PWA UI. Safe to re-run; they update in place.

| Host | Script | One-liner |
|------|--------|-----------|
| Linux | [`install.sh`](install.sh) | `curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.sh \| bash` |
| macOS | [`install-macos.sh`](install-macos.sh) | `curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install-macos.sh \| bash` |
| Windows | [`install.ps1`](install.ps1) | `irm https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.ps1 \| iex` |

From an existing checkout, run the script directly instead of piping from the
network — it detects the surrounding checkout and uses it in place:

```bash
./scripts/setup/install.sh              # Linux
./scripts/setup/install-macos.sh        # macOS
.\scripts\setup\install.ps1             # Windows (PowerShell)
```

## What each stage does

1. **Detect** — OS, distro/version, architecture, provider (native-linux /
   wsl2 / native-macos / native-windows), CPU, memory, disk, and
   virtualization availability (KVM on Linux, Hyper-V/WSL2 on Windows).
2. **Report** — a table of host tools (git, python, pip, docker, compose, adb,
   java, node; plus Xcode/simctl on macOS) with the resolved path and version,
   or `miss` when absent. `--report-only` stops here and changes nothing.
3. **Install prerequisites** — core tools (git, python3 + venv) via the host
   package manager: apt/dnf/yum/pacman/zypper/apk on Linux, Homebrew on macOS,
   winget/Chocolatey on Windows. Docker is reported but never force-installed.
4. **Fetch/update** — clone os-lab to the target directory, or reuse an
   existing checkout. A fresh clone (or `--update`) fast-forwards the current
   branch; a developer's working branch is never switched.
5. **Virtualenv** — create `.venv` in the checkout and install
   `android-lab/lab/requirements.txt`. `--minimal` skips the heavy tool deps;
   the web console itself runs on the Python standard library.
6. **Dashboard** — with Node.js 22+ present, rebuild the dashboard into the
   untracked `dashboard/build`; otherwise use the committed `dashboard/dist`
   (see [`dashboard/`](../../dashboard/README.md)).
7. **Launch** — start the web console and open the browser at
   `http://127.0.0.1:5050`. It opens on *This computer*: which labs this host
   can run and what each one still needs.

## Options

Shell (`install.sh`, `install-macos.sh`) / PowerShell (`install.ps1`):

| Shell | PowerShell | Meaning |
|-------|-----------|---------|
| `-d, --dir DIR` | `-Dir DIR` | install/checkout directory (default: `~/os-lab`) |
| `-b, --branch NAME` | `-Branch NAME` | git branch to track (default: `master`) |
| `-p, --port N` | `-Port N` | web console port (default: `5050`) |
| `--report-only` | `-ReportOnly` | detect + report only; change nothing |
| `--no-install` | `-NoInstall` | do not install system prerequisites |
| `--no-run` | `-NoRun` | set up but do not launch the console |
| `--minimal` | `-Minimal` | virtualenv for the UI only (skip heavy deps) |
| `--update` | `-Update` | pull latest even if the checkout exists |

Environment overrides (all hosts): `OSLAB_REPO`, `OSLAB_DIR`, `OSLAB_BRANCH`,
`OSLAB_PORT`, and `OSLAB_DASHBOARD_BUILD=0` to skip the dashboard rebuild.

## Notes

- **VM labs need virtualization.** The Windows and Linux VM labs require a KVM
  Linux host (or nested virt). On macOS and bare Windows the installer reports
  this and steers you to the Android and iOS tooling.
- **Windows PowerShell 5.1** is supported; `install.ps1` is saved UTF-8 with a
  BOM so 5.1 parses it correctly.
- Re-running is the supported update path — the installer is idempotent.

## Source Lab

The desktop runtime includes Source Lab's Python engine, schemas, browser probe
and console adapters; it does not require the private source repository. Source
private storage and resource inputs are never staged, even if accidentally tracked.
Updates preserve existing private Source storage.

Minimal mode uses the standard library and committed dashboard, skips pip
upgrades/dependency installs, and reports Source readiness without downloads.
Source Lab requires Python 3.11+ and writable private storage. Set
`SOURCE_LAB_PYTHON` to select another supported interpreter. Git is needed only
for repository acquisition; optional tree-sitter grammars improve parsing, and
Playwright plus Chromium are installed separately for live browser collection.
Static detection never requires Node, containers or virtualization.

Native macOS/Windows installer acceptance remains a release verification step;
Linux packaging tests do not establish native host support.
