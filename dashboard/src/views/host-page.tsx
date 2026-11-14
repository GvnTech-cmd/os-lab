/** "/" — this computer: OS and hardware, which labs it can run, missing dependencies and host tools. */
import {
  ArrowClockwiseIcon,
  CheckCircleIcon,
  CpuIcon,
  DesktopTowerIcon,
  HardDrivesIcon,
  LightningIcon,
  MemoryIcon,
  PackageIcon,
  WarningCircleIcon,
  XCircleIcon
} from "@phosphor-icons/react";
import { useState } from "react";
import { AppShell, LAB_ICON, labHref } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { MinimalistHero } from "../apk-lab/components";
import { Badge, Empty, IconButton, Modal, Skeleton } from "../components/ui";
import { AppUpdatePanel } from "./app-update-panel";
import { ContentPanel } from "./content-panel";
import { localeFromPath, localePath } from "../i18n/paths";
import { formatBytes, hostStore, type HostInfo, type LabStatus } from "../lib/api";

const PROVIDER_LABEL: Record<string, string> = {
  "native-macos": "Native on this Mac",
  "macos-containers": "Containers on this Mac",
  "linux-containers": "Containers on Linux",
  wsl2: "Inside WSL2"
};

export function stateBadge(state: LabStatus["state"]) {
  if (state === "ready") return <Badge tone="success">Ready</Badge>;
  if (state === "needs-setup") return <Badge tone="warning">Needs setup</Badge>;
  return <Badge>Unavailable</Badge>;
}

function Stat({ icon, label, value, sub, tone }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub: React.ReactNode; tone?: "ok" | "warn" }) {
  return (
    <div className="iux-card gap-1 px-5 py-4">
      <span className="flex items-center gap-1.5 text-xs text-(--iux-muted-foreground)">
        {icon}
        {label}
      </span>
      <span
        className={`text-2xl font-bold tracking-tight tabular-nums ${tone === "warn" ? "text-(--iux-warning)" : tone === "ok" ? "text-(--iux-success)" : ""}`}
      >
        {value}
      </span>
      <span className="truncate text-xs text-(--iux-muted-foreground)">{sub}</span>
    </div>
  );
}

function LabCard({ lab }: { lab: LabStatus }) {
  const missing = lab.requirements.filter((r) => r.required && !r.found);
  const appiumMissing = lab.provider === "native-macos" && lab.requirements.some((r) => r.id === "appium" && !r.found);
  const setupAvailable = lab.actions.some((a) => a.id === "setup");
  const href = labHref(lab.id);
  return (
    <div
      className={`apk-crosshair-box iux-card gap-3 p-5 transition-colors hover:border-[#f36c21]/40 ${lab.state === "unavailable" ? "opacity-70" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex size-9 items-center justify-center rounded-md border border-(--iux-border) bg-(--iux-muted) text-[#f36c21]">
          {LAB_ICON[lab.id](18)}
        </span>
        {stateBadge(lab.state)}
      </div>
      <div>
        <h3 className="text-sm font-semibold">{lab.label}</h3>
        <p className="mt-1 text-xs leading-relaxed text-(--iux-muted-foreground)">{lab.summary}</p>
      </div>
      {lab.provider ? (
        <p className="text-xs text-(--iux-muted-foreground)">{PROVIDER_LABEL[lab.provider] ?? lab.provider}</p>
      ) : null}
      {lab.reasons.length > 0 && (
        <ul className="space-y-1 text-xs">
          {lab.reasons.map((r) => (
            <li key={r} className="flex gap-1.5 text-(--iux-muted-foreground)">
              <WarningCircleIcon size={14} className="mt-px shrink-0 text-(--iux-warning)" />
              {r}
            </li>
          ))}
        </ul>
      )}
      {lab.notes.length > 0 && (
        <ul className="space-y-1 text-xs text-(--iux-muted-foreground)">
          {lab.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      <div className="mt-auto flex flex-wrap gap-2 pt-1">
        <a className="iux-btn" data-variant={lab.state === "ready" ? "primary" : "outline"} href={href}>
          {lab.state === "needs-setup" ? "View requirements" : "Open"}
        </a>
        {(missing.length > 0 || appiumMissing) && setupAvailable ? (
          <a className="iux-btn bg-[#f36c21] text-white hover:bg-[#fa7b32]" href={`${href}#action=${appiumMissing && missing.length === 0 ? "appium-install" : "setup"}`}>
            {appiumMissing && missing.length === 0 ? "Install Appium" : "Install dependencies"}
          </a>
        ) : null}
      </div>
    </div>
  );
}

