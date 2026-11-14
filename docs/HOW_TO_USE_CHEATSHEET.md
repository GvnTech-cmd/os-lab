# os-lab operational technical cheatsheet

This entire reference is embedded in the generated prompt, alongside the exact
command inventory and capability catalog. It is public, shipped documentation,
not a report about the user's machine. Commands below assume a source checkout
root unless a working directory is given. Replace uppercase placeholders; never
run all examples as a single script. Choose only the operations needed for the
task and supported by the host. A packaged desktop app can run its bundled
runtime without a Git checkout; use its UI or explicitly locate that runtime
before proposing checkout-relative commands.

## 1. Host requirements and choosing an execution path

| Capability | Requirements and limits |
|---|---|
| Local console / desktop | Python 3.9+ for the shared console; Source specifically needs 3.11+. Desktop can offer managed CPython 3.12 on explicit request. No Node server runs in production. |
| Source static detection / maps | Native Python 3.11+, readable authorized targets and writable private storage. No Docker, KVM, Node, database or browser required. Git only for acquisition; tree-sitter grammars and Playwright/Chromium optional. |
| Linux-host Windows VM | Linux with accessible KVM, Docker/Podman + Compose, /dev/net/tun and NET_ADMIN; 32 GB free disk minimum, 64 GB+ recommended; at least 2 GB available RAM plus guest/host overhead. Configure licensed Windows media/version and credentials. |
| Linux VM | Same KVM/container requirements; 16 GB free disk minimum, 32 GB+ recommended; at least 2 GB available RAM plus overhead. BOOT selects distro/ISO. |
| Android dynamic emulator | Practical supported route: x86_64 Linux with VT-x/AMD-V and accessible KVM, Docker/Compose, ADB; documented host minimum 8 GB RAM / 20 GB free disk, recommended 16 GB / 40 GB+. ARM full emulation is not a practical equivalent. |
| Android static | No emulator or KVM needed for static work. MobSF/JADX/container workflows still need their respective tools/runtime; native Python helpers need their declared requirements and Java/JADX where used. |
| Native iOS/macOS | Real macOS, full Xcode, selected developer directory, accepted Xcode licence, downloaded iOS Simulator runtime and a matching device; optional Node/Appium + XCUITest for automation. Command Line Tools alone do not provide the Simulator. |
| iOS macOS VM | Compatible x86_64 KVM host, Docker/Compose, Apple hardware/licence compliance; preflight minimum 64 GB free disk and 4 GB available RAM, recommended 128 GB+ disk plus configured guest RAM. Xcode/Simulator installation inside the guest is manual. GPU path is opt-in and requires /dev/dri and compatible Vulkan hardware. |
| Firewall authoring / rendering | Python 3 standard library for validation/catalog/rendering; no VM needed to design or render. Optional firewall VM needs Linux/KVM/Compose; SSH client and optional sshpass for apply. |
| Public Pages | Static information site only. No local engine, target upload, VM controls or live host inventory. Prompt generation/copy runs in the browser. |

Run the relevant doctor/preflight: a catalog support label does not mean that
requirements are installed or a service is ready. Virtualization in firmware,+nested virtualization, group membership and Compose availability must be checked.
Refresh group membership after provisioning. Running containers and responding
viewers are different readiness stages from usable guests.

## 2. Installation, desktop launcher, updates and local UI

From a reviewed checkout:

```sh
./scripts/setup/install.sh --report-only
./scripts/setup/install-macos.sh --report-only
# On Windows PowerShell:
.\scripts\setup\install.ps1 -ReportOnly
```

Choose the script for the actual host. Without report-only, installers can
install system prerequisites, fetch/update Git, prepare .venv and launch the
console. Shell options: --dir DIR, --branch NAME, --port N, --report-only,
--no-install, --no-run, --minimal, --update. PowerShell equivalents: -Dir,
-Branch, -Port, -ReportOnly, -NoInstall, -NoRun, -Minimal, -Update. Environment:
OSLAB_REPO, OSLAB_DIR, OSLAB_BRANCH, OSLAB_PORT; OSLAB_DASHBOARD_BUILD=0 skips
Node rebuilding. Minimal mode skips heavy Python package installs and uses the
committed dashboard. Re-running the installer is the supported checkout update
path; preserve a developer's branch and private state.

```sh
./labctl ui --port 5050
# Without Bash, using a suitable Python interpreter:
python android-lab/lab/web_ui.py 5050
```

