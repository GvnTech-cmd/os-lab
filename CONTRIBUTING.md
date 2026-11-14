# Contributing to os-lab

Thanks for your interest in contributing! os-lab builds isolated security labs
(Android, Windows, Linux and macOS/iOS) and a web console that drives them.
Contributions of all kinds are welcome: code, documentation, Frida hooks,
workflow recipes, translations and bug reports.

## Ground rules

- **Authorization only.** Everything here is for testing systems and apps you
  own or are authorized in writing to assess, inside isolated labs. Do not
  contribute content, artifacts or examples taken from systems you were not
  authorized to test. See the [Acceptable Use Policy](docs/legal/ACCEPTABLE_USE.md).
- **No third-party binaries or proprietary media.** Do not commit APKs you do
  not own, Windows or macOS images, Google's platform-tools or other vendor
  binaries. Download them at setup time from the vendor instead (see
  `android-lab/lab/scripts/get_platform_tools.py`).
- **Compatible licences only.** New dependencies must have a licence compatible
  with Apache-2.0 and must be added to the
  [Third-Party Notices](docs/legal/THIRD_PARTY_NOTICES.md).
- **No secrets or personal data** in code, tests, fixtures or screenshots.
- Changing Firewall Lab companies, guides or hooks? They ship to users as a signed content pack; see
  [Content updates](docs/CONTENT.md) for how, and for the optional proof (verification report, video) that speeds review.
- Be respectful: see the [Code of Conduct](CODE_OF_CONDUCT.md).
- Found a vulnerability in os-lab itself? Follow the [Security Policy](SECURITY.md);
  do **not** open a public issue.

## Step 1: Set up

You need git, Python 3.11 or newer and bash (Linux, macOS or WSL2). Node.js 22+
is only needed to work on the dashboard.

```bash
git clone https://github.com/<you>/os-lab   # your fork
cd os-lab
git remote add upstream https://github.com/keyvanarasteh/os-lab
./labctl ui                                  # the web console at http://127.0.0.1:5050
```

The one-command installers in [`scripts/setup/`](scripts/setup/README.md) also
set up a virtualenv and the dashboard.

## Step 2: Create a branch

```bash
git fetch upstream
git checkout -b feat/short-description upstream/master   # or fix/…, docs/…, chore/…
```

Keep each pull request to one logical change.

## Step 3: Make the change

| Area | Where | Notes |
|------|-------|-------|
| Android lab scripts | `android-lab/lab/scripts/` | Prefer the Python standard library; expose a `main()` and importable helpers |
| Frida hooks | `android-lab/lab/hooks/` | One concern per file, with a header comment saying what it bypasses or traces and how to load it |
| Web console API and lab engine | `android-lab/lab/web_ui.py`, `console/oslab.py` | Lab actions must stay typed and validated; never accept command strings from the page |
| Dashboard | `dashboard/src/` | Astro + React + Tailwind; run `npm run dev` with the console on port 5050 |
| VM labs | `win-lab/`, `linux-lab/`, `ios-lab/`, `labctl` | `bash` with `set -euo pipefail` |
| Windows lab script | `android-lab/lab/lab.ps1`, `scripts/setup/install.ps1` | Must parse in Windows PowerShell 5.1 and PowerShell 7; keep **UTF-8 with BOM** |
| Legal documents | `docs/legal/` | Shown in the dashboard at `/legal/`; every statement must match what the code does |

For the Android lab runbook see [`android-lab/lab/README.md`](android-lab/lab/README.md),
for Windows non-admin use [`android-lab/lab/README-WINDOWS.md`](android-lab/lab/README-WINDOWS.md),
and for iOS [`ios-lab/README.md`](ios-lab/README.md).

## Curated Contribution Roadmap & Priority TODOs

Looking for high-impact areas to contribute? The following curated tasks are classified across our three core domains: **Penetration Testing**, **Open Source Operating Systems**, and **Firewall Solutions**. They incorporate architectural patterns from our desktop runtime (local MCP hosting, capability discovery, single-instance execution, release profile tuning) and real-world security engineering instrumentation.

These tasks are also interactively browsable and filterable inside the dashboard under the **Contribute → Roadmap & TODOs** tab.

### Reserving a task

So two people don't build the same thing, **reserve a task before you start**. A reservation is just a
PR that adds one file, `reservations/<TASK-ID>.json` (one file per task, so reservations never conflict).
The easiest way is the **Reserve via PR** button on each task card, which opens a pre-filled PR for you;
by hand, copy the template in [`reservations/README.md`](reservations/README.md). The dashboard shows each
task as Available, Reserved, PR open or Done, and you keep your file's `status`/`pr` current as you go.
Course midterm reservations add a `course` (and an option number in `note`) — see the course's
`vize/vize-projesi.md`.

### 1. Penetration Testing (Pentesting)

