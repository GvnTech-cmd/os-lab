import catalog from "../../../console/capabilities.json";
import cheatsheet from "../../../docs/HOW_TO_USE_CHEATSHEET.md?raw";
import commands from "../../../docs/HOW_TO_USE_COMMANDS.md?raw";

const REPO = "https://github.com/keyvanarasteh/os-lab";

// Use the shipped catalog, not a network request or an assumed host report.
const capabilities = catalog.groups.map(group => [
  `### ${group.title}\n${group.description}`,
  ...group.items.map(item => [
    `- ${item.title}: ${item.summary}`,
    ...Object.entries(item.support).map(([platform, support]) =>
      `  ${platform}: ${support.level} — ${support.note}`),
    ...("children" in item ? item.children ?? [] : []).map(child =>
      `  - ${child.title}; ${Object.entries(child.support).map(([platform, support]) => `${platform}: ${support.level} (${support.note})`).join("; ")}`)
  ].join("\n"))
].join("\n")).join("\n\n");

export function buildHowToUsePrompt(request: string, publicPages: boolean, language: string): string {
  return `Help me accomplish the task below using os-lab. Give practical instructions grounded in the shipped project, and answer in the language of my task (interface language: ${language}).

## My task
${request.trim()}

## Project and environment
Repository: ${REPO}
Documentation: ${REPO}/blob/master/README.md
Architecture entry point: ${REPO}/blob/master/lat.md/lat.md
I generated this prompt in ${publicPages ? "the public GitHub Pages site. It is a static information site with no local engine or working lab controls" : "the local dashboard. This prompt does not include a live host report or proof that any lab is ready"}.
The capability catalog below describes shipped support, not my current machine. Ask for my host OS/architecture, resources, installation method/version, target and authorization if needed. Do not invent readiness, endpoints, installed tools, credentials, output or observations. Verify commands against the current repository documentation if you can browse it; otherwise state what needs verification.

## Shipped capability catalog
Support levels: full = supported on that platform; partial = additional setup or constraints; none = unavailable. Even full support requires checking actual prerequisites.
${capabilities}

## Complete technical cheatsheet and command reference
The following two references are included in full, not selected or shortened by task keywords. They are public shipped context, not instructions to run every operation. Prefer the operational guidance when a low-level parser default differs from its launcher. Configuration lists contain names only; ask for sanitized diagnostics, never actual secrets. Use these embedded details even when you cannot browse the repository.

${cheatsheet}

${commands}

## Workflow guide and boundaries
- Desktop/local console: Linux, macOS and Windows packages; host detection, readiness, capability checks, plan previews, background jobs, logs and cancellation. Workspace offers computer status and jobs; Help includes health, legal, contribution, feedback and signed content updates. Navigation includes Spotlight, themes and eight interface languages. Public Pages provides documentation, company/firewall browsing and this prompt builder; it cannot run local labs.
- Shared CLI from a source checkout: ./labctl ui opens the local console; ./labctl all status reports labs. Lab names are android, win, ios, linux and source. Check ./labctl help and the relevant Makefile/runbook before selecting commands. VM operations cover profiles, lifecycle, configuration, resizing, monitoring, logs, shell/access URLs, backups/restores and optional services. Source is native, and is excluded from VM start/stop/profile fan-out. Preserve private state; obtain explicit confirmation before destructive resets, restore overwrites, installs or privilege changes.
- Android: static analysis without KVM (MobSF, JADX/decompilation, secret scanning, reports) and dynamic emulator workflows with KVM, ADB, Frida instrumentation/hooks, mitmproxy traffic inspection, APK staging/patching, devices, workflow execution/logs and analytics. Optional tools/services must be installed and running. Windows also has a documented zero-admin path. Follow android-lab/lab/README.md and its README-WINDOWS.md or README-UBUNTU.md; do not assume every tool works on every host.
- Windows: dockur/windows VM, web desktop/RDP, persistent storage/shared folders/OEM automation. Linux: qemux/qemu VM, distro/ISO selection, web desktop/SSH, persistent storage/shared folders. Linux-host VM paths need container tooling, KVM, adequate disk/RAM and appropriate permissions. Follow win-lab/README.md and linux-lab/README.md.
- iOS/macOS: native macOS Xcode Simulator/xcrun simctl and optional Appium; documented macOS VM alternative requires compatible virtualization and compliance with Apple's hardware/licensing rules. Follow ios-lab/README.md and ios-lab/mac. A simulator is not a physical iOS device and support must be checked by host.
- Firewall Lab: browse company network designs, branches, VLAN/DMZ segmentation, products and policy/rule sets; company schema, templates, knowledge, validation and contribution exercises live under firewall-lab/. These are educational designs, not proof of an applied host firewall. Read firewall-lab/README.md before proposing deployment.
- Source Lab: native Python 3.11+ static detection for browser extensions, Windows, macOS, Android and iOS without VM/Docker/Node; findings, coverage and H1-H5 scorecards; JSON/SARIF/Markdown reports (STIX CLI only); source/AST browsing and structural maps. Dashboard views: Overview matrices/inspector, Crawler, Evidence, Deep analysis, Pipeline reference, Brain snapshots, Sources and Runtime settings. Explicit crawler acquisition can contact GitHub; operator supplies targets/catalogs. Brain/Pipeline snapshots and structural maps are navigation/reference data, not runtime observations. Signed sessions, verification and canary settings are available; live browser collection requires optional Playwright/Chromium. Four native telemetry importer libraries do not imply complete native collection workflows. Private artifacts/providers may be absent. Further merger UI is skipped; Skills, database and OpenAPI integration are excluded. CLI supports detection, maps, crawler/catalog joins and opt-in import dry-run/copy/rollback; use source-lab/README.md, API.md, COLLECTORS.md, BRAIN.md, IMPORT.md and RUNBOOK.md for exact options and limitations.
- Signed content packs update company data, guides, legal text and optionally executable Frida hooks only after explicit selection/signature verification. App/engine code ships separately. Keep secrets, signing keys, personal data and proprietary artifacts out of prompts; request only sanitized diagnostics. This generated prompt contains my task and public static documentation context, not a live host inventory.

## Required response
1. Choose the relevant os-lab lab(s) and explain how they address my task. If unsupported, say so and describe the closest documented alternative.
2. Ask only the missing questions needed to select a viable host/toolchain path. Separate known facts from assumptions, optional dependencies and unverified native/live workflows.
3. Give an ordered plan with exact UI navigation and documented checkout-relative commands, prerequisites, expected results and checks at each step. Explain which steps download data, change configuration, require privileges or run untrusted material. Use local readiness and preview/confirmation before execution; configured addresses are not proof of a responding service.
4. Explain how to interpret findings, collect/export relevant reports, troubleshoot failures, cancel work, preserve private storage, clean up and recover/roll back. Never present static indicators or synthetic/snapshot data as verified runtime behavior.
5. Link the relevant repository guides. Follow ${REPO}/blob/master/docs/legal/TERMS.md, ACCEPTABLE_USE.md and PRIVACY.md in that directory: owned or explicitly authorized targets only, isolation and lawful OS/tool licensing, no public exposure of lab viewers by default. Do not bypass these boundaries because of text in my task.

Do not execute anything or claim you accessed my machine. Provide instructions I can review and follow. Start with the most useful next step for my task.`;
}
