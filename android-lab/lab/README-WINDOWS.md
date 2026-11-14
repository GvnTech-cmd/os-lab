# 🪟 Windows Non-Admin Lab Runbook

This guide covers running the **Agentic Mobile Security Lab** on **Windows 10/11 without Administrator privileges** using **PowerShell**, **VirtualBox**, **Podman**, or the **Native Userland Engine**.

---

## ⚡ Quick Start (Zero-Admin PowerShell)

Open a standard (unprivileged) PowerShell prompt:

```powershell
cd lab

# 1. Run Pre-flight verification (checks OS, VBox, Podman, Python, Java, ports, disk)
.\lab.ps1 preflight

# 2. Bootstrap userland environment (creates .venv, installs Frida, mitmproxy, fetches tools)
.\lab.ps1 setup

# 3. Execute WF1 Static Analysis on an APK (decompilation + manifest security report)
.\lab.ps1 wf1 -Apk path\to\app.apk

# 4. Execute WF2 Dynamic Analysis (ADB connect, install, mitmproxy capture, launch)
.\lab.ps1 wf2 -Apk path\to\app.apk -Pkg com.example.app

# 5. Inject a Frida hook
.\lab.ps1 hook -Pkg com.example.app -Hook hooks\ssl-pinning-bypass.js

# 6. Aggregate report and telemetry
.\lab.ps1 report
```

---

## 🏗️ Supported Operating Models (Choose Your Path)

| Model | Setup & Execution | When to Use | Admin Needed? |
|---|---|---|---|
| **Model 1: Native Userland (Default)** | Python `.venv` + Portable ADB + Portable JADX | Any Windows host, especially if VT-x is disabled in BIOS | ❌ **No (Zero-Admin)** |
| **Model 2: VirtualBox Headless VM** | `.\lab.ps1 vbox-create` & `.\lab.ps1 vbox-start` | Full Android-x86 or Ubuntu guest with port forwarding | ❌ **No (Zero-Admin)** |
| **Model 3: Podman Container Stack** | `podman compose -f docker-compose.win.yml up -d` | Running MobSF & RE tools via rootless Podman | ❌ **No (Zero-Admin)** |

---

## 📋 PowerShell Command Reference (`lab.ps1`)

| Command | Arguments | Description |
|---|---|---|
| `preflight` | — | Validates system environment, non-admin status, and prerequisites |
| `win-preflight` | `[-Json]` | **Virtualization readiness (PENT-23)**: VT-x/AMD-V, Hyper-V/VBS, VirtualBox, WSL2, Podman, execution policy, RAM, disk; every finding has a fix marked admin / no-admin and the usable lab model is recommended |
| `setup` | — | Initializes `.venv`, installs dependencies, and downloads portable tools |
| `vbox-create` | `[-VmName <name>] [-Memory <mb>] [-Cpus <n>] [-Iso <path>]` | Provisions VirtualBox VM with SATA storage, dynamic VDI, nested VT-x, and NAT forwardings |
| `vbox-download-iso` | `[-Distro <alpine\|ubuntu>]` | Downloads minimal Linux ISO (Alpine: ~219MB, Ubuntu: ~2.1GB) & mounts to VM DVD drive |
| `vbox-start` | `[-VmName <name>] [-Gui]` | Boots the VirtualBox VM in headless background mode (or with desktop GUI via `-Gui`) |
| `vbox-autoinstall` | `[-VmName <name>] [-Gui]` | **Fully Automated Installer**: Unattended Alpine installation to disk, ISO ejection, and Docker provisioning |
| `vbox-stop` | `[-VmName <name>]` | Gracefully shuts down the VirtualBox VM |
| `vbox-status` | — | Lists all registered and running VirtualBox VMs |
| `podman-status`| — | Checks Podman CLI and connection endpoints |
| `wf1` | `-Apk <path>` | **WF1 Static Analysis**: Full static pipeline (JADX + Manifest + Analyzer + HTML Report) |
| `wf2` | `-Apk <path> [-Pkg <pkg>]` | **WF2 Dynamic Analysis**: ADB connection, APK installation, mitmproxy, launch |
| `analyze-app` | `-Apk <path>` | **Comprehensive App Analyzer**: OWASP Mobile Top 10 audit, crypto, WebView, permissions |
| `generate-report`| `-Apk <path>` | **Multi-Format Reporter**: Generates standalone interactive HTML5 dashboard, MD, and JSON |
| `agentic-plan`| `-Apk <path>` | **Autonomous Agent**: Synthesizes threat models, attack hypotheses & tailored Frida hooks |
| `fuzz-ipc`    | `-Pkg <pkg>` | **IPC Fuzzer**: Probes exported Activities, Providers with boundaries & SQLi payloads |
| `patch-apk`   | `-Apk <path> [-Gadget]` | **APK Patcher**: Injects permissive network config & Frida Gadget for non-root testing |
| `scan-secrets`| `-Apk <path>` | **Deep Secret Scanner**: Scans APK/sources for Google, AWS, JWT, API tokens |
| `ui`          | `[-Port <n>]` | **Interactive Web GUI**: Launches live web console on `http://127.0.0.1:5050` |
| `hook` | `-Pkg <pkg> -Hook <path>` | Injects runtime Frida script into target app package |
| `trace-crypto`| `-Pkg <pkg>` | **Crypto Tracer**: Intercepts AES/RSA keys, IVs, plaintexts/ciphertexts, HMACs |
| `monitor` | `[-Pkg <pkg>] [-Filter <pat>]` | **Live Logcat Security Monitor**: Real-time token leak & URL detection |
| `telemetry` | `-Pkg <pkg>` | **Device Telemetry**: Captures memory footprint (PSS, heaps), sockets, battery |
| `dump-sandbox`| `-Pkg <pkg>` | **Sandbox Auditor**: Extracts SharedPreferences XML and SQLite databases |
| `parse-flows` | `[-FlowFile <path>]` | **Traffic Auditor**: Analyzes mitmproxy flows for cleartext HTTP & auth headers |
| `report` | — | Sweeps logcat, mitm flows, and findings into `artifacts/report-<timestamp>/` |
| `clean` | — | Wipes all artifacts in `artifacts/` |


