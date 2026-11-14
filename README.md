<div align="center">

# os-lab

<a href="https://keyvanarasteh.github.io/os-lab/">
  <img src="docs/media/os-lab-promo.png" alt="os-lab — Windows, Android, iOS, Linux and Firewall security labs" width="100%">
</a>

### [keyvanarasteh.github.io/os-lab](https://keyvanarasteh.github.io/os-lab/)

[Code signing policy](CODE_SIGNING.md) · [Desktop releases](https://github.com/keyvanarasteh/os-lab/releases?q=app-v)

Four research-backed, runnable operating-system security labs in one repository,
each a reproducible, isolated guest driven by `make` and a shared management CLI.

[![Download](https://img.shields.io/github/v/release/keyvanarasteh/os-lab?style=for-the-badge&label=DOWNLOAD&color=2f9e44)](https://github.com/keyvanarasteh/os-lab/releases/latest)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=for-the-badge)](CONTRIBUTING.md)
[![License](https://img.shields.io/badge/LICENSE-Apache--2.0-blue?style=for-the-badge)](LICENSE)

</div>

## Download

| Platform | Installer | Also available |
|:--|:--|:--|
| **macOS** — Apple Silicon & Intel | [`os-lab_0.3.5_macos_universal.dmg`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_macos_universal.dmg) | [`.app.tar.gz`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_macos_universal.app.tar.gz) |
| **Windows x64** | [`os-lab_0.3.5_windows_x64-setup.exe`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_windows_x64-setup.exe) | [`.msi`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_windows_x64.msi) |
| **Linux amd64** | [`os-lab_0.3.5_linux_amd64.deb`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_linux_amd64.deb) | [`.rpm`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_linux_amd64.rpm) · [`.AppImage`](https://github.com/keyvanarasteh/os-lab/releases/download/app-v0.3.5/os-lab_0.3.5_linux_amd64.AppImage) |

<sub>Latest **0.3.5** · [all files, checksums & signatures](https://github.com/keyvanarasteh/os-lab/releases/tag/app-v0.3.5) · [install & uninstall](app/INSTALL.md) · [release notes](docs/RELEASES.md). Every asset has a `.sha256` and detached `.sig`; in-app updates use the signed feed published by the `updater-manifest` workflow.</sub>

Windows installers have verified updater signatures but no Authenticode signature;
SmartScreen may warn. See [Windows signing](app/SIGNING.md).

## Labs

| Lab | What you get |
|:--|:--|
| [**Windows**](win-lab/) | Windows VM in Docker (`dockur/windows`) — web desktop, RDP, shared folder, backup and reset |
| [**Android**](android-lab/) | Emulator + MobSF, mitmproxy, Frida and containerized RE tools; static and dynamic workflows |
| [**iOS**](ios-lab/) | macOS VM on Ubuntu, or native Xcode / Simulator / Appium on macOS |
| [**Linux**](linux-lab/) | Disposable KVM guest for malware detonation, ELF RE, exploit/kernel and container-escape practice |
| [**Source Lab**](source-lab/) | Portable Python source/package analysis, signed evidence, structural maps and local dashboard workflows; native/live verification remains open as bonus contributions |
| [**Firewall**](firewall-lab/) | Student-built company network and firewall designs, rendered at [`/firewall/`](https://keyvanarasteh.github.io/os-lab/firewall/) |

## Quick start

```bash
# Linux
curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.sh | bash
# macOS
curl -fsSL https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install-macos.sh | bash
# Windows (PowerShell)
irm https://raw.githubusercontent.com/keyvanarasteh/os-lab/master/scripts/setup/install.ps1 | iex
```

Add `--report-only` (`-ReportOnly` on Windows) to inspect the host without changing anything. Then:

```bash
./labctl ui            # web console → http://127.0.0.1:5050
./labctl all status    # android + win + linux at a glance
./labctl ios start     # Ubuntu macOS-VM path
```

The console shows what this computer can run, what each lab still needs, per-lab install/start/stop/preview actions, jobs, and the Android workbench. It and the desktop app are available in **English, Turkish, German, French, Spanish, Italian, Persian and Arabic** (right-to-left for Persian and Arabic).

> **Authorized use only.** Test only systems and apps you own or have written permission to assess; use valid Windows and macOS licences. See [SECURITY.md](SECURITY.md), the [Terms of Use](docs/legal/TERMS.md) and the [Acceptable Use Policy](docs/legal/ACCEPTABLE_USE.md).

<details>
<summary><b>Repo map, runtime map and deeper docs</b></summary>

| Path | What it is |
|:--|:--|
| [`labctl`](labctl) | Management CLI — profiles, lifecycle, resize, monitoring, service units |
| [`dashboard/`](dashboard/) | Web console and the public Pages site |
| [`app/`](app/) | Desktop client (Tauri) with signed in-app updates |
| [`firewall-lab/`](firewall-lab/) | BGT207 contribution lab: company network and firewall designs |
| [`docs/`](docs/) | Guides, releases, legal documents and media |
| [`lat.md/`](lat.md/) | Structured architecture and behaviour knowledge graph |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Issues, PRs, roadmap, task reservations, course workflow |

| Runtime | Endpoints |
|:--|:--|
| Windows VM (QEMU + KVM) | noVNC `:8006` · RDP `:3389` · shared storage |
| Android emulator (KVM) | noVNC `:6080` · ADB `:5555` · MobSF `:8000` · mitm `:8080/8081` |
| iOS (macOS VM or native) | VNC `:5900`, or Xcode / Simulator / Appium on macOS |
| Linux VM (`qemux/qemu`) | noVNC `:8006` · SSH `:2222` |

Quick starts and requirements live in each lab: [Windows](win-lab/) · [Android](android-lab/) · [iOS](ios-lab/) · [Linux](linux-lab/) · [Firewall](firewall-lab/). Translation review notes: [`dashboard/TRANSLATION_TODO.md`](dashboard/TRANSLATION_TODO.md).

</details>

## Contributing

Issues and PRs are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the lab map, roadmap and reservation process, the [issue templates](.github/ISSUE_TEMPLATE/) and the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities in os-lab itself through the [Security Policy](SECURITY.md).

## License

[Apache License 2.0](LICENSE). `dockur/windows` and `qemux/qemu` are MIT and do not distribute OS media; you are responsible for valid licences and vendor terms.
