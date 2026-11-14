/**
 * Android Lab workbench pages, laid out like qLar's apk-lab/*-page.tsx (PR #174) and driven by the
 * live web_ui.py API instead of demo data.
 */
import { useEffect, useMemo, useState } from "react";
import {
  ArrowClockwiseIcon,
  ArrowSquareOutIcon,
  ChartBarIcon,
  CheckCircleIcon,
  CircleIcon,
  CodeIcon,
  CpuIcon,
  DeviceMobileIcon,
  FileTextIcon,
  ListChecksIcon,
  MapTrifoldIcon,
  PlayIcon,
  PlugsConnectedIcon,
  ShieldCheckIcon,
  StopIcon,
  TerminalIcon,
  TrashIcon,
  TreeStructureIcon,
  UploadSimpleIcon,
  WarningCircleIcon
} from "@phosphor-icons/react";
import { AppShell, LAB_ICON, labHref } from "../../shell/app-shell";
import { TopBar } from "../../shell/top-bar";
import { localeFromPath, localePath } from "../../i18n/paths";
import {
  CodeShowcaseSwitcher,
  MinimalistHero,
  OrbitalWorkflowDag,
  ProgressConsoleReport,
  RoutesTopologyGraph,
  SegmentationBento,
  ShellSnippet,
  SitemapGrid,
  TipsNotesCard,
  WorkflowStepper
} from "../../apk-lab/components";
import type { RouteEntry } from "../../apk-lab/components";
import { Badge, Empty, EndpointList, PageHead, Section, Skeleton, Status } from "../../components/ui";
import { androidLogsStore, api, hostStore, message, useApk, usePoll } from "../../lib/api";
import { ACTIONS, ANDROID_ENDPOINTS, ActionTile, ApkTarget, Kpi, RunButton, parseJobs, useDevices, useRun } from "./common";

const BACK = { href: "/android/", label: "Overview" };

function Frame({ id, title, back = true, children }: { id: string; title: string; back?: boolean; children: React.ReactNode }) {
  return (
    <AppShell activeId={`android-${id}`}>
      <div className="iux min-h-screen">
        <TopBar title={`Android Lab · ${title}`} back={back ? BACK : undefined} />
        <main className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-8 sm:px-6">{children}</main>
      </div>
    </AppShell>
  );
}

// ── Overview ───────────────────────────────────────────────────────────

