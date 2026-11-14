# Cleaner Pro — plan (draft PR #214)

Planning document for the `feat/cleaner-pro` workstream on the Cleanup Lab.
Tasks are appended here (and to the PR body) as the maintainer dictates them;
**no implementation starts until they say so.** Each task lands as its own
commit on this branch once approved; a task that outgrows the branch splits
into a stacked PR per the "each Cleanup Lab task in its own PR" rule.

Task series: `CLNP-01…` (Cleaner Lab Pro). The existing roadmap covers
`CLN-01…CLN-29`; new ids join the dashboard Contribute → Roadmap page at
implementation time with the seven-locale translations.

---

## Task 1 — Optional permission checks and grants (CLNP-01 … CLNP-05)

Add an optional, read-only permission surface so the cleaner can say exactly
which macOS privacy grants (Full Disk Access, hidden/TCC-protected roots)
unlock which catalog entries — with grant guidance — and the honest
equivalents on Windows and Linux. Permissions never block readiness; they are
an optional capability, like `privileged-actions`.

### Current state (grounded in the code)

- `cleanup_lab/privilege.py::disk_access()` (CLN-20) already ports a read-only
  macOS FDA probe: `os.listdir` on `~/Library/Safari` and `~/Library/Mail`,
  returning `{applicable, granted, paths[], guidance}` with
  `applicable: False` elsewhere. It rides inside `privilege.capabilities()`
  as `diskAccess` and reaches the console only through
  `GET /api/cleanup/privileged`.
- `readiness.py` reports required checks (deciding `ready` / `needs-setup` /
  `unavailable`) plus optional capabilities that never block.
- The scan job reports unreadable paths under `unreadable` with a reason, but
  does not classify *permission denied* (a grant would fix it) against
  *not present / other errors*.
- `labctl cleanup doctor` prints readiness checks, paths and hints — no
  disk-access or permission lines.
- The dashboard renders no permission state; `diskAccess` appears only as
  roadmap text in `dashboard/src/views/cleanup-lab-tasks.tsx`.

### Design rules (from README safety rules + architecture contract)

1. **Read-only probes only** — `os.listdir` / `lstat` on fixed probe paths;
   no shell, no subprocess, no paths accepted from the page.
2. **Optional capability** — a missing or denied permission never flips
   readiness away from `ready`; it is surfaced as a capability with guidance.
3. **Typed payloads** — stable JSON shapes, unknown query parameters or keys
   → `400`, missing engine → `501`, no command strings.
4. **Grant affordance is guidance, not action** — the engine never opens
   System Settings or spawns anything. The dashboard renders the hint plus a
   plain client-side `x-apple.systempreferences:` link; `labctl doctor`
   prints the hint text.
5. **Proactive probes stay non-intrusive** — only FDA probe paths
   (`~/Library/Safari`, `~/Library/Mail`) are touched proactively; they fail
   silently under TCC without raising a macOS consent dialog. Desktop /
   Documents / Downloads TCC folders are *not* probed up front — probing them
   can trigger the system consent dialog — so they are classified reactively
   from scan-time permission errors instead.

### Permission set

| id | scope | how it is decided | grant hint |
| --- | --- | --- | --- |
| `macos-full-disk-access` | macOS | proactive probe of `~/Library/Safari`, `~/Library/Mail` (listdir; deny → `granted: false`) | System Settings → Privacy & Security → Full Disk Access + deep link `x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles` |
| `macos-desktop-folder` / `macos-documents-folder` / `macos-downloads-folder` | macOS | reactive: scan-time `PermissionError` on a root inside that folder classifies as needs-grant (`granted: null` until evidence) | System Settings → Privacy & Security → Files and Folders (or the named folder pane) |
| `hidden-roots` | all | read-only readability classification of hidden catalog roots (dot-directories, `~/Library`, `%APPDATA%` equivalents) per scan: `readable` / `permission-denied` / `not-present` | macOS: FDA hint (Library roots are TCC-protected); Windows: WindowsApps ACL note (report-only); Linux: owner/permission note |
| OneDrive placeholders | Windows | report-only `lstat` reparse-point classification on cloud-provider roots so the scan can say "online-only file, not measured" | none (informational) |
| TCC equivalents | Windows / Linux | every macOS permission reports `applicable: false` | — (existing `disk_access` shape already handles this) |

### Sub-tasks

#### CLNP-01 — Engine: typed `permissions` module
- [ ] New `cleanup-lab/engine/cleanup_lab/permissions.py` owning the
      permission model: one typed record per permission —
      `{id, name, applicable, granted (true/false/null), probePaths[],
      results[{path, readable, reason}], guidance, grantUrl|null}`.
- [ ] Move the CLN-20 FDA probe here; keep `privilege.disk_access()`
      delegating to it so the `GET /api/cleanup/privileged` payload shape
      stays byte-compatible for existing consumers.
- [ ] Reactive classification helper: given a scan's `unreadable` entries,
      map each to a permission id + guidance (FDA / Files-and-Folders /
      hidden-roots), leaving unmatched entries unclassified — no guessing.
- [ ] OneDrive/WindowsApps reparse + ACL classification is report-only and
      never blocks a scan.

#### CLNP-02 — Readiness and doctor
- [ ] `readiness.py` gains the optional `permissions` capability (present
      whenever the engine can answer the permission payload) — missing it
      never blocks `ready`.
- [ ] `labctl cleanup doctor` prints each permission: applicable / granted /
      probe results / guidance, and the deep-link hint text on macOS; exit
      codes unchanged (optional capability).

#### CLNP-03 — Console API
- [ ] `GET /api/cleanup/permissions` — typed, read-only; merges proactive
      probe results with the latest scan's reactive classification when one
      exists in the console process. Unknown query parameters → `400`;
      missing engine → `501`.
- [ ] Scan job payloads keep `unreadable` as-is; the *classification* joins
      through the permissions endpoint, not by widening the scan schema.

#### CLNP-04 — Dashboard
- [ ] `/cleanup/` gains a permissions card (readiness-probe section): state
      chip per permission (granted / denied / unknown / not applicable),
      probe paths with per-path reasons, guidance text, and — on macOS — a
      plain link to `x-apple.systempreferences:…` (client-side only, no
      engine call, no polling).
- [ ] Scan page: unreadable items show "which grant would unlock this" via
      the classified permission id.
- [ ] Seven-locale translations; Public Pages renders the card as
      documentation only, no engine calls, per `lat.md/ux-readiness.md`.

#### CLNP-05 — Tests, docs, knowledge graph
- [ ] `unittest` with fake probers: `PermissionError` / `FileNotFoundError` /
      other `OSError` / not-applicable / partial results; delegation keeps
      the CLN-20 payload shape stable.
- [ ] Console contract cases in `android-lab/lab/tests/test_cleanup_console.py`
      (400/501/typed payload).
- [ ] Update `cleanup-lab/README.md`, `cleanup-lab/STATUS.md`,
      `cleanup-lab/VERIFY.md`, `lat.md/cleanup-lab.md`; add `CLNP-01…05` to
      the Contribute → Roadmap page with translations; `lat check` passes.
- [ ] `scripts/run-tests.sh` suite green.

### Open questions (decide at implementation start)
- Should `macos-full-disk-access` gain more probe paths (e.g.
  `~/Library/Messages`)? Default: keep Safari + Mail unless a catalog root
  proves unreadable under FDA.
- Roadmap ids `CLNP-…` vs continuing `CLN-30…` on the Contribute page —
  default `CLNP-…` for workstream separation (WINMIR precedent).