| ID | Task | Scope & Reference | Priority / Effort |
|---|---|---|---|
| **PENT-01** | **Native Frida Instrumentation Module & Runtime Hook Suite** | Universal Interceptor skeleton (`onEnter`, `onLeave`, `retval.replace`), native test harness (`hedef.c`), and observation/modification scripts (`gozlem.js`, `degistir.js`). | **High** · Medium |
| **PENT-02** | **Automated Browser Extension Injection & Malicious Script Audit Engine** | Static and dynamic scanner for Manifest V3/V2 extensions; audits permissions (`all_urls`, `cookies`, `scripting`, `activeTab`, `nativeMessaging`) and AST/regex patterns for `eval`, `executeScript`, and two-stage dynamic payload delivery. | **High** · Medium |
| **PENT-03** | **Headless Android Analysis Pipeline & Objection SSL Pinning Bypass** | Containerized Alpine/Docker Android emulator runner; automated `frida-server` deployment, system CA installation for mitmproxy, and automated objection hooks for universal SSL pinning bypass. | **High** · Large |
| **PENT-04** | **Local MCP Security Tool Provider Host (Pattern D8/D9)** | Embedded Model Context Protocol (MCP) stdio JSON-RPC server exposing isolated security tools (Frida attachment, APK manifest inspector, socket audit) to autonomous AI agents. | **Medium** · Medium |
| **PENT-05** | **Binary Exploitation & Hardening Verification Harness** | Automated binary mitigation audit (`readelf` check for NX, ASLR/PIE, Stack Canaries, RELRO) and AFL++ crash triage smoke runner in `linux-lab/`. | **Medium** · Medium |
| **PENT-06** | **frida-trace Auto-Tracer & Call-Map Builder** | frida-trace wrapper discovering/tracing a lab process's functions into a JSON call map with per-call argument snapshots. (Teached 05.10) | **High** · Small |
| **PENT-07** | **Interceptor retval.replace & Argument-Tampering Script Library** | Policy-driven `onEnter`/`onLeave`/`retval.replace` runner against the deterministic lab auth harness (`hedef.c`), golden-file tested. (Teached 05.10) | **Medium** · Small |
| **PENT-08** | **Java/Obj-C Bridge Class Enumerator & Method Overrider** | Frida bridge class/method listing and selective override with before/after logging. | **Medium** · Medium · ⏳ Held: verified Android lab |
| **PENT-09** | **Frida Device & Process Inventory Tool** | Read-only `frida-ls-devices`/`frida-ps` (USB/TCP) inventory → JSON for the console and agents. (Teached 28.09/05.10) | **High** · Tiny–Small |
| **PENT-10** | **Electron App Unpacker & Injection-Point Mapper** | Static asar unpack + main/renderer/preload/nodeIntegration surface mapper, reproducing the lab Electron injection case. (Teached 28.09) | **Medium** · Small–Medium |
| **PENT-11** | **SSL/Certificate Pinning Detector & Classifier (Static)** | Classifies pinning method (OkHttp, TrustManager, Network Security Config, native) before any dynamic analysis, lab scope only. (Teached 28.09/26.10) | **High** · Small |
| **PENT-12** | **APK Static Triage: aapt Manifest, Permissions & Strings** | aapt-based manifest/permissions/strings extractor with risk scoring. | **Medium** · Small–Medium · ⏳ Held: verified Android lab |
| **PENT-13** | **mitmproxy Lab-Traffic Summarizer with Scope Guard** | Flow-dump summary of hosts/endpoints/tokens with a host-allowlist scope guard. | **Medium** · Small–Medium · ⏳ Held: verified Android lab |
| **PENT-14** | **Objection Runtime Toolkit Wrapper (Lab-Only)** | Curated objection actions (root/emulator checks, keystore/heap inspection) with per-step log and approval gate. | **Medium** · Medium · ⏳ Held: verified Android lab |
| **PENT-15** | **Two-Stage "Clean Dropper" Detection Harness** | Benign first-stage + local second-stage lab plus a detector for deferred remote-code fetch/eval — detection of the new-gen trojan model. (Teached 19.10) | **High** · Medium |
| **PENT-16** | **Browser-Extension Corpus Scanner & Injection Aggregator** | Batch audit over an extension directory, aggregating dangerous-call sites corpus-wide (the ~988-extension sweep). (Teached 19.10) | **High** · Medium |
| **PENT-17** | **Extension Exfiltration Endpoint & CSP Analyzer** | Extracts endpoints/fetch targets and CSP/declarativeNetRequest rules, flagging exfiltration and CSP weakenings. (Teached 19.10) | **Medium** · Small |
| **PENT-18** | **Extension Native-Messaging Host Risk Analyzer** | Audits nativeMessaging manifests/binaries, flagging browser→native privilege bridges. (Teached 19.10) | **Medium** · Small |
| **PENT-19** | **Analysis Session Brain-Map (lat.md) Generator** | Emits a lat.md knowledge graph of targets/findings/scripts so long investigations stay navigable. (Teached 19.10) | **Medium** · Small |
| **PENT-20** | **Pentest Session Scribe: Scoped, Logged, AI-Disclosed (Subagent)** | Holds the scope file, logs every step, discloses AI use, refuses out-of-scope targets; exports a signed report. (Teached 28.09) | **High** · Medium |
| **PENT-21** | **Authorization & Scope-Guard Library** | Shared `assert_in_scope()` that refuses non-lab hosts/packages/devices, enforcing the lab-only rule in code. (Teached 19.10/28.09) | **High** · Small |
| **PENT-22** | **AI-Use Disclosure & Analysis Report Generator** | Session log → markdown report with an AI-use appendix and reproducibility steps. (Teached 28.09) | **Medium** · Tiny–Small |
| **PENT-23** | **Windows No-Admin Lab Preflight (VT-x/Podman/VirtualBox/WSL)** | No-admin virtualization readiness check with remediation (reproduces 26.10 live issues). (Teached 26.10) | **High** · Small |
| **PENT-24** | **Docker-Based Android Emulator Provisioner** | One-command container emulator with adb + frida-server staged; smoke-tested. | **Medium** · Large · ⏳ Held: verified Android lab |
| **PENT-25** | **C2 Beacon Traffic Simulator & Blue-Team Detector (Lab)** | Tunable beacon generator (lab network only) + periodicity detector — detection, not operation. | **Medium** · Medium · ⏳ Held: C2 lecture (ders03, planned) |
| **PENT-26** | **Loader Behavior Telemetry Harness (Defensive, Lab)** | Instruments a lab loader to emit allocation/exec/syscall telemetry for detection study. | **Medium** · Medium · ⏳ Held: AV/EDR lecture (ders04, planned) |
| **PENT-27** | **Advanced Web Exploitation Lab Targets + Detection** | Dockerized vulnerable targets (SSRF→metadata, SSTI, deserialization, smuggling) with per-target detection/remediation. | **Medium** · Large · ⏳ Held: advanced-web lecture (ders05, planned) |
| **PENT-28** | **Binary Exploitation Teaching Harness with Mitigation Toggles** | Vulnerable lab binary built with toggleable NX/ASLR/PIE/canary/RELRO to show how each mitigation changes exploitability. | **Medium** · Medium · ⏳ Held: binary-exploitation lecture (ders06, planned) |
| **PENT-29** | **Linux Privilege-Escalation Audit Tool (GTFOBins/SUID/Caps)** | Read-only enumerator of SUID/caps/writable-PATH/GTFOBins → escalation paths for defenders to close. | **Medium** · Small–Medium · ⏳ Held: privesc lecture (ders08, planned) |
| **PENT-30** | **Windows Privilege-Escalation Audit (Token/UAC/Service)** | Audits unquoted service paths, weak ACLs, token/UAC posture; reports hardening actions. | **Medium** · Small–Medium · ⏳ Held: privesc lecture (ders08, planned) |
| **PENT-31** | **Isolated Wireless Lab: WPA2/WPA3 Handshake & PMKID Study** | Owned-lab-only handshake/PMKID analysis with a hard refusal for non-lab BSSIDs. | **Medium** · Medium · ⏳ Held: wireless lecture (ders09, planned) |
| **PENT-32** | **Pivoting & Tunneling Lab Topology + Detection** | Multi-subnet lab with SOCKS/chisel/ligolo exercises and a lateral-movement detector. | **Medium** · Medium · ⏳ Held: pivoting lecture (ders10, planned) |
| **PENT-33** | **Container & Kubernetes Security Auditor** | Privileged/mount/capability audit for containers and over-broad RBAC flags for k8s. | **Medium** · Medium · ⏳ Held: container/k8s lecture (ders11, planned) |
| **PENT-34** | **Fuzzing Harness: AFL++/libFuzzer Coverage & Crash Triage** | Campaign orchestration with coverage and dedup/minimized crash triage, extending PENT-05. | **Medium** · Medium · ⏳ Held: fuzzing lecture (ders12, planned) |
| **PENT-35** | **Red-Team Report & MITRE ATT&CK Mapping Generator** | Session log → ATT&CK-mapped professional report (md + PDF). | **Medium** · Medium · ⏳ Held: red-team reporting lecture (ders13, planned) |