export function OverviewPage() {
  const { data: logs } = androidLogsStore.use();
  const { data: hostData } = hostStore.use();
  const hostOs = hostData?.host.os;
  // The ADB tab needs adb; while the host report is still loading keep it
  const adbFound = !hostData || hostData.host.tools.some((tool) => tool.id === "adb" && tool.found);
  const devices = useDevices();
  const reports = usePoll(api.reports, 0, []);
  const jobs = useMemo(() => parseJobs(logs?.logs ?? [], Boolean(logs?.running)), [logs]);
  const last = jobs[jobs.length - 1];
  const lab = hostData?.labs.find((l) => l.id === "android");
  return (
    <Frame id="overview" title="Security Overview" back={false}>
      <MinimalistHero
        badgeText="OS Lab"
        headline="The Mobile OS Lab"
        description="Agentic Android reverse engineering and vulnerability scanning: containerized Docker-Android emulators, JADX decompilation, OWASP MASVS rules, IPC fuzzing, APK patching and Frida playbooks."
        primaryCtaText="Launch Security Scan"
        primaryCtaHref="/android/workflows/"
        secondaryCtaText="Runtime & setup"
        secondaryCtaHref={labHref("android")}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi icon={<CpuIcon size={14} />} label="Runtime" value={lab ? (lab.state === "ready" ? "Ready" : lab.state === "needs-setup" ? "Setup" : "N/A") : "…"} sub={lab?.provider ?? "Docker-Android stack"} />
        <Kpi icon={<DeviceMobileIcon size={14} />} label="ADB devices" value={devices.loaded ? devices.list.length : "…"} sub="attached emulators and phones" />
        <Kpi icon={<FileTextIcon size={14} />} label="Reports" value={reports.data ? reports.data.reports.length : "…"} sub="HTML reports in artifacts/" />
        <Kpi
          icon={<TerminalIcon size={14} />}
          label="Last run"
          value={last ? (last.status === "running" ? "Running" : last.status === "ok" ? "Passed" : "Failed") : "—"}
          sub={last?.title ?? "No jobs this session"}
        />
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">Quick Environment Setup</h2>
          <p className="text-xs text-(--iux-muted-foreground)">Select your environment to verify KVM acceleration and launch the containerized emulator.</p>
        </div>
        <ShellSnippet
          prefix="$"
          tabs={[
            ...(hostOs === "linux" || !hostOs ? [{ id: "linux", label: "Linux (native)", command: "./labctl android doctor && ./labctl android start --wait", explanation: "Checks KVM, the container runtime, ports and disk, then starts the stack and waits for the emulator." }] : []),
            { id: "static", label: hostOs === "macos" ? "Static analysis" : "No KVM (static)", command: "./labctl android profile use lightweight && ./labctl android start", explanation: "Runs only MobSF, mitmproxy and the tools container: everything WF1 needs, without an emulator." },
            ...(hostOs === "windows" || !hostOs ? [{ id: "windows", label: "Windows", command: "./lab.ps1 setup; ./lab.ps1 start", explanation: "Zero-admin Windows runtime; see README-WINDOWS.md for the VirtualBox and WSL2 options." }] : []),
            ...(adbFound ? [{ id: "adb", label: "ADB Control", command: "adb connect 127.0.0.1:5555 && adb devices", explanation: "Attach to the emulator over TCP for instrumentation and Frida injection." }] : [])
          ]}
        />
      </section>

      <Section icon={<UploadSimpleIcon size={16} />} title="Target APK Project" description="Upload a package or select one already staged for decompilation.">
        <ApkTarget />
      </Section>

      <section className="space-y-3">
        <div>
          <h2 className="text-base font-semibold">Quick pipeline launch</h2>
          <p className="text-xs text-(--iux-muted-foreground)">Common first steps. Output streams to Execution &amp; Logs.</p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {["preflight", "create-sample", "wf1", "scan-secrets"].map((id) => (
            <ActionTile key={id} id={id} />
          ))}
        </div>
      </section>

      <SegmentationBento
        badgeLabel="Lab Architecture"
        headline="End-to-End Mobile Pentest Pipeline"
        subtitle="From static bytecode decompilation to runtime hooking and live telemetry interception."
        ctaText="View Execution Workflows"
        onCtaClick={() => window.location.assign(localePath("/android/workflows/", localeFromPath(window.location.pathname)))}
      />

      <TipsNotesCard
        quote="Containerizing the Android emulator with hardware KVM passthrough gives fully reproducible mobile testing environments, so agents can run end-to-end reverse engineering without a physical device farm."
        authorName="Mobile OS Lab Guideline"
        authorRole="knowledge/segmentation.md"
        companyName="Android Lab"
      />
    </Frame>
  );
}

// ── Code & Providers ───────────────────────────────────────────────────