Console URL: http://127.0.0.1:5050 by default; desktop chooses a free localhost
port. The desktop launcher resolves OSLAB_ROOT, a selected checkout, a debug
checkout, then its bundled runtime. It offers Get Python, Retry, Start installed
engine and, where supported, Get Docker Desktop. These require explicit user
actions; downloading an installer is not a finished installation or licence
acceptance. Continue to dashboard supports non-container labs. File → Container
setup reopens setup; File → Files folder selects an empty writable destination
and copies app data. Do not unplug that folder while the app uses it. Updates
preserve .env/config.env, storage and artifacts. Quitting the app stops its
console supervisor/process group, including jobs.

Use Workspace → This computer for live host readiness; Workspace → Jobs for
output and cancellation; Help → Health check for platform capability details.
Advanced settings exposes configured addresses/configuration; a configured URL
does not establish a running service. Spotlight uses Ctrl+K / Cmd+K; sidebar,
mobile drawer, eight interface languages, light/dark themes, feedback, legal and
contribution pages are provided. /classic/ is the fallback console. How to use
does not send tasks to an LLM, persist tasks or include live host data.

Reference: scripts/setup/README.md, app/README.md, dashboard/README.md.

## 3. Shared lifecycle, configuration, profiles and recovery

```sh
./labctl help
./labctl all status
./labctl all doctor
./labctl LAB doctor
./labctl LAB profiles
./labctl LAB profile use development
./labctl LAB profile show
./labctl LAB config path
./labctl LAB config show
./labctl LAB start --wait
./labctl LAB status
./labctl LAB monitor --once
./labctl LAB logs -f
./labctl LAB urls
./labctl LAB stop
```

LAB for VM dispatch is win, linux, ios or android (aliases in command inventory).
Source has its own verbs; it participates in all status/doctor/monitor, not VM
start/stop/restart/profile fan-out. macOS iOS dispatch uses native scripts.
VM profiles: lightweight, development, performance; profile use writes .env,
--profile NAME overlays it for one invocation. config set KEY=VALUE, unset KEY,
edit, get KEY and path are available. config show masks secrets; --reveal,
config get, Make env and connection-detail commands can expose credentials:
do not request their unsanitized output in an LLM prompt.

```sh
./labctl win resize --cpus 4 --ram 8G --dry-run
./labctl win resize --cpus 4 --ram 8G --apply
make -C win-lab backup FULL=1
make -C win-lab restore FILE=backups/REVIEWED_BACKUP.tar.gz
```

Resize may persist configuration and --apply recreates the container. Android
adds --device NAME. VM disks are persistent/grow-only; after disk expansion,
grow the guest partition/filesystem separately (APFS in macOS). The shared help
has historical Windows-only disk wording; Linux/iOS VM runbooks also document
disk expansion. Do not shrink disks or equate RAM allocation with host free RAM.
Backups are cold by default; FULL=1 includes shared data (Windows also OEM).
Restore moves existing storage aside in the OS VM labs. Review the archive,
destination and free space before confirming restore. install-service and
uninstall-service manage systemd boot units on supported Linux hosts.

Private layout: per-lab .env, storage/, shared/, backups/; Windows oem/ maps to
C:\OEM and shared/ to guest Z:. Linux/iOS shares need the guest's documented
mount mechanism. Container shell is a wrapper/tools shell, not necessarily a
shell inside the guest OS. Make reset CONFIRM=yes destroys VM disks. In the
OS VM labs clean removes backups; Android clean removes analysis artifacts.
Preserve artifacts/backups before cleanup and obtain explicit confirmation for
destructive operations. Choose distinct host ports when multiple guests run:
Windows/Linux/iOS all default their web viewer to port 8006.

Reference: labctl, win-lab/README.md, linux-lab/README.md, ios-lab/README.md.

## 4. Windows and Linux guest operations

```sh
make -C win-lab preflight
make -C win-lab prepare
make -C win-lab boot
make -C win-lab wait-install
make -C win-lab status
make -C win-lab rdp
make -C win-lab smb
make -C linux-lab preflight
make -C linux-lab prepare
make -C linux-lab boot
make -C linux-lab wait-ready
make -C linux-lab ssh
make -C linux-lab share
```

prepare creates missing .env/data directories; edit credentials and resources
before boot. setup installs host prerequisites and changes groups (privileged).
boot waits for web viewer only. Windows readiness additionally requires
storage/windows.boot; Linux waits for SSH then writes storage/linux.ready.
Defaults (configured, not proven live): Windows web 8006 / RDP 3389 TCP+UDP;
Linux web 8006 / SSH host 2222 to guest 22. Bind or tunnel access locally;
do not expose them on an untrusted network.

