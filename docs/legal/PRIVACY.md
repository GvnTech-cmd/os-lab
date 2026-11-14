# Privacy Notice

_Last updated: November 9, 2026_

os-lab is software you run yourself. The project does not operate a hosted
service, has no accounts, and **does not collect telemetry, analytics or crash
reports**. Nothing in the Software sends data to the os-lab maintainers.
Third-party images that the labs run can have their own data practices; the one
known to send analytics (Docker-Android) is switched off by default (section 4).

This notice explains what the Software stores on your machine, what it sends
over the network on your behalf, and where your own obligations begin.

## 1. The web console stays on your machine

The console (`./labctl ui`, or `android-lab/lab/web_ui.py`) listens on
`127.0.0.1` only. It rejects requests whose `Host` header is not a local
address, and every state-changing request must carry an `X-OSLab` header, so
other websites you visit cannot drive it. It makes no outbound internet
requests of its own.

## 2. What is stored locally

| Data | Where | How long |
|------|-------|----------|
| Host report: OS, CPU, memory, disk, KVM, WSL distributions, installed tools | Console memory | Recomputed every few seconds; not written to disk |
| Lab jobs: command, output (configured credentials are redacted), exit status | Console memory; Source Lab also journals under private storage `control/jobs.json` | The 50 most recent; Source records remain until the operator removes them |
| Android workbench log | Console memory | Last 1,000 lines, until cleared or the console stops |
| APKs you upload | `android-lab/lab/apks/` | Until you delete them |
| Analysis results, reports, traffic captures | `android-lab/lab/artifacts/` and each lab's folders | Until you delete them (`make clean` for Android) |
| Source Lab analysis reports, cloned workspaces, merged lab extensions and runtime sessions | `source-lab/storage/` by default, or the operator-configured storage root | Until you delete them; the project does not receive them |
| Source Lab opt-in import journals and rollback backups | Private storage `control/imports/` and `control/import-backups/` | Retained after import/rollback until the operator removes them |
| Source Lab input catalogs and local targets | Operator-provided resource/target paths; no third-party datasets are bundled | Managed by the operator |
| Lab configuration, including passwords you set | Each lab's `.env` | Until you change it; shown masked in the console |
| VM disks, backups and shared folders | Each lab's `storage/`, `backups/`, `shared/` | Until you delete them |

## 3. What the browser stores

The dashboard and the classic console set **no cookies**. They keep a few
preferences in your browser's local storage, which never leave your browser:

| Key | Purpose |
|-----|---------|
| `theme` | Light or dark mode (dashboard) |
| `oslab.theme` | Light or dark mode (classic console) |
| `oslab.sidebar.collapsed` | Whether the sidebar is collapsed |
| `oslab.spotlight.recents` | Your last few search picks |
| `oslab.apk` | The target APK path |
| `oslab.workflow` | The selected workflow tab (classic console) |

Clearing your browser's site data removes them.

Source Lab page selections (target, repository, file, tab, node and filters) can
appear in the local page URL and browser history. No graph or provider snapshot
is saved to browser storage by Source Lab. Clear browser history to remove those
URL records.

The **How to use** page builds a prompt in browser memory from your task and
public project context. It does not save the task, include live host data, call an
LLM or send the task to a server. Submitting copies the generated prompt to your
system clipboard if permission allows; it remains there according to your
system/clipboard-history settings. Clear it there if needed. If you paste it into
an external LLM, that provider handles it under its own policies; review the
prompt and remove private data before sharing.

## 4. Network connections made on your behalf

Installing, updating and running the labs contacts third parties. Each one
receives your IP address and the request, under its own privacy policy:

- **GitHub**: cloning and updating os-lab; tool downloads such as JADX; and the signed
  content pack (Firewall Lab data, guides, hooks) when you press *Check for updates* or
  *Update content*. Nothing is downloaded in the background, and `OSLAB_CONTENT_OFFLINE=1`
  switches it off.
- **Package managers**: apt, dnf, pacman, Homebrew, winget or Chocolatey, PyPI
  (Python dependencies) and npm (when the dashboard is rebuilt).
- **Container registries**, mainly Docker Hub, for the lab images.
- **Microsoft and Apple servers**, contacted by the Windows and macOS images to
  download installation media or recovery images.
- **Google** (`dl.google.com`): Android platform tools, downloaded when `adb`
  is missing (set `OSLAB_NO_DOWNLOAD=1` to prevent it), and emulator images.
- **Source Lab repository acquisition and metadata**: explicitly invoking its crawler
  or merge acquisition can contact GitHub for selected repositories. Local static
  detection and structural mapping do not contact a network service. Source Lab
  setup and readiness checks do not download or install software.
- **The targets you analyse** and any service a guest or app connects to. Source
  Lab's optional live browser canary visits only the test URL the operator passes;
  its session events and artifacts stay in local output storage. Simulated canary
  fallback is labeled and excluded from runtime correlation.

**Docker-Android analytics.** The Android emulator image reports usage analytics
to its maintainers (Google Forms) unless disabled, including the host's OS
release string, feature settings, and city, region and country looked up from
your IP address through ipinfo.io. os-lab disables this by default with
`USER_BEHAVIOR_ANALYTICS=false`; set `DOCKER_ANDROID_ANALYTICS=true` in
`android-lab/lab/.env` to opt in. Details are in the
[Third-Party Notices](THIRD_PARTY_NOTICES.md).

## 5. Personal data inside your labs

Apps, captured traffic, sandbox dumps and VM guests can contain other people's
personal data. You decide what is processed, so you are the controller for it
under the Turkish Personal Data Protection Law No. 6698 (KVKK), the EU GDPR or
other applicable law. Process it only with a lawful basis, keep it no longer
than needed, protect it, and delete it at the end of the engagement. See the
[Terms of Use](TERMS.md), section 5.

## 6. Contact

The maintainers do not receive or hold data from your installation. Questions
about this notice: [GitHub issues](https://github.com/keyvanarasteh/os-lab/issues).
If you contact the project through GitHub, GitHub's privacy statement applies
to that communication.

Source Lab runtime settings and its managed session signing key stay in private
storage under `control/`. Key files use mode 0600 where supported. Keys never
appear in API responses. Environment-owned keys remain operator-managed.
Changing a signing key prevents verification of prior sessions with that key;
retain originals securely if earlier evidence must remain verifiable. Source
jobs report interrupted work after a console restart; partial outputs remain
local for review. Explicit browser canary runs contact the selected test URL.