export function ProvidersPage() {
  const devices = useDevices();
  const hooks = usePoll(api.hooks, 0, []);
  const [apk] = useApk();
  return (
    <Frame id="providers" title="Code & Providers">
      <PageHead
        icon={<PlugsConnectedIcon size={22} />}
        title="Code & target providers"
        description="Where the lab gets its targets: attached ADB devices, staged APKs, the emulator stack's endpoints and the bundled Frida hooks."
        actions={
          <button type="button" className="iux-btn" data-variant="outline" onClick={devices.reload}>
            <ArrowClockwiseIcon size={14} /> Refresh devices
          </button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Section icon={<DeviceMobileIcon size={16} />} title="Connected devices (ADB)" description={<>Output of <code>adb devices</code> on this host.</>}>
          {!devices.loaded ? (
            <Skeleton rows={2} />
          ) : devices.list.length === 0 ? (
            <Empty>{devices.raw && !/List of devices/.test(devices.raw) ? devices.raw.trim() : "No devices attached. Start the lab or run adb connect 127.0.0.1:5555."}</Empty>
          ) : (
            <ul className="divide-y divide-(--iux-border)">
              {devices.list.map((d) => (
                <li key={d.serial} className="flex items-center gap-3 py-2.5">
                  <DeviceMobileIcon size={16} className="text-[#f36c21]" />
                  <span className="flex-1 font-mono text-sm">{d.serial}</span>
                  <Badge tone={d.state === "device" ? "success" : "warning"}>{d.state}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <details className="iux-card p-5">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
            <CpuIcon size={16} className="text-[#f36c21]" /> Emulator stack endpoints
          </summary>
          <p className="mt-2 text-sm text-(--iux-muted-foreground)">Published when the dynamic stack runs (<a className="underline" href={labHref("android")}>Runtime &amp; setup</a>).</p>
          <div className="mt-4"><EndpointList items={ANDROID_ENDPOINTS} /></div>
        </details>
      </div>
      <Section icon={<UploadSimpleIcon size={16} />} title="Target APK" description="Upload a package or enter a path on disk.">
        <ApkTarget />
      </Section>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Frida hooks</h2>
        {hooks.error ? (
          <Status value={{ ok: false, text: hooks.error }} />
        ) : !hooks.data ? (
          <Skeleton rows={3} />
        ) : hooks.data.hooks.length === 0 ? (
          <Empty>No hooks found in android-lab/lab/hooks/.</Empty>
        ) : (
          <CodeShowcaseSwitcher
            items={hooks.data.hooks.map((h) => ({
              id: h.name,
              title: h.name.replace(/\.js$/, ""),
              description: `hooks/${h.name}`,
              filename: h.name,
              code: h.code,
              language: "javascript"
            }))}
          />
        )}
      </section>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">ADB &amp; Frida commands</h2>
        <ShellSnippet
          tabs={[
            { id: "connect", label: "Connect", command: "adb connect 127.0.0.1:5555", explanation: "Attach to the containerized emulator over TCP." },
            { id: "install", label: "Install APK", command: `make -C android-lab/lab install APK=${apk}`, explanation: "Push the current target APK into the emulator." },
            { id: "hook", label: "Frida hook", command: "make -C android-lab/lab hook PKG=com.example.app HOOK=hooks/ssl-pinning-bypass.js", explanation: "Spawn the app with a bundled hook from hooks/." }
          ]}
        />
      </section>
    </Frame>
  );
}

// ── Workflows & DAG ────────────────────────────────────────────────────

const ORBITAL_NODES = [
  { id: "o1", title: "1. Static Bytecode Decompilation", description: "JADX and the manifest audit extract exported components, permissions and hard-coded secrets.", linkText: "Run WF1", linkHref: "#all-actions" },
  { id: "o2", title: "2. KVM Containerized Boot", description: "Docker-Android starts with KVM passthrough, ADB on 5555 and a noVNC screen on 6080.", linkText: "Runtime & setup", linkHref: "/labs/android/" },
  { id: "o3", title: "3. Frida Runtime Hook Injection", description: "Hooks from hooks/ bypass root detection and certificate pinning inside the ART runtime.", linkText: "Hooks", linkHref: "/android/providers/" },
  { id: "o4", title: "4. Network Interception & Telemetry", description: "mitmproxy records traffic to artifacts/flows.mitm; findings render into HTML reports.", linkText: "Reports", linkHref: "/android/analytics/" }
];
const STATIC_STEPS = [
  { id: "s1", title: "Step 1: APK ingestion", description: "Resolve the target and create a per-APK folder under artifacts/." },
  { id: "s2", title: "Step 2: JADX decompilation & manifest parsing", description: "Disassemble DEX to Java and extract permissions and exported IPC components." },
  { id: "s3", title: "Step 3: OWASP MASVS rule audit", description: "Flag weak cryptography, debuggable builds, cleartext traffic and hard-coded secrets." },
  { id: "s4", title: "Step 4: Report", description: "Write static-report.md and static-manifest-analysis.json and render the HTML report." }
];
const DYNAMIC_STEPS = [
  { id: "d1", title: "Step 1: Install APK", description: "Push the target into the running Docker-Android emulator over ADB." },
  { id: "d2", title: "Step 2: Route traffic through mitmproxy", description: "Point the emulator's proxy at the mitmproxy container; flows stream to artifacts/flows.mitm." },
  { id: "d3", title: "Step 3: Launch the package", description: "Start the target app when a package name is given." },
  { id: "d4", title: "Step 4: Frida server", description: "Start frida-server in the rooted emulator so hooks can attach." }
];

export function WorkflowsPage() {
  const [mode, setMode] = useState<"static" | "dynamic">("static");
  const [apk] = useApk();
  const { error } = useRun();
  const tab = (id: "static" | "dynamic", icon: React.ReactNode, label: string) => (
    <button
      type="button"
      onClick={() => setMode(id)}
      className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-all ${
        mode === id ? "bg-[#f36c21] text-white shadow-sm" : "border border-(--iux-border) bg-(--iux-card) text-(--iux-muted-foreground) hover:text-(--iux-foreground)"
      }`}
    >
      {icon}
      {label}
    </button>
  );
  return (
    <Frame id="workflows" title="Agentic Workflows & DAG">
      <PageHead
        icon={<TreeStructureIcon size={22} />}
        title="Agentic Orchestration & Workflows"
        description="Multi-phase pipelines for autonomous mobile penetration testing and reverse engineering."
        actions={<RunButton action="wf1" label="Execute Pipeline" variant="brand" />}
      />
      <Status value={error ? { ok: false, text: error } : null} />
      <section className="space-y-3">
        <h2 className="text-sm font-semibold tracking-wider text-(--iux-muted-foreground) uppercase">Autonomous Agent Lifecycle (DAG)</h2>
        <OrbitalWorkflowDag nodes={ORBITAL_NODES} />
      </section>
      <section className="space-y-6">
        <div className="flex flex-wrap items-center gap-3 border-b border-(--iux-border) pb-3">
          {tab("static", <ShieldCheckIcon size={16} />, "Workflow 1: Static Bytecode & Manifest Audit")}
          {tab("dynamic", <CpuIcon size={16} />, "Workflow 2: Dynamic Runtime & Frida Analysis")}
        </div>
        {mode === "static" ? (
          <WorkflowStepper title="Static Bytecode Audit Workflow" steps={STATIC_STEPS} />
        ) : (
          <>
            <WorkflowStepper title="Dynamic Runtime Analysis Workflow" steps={DYNAMIC_STEPS} />
            <ShellSnippet
              tabs={[{ id: "wf2", label: "WF2", command: `make -C android-lab/lab wf2 APK=${apk} PKG=com.example.app`, explanation: "Needs the emulator stack (Runtime & setup → Start). Deploys the APK, routes traffic through mitmproxy and starts frida-server." }]}
              showTabs={false}
            />
          </>
        )}
      </section>
      <Section icon={<UploadSimpleIcon size={16} />} title="Target" description="Every action below runs on this APK.">
        <ApkTarget />
      </Section>
      <section id="all-actions" className="space-y-3">
        <h2 className="text-sm font-semibold">All actions</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Object.keys(ACTIONS).map((id) => (
            <ActionTile key={id} id={id} />
          ))}
        </div>
      </section>
    </Frame>
  );
}

// ── Execution & Logs ───────────────────────────────────────────────────

export function ConsolePage() {
  const { data } = androidLogsStore.use();
  const running = Boolean(data?.running);
  const jobs = useMemo(() => parseJobs(data?.logs ?? [], running), [data, running]);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState<string | null>(null);
  const lines = (data?.logs ?? []).map((l) => l.replace(/^\n+|\n+$/g, "")).filter((l, i) => l || i > 0);
  return (
    <Frame id="console" title="Execution & Progress Console">
      <PageHead
        icon={<TerminalIcon size={22} />}
        title="Execution Engine & Progress Console"
        description="Live output of workbench jobs (WF1, scanners, fuzzer, patcher, playbooks) and their outcome."
        actions={
          <>
            {running ? (
              <button
                type="button"
                onClick={async () => {
                  try {
                    await api.stop();
                    setStatus({ ok: true, text: "Stop requested" });
                  } catch (e) {
                    setStatus({ ok: false, text: message(e) });
                  }
                }}
                className="iux-touch-target flex items-center gap-1.5 rounded-lg border border-red-500/50 bg-red-500/10 px-3.5 py-1.5 text-xs font-semibold text-red-400 transition-colors hover:bg-red-500/20"
              >
                <StopIcon size={14} weight="fill" /> Stop job
              </button>
            ) : (
              <a href="/android/workflows/" className="iux-touch-target flex items-center gap-1.5 rounded-lg bg-[#00d084] px-3.5 py-1.5 text-xs font-semibold text-zinc-950 transition-colors hover:bg-[#00d084]/90">
                <PlayIcon size={14} weight="fill" /> New run
              </a>
            )}
            <button
              type="button"
              className="iux-btn"
              data-variant="outline"
              disabled={running || clearing}
              onClick={async () => {
                setClearing(true);
                setStatus(null);
                setClearError(null);
                try {
                  await api.clearLogs();
                  await androidLogsStore.refresh();
                  setStatus({ ok: true, text: "Logs cleared." });
                } catch (error) {
                  setClearError(message(error));
                } finally {
                  setClearing(false);
                }
              }}
            >
              <TrashIcon size={14} /> {clearing ? "Clearing…" : "Clear"}
            </button>
          </>
        }
      />
      <Status value={status} />
      {clearError ? <p role="alert" className="text-sm text-(--iux-danger)"><span>Could not clear logs:</span> <span data-no-translate>{clearError}</span>. <span>Try again.</span></p> : null}
      <ProgressConsoleReport
        title="Execution Pipeline Status"
        description="Jobs started from this console, newest first. Output streams below as it arrives."
        stages={
          jobs.length
            ? jobs
                .slice(-6)
                .reverse()
                .map((j) => ({
                  id: j.id,
                  version: j.title,
                  updatedAt: `${j.lines} lines`,
                  status: j.status === "running" ? "Running" : j.status === "ok" ? "Deployed" : "Failed"
                }))
            : [{ id: "none", version: "No jobs yet", updatedAt: "start one from Workflows", status: "Queued" }]
        }
        logs={lines.length ? lines : ["Waiting for commands…"]}
        streaming={running}
      />
      <section className="space-y-4 rounded-2xl border border-(--iux-border) bg-(--iux-card) p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DeviceMobileIcon size={20} className="text-[#f36c21]" />
            <h2 className="text-sm font-semibold">Visual Screen Debugging (noVNC)</h2>
          </div>
          <a href="http://127.0.0.1:6080/" target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-[#2563eb] hover:underline">
            Open in Fullscreen <ArrowSquareOutIcon size={13} />
          </a>
        </div>
        <div className="relative flex aspect-video w-full flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-black/80 p-6 text-center">
          <div className="mb-3 flex size-14 items-center justify-center rounded-2xl border border-zinc-700 bg-zinc-900 text-[#f36c21]">
            <DeviceMobileIcon size={32} />
          </div>
          <h3 className="text-sm font-semibold text-white">Emulator display stream</h3>
          <p className="mt-1 max-w-md text-xs text-zinc-400">Served by the emulator container on port 6080 once the dynamic stack is running.</p>
          <a href={labHref("android")} className="mt-4 inline-flex items-center gap-1 rounded-full bg-[#00d084]/15 px-2.5 py-1 text-xs font-medium text-[#00d084]">
            <CircleIcon size={8} weight="fill" /> Runtime &amp; setup
          </a>
        </div>
      </section>
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Troubleshooting &amp; Terminal Diagnosis</h2>
        <ShellSnippet
          tabs={[
            { id: "status", label: "Lab status", command: "./labctl android status", explanation: "Containers, endpoints, CPU/RAM and device readiness in one report." },
            { id: "logs", label: "Tail emulator logs", command: "./labctl android logs -f", explanation: "Follows the emulator container's output to confirm KVM and ADB came up." },
            { id: "logcat", label: "Filtered logcat", command: "adb logcat -v time | grep -i frida", explanation: "Android system log filtered to Frida instrumentation messages." }
          ]}
        />
      </section>
    </Frame>
  );
}

// ── Analytics ──────────────────────────────────────────────────────────

export function AnalyticsPage() {
  const { data } = androidLogsStore.use();
  const reports = usePoll(api.reports, 0, []);
  const jobs = useMemo(() => parseJobs(data?.logs ?? [], Boolean(data?.running)), [data]);
  const done = jobs.filter((j) => j.status !== "running");
  const ok = done.filter((j) => j.status === "ok").length;
  const wasRunning = Boolean(data?.running);
  useEffect(() => {
    if (!wasRunning) reports.reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wasRunning]);
  return (
    <Frame id="analytics" title="Security Analytics">
      <PageHead
        icon={<ChartBarIcon size={22} />}
        title="Analytics & reports"
        description="Outcomes of this session's runs and the security reports generated so far."
        actions={
          <button type="button" className="iux-btn" data-variant="outline" onClick={reports.reload}>
            <ArrowClockwiseIcon size={14} /> Refresh
          </button>
        }
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi icon={<TerminalIcon size={14} />} label="Jobs run" value={jobs.length} sub="this console session" />
        <Kpi icon={<CheckCircleIcon size={14} />} label="Passed" value={ok} sub={done.length ? `${Math.round((ok / done.length) * 100)}% of finished jobs` : "no finished jobs"} />
        <Kpi icon={<WarningCircleIcon size={14} />} label="Failed" value={done.length - ok} sub="non-zero exit or error" />
        <Kpi icon={<FileTextIcon size={14} />} label="Reports" value={reports.data ? reports.data.reports.length : "…"} sub="HTML files in artifacts/" />
      </div>
      <Section icon={<FileTextIcon size={16} />} title="Generated security reports" description={<>HTML reports written under <code>artifacts/</code>.</>} action={<RunButton action="wf1" variant="outline" />}>
        {reports.error ? (
          <Status value={{ ok: false, text: reports.error }} />
        ) : !reports.data ? (
          <Skeleton rows={2} />
        ) : reports.data.reports.length === 0 ? (
          <Empty>No reports generated yet. Run WF1 first.</Empty>
        ) : (
          <ul className="divide-y divide-(--iux-border)">
            {reports.data.reports.map((r) => (
              <li key={r.url} className="flex items-center gap-3 py-2.5">
                <FileTextIcon size={16} className="text-[#f36c21]" />
                <span className="min-w-0 flex-1 truncate font-mono text-[13px]" title={r.name}>
                  {r.name}
                </span>
                <a className="iux-btn" data-variant="outline" href={r.url} target="_blank" rel="noreferrer">
                  <ArrowSquareOutIcon size={14} /> Open
                </a>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Frame>
  );
}

// ── Routes & Sitemap ───────────────────────────────────────────────────

export function SitemapPage() {
  const { data } = hostStore.use();
  const routes = useMemo<RouteEntry[]>(
    () => [
      ...ANDROID_ENDPOINTS.map((e) => ({
        id: `android-${e.label}`,
        destination: e.address,
        type: (/^https?:/.test(e.address) ? "Hostname" : "System") as RouteEntry["type"],
        connector: "Android Lab",
        description: `${e.label} on the Docker-Android stack`,
        connectorType: "source" as const
      })),
      ...(data?.labs ?? [])
        .filter((l) => l.id !== "android" && l.state !== "unavailable")
        .map((l) => ({
          id: l.id,
          destination: `/labs/${l.id}/`,
          type: "Tunnel" as const,
          connector: l.label,
          description: `${l.provider ?? ""} · ${l.state}`,
          connectorType: "mesh" as const
        }))
    ],
    [data]
  );
  return (
    <Frame id="sitemap" title="Routes & Sitemap">
      <PageHead
        icon={<MapTrifoldIcon size={22} />}
        title="Routes & capability sitemap"
        description="Every page, workflow, endpoint and lab of the console, and where it leads."
        actions={<RunButton action="analyze" variant="brand" />}
      />
      <SitemapGrid
        categories={[
          {
            id: "targets",
            name: "Targets",
            items: [
              { id: "upload", title: "Upload APK", description: "Stage a package into apks/", icon: <UploadSimpleIcon size={16} />, href: "/android/" },
              { id: "adb", title: "ADB devices", description: "Emulators and phones on this host", icon: <DeviceMobileIcon size={16} />, href: "/android/providers/" },
              { id: "hooks", title: "Frida hooks", description: "Bundled hook scripts", icon: <CodeIcon size={16} />, href: "/android/providers/" }
            ]
          },
          {
            id: "workflows",
            name: "Workflows",
            items: [
              { id: "wf1", title: "WF1 static audit", description: "JADX, manifest and MASVS rules", icon: <ShieldCheckIcon size={16} />, href: "/android/workflows/", badge: "Core" },
              { id: "wf2", title: "WF2 dynamic", description: "Emulator, mitmproxy and Frida", icon: <CpuIcon size={16} />, href: "/android/workflows/" },
              { id: "runtime", title: "Runtime & setup", description: "Start, stop and install dependencies", icon: <TreeStructureIcon size={16} />, href: "/labs/android/" }
            ]
          },
          {
            id: "observe",
            name: "Observe",
            items: [
              { id: "console", title: "Execution & logs", description: "Live workbench output", icon: <TerminalIcon size={16} />, href: "/android/console/" },
              { id: "analytics", title: "Analytics", description: "Run outcomes and reports", icon: <ChartBarIcon size={16} />, href: "/android/analytics/" },
              { id: "jobs", title: "Lab jobs", description: "Lifecycle and setup jobs", icon: <ListChecksIcon size={16} />, href: "/jobs/" }
            ]
          },
          {
            id: "platforms",
            name: "Platforms",
            items: (["ios", "windows", "macos", "linux"] as const).map((id) => {
              const lab = data?.labs.find((l) => l.id === id);
              return {
                id,
                title: lab?.label ?? id,
                description: lab ? `${lab.state}${lab.provider ? ` · ${lab.provider}` : ""}` : "…",
                icon: LAB_ICON[id](16),
                href: labHref(id),
                badge: lab?.state === "ready" ? "Ready" : undefined
              };
            })
          }
        ]}
      />
      <RoutesTopologyGraph title="Lab routes" description="Service endpoints of the Android stack and the other labs available on this computer." routes={routes} />
    </Frame>
  );
}