Windows configuration covers VERSION, language/region/keyboard, resource/disk
settings, WINDOWS_USER/WINDOWS_PASSWORD, RDP/WEB ports, protected viewer, Samba,
OEM automation, media cleanup and shutdown timeouts. Linux covers BOOT distro
shortcut or ISO URL, BOOT_MODE, LINUX_USER/LINUX_PASSWORD, resource/disk settings
and SSH/WEB ports. For a local ISO bind ./boot.iso to /boot.iso as documented.
First boot can download large images/media. update pulls a newer container and
recreates it; restart/down stop/recreate according to each Make target. Check
logs and guest installation state before assuming an unreachable viewer means
analysis failure. Linux guest use cases include isolated ELF/reverse-engineering,
kernel/fuzzing and containment exercises, not unrestricted host execution.

## 5. Android static, dynamic, reverse engineering and diagnostics

Run make targets from android-lab/lab (or use make -C android-lab/lab).
Start with preflight and an appropriate mode in .env (LAB_MODE=static|dynamic).

```sh
make -C android-lab/lab setup-python
make -C android-lab/lab platform-tools
make -C android-lab/lab static-up
make -C android-lab/lab wf1 APK=/path/to/OWNED.apk
make -C android-lab/lab boot
make -C android-lab/lab install APK=/path/to/OWNED.apk
make -C android-lab/lab wf2 APK=/path/to/OWNED.apk PKG=com.example.owned
make -C android-lab/lab hook PKG=com.example.owned HOOK=hooks/REVIEWED.js
make -C android-lab/lab report
```

These are alternative task paths, not a sequence to run blindly. setup-python
creates the lab .venv/installs requirements; platform-tools downloads Google's
ADB/fastboot (not redistributed). OSLAB_NO_DOWNLOAD=1 prevents the automatic
platform-tool fetch. Static services use docker-compose.win.yml (MobSF,
mitmproxy, tools); dynamic adds the emulator. WF1 scans with MobSF, decompiles
with JADX and creates a report; WF2 boots/deploys the target and captures traffic,
with optional Frida instrumentation. Check actual runtime/tool availability;
Frida client/server/Gadget versions and APK ABI must match. Patched APKs need
signing and installation compatible with the target; attaching/debug/sandbox
access can require a debuggable app, appropriate device permissions or a rooted
disposable device. Never promise arbitrary private sandbox access on stock phones.

Python orchestrator prefix from checkout root:
`python android-lab/lab/orchestrator.py COMMAND` (activate the appropriate .venv).

| COMMAND and arguments | Result / additional requirement |
|---|---|
| preflight | Host tools and connectivity checks; may trigger documented tool acquisition unless downloads disabled. |
| wf1 --apk APK | Static pipeline; needs relevant scanning/decompilation tooling. |
| analyze-app --apk APK | Manifest/permission, crypto, WebView and other heuristic vulnerability analysis. |
| scan-secrets --target APK_OR_DIRECTORY | Secret pattern review; redact any findings before sharing. |
| generate-report --input APK_OR_ANALYSIS_JSON --out PRIVATE_DIRECTORY | Standalone HTML, Markdown and JSON report generation. |
| monitor --pkg PACKAGE --filter REGEX | Live logcat security monitor via ADB; both filters optional. |
| telemetry --pkg PACKAGE | Device/app memory/socket/battery snapshot; attached authorized device. |
| dump-sandbox --pkg PACKAGE | Sandbox extraction/audit with required device permissions. |
| fuzz-ipc --pkg PACKAGE | Exercises exported components; changes app/device behavior. Use disposable authorized targets. |
| patch-apk --apk APK --gadget | Modify network security / optional Gadget injection; preserve original APK. |
| agentic-plan --input APK_OR_ANALYSIS_JSON | Heuristic threat model/hypothesis and tailored hook generation; not a verified exploit or autonomous success. |
| parse-flows --file PRIVATE_FLOWS.mitm | Parse an existing mitmproxy capture; can contain sensitive traffic. |
| ui --port 5050 | Local browser console. |
| clean | Deletes artifacts; export wanted results first. |

Direct helper MobSF client:
`python android-lab/lab/scripts/mobsf_client.py status --url http://127.0.0.1:8000`,
`start`, or `scan APK -o PRIVATE_REPORT.json`. Supply credentials through the
documented private setup, never ask the user to paste API keys into a prompt.
app_analyzer.py also takes APK [OUTPUT_DIRECTORY] directly. The generated parser
inventory includes helper-specific flags and choices.

Configured Android endpoints: noVNC 6080, ADB 5555, MobSF 8000,
mitmproxy 8080 and its web UI 8081; use actual host report/configuration. Check
ADB devices, emulator boot-completed status, package ID, proxy/trust certificate
setup and capture freshness. Certificate pinning bypass/crypto hooks are for
owned or explicitly authorized test apps only. Emulator internet/traffic routing
does not imply a physical device is configured. DOCKER_ANDROID_ANALYTICS=false
is the default; keep it disabled unless the operator knowingly changes it.

