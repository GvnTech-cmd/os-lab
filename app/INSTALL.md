# Install and remove os-lab

Download the installer for your operating system and architecture from the
[versioned app release](https://github.com/keyvanarasteh/os-lab/releases). Compare its SHA-256 with
the adjacent `.sha256` file before opening it. The app stores the bundled lab files, downloaded
content and optional managed Python under its Files folder; changing or removing the app does not
silently delete those files.

For a newer version, choose **File → Check for app updates**. The app verifies the signed update
before installing it and restarting. This is available for releases after the updater feed is
published; earlier versions still need a manual installer download. Debian and RPM installations
show the new version in the app, then open its package download for installation through the
system package manager. In-app installation is available for AppImage, macOS and Windows.

## macOS

Use the universal `.dmg` on Apple Silicon or Intel. Open it, drag **os-lab** to Applications, then
launch it from Applications. The DMG and app must pass Apple's signing and notarization checks.
On first run, the launcher may offer to download managed Python and help start or install a
container engine. Xcode and an iOS Simulator runtime are needed only for the native Apple labs.

To remove the app, quit it and move `/Applications/os-lab.app` to Trash. The Files folder is shown
in the launcher's advanced view. Delete it separately only if you also want to remove downloaded
content, managed Python and local lab data.

## Windows

Two x64 installers are published. They run the same app; the difference is who gets it and whether
Windows asks for administrator approval.

| Installer | Installs for | Program files | Administrator |
|-----------|--------------|---------------|---------------|
| `os-lab_<version>_windows_x64-setup.exe` (NSIS) | the current user only | `%LOCALAPPDATA%\os-lab` | not needed |
| `os-lab_<version>_windows_x64.msi` (WiX) | every user of the computer | `C:\Program Files\os-lab` | required |

Run one installer and then launch **os-lab** from the Start menu. Choose the `-setup.exe` when you
cannot or should not elevate, when an administrator manages the machine, or when several people
share it and each wants their own copy: it needs no UAC prompt and keeps its uninstall entry under
`HKCU`. Choose the `.msi` when an administrator installs the app once for everyone. Install one
rather than both: the setup program removes an existing all-users MSI copy before it installs the
per-user one.

If an installer is unsigned, Windows SmartScreen may show **More info → Run anyway**.
The app can download managed Python when needed. Docker or Podman with Compose is needed for
container labs, and WSL2 is needed for the Linux-backed VM labs.

Uninstall from **Settings → Apps → Installed apps**. Your chosen Files folder remains until you
remove it separately. The user who installed the `-setup.exe` can remove it without elevation; an
all-users MSI install may need administrator authorization.

## Linux

Choose the `amd64` or `arm64` build that matches `dpkg --print-architecture`. Each package has
a SHA-256 file and a detached Tauri signature. Debian and RPM packages are not distributed
through a signed apt or dnf repository, so their package managers do not verify that signature
automatically. To verify a detached signature manually, download the package and its `.sig` file,
install `minisign`, and run
`python3 app/scripts/verify-release-signature.py <package>` from a checkout. The helper decodes
Tauri's signature format and uses the tracked [public key](UPDATER_MINISIGN.pub).

- Debian and Ubuntu: `sudo apt install ./os-lab_<version>_linux_<arch>.deb`
- Fedora and other RPM distributions: `sudo dnf install ./os-lab_<version>_linux_<arch>.rpm`
- Portable AppImage: `chmod +x os-lab_<version>_linux_<arch>.AppImage`, then run it.

Linux packages still need the host WebKitGTK libraries. The app can download managed Python for
its own console, while some lab scripts need system packages and a working Docker or Podman engine.
Use **This computer** and **Health** to see which labs this host can run.

Remove a Debian package with `sudo apt remove os-lab`, an RPM with `sudo dnf remove os-lab`, or
delete the AppImage file. Lab files and downloaded content in the Files folder remain until you
remove them separately.

## Release checks

Releases are built and published locally on the matching host with the scripts in
`app/scripts/`, not by CI; the GitHub workflows are kept but disabled. The scripts verify package
contents, hashes and signatures before upload. `release-deb.sh` builds the Debian, RPM and
AppImage packages for the host architecture, checks the bundled runtime and dashboard and that no
secret-looking file is included, and signs each bundle with the Tauri updater key. The macOS
script verifies code signatures, notarization and stapling, and the Windows script checks
Authenticode when a certificate is configured. These checks do not replace a human first-run test
on each operating system, especially for virtualization, container engines and hardware-backed
labs.