### 2. Open Source Operating Systems

| ID | Task | Scope & Reference | Priority / Effort |
|---|---|---|---|
| **OS-01** | **Automated Linux & Ubuntu Server Lab Provisioning with Systemd Lifecycle Engine** | Cloud-init unattended server deployment (Ubuntu Server / Alpine); hardened systemd service templates (`ProtectSystem=strict`, `PrivateTmp=true`, `Type=notify`) with automated watchdog timers and journal logging. | **High** · Medium |
| **OS-02** | **Remote-SSH Fleet Orchestration & Zero-Config Key Distribution** | Remote-SSH manager automating ed25519 key generation, dynamic IP discovery across virtualization bridges/NAT, and `~/.ssh/config` formatting with ProxyCommand and Cloudflare Access support. | **High** · Medium |
| **OS-03** | **Host Hardware & Installed Software Capability Detection Engine (Pattern D6)** | Cross-platform capability scanner querying package managers (`apt`, `dpkg`), toolchain versions (`git`, `node`, `uv`, `python3`), hypervisor capabilities (`/dev/kvm`, `VT-x/AMD-V`, `WSL2`), feeding the dashboard host view and client registry without external telemetry. | **High** · Small–Medium |
| **OS-04** | **Automated Auth Log Audit & Brute-Force Extraction Daemon** | Lightweight event-driven systemd service parsing `/var/log/auth.log` or SSH journal logs; extracts failed brute-force attacks, attacker IPs, and unauthorized `sudo` attempts into structured SQLite/JSON for dashboard analytics. | **Medium** · Small |
| **OS-05** | **Release Profile Tuning & Single-Instance Process Enforcement (Pattern D1/D5)** | Compiler profile optimization (`lto = true`, `codegen-units = 1`, `opt-level = "s"`, `panic = "abort"`, binary stripping) and single-instance socket/lockfile enforcement preventing redundant process execution. | **Medium** · Tiny–Small |
| **OS-06** | **Reproducible Ubuntu Server VM Installer & Snapshot Automation** | Repeatable VirtualBox Ubuntu Server build (OpenSSH, bridged) with a labeled post-install snapshot and SSH-reachable verification. (Teached 28.09/26.10) | **High** · Small–Medium |
| **OS-07** | **Lab Environment Selector: WSL vs VirtualBox** | Detects Windows constraints, recommends WSL2 or VirtualBox and runs the matching bootstrap (constrained lab PCs). (Teached 21.09) | **Medium** · Small |
| **OS-08** | **Distro Comparison & Selector (Ubuntu/Debian/Kali/Alpine)** | Structured distro dataset + recommender and comparison-table generator. (Teached 28.09) | **Medium** · Tiny–Small |
| **OS-09** | **Open-Source License Classifier (GPL/MIT/Apache)** | License/SPDX scan classifying copyleft vs permissive, flagging mixed/missing licenses. (Teached 28.09) | **Medium** · Small |
| **OS-10** | **Linux Filesystem Hierarchy Explorer & Teaching Map** | Annotated walk of `/`, `/home`, `/etc`, `/opt`, `/root` with hidden-file explanation. (Teached 28.09) | **Medium** · Tiny–Small |
| **OS-11** | **Guided Shell-Basics Practice & Auto-Grader** | Validates the week-3 `ali/eda/aleyna` directory/file exercise with per-path feedback. (Teached 05.10) | **High** · Small |
| **OS-12** | **Directory-Structure Scaffolder (mkdir -p Templates)** | Generates nested trees from a template spec with a dry-run preview. (Teached 05.10) | **Medium** · Tiny–Small |
| **OS-13** | **apt update/upgrade Safe Wrapper (Order + Dry-Run)** | Enforces update-before-upgrade order with dry-run and a guard when update fails. (Teached 05.10/19.10) | **High** · Small |
| **OS-14** | **Node.js & Python Toolchain Installer with Version Check** | apt vs NodeSource choice, version verification and `python-is-python3` setup. (Teached 19.10/26.10) | **Medium** · Small |
| **OS-15** | **Disk Reclamation Helper (node_modules / Rust target / apt clean)** | Scans + dry-run + approved cleanup with reclaimed-size report (in-class disk-full recovery). (Teached 26.10) | **Medium** · Small |
| **OS-16** | **Server First-Look Health Report** | `uname`/`lsb_release`/`inxi`/`free`/`df`/`systemctl` → JSON + readable report with arch note. (Teached 19.10) | **High** · Small |
| **OS-17** | **SSH Connection Troubleshooter** | Classifies timeout, wrong password, `127.0.1.1`, school-firewall block and wrong adapter, with fixes. (Teached 12.10) | **High** · Small |
| **OS-18** | **Dynamic Lab IP Finder via ARP + Auto-SSH** | Cross-platform rewrite of the PowerShell idea: boot-wait → ARP IP discovery → SSH → info collection. (Teached 19.10) | **Medium** · Small |
| **OS-19** | **SSH Port-Relocation Hardening Helper** | Moves sshd off 22, updates `sshd_config` + ufw together, verifies the new port before closing the old. (Teached 12.10) | **Medium** · Small |
| **OS-20** | **VS Code Remote-SSH Host Registration & Bootstrap** | Registers/validates a Remote-SSH host and remote server bootstrap (green-indicator state). (Teached 19.10/26.10) | **Medium** · Small |
| **OS-21** | **Boot-Time Python Service Starter (systemd)** | Minimal enabled-at-boot `.service` + looping `loop.py` with enable/status/journal verification (week-6 homework). (Teached 26.10) | **High** · Small |
| **OS-22** | **apt Repair Assistant: Clock/Timezone & Broken Sources** | Diagnoses wrong clock/timezone, held packages and broken sources; approval-gated apply (timezone → Istanbul). (Teached 26.10) | **High** · Small |
| **OS-23** | **dpkg Package Inventory & File Reverse-Lookup** | `dpkg -l/-L/-S` wrappers with a path→owning-package reverse lookup. (Teached ders05) | **Medium** · Small |
| **OS-24** | **Local .deb Installer with Dependency Resolution** | `apt install ./x.deb` with a dependency preview and post-install verification. (Teached ders05) | **Medium** · Tiny–Small |
| **OS-25** | **apt Sources Manager & Validator (sources.list.d)** | List/add/validate sources (modern `.sources`) with GPG key + reachability checks. (Teached ders05) | **Medium** · Small |
| **OS-26** | **File Permission & Ownership Auditor** | Scans for world-writable files, over-permissive modes and ownership drift with suggested fixes. (Teached ders03) | **Medium** · Small |
| **OS-27** | **Permission-Fix Advisor with 644/755/600 Presets** | Preset-based `chmod` with preview and approval, explaining each preset. (Teached ders03) | **Medium** · Tiny–Small |
| **OS-28** | **File Search & Text-Grep Teaching Wrapper** | Builds correct `find`/`grep` commands (with wildcards) from a query and explains what ran. (Teached ders02) | **Medium** · Tiny–Small |
| **OS-29** | **Server Log Viewer Helper (less/head/tail/wc)** | head/tail/follow/count modes over a log path, safe on large/rotating files. (Teached ders02) | **Medium** · Tiny–Small |
| **OS-30** | **Ubuntu Server Hardening Checker/Applier** | SSH/users/updates/ufw baseline audit with approval-gated apply (hardened-from-scratch candidate). (Teached vize adayı) | **High** · Small–Medium |
| **OS-31** | **journald Structured Logging & Log-Rotation Setup** | Persistent journald + size limits + logrotate profile for lab services, with rotation verification. (Teached 26.10/05.10) | **Medium** · Small |
| **OS-32** | **Service Inventory & Health Report (systemctl)** | Read-only units inventory with active/enabled state and failed/flapping highlights. (Teached 12.10/26.10) | **Medium** · Small |
| **OS-33** | **VirtualBox Snapshot/Restore Automation** | `VBoxManage` snapshot take/list/restore with an optional pre-change auto-snapshot hook. (Teached ders02) | **Medium** · Tiny–Small |
| **OS-34** | **Bridged vs NAT Network Adapter Configurator & Checker** | Reads/sets adapter mode and verifies a reachable LAN IP (root cause of SSH failures). (Teached 12.10) | **Medium** · Small |
| **OS-35** | **Browser-Extension Injection Detector (Static)** | `sha256sum`/`unzip`/`jq`/`rg` pipeline → H1–H5 clue report, detector/evidence/risk-rule kept distinct. (Teached ders06) | **Medium** · Small |
| **OS-36** | **Classroom Server Reachability Checker (ping + SSH sweep)** | Sweeps the class subnet (e.g. `10.25.130.x`), reporting up/down and optional local roster mapping. (Teached 26.10) | **Medium** · Tiny–Small |
| **OS-37** | **DNS Resolver Inventory & Health Check** | `resolvectl`/`resolv.conf`/stub (`127.0.0.53`) + per-interface DNS → report; flags the no-usable-resolver fault (Wi-Fi vs cable). (Teached 02.11) | **High** · Small |
| **OS-38** | **Multi-Resolver nslookup/dig Comparator** | Queries a name against campus / `8.8.8.8` / `1.1.1.1`, compares answers and latency over N tries → report (the 02.11 homework). (Teached 02.11) | **High** · Small |
| **OS-39** | **netplan DNS Configurator (approval-gated)** | Persistent DNS via `/etc/netplan/*.yaml` with a shown diff, `netplan try`/apply and a verify query; static vs DHCP. (Teached 02.11) | **Medium** · Small |
| **OS-40** | **Wi-Fi / Interface DNS Troubleshooter** | Reproduces the 02.11 fault (DHCP `ignore-auto-dns`, empty resolver on Wi-Fi) and offers the `nmcli` fix; cache + AP/router/switch primer. (Teached 02.11) | **High** · Small |