Dashboard Android routes: /android/ overview/staged APKs; /labs/android/ runtime;
/android/providers/ devices/endpoints/hooks; /android/workflows/ actions;
/android/console/ output; /android/analytics/ reports;
/android/sitemap/ route map. APKs are in android-lab/lab/apks/ and private reports,
flows, dumps and analysis in android-lab/lab/artifacts/. Upload checks do not
establish trust in a binary. Download/export desired reports before cleaning.

Windows PowerShell alternative (working directory android-lab/lab):
`.\lab.ps1 preflight`, `setup`, `wf1 -Apk PATH`, `wf2 -Apk PATH -Pkg PACKAGE`,
`hook -Pkg PACKAGE -Hook PATH`, `trace-crypto -Pkg PACKAGE`, `report`.
The generated inventory lists every accepted command/parameter, including
MobSF operations, VirtualBox lifecycle, vbox-deploy-android and Podman status.
VirtualBox/Podman must be available; userland/zero-admin workflows do not waive
host virtualization, installation or organizational permission requirements.
vbox-download-iso downloads media; vbox-autoinstall provisions a guest disk;
vbox-deploy-android installs the Android stack in that guest. VM -Memory is MB,
-Cpus is cores; -Gui changes the VM presentation. Preserve PowerShell 5.1 UTF-8
BOM when editing scripts. Follow README-WINDOWS.md for exact host model/setup.

Reference: android-lab/lab/README.md, README-UBUNTU.md, README-WINDOWS.md,
orchestrator.py, requirements.txt, hooks/, scripts/.

## 6. iOS Simulator, native macOS, Appium and macOS VM

```sh
make -C ios-lab mac-doctor
make -C ios-lab mac-setup
make -C ios-lab mac-profiles
make -C ios-lab mac-profile PROFILE=iphone
make -C ios-lab mac-sim
make -C ios-lab mac-status
make -C ios-lab mac-appium
make -C ios-lab mac-appium-stop
make -C ios-lab mac-stop
```

mac-setup checks Xcode; INSTALL=1 opts into Node/Appium installation as documented.
Device presets: iphone, ipad, legacy. ios-lab/mac/config.env selects SIM_DEVICE,
IOS_RUNTIME, APPIUM_HOST, APPIUM_PORT, APPIUM_LOG, BOOT_TIMEOUT. Native checks:
`xcode-select -p`, `xcrun simctl list devices available`,
`xcrun simctl list runtimes`; these do not install a missing Xcode/runtime.
Optional Appium requires XCUITest; default address 127.0.0.1:4723, configured
log artifacts/appium.log relative to the native lab. mac-stop shuts down
simulators; save test state first. Native scripts, appium install/start/stop
and available preset controls are gated by the actual host capabilities.

For the macOS VM path use ios-lab preflight/prepare/boot/status/web/vnc,
optionally up-gpu, plus lifecycle/backup/profile/service targets in the inventory.
Defaults: viewer 8006, VNC 5900, CPU 4 / RAM 8G / disk 128G (change to fit host).
MACOS_VERSION/MAC_MODEL/GPU/resources/ports are configuration, not proof a guest
is installed. boot waits only for viewer; complete macOS Setup Assistant and
install Xcode + Simulator runtime inside the guest manually. Native Simulator
is not a physical iPhone, and this integration is not a general iOS jailbreak
or physical-device instrumentation service. VM GPU/Apple-ID end-to-end validation
and automated Xcode/Appium setup inside the guest are not claimed complete.

Reference: ios-lab/README.md, ios-lab/mac/README.md,
ios-lab/knowledge/setup-mac.md, setup-ubuntu.md, networking.md, operations.md.

## 7. Source Lab: detection, source mapping, acquisition and evidence

Use the launcher so private storage defaults are correct:

```sh
./labctl source doctor --json
./labctl source setup
./labctl source detect /path/to/AUTHORIZED_TARGET --platform browser-extension --format all
./labctl source detect /path/to/AUTHORIZED.apk --platform android-app --format sarif
./labctl source map --root /path/to/OWNED_SOURCE --out /path/to/private/repo-map.json --format json
./labctl source map query --map /path/to/private/repo-map.json --lang python --exported-only
./labctl source crawl OWNER/OWNED_REPO --workers 1 --depth 1 --keep-workspace
./labctl source crawl -i /path/to/authorized-list.csv --no-metadata
./labctl source merge --slugs owner__repo --no-clone --plan
./labctl source merge-csvs --sources /path/to/operator/catalogs --output-dir /path/to/private/catalogs
```

On Windows without Bash replace ./labctl source with `python source-lab/run.py`.
doctor/status are read-only; setup only creates private directories, with no
package installation/download. SOURCE_LAB_PYTHON selects the console interpreter;
export SOURCE_LAB_STORAGE (default source-lab/storage), SOURCE_LAB_RESOURCES
(default storage/resources) in the caller. Source .env examples are never
evaluated as shell scripts. Console candidates are under private targets/ and
cloned-repos/; it does not accept arbitrary browser-submitted absolute paths.

