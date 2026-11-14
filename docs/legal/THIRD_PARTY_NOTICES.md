# Third-Party Notices

_Last updated: November 9, 2026_

os-lab is licensed under the [Apache License 2.0](../../LICENSE). It
orchestrates, downloads or bundles software from other projects, which remains
under its own licence and terms. The licences below were taken from each
project's repository on the date above; always check the project itself for
the current terms.

## Container images pulled by the labs

| Component | Used by | Licence |
|-----------|---------|---------|
| [Docker-Android](https://github.com/budtmo/docker-android) (`budtmo/docker-android`) | android-lab emulator | Apache-2.0 **with amendments** on forks and data processing (usage analytics; see below) |
| [MobSF](https://github.com/MobSF/Mobile-Security-Framework-MobSF) (`opensecurity/mobile-security-framework-mobsf`) | android-lab static analysis | GPL-3.0 |
| [mitmproxy](https://github.com/mitmproxy/mitmproxy) (`mitmproxy/mitmproxy`) | android-lab traffic interception | MIT |
| `cryptax/android-re` | android-lab tools container | See the image's documentation on Docker Hub |
| [dockur/windows](https://github.com/dockur/windows) (`dockurr/windows`) | win-lab | MIT (the container scripts; Windows itself is licensed by Microsoft) |
| [dockur/macos](https://github.com/dockur/macos) (`dockurr/macos`) | ios-lab | MIT (the container scripts; macOS itself is licensed by Apple) |
| [qemus/qemu](https://github.com/qemus/qemu) (`qemux/qemu`) | linux-lab | MIT (the container scripts; guest operating systems keep their own licences) |

### Docker-Android usage analytics

Docker-Android's licence includes a data-processing amendment: unless disabled,
the container reports usage analytics to its maintainers through Google Forms,
including start time, the host's OS release string, the Docker-Android version,
feature flags, device settings, and city, region and country derived from your
IP address through ipinfo.io. The image honours the opt-out variable
`USER_BEHAVIOR_ANALYTICS=false`.

**os-lab sets `USER_BEHAVIOR_ANALYTICS=false` by default** in
`android-lab/lab/docker-compose.yml`, `docker-compose.win.yml` and
`scripts/setup-docker-android.sh`. To opt in, set
`DOCKER_ANDROID_ANALYTICS=true` in `android-lab/lab/.env`.

## Tools downloaded or installed

| Component | Licence |
|-----------|---------|
| [Docker Desktop](https://docs.docker.com/desktop/) | Downloaded only when requested on macOS or Windows; subject to the [Docker Subscription Service Agreement](https://www.docker.com/legal/docker-subscription-service-agreement/) |
| [uv](https://github.com/astral-sh/uv) and the CPython builds it downloads from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) | Apache-2.0 or MIT for uv; CPython and included libraries retain their own licences |
| [JADX](https://github.com/skylot/jadx) | Apache-2.0 |
| [Apktool](https://github.com/iBotPeaches/Apktool) | Apache-2.0 |
| [Frida](https://github.com/frida/frida) and frida-tools | wxWindows Library Licence 3.1 |
| [Appium](https://github.com/appium/appium) (macOS path) | Apache-2.0 |
| Android SDK Platform-Tools (adb, fastboot) and emulator images | [Android SDK Terms and Conditions](https://developer.android.com/studio/terms) (Google) |
| Xcode and the iOS Simulator (macOS path) | Apple's Xcode and Apple SDKs licence agreement |
| Python packages in `android-lab/lab/requirements.txt` (Flask, mitmproxy, requests, cryptography and others) | Their own licences, listed in each package's metadata (`pip show <package>`) |
| Dashboard packages in `dashboard/package.json` (Astro, React, Tailwind CSS, Phosphor Icons and others) | Their own licences, listed in `dashboard/node_modules/<package>/LICENSE` after `npm ci` |

## Bundled in this repository

- Release installers include a pinned uv executable for their host architecture.
  The app uses it only when the user chooses **Get Python**; CPython is downloaded
  into the app's data folder rather than redistributed in the installer.
- Nothing from Google: os-lab does **not** redistribute Android SDK
  Platform-Tools. When `adb` is missing, `android-lab/lab/scripts/get_platform_tools.py`
  (run by preflight or `make platform-tools`), or `lab.ps1 setup` on Windows,
  downloads Google's official archive from `dl.google.com` into the git-ignored
  `android-lab/lab/tools/platform-tools/`. Its use is governed by the
  [Android SDK Terms and Conditions](https://developer.android.com/studio/terms);
  set `OSLAB_NO_DOWNLOAD=1` to stop the automatic download.
- `dashboard/src/shell/` and `dashboard/src/apk-lab/`: user-interface code
  ported from the qLar project by the same maintainers.

## Source Lab code and excluded material

`source-lab/engine/source_lab/`, its retained tests, and first-party manifest
annotations/Pipeline architecture metadata in `console/source_*.json` were ported from the
maintainer's iQ-SourceContol code with the owner's explicit authorization for
publication in os-lab under Apache-2.0. This is a first-party contribution, not
a claim that the private source repository declared an open-source license.
The source revision, file hashes and exclusions are recorded in
[Source Lab import policy](../../source-lab/IMPORT_POLICY.md) and its provenance
manifest. No third-party archive, dataset, binary, browser or parser grammar is
bundled with the port. The core engine uses Python's standard library; optional
tools are installed separately by the operator under their own terms.

## Operating systems

Windows, macOS, iOS and Android are proprietary or separately licensed
operating systems. os-lab does not include or licence them. Obtaining and
complying with their licences is the operator's responsibility; see the
[Terms of Use](TERMS.md), section 4.