#### Bonus — shipped reference tools (not reservable)

These are already implemented and merged under
[`linux-lab/scripts/bonus/`](linux-lab/scripts/bonus/). They close recurring
gaps that are not covered by OS-01…OS-40 and are **not** vize tasks — reserve an
`OS-…` row above instead. Read them as worked examples of the lab's script style:
read-only, `set -euo pipefail`, clear exit codes (`0` clean / `1` problem /
`2` usage), portable between macOS and Linux, no external tools required.

| ID | Tool | What it does |
|---|---|---|
| **OS-B1** | `env-doctor.sh` | Validates a lab `.env` against its `.env.example` — missing keys, empty values, unknown/extra keys, duplicates (`--json` for CI). Nothing today checks a copied `.env` for drift. |
| **OS-B2** | `port-check.sh` | Reports whether the lab's `WEB_PORT`/`SSH_PORT` (or ports you pass) are free on `127.0.0.1` via bash `/dev/tcp`, catching the "port already allocated" start failure before `make up`. |
| **OS-B3** | `ssh-config-doctor.sh` | Summarises each `~/.ssh/config` Host block and flags a missing `HostName`, an absent `IdentityFile`, or a key with group/other-readable permissions that `ssh` silently ignores. |
| **OS-B4** | `shell-lint.sh` | `bash -n` (the repo's required gate) over the `*.sh` you touched, plus `shellcheck` advisories when installed — a scoped pre-PR check instead of the whole-repo `run-tests.sh`. |
| **OS-B5** | `md-linkcheck.sh` | Verifies local (non-http) Markdown links resolve on disk, so a typo'd path in `VERIFY.md`/`REPORT.md`/docs is caught before it becomes a dead link. |
| **OS-B6** | `secret-scan.sh` | Scans for known credential signatures (PEM/OpenSSH keys, AWS/GitHub/Slack/Google tokens) and reports `file:line` + rule with the value **redacted**; `--staged` for a pre-commit check. Complements the release scripts' tracked-key guard. |

### 2b. Cleanup Lab (CLN)

A disk-cleanup lab that ports [Qleaner](https://github.com/keyvanarasteh/Qleaner)'s scan detections,
detection signatures and clean techniques into os-lab. Only the behaviour is ported: pages follow the
os-lab dashboard and [`docs/UX_READINESS.md`](docs/UX_READINESS.md), and Qleaner's known bugs must not be
copied. Contract, safety rules, the port map and the bug list: [`cleanup-lab/README.md`](cleanup-lab/README.md).
Course note: **MYO063** students can take these tasks as a bonus (`"course": "MYO063"` in the reservation); at most **2 merged PRs per student**, so reserve at most two CLN tasks at a time.

| ID | Task | Priority / Effort |
|---|---|---|
| **CLN-01** | Cleanup Lab skeleton: engine, labctl, readiness and /cleanup/ page | **High** · Small–Medium |
| **CLN-02** | Detector catalog format, loader and Qleaner parity test | **High** · Medium |
| **CLN-03** | Scan job: bounded-parallel size scan with progress and cancel | **High** · Medium |
| **CLN-04** | Detections: system caches, logs, temp, crash reports, fonts, Spotlight, Trash | **High** · Small–Medium |
| **CLN-05** | Detections: browser caches and privacy data, every profile | **High** · Small–Medium |
| **CLN-06** | Detections: developer tool and package-manager caches | **High** · Medium |
| **CLN-07** | Detections: deep project sweep (node_modules, Rust target), Xcode DerivedData, simulators | **Medium** · Small–Medium |
| **CLN-08** | Detections: containers and VM images | **Medium** · Small |
| **CLN-09** | Detection signatures: macOS app leftovers | **High** · Medium |
| **CLN-10** | Detection signatures: Linux and Windows app leftovers | **Medium** · Medium |
| **CLN-11** | Detections: package orphans (Homebrew leaves, global pip, gems) | **Medium** · Small |
| **CLN-12** | Safety guard: canonical paths, allowed roots, ownership, running apps | **High** · Small–Medium |
| **CLN-13** | Plan → confirm → clean, Trash by default, honest results | **High** · Medium |
| **CLN-14** | Secure shred technique, done honestly | **Medium** · Small–Medium |
| **CLN-15** | Audit history with a real integrity signature | **Medium** · Small |
| **CLN-16** | Cleanup pages: scan, results, leftovers (os-lab UX) | **High** · Medium |
| **CLN-17** | Ignore rules, enforced by the engine | **Medium** · Small |
| **CLN-18** | Schedules: scheduled dry-run scans | **Medium** · Small–Medium |
| **CLN-19** | Headless CLI parity: labctl cleanup scan / plan / clean --json | **Medium** · Small |
| **CLN-20** | Privileged targets and disk-access check | **Medium** · Small–Medium |
| **CLN-21** | Native scan backend: wire qrust-scan into the desktop app | **High** · Medium |
| **CLN-22** | Harden qrust-scan: nested .gitignore, iterative glob, verified candidates | **High** · Small–Medium |
| **CLN-23** | Disk Explorer page: read-only size tree, hotspots and seek | **Medium** · Medium |
| **CLN-24** | Project artifact signatures proved by marker files | **High** · Small–Medium |
| **CLN-25** | Tool-reported cache locations: environment, then the tool, then the default | **High** · Small |
| **CLN-26** | Learning loop: cleaned-items ledger, soft pre-selection, Quick Clean | **Medium** · Medium |
| **CLN-27** | Relocate caches to another volume behind a symlink | **Medium** · Medium |
| **CLN-28** | Volumes overview and disk-pressure card | **Medium** · Small |
| **CLN-29** | Simulator and emulator runtimes: list, size, remove | **Medium** · Small–Medium |

CLN-21 … CLN-29 start from working, tested reference code in [`cleanup-lab/reference/`](cleanup-lab/reference/README.md)
(the `qrust-scan` Rust crate and the `cleanup_ref` Python modules). Adapt it to the contract; do not bypass the safety guard.

### 3. Firewall Solutions

| ID | Task | Scope & Reference | Priority / Effort |
|---|---|---|---|
| **FW-01** | **UFW Automation Engine & Priority-Aware Rule Optimizer** | Programmatic UFW orchestrator managing default policies (`default deny incoming`, `default allow outgoing`) and rule ordering; optimizes rule sequence by placing high-frequency traffic rules ahead of broad matchers; handles `deny` vs `reject` semantics. | **High** · Medium |
| **FW-02** | **Real-Time Firewall Log Streaming & Telegram Alert Daemon with Loop Suppression** | Daemon tailing `/var/log/ufw.log` with instant alert dispatches; includes intelligent noise reduction and loop-prevention filters suppressing outbound ALLOW logs and port 53 DNS loops to avoid notification storms. | **High** · Medium |
| **FW-03** | **Automated Firewall Security Audit Engine & Systemd Timer** | Continuous compliance checker on systemd timer (`ufw-audit.timer`); audits active rules against RFC 1918 private subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), flags insecure exposed management ports, and validates DMZ boundaries. | **High** · Small–Medium |
| **FW-04** | **Layer 7 WAF Integration & Application Threat Defense** | Ready-to-deploy L7 WAF recipes (ModSecurity / OWASP Core Rule Set / Nginx reverse proxy) illustrating defense-in-depth where L3/L4 packet filters cannot inspect payloads (e.g., PHP memory exhaustion RCE, request smuggling). | **Medium** · Medium |
| **FW-05** | **Multi-Branch Enterprise Network Segmentation & Open Source Appliance Benchmarks** | Realistic multi-branch topology templates (HQ, Branch, DMZ, Dev LAN) with CIDR allocations (/24, /17) and VLAN tagging; automated performance benchmarks comparing throughput and latency across pfSense, OPNsense, IPFire, and native UFW/nftables. | **Medium** · Large |
| **FW-06** | **Zero-Trust Role-Based VPN Gateway vs Direct SSH Ingress** | WireGuard mesh gateway eliminating public SSH port exposure; provides automated key provisioning and role-based subnet routing per authenticated client profile. | **Medium** · Medium |
| **FW-07** | **UFW Application Profiles Manager** | List/create/apply `/etc/ufw/applications.d` profiles with port+protocol validation. (Teached 09.10) | **Medium** · Small |
| **FW-08** | **before.rules ICMP Policy & hashlimit Rate-Limit Generator** | Validated ICMP + hashlimit fragments; rejects the known-invalid `ufw route … limit in rate` / `ufw append` forms. (Teached ders02) | **Medium** · Small–Medium |
| **FW-09** | **nmap-Based Firewall Rule Verification Harness** | Scans srv from cli and diffs observed open/filtered/closed against the intended policy. (Teached ders02/09.10) | **High** · Small |
| **FW-10** | **Stateful vs Stateless Rule Explainer & Validator** | Classifies behavior, explains established/related and flags state assumptions. (Teached 25.09) | **Medium** · Tiny–Small |
| **FW-11** | **UFW Enable Safety Guard (SSH-Before-Enable)** | Refuses `ufw enable` unless an allow rule for the current SSH session exists. (Teached ders03) | **High** · Tiny–Small |
| **FW-12** | **UFW Log-Level Configurator & [UFW BLOCK] Parser** | Sets off/low/medium/high/full levels and parses block lines into structured events. (Teached ders02) | **Medium** · Small |
| **FW-13** | **Service Port Exposure Limiter (MySQL 3306 → App Subnet)** | `allow from <subnet> to <port>` generator with a reachability check; refuses exposing DB/mgmt ports to `0.0.0.0/0`. (Teached 09.10) | **Medium** · Small |
| **FW-14** | **Serverless UFW Alert via Cloudflare Workers** | Worker receiving block events + a server-side poster sending only blocks. (Teached 09.10) | **Medium** · Small |
| **FW-15** | **Rule-Order Simulator & Latency Estimator Under Load** | First-match simulator with per-rule hit cost and a reorder suggestion for heavy/DDoS traffic. (Teached 09.10) | **Medium** · Small–Medium |
| **FW-16** | **Duplicate & Shadowed Rule Detector (status numbered)** | Flags shadowed/duplicate/over-broad/mis-ordered rules with a corrected-order suggestion. (Teached 09.10) | **High** · Small |
| **FW-17** | **UFW Log Analyzer: Top Blocked Sources, Ports & Scan Detection** | Aggregates blocked src/port, detects port-scan patterns, time-bucketed JSON for the dashboard. (Teached ders02/09.10) | **High** · Small |
| **FW-18** | **Reject-vs-Deny Scanner-Exposure Tester** | Applies both, scans and tabulates scanner-visible differences (silent drop vs ICMP unreachable). (Teached 09.10) | **Medium** · Small |
| **FW-19** | **Notification-Storm Regression Harness (Loop Suppression)** | Feeds synthetic `ufw.log` and asserts outbound ALLOW + 53/udp suppression and dedupe/rate-limit — regression test for FW-02. (Teached 09.10) | **High** · Small |
| **FW-20** | **Subnet & Bandwidth Planner (Users × Services → CIDR + Estimate)** | Counts + service mix → CIDR allocation and per-branch bandwidth estimate; explains /24 vs /17. (Teached 23.10) | **High** · Medium |
| **FW-21** | **Multi-Branch Company Repo Scaffolder (HQ/Branch/Academic/DMZ)** | Generates the week-5 homework folder skeleton with per-branch count/bandwidth/product/rule stubs. (Teached 23.10) | **Medium** · Small |
| **FW-22** | **VLAN Segmentation Rule-Set Generator** | Per-VLAN rules (staff/student/R&D/software) with an inter-VLAN default-deny matrix. (Teached 23.10) | **Medium** · Medium |
| **FW-23** | **DMZ Boundary Policy Generator & Validator** | DMZ↔internal/internet rules with reachability validation flagging internal leaks. (Teached 25.09/23.10) | **Medium** · Small |
| **FW-24** | **Base-Service Rule Templates (NTP 123, DHCP 67/68)** | Essential infra rules with lockout-prevention warnings (don't kill DHCP). (Teached 23.10) | **Medium** · Tiny–Small |
| **FW-25** | **Private-IP (RFC 1918) Range Validator** | Flags accidental public-range allows in internal rules (10./172./192.). (Teached 09.10) | **Medium** · Tiny–Small |
| **FW-26** | **Firewall Product Comparison & Segment Selector** | Top-5 per segment (FortiGate/pfSense/OPNsense/Sophos/local) with bandwidth fit and real-license vs trial notes. (Teached 23.10) | **Medium** · Medium |
| **FW-27** | **pfSense/OPNsense Rule Export & Cross-Translation from UFW** | UFW ↔ pfSense/OPNsense rule mapping with a non-translatable diff report. | **Medium** · Medium · ⏳ Held: pfSense/OPNsense appliance lab |
| **FW-28** | **Attack-Surface Analyzer: VPN vs Exposed-Port Posture** | Enumerates exposed services and scores the reduction from moving access behind a role-based VPN. (Teached 23.10) | **Medium** · Small |
| **FW-29** | **Firewall Monitoring Plan Generator (Human + Systematic)** | Alert routing, ownership, human/auto split and application- vs security-monitoring separation. (Teached 23.10) | **Medium** · Small |
| **FW-30** | **Branch Firewall Generator from Company Spec (Why-Per-Rule)** | Spec → UFW/nftables rule set with a per-rule rationale and an approval gate before apply. | **Medium** · Large · ⏳ Held: rule-set lecture (BGT207, planned) |
| **FW-31** | **UFW → nftables Equivalent Generator** | Emits the nft ruleset equivalent to a UFW policy, verified to produce the same scan result. (Teached 23.10/09.10) | **Medium** · Small–Medium |
| **FW-32** | **Vulnerable-PHP Lab + Virtual-Patch Verification (ModSecurity)** | Lab PHP target plus a check that a ModSecurity/CRS virtual patch blocks the exploit while the upgrade is pending. | **Medium** · Medium · ⏳ Held: ModSecurity/WAF lecture (BGT207, planned) |
| **FW-33** | **L3/L4 vs L7 Demonstration** | Side-by-side lab showing an app-layer attack passing UFW-only but caught by an L7 WAF (regex/CDN can't see it). | **Medium** · Small–Medium · ⏳ Held: WAF lecture (BGT207, planned) |
| **FW-34** | **CVE/Advisory Watcher with Version-Affected Check** | Advisory feed + installed-version affected check per service (weekly-advisory extra credit). (Teached 23.10) | **Medium** · Small |
| **FW-35** | **Patch vs Mitigation Decision Assistant** | Separates a temporary mitigation from the real fix (apt upgrade) into an ordered action plan. (Teached 23.10) | **Medium** · Tiny–Small |
| **FW-36** | **Trusted apt Source Adder & Verifier** | Adds a vetted repo with GPG verification + apt pinning when the distro lags; refuses unsigned sources. (Teached 23.10) | **Medium** · Small |
| **FW-37** | **KVKK/Cookie/Privacy-Text Compliance Checker** | Checks allowlisted pages for required KVKK/cookie/privacy notices, flagging missing/stale policies. (Teached 23.10) | **Medium** · Small |
| **FW-38** | **"Explain-Your-Rule" Audit (Unexplained Rule = Vulnerability)** | Requires a one-line justification per rule and blocks sign-off until every rule has a rationale. (Teached 23.10) | **Medium** · Small |

### Source Lab bonus contributions — open

The owner deferred the following remaining verification and related patches to
bonus contributions. They are reservable in **Contribute → Roadmap & TODOs** as
`SRC-B01`–`SRC-B06`; they are not course exam options or claims of completed
native/live acceptance. Follow [the runbook](source-lab/RUNBOOK.md), record
sanitized evidence in [VALIDATION.md](source-lab/VALIDATION.md), and include any
required fixes with the verification. Release signatures remain mandatory.

| Task | Priority | Required result |
|---|---|---|
| SRC-B01 — Native install/update | High | Fresh packaged and minimal macOS/Windows install, restart/update with existing private state, Python 3.11+ readiness, five-platform portable acceptance fingerprint and Source UI/report smoke; parse Windows installer with PowerShell 5.1 and 7. |
| SRC-B02 — Live browser | High | Owned canary target, real Playwright/Chromium, signed non-synthetic session, deliberate tamper rejection, profile/process cleanup and documented optional-tool fallback. |
| SRC-B03 — Native telemetry | Medium | Authorized Windows/macOS/Android/iOS collection recipes feeding the four retained importer libraries, host/tool provenance, integrity checks and no fabricated live proof. |
| SRC-B04 — Snapshot generation | Medium | Reproducible Brain/Pipeline generation from owned source, revisions/dates/provider validation and absent-provider tests; no database, Skills or OpenAPI integration. |
| SRC-B05 — Native lifecycle/path checks | High | Cancellation/timeout/restart, cross-process locks, CRLF sessions, symlink/junction/reparse-point refusal and private-key behavior on actual native hosts; patch failures. |
| SRC-B06 — Large workspace browsing | Medium | Bounded pagination/summary-only reads beyond current target/session/aggregate limits, clear partial coverage and measured owned-fixture UI/API performance. |

Further merger UI is skipped by owner. Research-only collection and remote
hosting proposals remain separate upstream follow-ups, not hidden release
requirements or implemented capabilities. See [scope audit](source-lab/AUDIT.md).

## Step 4: Add tests

Add or update tests in `android-lab/lab/tests/` for any change in behaviour.
Tests run offline: mock network calls and never download from the internet.

## Step 5: Run the checks

GitHub Actions is disabled for this repository; the local runner replaces CI.
Run it before every pull request:

```bash
./scripts/run-tests.sh          # everything
./scripts/run-tests.sh --quick  # unit tests only
```

It runs the pytest suite, a sample-analysis smoke test, `bash -n` on every
shell script, `lat check` when `lat` is installed, and, when
`dashboard/node_modules` exists, the dashboard typecheck plus a check that the
committed build is current.

## Step 6: Rebuild the dashboard if you changed it

`dashboard/dist/` is committed so hosts without Node.js still get the
dashboard. After changing anything in `dashboard/src/` or `docs/legal/`:

```bash
cd dashboard
npm ci
npm run check
npm run build      # refreshes dashboard/dist; commit it with your change
```

## Step 7: Update the docs and the knowledge graph

- Update the README of the area you changed.
- If you changed architecture, behaviour or tests, update the knowledge graph in
  [`lat.md/`](lat.md/) (what the project does and why, not a changelog) and run
  `lat check`.
- If you changed what data is stored or sent, or added a dependency, update
  [`docs/legal/`](docs/legal/).

## Step 8: Commit and open a pull request

1. Commit with [Conventional Commits](https://www.conventionalcommits.org/),
   for example `fix(android): …`, `feat(dashboard): …`, `docs: …`.
2. Push to your fork and open a pull request against `master`.
3. Fill in the [pull request template](.github/PULL_REQUEST_TEMPLATE.md),
   including how you tested the change.
4. Respond to review comments; maintainers merge once the checks pass and the
   review is done.

## Reporting bugs and requesting features

Use the [issue templates](.github/ISSUE_TEMPLATE/). For open-ended questions,
open a [Discussion](https://github.com/keyvanarasteh/os-lab/discussions).

## Licence

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE), the licence that covers this project.