Platform IDs: browser-extension, windows-app, macos-app, android-app, ios-app;
omit --platform for auto selection. Detection accepts target directory/package/
repository, --output DIRECTORY, --session DIRECTORY, --run-canary AUTHORIZED_URL,
--format all|json|sarif|markdown|stix. Outputs are per-target under analysis/:
analysis-v2.json/findings/coverage, H1-H5 scorecards and requested report files.
Do not mistake incomplete/static indicators for malicious behavior or verified
runtime injection. Coverage and limitations must accompany conclusions. STIX
export is CLI-only; five allowlisted report files can be served by the console.

Structural maps support Python, JS/TS, PHP, Rust, Swift, Objective-C, Kotlin,
Java and markup; disk/archive VFS includes supported packages/ASAR. Outputs
json/md/dot. Filters include language/kind/role/path/target, exported-only and
minimum role confidence; budgets include files, file KB, symbols and time.
Optional grammars improve extraction; fallback/binary-only limitations are
explicit. A source/AST/structural graph is navigation data, not observed behavior.

Crawler accepts explicit repo slugs/GitHub URLs/local directories, CSV/TXT/XLSX
lists or --scan-dir. Git is needed for acquisition; metadata may contact GitHub.
Use GITHUB_TOKEN/GH_TOKEN privately where needed; the CLI also accepts --token
but putting credentials in arguments/shell history/prompts is discouraged.
Options include workers/depth/retries/clone-timeout/api-max-wait, tree/AST caps,
resume, keep-workspace, no-ast/no-metadata/no-map and map filters/budgets. The
generated command inventory contains every parser flag. Launcher overrides
engine defaults with private analysis and workspace paths. Review stale artifacts
when using resume or skipping stages; use separate output roots for clean work.
CSV joins use operator-provided browser-extensions.csv/browser-extension-repos.csv
and crawler metadata, producing private catalogs without changing resource inputs.

Merger backend/CLI remains available: explicit slugs, name, MV2/MV3 selection,
no-clone, clone timeout, include-flagged and manifest-only --plan. Plan is not a
runtime test. Acquisition can contact networks if not disabled. Use resulting
extensions only in disposable authorized profiles. Further merger UI is skipped;
Skills, database integration, OpenAPI and third-party datasets/binaries are
excluded. Do not suggest those as installed os-lab Source capabilities.

Dashboard routes: /labs/source/ readiness; /source/ matrices/inspectors/CSV/JSON;
/source/analyzer/ crawler; /source/evidence/ detection/findings/coverage/sessions;
/source/deep-analysis/ source/AST/maps; /source/pipeline/ architecture/snapshots;
/source/brain/ graph/providers; /source/sources/ catalogs and join;
/source/settings/runtime/ keys/canary/verification; /source/docs/ guides.
Empty private targets/catalogs/providers are legitimate unavailable states.

Runtime evidence: separately install Playwright + Chromium only for live browser
canary work. IQ_SESSION_HMAC_KEY or IQ_SESSION_HMAC_KEY_FILE supplies at least
32 bytes; secrets must never enter prompt text, CLI arguments or version control.
Managed keys use private storage/mode 0600 where supported; environment-owned
keys are read-only to the UI. Preview/confirm generation or acknowledged rotation;
keep original keys for old sessions. Rotation does not re-sign old bundles.
Settings only configure a URL; they do not contact it. Detection with canary
explicitly contacts the target. Missing tooling/clean baseline may yield synthetic
events; failures yield collection_failed. Neither can confirm runtime behavior.

Sessions live under analysis/SLUG/runtime-sessions/SESSION/. Browsing does not
verify integrity. Explicit verify-session validates signed metadata/events and
hashes locally; it does not independently attest collector truth. Correlation
requires successful nonsynthetic collection, valid signatures and matching target/
platform. Four importer libraries (Windows PE-sieve/ETW; macOS dyld/swizzles;
Android process maps/threads/logcat; iOS dylibs/trampolines) take TargetIdentity,
output_root and import_session(...). They do not launch native collectors.

Brain provider contract: private storage/brain-data/manifest.json has date,
tabs [{id,label,file}] and optional providers source/history/flow/sequence/aiRules.
Graphs contain meta, nodes {id,label,type,data}, edges {source,target,...}.
Limits: 20,000 nodes/50,000 edges loaded; 100 nodes/page, at most 2,000 in-window
edges rendered. Missing providers are unavailable; dangling edges are counted,
duplicate IDs rejected. Source/history/flow/sequence/rules are plain static data.
Flow: 300 steps/eight nesting levels; diff: bounded 1,000 lines/side. Snapshot
metrics are recorded rankings; export includes the full loaded graph. No live
application stress provider is configured. Pipeline is a dated operator snapshot
or pinned architecture reference, never a claimed live analysis run.