function Tools({ host }: { host: HostInfo }) {
  return (
    <ul className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
      {host.tools.map((tool) => (
        <li key={tool.id} className="flex items-center gap-2.5 border-b border-(--iux-border) py-2 text-sm">
          {tool.found ? (
            <CheckCircleIcon size={16} weight="fill" className="shrink-0 text-(--iux-success)" />
          ) : (
            <XCircleIcon size={16} className="shrink-0 text-(--iux-muted-foreground)" />
          )}
          <span className="min-w-0 flex-1 truncate">{tool.label}</span>
          <span className="max-w-[45%] truncate font-mono text-[11px] text-(--iux-muted-foreground)" title={tool.path ?? ""}>
            {tool.path ?? "not found"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function HostPage() {
  const { data, error, refresh } = hostStore.use();
  const host = data?.host;
  const labs = data?.labs ?? [];
  // Host tools and providers open on demand instead of stacking two long cards on the page.
  const [toolsOpen, setToolsOpen] = useState(false);
  const [providersOpen, setProvidersOpen] = useState(false);
  const ready = labs.filter((l) => l.state === "ready").length;
  const hostLab = host?.os === "windows" ? "windows" : host?.os === "macos" ? "macos" : host?.os === "linux" ? "linux" : null;
  const stateOrder = { ready: 0, "needs-setup": 1, unavailable: 2 };
  const orderedLabs = labs.map((lab, index) => ({ lab, index })).sort((a, b) =>
    stateOrder[a.lab.state] - stateOrder[b.lab.state] ||
    Number(b.lab.id === hostLab) - Number(a.lab.id === hostLab) || a.index - b.index
  );
  // Labs this computer cannot run are not cards: one line says where they run instead.
  const runnableLabs = orderedLabs.filter(({ lab }) => lab.state !== "unavailable");
  const elsewhereLabs = orderedLabs.filter(({ lab }) => lab.state === "unavailable").map(({ lab }) => lab);
  const setupLab = orderedLabs.find(({ lab }) => lab.state === "needs-setup" && lab.actions.some((a) => a.id === "setup"))?.lab;
  const primaryLab = orderedLabs.find(({ lab }) => lab.state === "ready")?.lab;
  const iosSimulatorReady = !!(host?.xcode?.installed && host.xcode.iosRuntime && host.xcode.iosDevice);
  const virtualization = host?.os === "macos"
    ? { label: "iOS Simulator", value: iosSimulatorReady ? "Available" : "Needs setup", sub: "Xcode on this Mac", ok: iosSimulatorReady }
    : host?.os === "windows"
      ? { label: "WSL2", value: host.wsl.distributions.length, sub: "installed distributions", ok: host.wsl.distributions.length > 0 }
      : { label: "KVM", value: host?.kvm.usable ? "Usable" : host?.kvm.present ? "Denied" : "Absent", sub: host?.kvm.present && !host?.kvm.usable ? "join the kvm group" : "/dev/kvm", ok: !!host?.kvm.usable };
  const containerCliInstalled = !!host?.tools.some((tool) => (tool.id === "docker" || tool.id === "podman") && tool.found);
  return (
    <AppShell activeId="host">
      <div className="iux min-h-screen">
        <TopBar title="This computer" icon={<DesktopTowerIcon size={20} weight="duotone" />} />
        <main className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-8 sm:px-6">
          {error && !host ? (
            <Empty>Could not reach the lab engine: {error}. Is web_ui.py running?</Empty>
          ) : !host ? (
            <Skeleton rows={6} />
          ) : (
            <>
              <MinimalistHero
                badgeText={`${host.os} · ${host.arch}`}
                headline={host.osPretty}
                description={`${ready} of ${runnableLabs.length} labs can run on ${host.hostname || "this computer"} right now. Labs that need setup list what is missing, and Install dependencies previews exactly what will change before anything runs.`}
                primaryCtaText={setupLab ? `Set up ${setupLab.label}` : primaryLab ? `Open ${primaryLab.label}` : "View lab requirements"}
                primaryCtaHref={setupLab ? `${labHref(setupLab.id)}#action=setup` : primaryLab ? labHref(primaryLab.id) : "#labs"}
                secondaryCtaText="View jobs"
                secondaryCtaHref="/jobs/"
                illustration={
                  <div className="flex size-24 items-center justify-center rounded-3xl border border-dashed border-[#f36c21]/60 bg-[#f36c21]/10 text-[#f36c21]">
                    <DesktopTowerIcon size={48} weight="duotone" />
                  </div>
                }
              />

              <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
                <Stat icon={<CpuIcon size={14} />} label="CPU" value={host.cpus ?? "—"} sub="logical cores" />
                <Stat icon={<MemoryIcon size={14} />} label="Memory" value={formatBytes(host.memory)} sub="installed RAM" />
                <Stat
                  icon={<HardDrivesIcon size={14} />}
                  label="Disk free"
                  value={formatBytes(host.disk?.free)}
                  sub={`of ${formatBytes(host.disk?.total)} at the checkout`}
                  tone={host.disk && host.disk.free < 40 * 1024 ** 3 ? "warn" : undefined}
                />
                <Stat
                  icon={<LightningIcon size={14} />}
                  label={virtualization.label}
                  value={virtualization.value}
                  sub={virtualization.sub}
                  tone={virtualization.ok ? "ok" : "warn"}
                />
                <Stat
                  icon={<PackageIcon size={14} />}
                  label="Containers"
                  value={host.runtime ?? "None"}
                  sub={host.runtime ? "engine and Compose available" : containerCliInstalled ? "start engine and check Compose" : "install Docker or Podman"}
                  tone={host.runtime ? "ok" : "warn"}
                />
                <Stat
                  icon={<DesktopTowerIcon size={14} />}
                  label="Python"
                  value={host.python}
                  sub={host.wsl.guest ? "inside WSL2" : "console runtime"}
                />
              </div>

              <section id="labs" className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-base font-semibold">Labs on this computer</h2>
                      <p className="text-xs text-(--iux-muted-foreground)">
                        Availability follows this host's OS, architecture, KVM and tools. Labs that cannot run here are left out.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <IconButton label="Host tools" onClick={() => setToolsOpen(true)}>
                        <PackageIcon size={14} />
                      </IconButton>
                      <IconButton label="Providers" onClick={() => setProvidersOpen(true)}>
                        <CpuIcon size={14} />
                      </IconButton>
                      <button type="button" className="iux-btn" data-variant="outline" onClick={() => void refresh()}>
                        <ArrowClockwiseIcon size={14} /> Re-detect
                      </button>
                    </div>
                  </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {runnableLabs.map(({ lab }) => (
                    <LabCard key={lab.id} lab={lab} />
                  ))}
                </div>
                {elsewhereLabs.length > 0 ? (
                  <p className="text-xs text-(--iux-muted-foreground)">
                    Labs that do not run on this computer: {elsewhereLabs.map((lab) => lab.label).join(", ")}.{" "}
                    <a className="underline" href={localePath("/health/", typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname))}>
                      See what each platform supports
                    </a>
                    .
                  </p>
                ) : null}
              </section>

              {toolsOpen ? (
                <Modal title="Host tools" icon={<PackageIcon size={16} />} description={`Found on PATH for ${host.root}.`} onClose={() => setToolsOpen(false)}>
                  <Tools host={host} />
                </Modal>
              ) : null}

              <AppUpdatePanel />

              <ContentPanel />

              {providersOpen ? (
                <Modal title="Providers" icon={<CpuIcon size={16} />} description="How each kind of guest would run on this host." onClose={() => setProvidersOpen(false)}>
                  <ul className="divide-y divide-(--iux-border)">
                    {host.providers.map((p) => (
                      <li key={p.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                        <span className="w-44 shrink-0 font-mono text-xs">{p.id}</span>
                        <span className="min-w-0 flex-1">
                          {p.guest}
                          <span className="block text-xs text-(--iux-muted-foreground)">{p.requirements}</span>
                        </span>
                        {p.candidate ? <Badge tone="success">Candidate</Badge> : <Badge>Not on this host</Badge>}
                      </li>
                    ))}
                  </ul>
                </Modal>
              ) : null}
            </>
          )}
        </main>
      </div>
    </AppShell>
  );
}
