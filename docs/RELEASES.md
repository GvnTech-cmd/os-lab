# App releases

Release packages use the scripts in `app/scripts/` on their matching hosts.
Linux and macOS workflows publish signed packages. Windows review builds can
run independently; publication requires SignPath configuration or explicit
unsigned-release approval. Local builds remain supported. The
`updater-manifest` workflow publishes the signed feed only when all required
platform assets are present. The release note for each version follows.

## Publish the updater feed ("latest" detection)

The desktop app and the dashboard's **App update** card read the signed feed at
`app-updates/latest.json`. It is published automatically: `.github/workflows/updater-manifest.yml`
runs every 20 minutes, on release changes, and on demand. It picks the newest non-draft
`app-v*` release whose five signed assets are all present, builds the manifest, verifies every
signature with the pinned public key, uploads `latest.json` and marks that release as GitHub
Latest. A newer release with incomplete assets is skipped, and the feed is never downgraded, so
uploading the platforms one by one is safe.

No command is needed. To run it by hand (or pin a version before the schedule catches up):

```bash
node scripts/publish-app-update.mjs --detect-latest --check   # what would be published
node scripts/publish-app-update.mjs --detect-latest --mark-latest --verify
node scripts/publish-app-update.mjs 0.2.8 --mark-latest --verify
```

The script reads assets from `app/out/<version>` when present, otherwise downloads them from the
release with `gh`, verifies every SHA-256 through `app/scripts/build-update-manifest.mjs`, and
uploads `latest.json` to the `app-updates` prerelease.

## 0.3.5

- Redesign Cleanup Lab's dashboard views. The advanced `/cleanup/scan/` page
  renders catalog entries as sortable cards — largest-first once a scan exists,
  or safest-first — with category icons, risk badges, measured sizes and
  relative size bars. Hints, impacts, resolved paths, sources and privilege
  notes moved into hover/focus detail popovers, and selection chips (Defaults /
  All / None) sit beside the card grid.
- Add a "Measured space" summary with a stacked bar by risk class; results are
  grouped by category and size-sorted; clean reports show Trashed / Deleted /
  Skipped / Failed badges; history rows collapse per-run item lists.
- "Review & clean" builds the plan and opens a focused confirmation dialog
  listing ready items with sizes and skipped items with their guard reasons
  (for example a running application), so the selection can be corrected before
  running. The dashboard's confirm step uses the same dialog. Trash remains the
  default and the plan's fingerprint checks are unchanged.
- Name container prune actions from their action ids with the command and risk
  badge visible before confirming; leftover findings sort by confidence with
  paths in the detail popover and no delete actions.
- Fix size formatting: values of one kibibyte and above were previously rendered
  as "MiB", and sizes now keep their left-to-right order in right-to-left
  locales. New interface strings are translated in all seven supported locales.

## 0.3.4

- Pin the Windows NSIS setup to per-user installs and verify the per-user mode
  during install; clear the stored install-path value on uninstall so a
  reinstall does not inherit a stale path.
- Add a read-only volume inventory to Cleanup Lab's engine: `GET
  /api/cleanup/volumes` and `labctl cleanup volumes` list every local volume's
  capacity and kind, mark the volume holding the home folder, and warn above
  90% usage.
- Add typed privileged maintenance actions behind the desktop's own elevation
  prompt — APT package cache, journald vacuum, apt autoremove, the Spotlight
  index rebuild and DISM's component store cleanup — with fingerprinted
  single-use previews and an audited run, plus the read-only macOS Full Disk
  Access probe. No stored password; an elevated `rm` stays refused.
- Add cache relocation: move a catalog entry to another volume behind a
  symlink and back (restore, relink, resume), where every step keeps either
  the original or a verified copy. These Cleanup Lab capabilities live in the
  engine, the console API and `labctl`; their dashboard cards follow in a
  later release.

## 0.3.3

- Make Cleanup Lab's default page a compact scan, recommendation, plan review,
  confirmation, progress and report flow. The scan measures every available
  catalog category without deleting anything. The recommended preset selects
  only measured, default-selected, nonprivileged low/medium-risk items; privacy,
  credentials and high-risk items stay outside it.
- Keep individual catalog controls and permanent-delete mode on the advanced
  `/cleanup/scan/` page. Results, leftovers and audit history remain available.
- Include translations for all seven supported locales. Windows installers in
  this release are unsigned by Authenticode, with SHA-256 files and detached
  updater signatures, under the owner's prior approval.

## 0.3.2

- Require Python 3.11 or newer in the desktop launcher, matching Cleanup Lab's
  runtime requirement. If the host only has an older Python, **Get Python**
  installs the app-managed Python 3.12 before the console starts.
- Replace the checkout-specific Cleanup Lab readiness hint with instructions
  that also apply to installed desktop builds.

## 0.3.1

- Bundle the Cleanup Lab engine and catalog in the desktop app so the merged
  scan, plan, clean, results, leftovers and audit history pages work in an
  installed build. The dashboard includes the merged system, browser, developer,
  deep sweep, container/VM and leftover detectors.
- This release is for installed-app testing. Later Cleanup Lab tasks remain open.

## 0.3.0

- Add Source Lab: portable five-platform static analysis, signed evidence,
  structural maps, crawler/catalog workflows and guarded background jobs.
- Add Overview, Evidence/runtime, Deep analysis, Pipeline and bounded Brain
  snapshot pages with localized navigation and informational public Pages.
- Add authorized legacy artifact import with reviewed hashes/backups/rollback;
  preserve private Source state across desktop updates.
- Include workflow guides, owned-fixture acceptance and explicit capability
  limits. Skills, databases, OpenAPI and further merger UI remain excluded.
- Native/live verification and related patches are tracked as Source Lab bonus
  contributions; native manual Source acceptance is not claimed.
- Published Linux amd64/arm64 `.deb`, `.rpm` and `.AppImage`, macOS universal
  `.dmg`/`.app.tar.gz`, and Windows x64 setup/MSI with hashes and verified updater
  signatures. macOS is Developer ID signed and notarized. Windows has no
  Authenticode signature and may show SmartScreen; publication was approved by
  the owner. The updater feed covers all five platform entries.

## 0.2.9

- Add **Don't show this warning next time** to the container-runtime launcher page. The choice is
  remembered; **File → Container setup…** reopens the page so the warning can be restored.
- Keep an explicit **Retry** checking the engine even when the warning is hidden.

## 0.2.8

- Add the **App update** card; it checks the signed feed and appears only when a newer build exists.
- Show the content card only when a newer signed pack is available.
- Publish the updater feed automatically through the `updater-manifest` workflow.

## 0.2.7

- Add DNS roadmap tasks OS-37..OS-40 to the contribute page.
- Reserve roadmap tasks through a pull request.
- Rebuilt dashboard for all locales.

Assets published on `app-v0.2.7`:

| Platform | Files |
| --- | --- |
| Linux amd64 | `.deb`, `.rpm`, `.AppImage`, each with `.sha256` and `.sig` |
| Linux arm64 | `.deb`, `.rpm`, `.AppImage`, each with `.sha256` and `.sig` |
| macOS universal | `.dmg` and `.app.tar.gz`, each with `.sha256` and `.sig` |
| Windows x64 | `-setup.exe` and `.msi`, each with `.sha256` and `.sig` |

Linux packages were built locally with `app/scripts/release-deb.sh --all-formats` on an amd64
host. Verify a download by comparing it with the adjacent `.sha256`, and verify the detached
signature with `app/scripts/verify-release-signature.py <package> --version 0.2.7`.