Contracts:

```sh
./labctl source contracts
./labctl source contracts --format typescript --out /path/to/private/contracts.ts
./labctl source contracts --check /path/to/analysis-v2.json --kind AnalysisV2
./labctl source contracts --check /path/to/repo-map.json --kind RepoMapV1
```

Opt-in legacy import defaults to a no-copy dry run:

```sh
./labctl source import-legacy --source /path/to/owned/analysis --slug owner__repo
./labctl source import-legacy --source /path/to/owned/analysis --slug owner__repo --copy --authorized --expected-plan REVIEWED_FINGERPRINT
./labctl source import-legacy --rollback IMPORT_ID
./labctl source import-legacy --rollback IMPORT_ID --copy --authorized --expected-plan REVIEWED_ROLLBACK_FINGERPRINT
```

Import only reviewed allowed report/map/AST/signed-session artifacts, never whole
projects/workspaces, secrets, archives, datasets, databases, binaries or browser
profiles. Limits: 5 MB/file, 64 MB/import, 1,000 files. Sessions require the
original valid key already supplied privately; no key is imported. Existing
session IDs cannot be overwritten. Originals remain intact; private journals
control/imports/ and backups control/import-backups/ are retained. Rollback
refuses newer edits and retains backups/journals. After interruption review
rollback by journal ID before retrying.

Reference: source-lab/README.md, API.md, RUNBOOK.md, COLLECTORS.md, BRAIN.md,
IMPORT.md, INVENTORY.md, AUDIT.md. Native/manual and live browser verification
limits remain tracked as SRC-B01–SRC-B06 bonus work; do not claim they all passed.

## 8. Local API, previews, background jobs and limits

All engine routes require a localhost Host. POST/DELETE require X-OSLab: 1;
do not weaken these protections or expose the console publicly. Public Pages
has no API. Use the UI by default; technical API instructions require an actual
local console origin, not the Pages URL or an assumed port.

Host/catalog GETs: /api/health, /healthz, /api/host, /api/capabilities,
/api/labs/LAB/config, /api/labs/LAB/monitor, /api/jobs, /api/jobs/ID.
API lab IDs are android, windows, linux, ios, macos, source (the Windows CLI
alias win is not its API ID). Lab plan/start: POST /api/labs/plan with
{"request":{"lab":"LAB","action":"ACTION"}}, review returned token/plan,
then POST /api/labs/start with {"request":SAME_REQUEST,"token":"TOKEN"}.
Optional request fields are profile, cpus, ram, disk, device, wslDistro, backup
only where the selected action accepts them. Actions include doctor/setup/status,
start/stop/restart/logs/monitor/profile/resize/backup/service-install/service-uninstall;
native macOS offers its supported Simulator/Appium subset. Check the live action
list and readiness before choosing one. Cancel via
POST /api/jobs/ID/cancel. Check actual request types before scripting; do not
invent JSON fields from route names. Android workbench reads devices, apks,
hooks, reports/logs and exposes guarded run/stop/upload/log-clear routes.

Source operations use POST /api/source/ROUTE with
{"options":{...},"preview":true}; review {plan,token}, then send the same
options with token. Changed options/configuration invalidate previews. Accepted
starts return 202 {job}; read shared jobs for actual state/logs; conflicts 409.
One mutation holds the Source lock across processes until cleanup. Cancellation
or timeout kills the process tree; restart marks unfinished jobs interrupted.
Jobs retain at most 50 records privately under control/jobs.json (4 MB journal),
logs at most 4,000 lines/1 MB. A second console cannot cancel another's live job.
Partial output is not success; preserve it for review before retrying.

| Source route under /api/source | Supported technical operation |
|---|---|
| /detection | GET candidates/readiness/latest run; POST target candidate key, optional platform/runCanary/testUrl/session; DELETE matching jobId. |
| /evidence | GET summaries, or slug detail, or slug+session timeline. |
| /evidence/report | GET slug + allowlisted file; no STIX/keys/seals. |
| /analyzer | GET crawl state/report/sourceFiles/first 50 summary rows; POST sourceFile basename OR repos OR local target, plus bounded crawler options. |
| /analyzer/merged | GET matrices/bundles; export=json|csv. |
| /deep-analysis | GET repo and optional file, view=ast for indexed AST; POST bounded crawler/reanalysis options. |
| /deep-analysis/merge | GET jobs/reports, download=folder inspected ZIP, plan=1&slugs=... read-only command preview; POST slugs/name/includeFlagged/allowClone/mv/plan. Default API clone permission is false. |
| /settings/runtime | GET key status/canary/tooling; POST action generate-key (+ rotate=true acknowledgment), set-canary (+ testUrl), verify-session (+ slug/session). Never returns a key. |
| /sources | GET operator catalogs/downloads with origin=resources|generated; POST empty options to join private catalogs. |
| /brain, /brain/files/PATH | GET manifest or bounded allowlisted private provider JSON. |
| /pipeline | GET dated reference/operator snapshot with provenance. |
| /spotlight | GET q, section=evidence|deep-analysis|sources, limit=1..25. |

