# 🧪 Compact Agentic Mobile Security Lab

Minimal runnable core of the blueprint in [`knowledge/segmentation.md`](../knowledge/segmentation.md):
one compose stack, two workflow DAGs, verified commands from
[`../docker-android-cheat-sheet.md`](../docker-android-cheat-sheet.md).

```
┌────────────── labnet ──────────────────────────────┐
│ android (budtmo/docker-android)  noVNC :6080       │
│   └ ADB :5554/:5555 · rooted · /dev/kvm            │
│ mobsf (static+dynamic scan)      UI   :8000        │
│ mitmproxy (traffic capture)      proxy:8080 UI:8081│
│ tools (cryptax/android-re: jadx, apktool, r2)      │
└────────────────────────────────────────────────────┘
```

## Requirements

Linux host with `/dev/kvm` (native, WSL2 or Ubuntu VM — cheat sheet §0–§4).
macOS/Windows hosts: run this inside an Ubuntu VM; there is no native path.
~10 GB disk, 8 GB RAM recommended. `make preflight` checks all of it.

**Ubuntu Server:** see [`README-UBUNTU.md`](README-UBUNTU.md) for the host setup
script (`./setup.sh` / `make setup`), KVM group checks, systemd, firewall and
the KVM-free static-only path.

## Quick start

```bash
cd lab
cp .env.example .env            # adjust device profile / API key if you like
make preflight                  # OS / KVM / docker / adb / ports / disk
make boot                       # start stack + wait for emulator "ready"
# Ubuntu Server shortcut: ./setup.sh then ./run.sh
#   screen: http://localhost:6080   (noVNC)
```

## Workflows (the two DAGs from segmentation.md)

**WF1 — Static** · `make wf1 APK=path/to/app.apk`
MobSF upload → scan (JSON + PDF report) → JADX decompile.
Artifacts land in `artifacts/<app>-static-<stamp>/`.

**WF2 — Dynamic** · `make wf2 APK=path/to/app.apk PKG=com.example.app`
Boot emulator → install APK → route traffic through mitmproxy → launch app →
start frida-server (if present in `frida/`). Then, from the host:

```bash
adb connect 127.0.0.1:5555
make hook PKG=com.example.app HOOK=hooks/ssl-pinning-bypass.js
#   or HOOK=hooks/root-detection-bypass.js
```

Captured traffic streams to `artifacts/flows.mitm`; inspect live at
`http://localhost:8081`. Install the proxy CA on the emulator by opening
`http://mitm.it` in its browser (via noVNC).

**Report** · `make report` — sweeps device status, logcat, docker logs and
flows into `artifacts/report-<stamp>/`.

## Profiles and management

Use the repo-level `labctl` for presets, lifecycle, hardware and monitoring:

```bash
../../labctl android profiles
../../labctl android profile use lightweight   # static, no KVM
../../labctl android start --wait
../../labctl android monitor
../../labctl android resize --cpus 4 --ram 6g --device "Samsung Galaxy S10" --apply
../../labctl android config show
```

| Profile | Mode | CPU | RAM | Use |
|---|---|---:|---:|---|
| `lightweight` | static | 1 | 2g | MobSF/mitmproxy/tools only |
| `development` | dynamic | 2 | 4g | Android 11 emulator |
| `performance` | dynamic | 4 | 6g | Android 13 emulator |

`profile use` writes the preset into `.env`; `--profile P` is a one-shot
overlay. CPU/RAM are container limits; `--device` changes the emulator hardware
profile. An existing AVD may need the `android_data` volume reset to pick up a
new device profile.

## Make targets