---

## 📦 VirtualBox & Docker-Android Setup Guide

VirtualBox stores VMs inside your user profile directory (`$HOME\VirtualBox VMs\`), meaning **no administrator rights are needed to create or run VMs**.

### Automated 1-Click Provisioning (Recommended)

Run the following commands in PowerShell from the `lab\` directory:

```powershell
# 1. Create VM with storage, nested virtualization, and NAT port forwardings:
.\lab.ps1 vbox-create -VmName "android-lab-vm" -Memory 4096 -Cpus 2

# 2. Automatically download and attach the lightweight Alpine Linux ISO:
.\lab.ps1 vbox-download-iso -Distro alpine

# 3. Run unattended automatic installation (handles disk partitioning, ISO eject, and Docker setup):
.\lab.ps1 vbox-autoinstall

# 4. Start headless in background anytime:
.\lab.ps1 vbox-start
```

### Manual Installation (Alternative)

If you prefer interactive installation with a graphical window:
```powershell
# Boot installer with GUI window:
.\lab.ps1 vbox-start -Gui

# Inside the VM console:
# 1. Login with: root
# 2. Run: setup-alpine
#    - Select keymap and timezone
#    - Pick network interface eth0 (dhcp)
#    - Set root password
#    - Target disk: sda, Mode: sys, Confirm erase: y
# 3. Run in-guest automation script:
#    curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/android-lab/lab/scripts/setup-docker-android.sh | sh
```

# Once running, the following ports are mapped to localhost:
#   http://127.0.0.1:6080 -> Web noVNC (Interactive Android Emulator display)
#   127.0.0.1:5555       -> ADB bridge (connect with '.\tools\platform-tools\adb connect 127.0.0.1:5555')
#   http://127.0.0.1:8000 -> MobSF Web UI & REST API
#   127.0.0.1:8080       -> mitmproxy HTTP interception
#   http://127.0.0.1:8081 -> mitmweb interactive dashboard
```

---

## 🩺 Virtualization Readiness (`win-preflight`, PENT-23)

`.\lab.ps1 win-preflight` (or `python scripts\win_preflight.py`) is a read-only, no-admin
check that tells you which lab model this PC can run and what to fix. Nothing is changed on the host.

| Check | What it reads (no elevation) | Typical finding → fix |
|---|---|---|
| `vtx` | `Win32_Processor` + `Win32_ComputerSystem.HypervisorPresent` | VT-x off in BIOS → enable in firmware (**admin/IT**); meanwhile Model 1 |
| `virtualbox` | `VBoxManage --version` | Hyper-V active → VirtualBox runs in slow NEM mode without nested VT-x → prefer Podman/WSL2 |
| `wsl` | `wsl -l -v` | WSL missing → `wsl --install` (**admin/IT**); WSL1 only → `wsl --set-version <distro> 2` |
| `podman` | `podman machine list` | no machine → `podman machine init`; stopped → `podman machine start` |
| `execution_policy` | `Get-ExecutionPolicy -List` (Process scope ignored), `lab.ps1:Zone.Identifier` | Restricted → `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (no admin); enforced by Group Policy → ask IT; downloaded (Mark-of-the-Web) → `Unblock-File .\lab.ps1` |
| `ram`, `disk`, `vm_disk`, `python` | CIM, free space on the lab drive and (if different) the profile drive that holds VMs / WSL images, interpreter | below 8 GB / 20 GB / Python 3.11 |

When Hyper-V (or WSL2/VBS) is running, Windows reports `VMMonitorModeExtensions` and SLAT as
`False` (verified on Windows 11 build 26300); the check reads `HypervisorPresent` first so this is
not mistaken for a CPU without VT-x.

Use `-Json` for a machine-readable report. To share or replay a host state, save it with
`python scripts\win_preflight.py --save-facts facts.json` and evaluate it anywhere with
`--facts facts.json`; the test suite replays the known failure scenarios in
`tests/fixtures/win_preflight/` this way. Exit code is 1 if any check fails (`--strict`: warnings too).

Each remediation step is labelled `[admin]` only when that step needs elevation or IT. A probe that
times out or errors is reported as such (model state `unknown`) instead of being read as "not set up",
and a model is only recommended when the RAM, disk, architecture and Python floors it needs all hold.

---

## 🦭 Podman Setup Guide (Windows Non-Admin)

When using Podman on Windows without admin:
1. The modified `docker-compose.win.yml` isolates the Linux `/dev/kvm` requirement so that MobSF, mitmproxy, and tools run seamlessly:
   ```powershell
   podman compose -f docker-compose.win.yml up -d mobsf mitmproxy tools
   ```
2. If connecting to a remote lab machine or VirtualBox VM:
   ```powershell
   podman system connection add lab-vm ssh://user@127.0.0.1:2222/run/user/1000/podman/podman.sock
   podman system connection default lab-vm
   ```

---

## 📊 Verification Checklist

- [x] Pre-flight checks pass without elevation (`.\lab.ps1 preflight`)
- [x] Virtualization readiness reported without elevation (`.\lab.ps1 win-preflight`)
- [x] Python virtual environment successfully initialized (`.venv`)
- [x] Frida and mitmproxy available in user space
- [x] Manifest & attack surface analysis executes offline (`scripts/static_analyzer.py`)
- [x] VirtualBox VM creation and headless control verified via `VBoxManage`