POST Source analyzer/deep-analysis/merge also accepts action=cancel or stop plus
jobId. Input caps: 64 KB bodies; sources discovery 100 files/1,000 scanned entries;
workers 1–8, depth 1–10, retries 1–5, clone timeout 1–600 sec, API wait 1–120 sec,
tree entries ≤50,000, AST files ≤1,000, map files ≤10,000, map time ≤120,000 ms.
Readers: 5 MB JSON/events file, 10 MB report, 16 MB aggregate, 100 targets/sessions,
500 returned events. Unsafe/duplicate/unknown parameters, symlink/reparse paths,
private names, unsupported formats and credential-bearing URLs are rejected.
CLI accepts some broader explicit output/path choices; do not assume CLI flags
are accepted as browser API fields. Consult source-lab/API.md for exact contracts.

## 9. Firewall design, validation, rendering and isolated apply

Company designs include branches/headcounts/bandwidth, VLAN/subnet/DMZ
segmentation, firewall products with justified sizing/prices, default policies,
ordered rules with mandatory notes, role-based VPN/bastion administration,
remote access and assigned monitoring ownership. Keep DHCP 67/68, DNS 53 and
NTP 123 requirements explicit; do not blindly deny base services. Size addresses
by devices, not people; verify current product/CVE/pricing claims externally.

```sh
cp -r firewall-lab/templates/company firewall-lab/companies/OWNED-SLUG
python3 firewall-lab/scripts/validate.py OWNED-SLUG
python3 firewall-lab/scripts/build-seed.py
python3 firewall-lab/scripts/catalog.py
python3 firewall-lab/scripts/catalog.py --check
python3 firewall-lab/vm/scripts/render-rules.py OWNED-SLUG --branch BRANCH_ID --segment SEGMENT_ID --target table
python3 firewall-lab/vm/scripts/render-rules.py OWNED-SLUG --target ufw -o /path/to/reviewed-rules.sh
```

Folder and company.json slug must agree (lowercase-kebab-case); fill schema
fields and write the design narrative in README.md. Renderer targets: ufw,
nft (Linux nftables), table (neutral policy). Appliance rules require translation
and validation for that appliance's actual packet filter; nftables output is not
directly compatible with every firewall product. Symbolic unknown endpoints can
be rendered as any with a note: resolve them before applying. Review order and
defaults. Rendering does not apply rules or establish a protected network.

Optional disposable VM:

```sh
make -C firewall-lab/vm preflight
make -C firewall-lab/vm prepare
make -C firewall-lab/vm boot
make -C firewall-lab/vm wait-ready
make -C firewall-lab/vm render SLUG=OWNED-SLUG TARGET=ufw
make -C firewall-lab/vm apply SLUG=OWNED-SLUG TARGET=ufw
```

Edit .env/credentials before boot; defaults viewer 8007 / SSH 2223 avoid the
other labs' common ports. Review shared/SLUG.ufw.sh or nft output before apply;
apply uses SSH/sshpass or prints manual steps. Verify inside the disposable
guest: sudo ufw status numbered, sudo ufw status verbose, /var/log/ufw.log;
for nftables inspect its ruleset. Protect administrative access against lockout.
Optional block-alert integration is documented via ufw-logger; it is not an
always-running bundled external service. reset destroys the firewall VM disk.

Reference: firewall-lab/README.md, schema/README.md, companies/README.md,
templates/company/, knowledge/, vm/README.md.

## 10. Signed content, app updates, contribution and diagnostics

This computer → Content updates offers check/update/reset; hooks require explicit
selection every time. Data packs contain firewall company/catalog/schema/guides,
iOS knowledge and legal text. Hooks are executable Frida scripts. Console,
dashboard, installers and engine code ship in app/source updates, not data packs.
Ed25519 manifest and per-file hashes are checked before installation; signature,
path, size or downgrade failures stop the update. Keep bundled content usable
offline. OSLAB_CONTENT_DIR selects overlay storage; OSLAB_CONTENT_OFFLINE=1
disables downloads. Reset removes the overlay and returns to bundled content.
API: GET /api/content/status, /companies, /file?path=...;
POST /api/content/check, /update ({"hooks":true} only on opt-in), /reset.
`python3 console/content.py status|check|update|reset` gives the terminal
interface; add --hooks to update only on explicit selection.