| Target | What it does |
|---|---|
| `preflight` | OS / KVM / docker / ports / disk checks (cheat sheet §0) |
| `up` / `boot` / `down` | stack lifecycle (`boot` waits for emulator ready) |
| `logs` / `status` / `adb` | follow logs, check device, shell into emulator |
| `monitor` / `profiles` | live dashboard; list management profiles |
| `install APK=` | copy APK into `apks/` and `adb install -r` |
| `wf1 APK=` | static workflow (MobSF + JADX) |
| `wf2 APK= [PKG=]` | dynamic workflow (emulator + mitm + frida) |
| `pinning APK=` | PENT-11: static SSL-pinning detector/classifier (run before `wf2`) |
| `hook PKG= HOOK=` | attach a Frida hook to a running app |
| `report` | collect logs/status/flows into `artifacts/` |
| `clean` | wipe `artifacts/` |

## Layout

```
lab/
├── docker-compose.yml     # android · mobsf · mitmproxy · tools on labnet
├── .env.example           # mode, device, image tag, CPU/RAM, MobSF key
├── profiles/              # lightweight / development / performance presets
├── Makefile               # all targets above
├── setup.sh / run.sh      # Ubuntu Server wrappers
├── docker-compose.win.yml # KVM-free subset (MobSF/mitmproxy/tools)
├── scripts/
│   ├── setup-ubuntu.sh    # Ubuntu Server host setup (KVM, Docker, adb, dirs)
│   ├── preflight.sh       # §0 checks: /dev/kvm, kvm-ok, docker, adb, ports, disk
│   ├── wait-boot.sh       # poll device_status until "ready"
│   ├── wf1-static.sh      # MobSF upload → scan → PDF/JSON → jadx
│   ├── wf2-dynamic.sh     # boot → install → proxy → frida-server
│   ├── pinning_detector.py # PENT-11 static SSL/certificate-pinning classifier
│   ├── report.sh          # artifact sweep
│   ├── install-service.sh # systemd unit for boot start
│   └── uninstall-service.sh
├── hooks/                 # Frida scripts (educational bypasses)
│   ├── ssl-pinning-bypass.js
│   └── root-detection-bypass.js
├── apks/                  # drop APKs here (gitignored)
├── frida/                 # drop frida-server-<ver>-android-x86_64 here (gitignored)
└── artifacts/             # all reports, sources, captures (gitignored)
```

To enable Frida runtime hooking, download the x86_64 `frida-server` matching
your host's `frida` CLI from
[github.com/frida/frida/releases](https://github.com/frida/frida/releases),
un-xz it to `frida/frida-server` - WF2 picks it up automatically.

## Mapping to the blueprint (segmentation.md)

| Blueprint phase | Route | Here |
|---|---|---|
| 1 Lab Entry / env pick | `/` | `make preflight` + `.env` |
| 2 Integration (upload APK) | `/providers` | `apks/` + `make install` |
| 3 Agent setup (WF select) | `/workflows` | `make wf1` / `make wf2` |
| 4 Execution (live console) | `/console-report` | `make logs`, noVNC :6080, mitmweb :8081 |
| 5 Analysis (findings) | `/analytics` | `artifacts/*-static-*/mobsf-report.json` |
| 6 Review (export) | `/sitemap` | `make report` |

The frontend shell (`/`, `/providers`, …) is **not** built here — this repo is
the backend core the agents (Orchestrator / Analyst / Exploit, per
segmentation.md §"Specialized Agent Classifications") drive via these scripts.
`../format/Agent Build Brief.md` is the handover template for commissioning
those agents on top of this lab.

## Agent brief (compact)

- **Mission:** given an APK, produce static findings (MobSF/JADX) and dynamic
  evidence (flows, logcat) in `artifacts/`, reproducibly, via `make` targets.
- **Tools:** the five scripts above + `docker compose exec` + `adb` + `frida`.
- **Guardrails:** never target anything but `labnet` containers or apps you
  own/have authorization to test; hooks are for authorized analysis only.
- **Return shape:** one `artifacts/<app>-{static,dynamic}-<stamp>/` directory
  per run containing `mobsf-report.{json,pdf}`, `jadx_out/`, `install.log`,
  `logcat.txt`, `flows.mitm` as applicable.