Desktop/app updates have separate check/install actions and platform-specific
packages/updater signatures. Verify the selected release's signing status; an
updater signature does not imply Windows Authenticode. Do not fabricate a new
release version, signing approval or successful install. Application updates
preserve private state; back it up separately. Developer build requirements:
Node 22+, Rust 1.85+, platform Tauri prerequisites, suitable Python; in app/:
npm ci, npm run stage, npm run dev, npm run build, npm run test:stage,
then cargo test in app/src-tauri. Building/publishing is a maintainer operation;
never put signing credentials in an LLM prompt.

Read-only diagnostics from linux-lab/: scripts/bonus/env-doctor.sh checks names/
missing/empty/duplicate env keys without printing values; port-check.sh checks
loopback port availability; ssh-config-doctor.sh checks HostName/IdentityFile/
key permissions; shell-lint.sh checks syntax and optional ShellCheck advisories;
md-linkcheck.sh checks local Markdown targets; secret-scan.sh --staged reports
redacted credential-pattern matches. Exit codes: 0 clean, 1 finding, 2 usage/I/O
error. These helpers do not fix the host or establish service readiness.

Contribute via /contribute/, CONTRIBUTING.md, task reservations and documented
tests; Source bonus tasks remain distinct from course exam options. Feedback
offers issue/feature templates, discussions and private vulnerability reporting.
Never publish private reports or keys as reproduction evidence. Required change
checks depend on scope: scripts/run-tests.sh (Python suites, shell syntax, graph,
dashboard freshness), dashboard npm run check/test:i18n/build/test:e2e,
lat check after graph edits. Source tests run separately from Android tests;
portable acceptance.py tests five static analyzers without optional dependencies
but does not prove native GUI/live collection acceptance. Public Pages uses
scripts/deploy-page.sh and must be checked after its route filters, including
locale/base paths and absence of engine requests. Do not instruct a normal
operator to publish releases/deployments to accomplish unrelated lab work.

## 11. Troubleshooting, privacy, interpretation and safe completion

- KVM permission failure: inspect /dev/kvm, firmware virtualization/nested support,
  kvm group and refreshed login. Container failure: check engine running, Compose
  provider, docker group/authorization and available disk. Do not default to
  privileged containers or bypass access controls as a universal fix.
- Port conflict: inspect actual host listeners, choose unused ports in .env and
  recreate only the affected service. For remote hosts use approved SSH tunnels
  to loopback services; do not expose web/RDP/ADB/VNC/Appium/MobSF/proxy publicly.
- Guest stuck installing: inspect container logs, ISO/network/disk, guest setup
  and actual install marker; HTTP 200 alone is insufficient. macOS native failures
  need full Xcode, correct developer directory, available runtime/device and
  optional Appium driver. Simulator and physical-device support are different.
- Android failures: check ADB target/package/ABI, Java/JADX/MobSF status, proxy/CA
  trust and Frida version compatibility. Treat network captures, sandbox dumps,
  crypto traces and discovered secrets as sensitive private evidence.
- Source failures: confirm Python 3.11+, selected interpreter, private root
  permissions/free space, target availability and parsing/coverage limits.
  Optional Git/browser/grammar absence should not block static detection.
  Check job logs/conflicts; cancel through the owning console. After restart
  inspect interrupted output before retrying. Signature failure requires correct
  original key and intact bundle; never weaken verification to make a run pass.
- Map/Brain/Pipeline edges, heuristic indicators and recorded/synthetic telemetry
  are not proof of executed behavior. Report unsupported inputs, truncation,
  absent providers and unavailable native collectors honestly.
- Preserve originals and provenance; review exports, restore/rollback plans and
  destructive cleanup with the operator. Do not infer authorization from the
  existence of a URL, repo, binary or credential. Use only owned or explicitly
  authorized targets and compliant OS/tool licences in isolated labs.
- Clipboard sharing is explicit; this prompt contains the task and public static
  context only. It excludes actual credentials, .env contents, signing keys,
  personal paths, live host reports, private catalogs, snapshots and targets.
  Remove private information from the task before sharing with any LLM provider.

Legal references:
https://github.com/keyvanarasteh/os-lab/blob/master/docs/legal/TERMS.md
https://github.com/keyvanarasteh/os-lab/blob/master/docs/legal/ACCEPTABLE_USE.md
https://github.com/keyvanarasteh/os-lab/blob/master/docs/legal/PRIVACY.md
https://github.com/keyvanarasteh/os-lab/blob/master/docs/legal/THIRD_PARTY_NOTICES.md
