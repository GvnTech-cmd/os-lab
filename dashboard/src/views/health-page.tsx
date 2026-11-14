/** /health/ — is the lab engine up, what is wrong on this computer, and what os-lab supports on Windows, macOS and Linux. */
import { useMemo, useState } from "react";
import {
  ArrowClockwiseIcon,
  CaretRightIcon,
  CheckCircleIcon,
  HeartbeatIcon,
  MinusCircleIcon,
  WarningCircleIcon,
  XCircleIcon
} from "@phosphor-icons/react";
import { AppShell, LAB_ICON, labHref } from "../shell/app-shell";
import { TopBar } from "../shell/top-bar";
import { Badge, CopyButton, Empty, Section, Skeleton } from "../components/ui";
import { ago, api, contentStore, formatBytes, healthStore, hostStore, usePoll, type LabStatus } from "../lib/api";
import {
  LEVEL_LABEL,
  hostPlatform,
  summarize,
  type Capability,
  type CapabilityCatalog,
  type CapabilityGroup,
  type Level,
  type PlatformId,
  type Support
} from "../health/capabilities";

type CheckState = "ok" | "warn" | "fail" | "idle";
interface Check {
  id: string;
  label: string;
  state: CheckState;
  detail: string;
  fix?: string;
  helpUrl?: string;
  helpLabel?: string;
}

const STATE_ICON: Record<CheckState, React.ReactNode> = {
  ok: <CheckCircleIcon size={18} weight="fill" className="text-(--iux-success)" />,
  warn: <WarningCircleIcon size={18} weight="fill" className="text-(--iux-warning)" />,
  fail: <XCircleIcon size={18} weight="fill" className="text-red-500" />,
  idle: <MinusCircleIcon size={18} className="text-(--iux-muted-foreground)" />
};

const LEVEL_TONE: Record<Level, "success" | "warning" | undefined> = { full: "success", partial: "warning", none: undefined };
const LEVEL_DOT: Record<Level, string> = { full: "bg-(--iux-success)", partial: "bg-(--iux-warning)", none: "bg-(--iux-muted-foreground)/40" };

function LevelBadge({ level }: { level: Level }) {
  return <Badge tone={LEVEL_TONE[level]}>{LEVEL_LABEL[level]}</Badge>;
}

function LiveChip({ lab }: { lab: LabStatus | undefined }) {
  if (!lab) return null;
  if (lab.state === "ready") return <Badge tone="success">Ready on this computer</Badge>;
  if (lab.state === "needs-setup") return <Badge tone="warning">Needs setup on this computer</Badge>;
  return <Badge>Unavailable on this computer</Badge>;
}

function Node({
  title,
  support,
  summary,
  lab,
  live,
  icon,
  children,
  forceOpen
}: {
  title: string;
  support: Support;
  summary?: string;
  lab?: LabStatus;
  live?: boolean;
  icon?: React.ReactNode;
  children?: React.ReactNode;
  forceOpen?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const expandable = Boolean(children) || Boolean(lab && (lab.reasons.length || lab.requirements.length));
  const isOpen = (open || forceOpen) && expandable;
  return (
    <li>
      <button
        type="button"
        className="flex w-full items-start gap-3 rounded-md px-2 py-2.5 text-left transition-colors hover:bg-(--iux-muted) disabled:cursor-default disabled:hover:bg-transparent"
        onClick={() => setOpen(!open)}
        disabled={!expandable}
        aria-expanded={expandable ? isOpen : undefined}
      >
        <span className="mt-1 flex w-4 shrink-0 justify-center text-(--iux-muted-foreground)">
          {expandable ? <CaretRightIcon size={12} weight="bold" className={`transition-transform ${isOpen ? "rotate-90" : ""}`} /> : <span className={`size-2 rounded-full ${LEVEL_DOT[support.level]}`} />}
        </span>
        {icon ? <span className="mt-0.5 shrink-0 text-[#f36c21]">{icon}</span> : null}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{title}</span>
            <LevelBadge level={support.level} />
            {live && support.level !== "none" ? <LiveChip lab={lab} /> : null}
          </span>
          {summary ? <span className="mt-0.5 block text-xs text-(--iux-muted-foreground)">{summary}</span> : null}
          <span className="mt-0.5 block text-xs text-(--iux-muted-foreground)">{support.note}</span>
        </span>
      </button>
      {isOpen ? <div className="ml-4 border-l border-(--iux-border) pl-3">{children}</div> : null}
    </li>
  );
}

function LiveDetail({ lab }: { lab: LabStatus }) {
  const missing = lab.requirements.filter((r) => r.required && !r.found);
  return (
    <div className="space-y-2 px-2 pb-3 text-xs">
      {lab.reasons.length > 0 && (
        <ul className="space-y-1">
          {lab.reasons.map((r) => (
            <li key={r} className="flex gap-1.5 text-(--iux-muted-foreground)">
              <WarningCircleIcon size={14} className="mt-px shrink-0 text-(--iux-warning)" />
              {r}
            </li>
          ))}
        </ul>
      )}
      {lab.requirements.length > 0 && (
        <ul className="grid gap-x-6 sm:grid-cols-2">
          {lab.requirements.map((r) => (
            <li key={r.id} className="flex items-center gap-2 border-b border-(--iux-border) py-1.5" title={r.found ? "" : r.hint}>
              {r.found ? <CheckCircleIcon size={14} weight="fill" className="text-(--iux-success)" /> : <XCircleIcon size={14} className={r.required ? "text-red-500" : "text-(--iux-muted-foreground)"} />}
              <span className="min-w-0 flex-1 truncate">{r.label}</span>
              {!r.required ? <span className="text-(--iux-muted-foreground)">optional</span> : null}
            </li>
          ))}
        </ul>
      )}
      {missing.length > 0 && lab.actions.some((a) => a.id === "setup") ? (
        <a className="iux-btn inline-flex" data-variant="outline" href={`${labHref(lab.id)}#action=setup`}>
          Install dependencies
        </a>
      ) : null}
    </div>
  );
}

function CapabilityTree({ groups, platform, hostOs, labs }: { groups: CapabilityGroup[]; platform: PlatformId; hostOs: PlatformId | null; labs: LabStatus[] }) {
  const [filter, setFilter] = useState<Level | "all">("all");
  const live = platform === hostOs;
  const byLab = useMemo(() => new Map(labs.map((l) => [l.id, l])), [labs]);
  const keep = (item: Capability) => filter === "all" || item.support[platform].level === filter;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter">
        {(["all", "full", "partial", "none"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className="iux-btn"
            data-variant={filter === value ? "primary" : "outline"}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {value === "all" ? "All" : LEVEL_LABEL[value]}
          </button>
        ))}
      </div>
      {groups.map((group) => {
        const items = group.items.filter(keep);
        if (!items.length) return null;
        return (
          <section key={group.id} aria-labelledby={`cap-${group.id}`}>
            <h3 id={`cap-${group.id}`} className="text-sm font-semibold">{group.title}</h3>
            <p className="mb-1 text-xs text-(--iux-muted-foreground)">{group.description}</p>
            <ul className="divide-y divide-(--iux-border)">
              {items.map((item) => {
                const lab = item.lab ? byLab.get(item.lab) : undefined;
                const showLive = live && Boolean(lab);
                return (
                  <Node
                    key={item.id}
                    title={item.title}
                    summary={item.summary}
                    support={item.support[platform]}
                    lab={lab}
                    live={showLive}
                    icon={item.lab ? LAB_ICON[item.lab](16) : undefined}
                  >
                    {item.children || (showLive && lab) ? (
                      <>
                        {showLive && lab ? <LiveDetail lab={lab} /> : null}
                        {item.children ? (
                          <ul>
                            {item.children.map((child) => (
                              <Node key={child.id} title={child.title} support={child.support[platform]} />
                            ))}
                          </ul>
                        ) : null}
                      </>
                    ) : null}
                  </Node>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function PlatformTabs({ catalog, hostOs, labs }: { catalog: CapabilityCatalog; hostOs: PlatformId | null; labs: LabStatus[] }) {
  const [platform, setPlatform] = useState<PlatformId>(hostOs ?? "macos");
  const selectAt = (index: number) => {
    const next = catalog.platforms[index];
    if (!next) return;
    setPlatform(next.id);
    document.getElementById(`health-platform-${next.id}`)?.focus();
  };
  const info = catalog.platforms.find((p) => p.id === platform)!;
  const counts = summarize(catalog.groups, platform);
  const total = counts.full + counts.partial + counts.none;
  return (
    <div className="space-y-4">
      <div role="tablist" aria-label="Platform" className="grid grid-cols-3 gap-2">
        {catalog.platforms.map((p) => {
          const c = summarize(catalog.groups, p.id);
          const active = p.id === platform;
          return (
            <button
              key={p.id}
              id={`health-platform-${p.id}`}
              role="tab"
              type="button"
              aria-selected={active}
              aria-controls="health-platform-panel"
              tabIndex={active ? 0 : -1}
              onClick={() => setPlatform(p.id)}
              onKeyDown={(event) => {
                const index = catalog.platforms.findIndex(item => item.id === p.id);
                const direction = document.documentElement.dir === "rtl" ? -1 : 1;
                const delta = event.key === "ArrowRight" ? direction : event.key === "ArrowLeft" ? -direction : 0;
                const next = event.key === "Home" ? 0 : event.key === "End" ? catalog.platforms.length - 1 : delta ? (index + delta + catalog.platforms.length) % catalog.platforms.length : -1;
                if (next >= 0) { event.preventDefault(); selectAt(next); }
              }}
              className={`rounded-lg border px-3 py-2.5 text-left transition-colors ${active ? "border-[#f36c21] bg-[#f36c21]/10" : "border-(--iux-border) hover:bg-(--iux-muted)"}`}
            >
              <span className="flex items-center gap-2 text-sm font-semibold">
                {p.label}
                {p.id === hostOs ? <Badge tone="success">This computer</Badge> : null}
              </span>
              <span className="mt-0.5 block text-xs text-(--iux-muted-foreground)">
                {c.full} supported · {c.partial} need setup · {c.none} not available
              </span>
            </button>
          );
        })}
      </div>
      <div className="rounded-lg border border-(--iux-border) p-3 text-xs text-(--iux-muted-foreground)">
        <div className="mb-2 flex h-2 overflow-hidden rounded-full bg-(--iux-muted)" aria-hidden="true">
          <span className="bg-(--iux-success)" style={{ width: `${(counts.full / total) * 100}%` }} />
          <span className="bg-(--iux-warning)" style={{ width: `${(counts.partial / total) * 100}%` }} />
        </div>
        <p><strong className="text-(--iux-foreground)">Installer:</strong> {info.installer}</p>
        <p><strong className="text-(--iux-foreground)">Runs labs with:</strong> {info.engine}</p>
      </div>
      <div id="health-platform-panel" role="tabpanel" aria-labelledby={`health-platform-${platform}`} tabIndex={0}>
        <CapabilityTree key={platform} groups={catalog.groups} platform={platform} hostOs={hostOs} labs={labs} />
      </div>
    </div>
  );
}

export default function HealthPage() {
  const { data: health, error: healthError, refresh: refreshHealth } = healthStore.use();
  const { data: hostData, error: hostError, refresh: refreshHost } = hostStore.use();
  const { data: content } = contentStore.use();
  const capabilities = usePoll(api.capabilities, 0);
  const host = hostData?.host;
  const labs = hostData?.labs ?? [];
  const engineUp = health?.status === "ok" && !healthError;

  const checks: Check[] = [];
  if (health || healthError) {
    checks.push({
      id: "engine",
      label: "Lab engine",
      state: engineUp ? "ok" : "fail",
      detail: engineUp ? `Running, version ${health?.version}` : `Not reachable: ${healthError ?? "no answer"}`,
      fix: engineUp ? undefined : "Restart os-lab, or run python3 android-lab/lab/web_ui.py from a terminal."
    });
  }
  if (engineUp && health) {
    checks.push({
      id: "console",
      label: "Lab console",
      state: health.console ? "ok" : "warn",
      detail: health.console ? "Lab actions (plan, start, jobs) are available" : "Only the Android workbench is available",
      fix: health.console ? undefined : "Start the engine from a full os-lab checkout or from the app."
    });
  }
  if (host) {
    const hostLab = labs.find((l) => l.state === "ready");
    const setupLab = labs.find((l) => l.state === "needs-setup" && l.requirements.some((r) => r.required && !r.found) && l.actions.some((a) => a.id === "setup"));
    const containerCli = host.tools.some((tool) => (tool.id === "docker" || tool.id === "podman") && tool.found);
    const containerHelp = host.os === "macos"
      ? { url: "https://docs.docker.com/desktop/setup/install/mac-install/", label: "Docker Desktop for Mac" }
      : host.os === "windows"
        ? { url: "https://docs.docker.com/desktop/setup/install/windows-install/", label: "Docker Desktop for Windows" }
        : { url: "https://docs.docker.com/engine/install/", label: "Docker Engine for Linux" };
    checks.push({
      id: "host",
      label: "This computer",
      state: "ok",
      detail: `${host.osPretty} · ${host.arch} · ${host.cpus ?? "?"} cores · ${formatBytes(host.memory)} RAM`
    });
    checks.push({
      id: "labs",
      label: "Labs that can run now",
      state: hostLab ? "ok" : "warn",
      detail: `${labs.filter((l) => l.state === "ready").length} of ${labs.length} ready, ${labs.filter((l) => l.state === "needs-setup").length} need setup`,
      fix: hostLab || !setupLab ? undefined : "Open a lab that needs setup and use Install dependencies."
    });
    checks.push({
      id: "runtime",
      label: "Container engine",
      state: host.runtime ? "ok" : "warn",
      detail: host.runtime ? `${host.runtime} with Compose` : "No working Docker or Podman with Compose",
      fix: host.runtime ? undefined : containerCli
        ? "Docker or Podman is installed. Start its engine (or Colima/Podman machine), then check docker compose version or podman compose version and Re-check."
        : "Install a container engine, start it, and check its Compose command. The Firewall Lab and native iOS Simulator do not need containers.",
      helpUrl: host.runtime ? undefined : containerHelp.url,
      helpLabel: host.runtime ? undefined : containerHelp.label
    });
    if (host.os === "linux") {
      checks.push({
        id: "kvm",
        label: "Hardware virtualization (KVM)",
        state: host.kvm.usable ? "ok" : "warn",
        detail: host.kvm.usable ? "/dev/kvm is usable" : host.kvm.present ? "/dev/kvm exists but you may not use it" : "/dev/kvm not found",
        fix: host.kvm.usable ? undefined : host.kvm.present ? "Add your user to the kvm group, then sign in again." : "Enable virtualization in firmware."
      });
    }
    if (host.os === "macos") {
      const ready = !!(host.xcode?.installed && host.xcode.iosRuntime && host.xcode.iosDevice);
      checks.push({
        id: "xcode",
        label: "Xcode and iOS Simulator",
        state: ready ? "ok" : "warn",
        detail: ready ? "Xcode, an iOS runtime and a device are installed" : "Xcode, an iOS runtime or a simulator device is missing",
        fix: ready ? undefined : "Install Xcode, then add an iOS runtime under Xcode > Settings > Components."
      });
    }
    if (host.os === "windows") {
      checks.push({
        id: "wsl",
        label: "WSL2",
        state: host.wsl.distributions.length ? "ok" : "warn",
        detail: host.wsl.distributions.length ? `${host.wsl.distributions.length} distribution(s) installed` : "No WSL2 distribution installed",
        fix: host.wsl.distributions.length ? undefined : "Run: wsl --install -d Ubuntu"
      });
    }
    const low = host.disk && host.disk.free < 40 * 1024 ** 3;
    checks.push({
      id: "disk",
      label: "Free disk space",
      state: low ? "warn" : "ok",
      detail: `${formatBytes(host.disk?.free)} free of ${formatBytes(host.disk?.total)}`,
      fix: low ? "VM labs need tens of gigabytes. Free some space before starting one." : undefined
    });
  } else if (hostError && engineUp) {
    checks.push({ id: "host", label: "This computer", state: "fail", detail: `Host detection failed: ${hostError}` });
  }
  if (content) {
    checks.push({
      id: "content",
      label: "Content updates",
      state: content.updateAvailable ? "warn" : "ok",
      detail: content.offline
        ? "Offline mode: using the bundled copy"
        : content.installed
          ? `Installed ${content.version ?? `#${content.sequence}`}${content.updateAvailable ? ", a newer one is available" : ", up to date"}${content.checkedAt ? ` · checked ${ago(content.checkedAt)}` : ""}`
          : "Using the content bundled with this app",
      fix: content.updateAvailable ? "Open This computer and press Update in Content updates." : undefined
    });
  }

  const bad = checks.filter((c) => c.state === "fail").length;
  const warn = checks.filter((c) => c.state === "warn").length;
  const overall: CheckState = !health && !healthError ? "idle" : bad ? "fail" : warn ? "warn" : "ok";
  const headline = { idle: "Checking…", ok: "Everything is working", warn: `${warn} thing${warn === 1 ? "" : "s"} could use attention`, fail: "The lab engine needs attention" }[overall];
  const hostOs = hostPlatform(host?.os);
  const raw = JSON.stringify({ health: health ?? null, error: healthError ?? null, host: host ?? null }, null, 2);

  return (
    <AppShell activeId="health">
      <div className="iux min-h-screen">
        <TopBar title="Health check" icon={<HeartbeatIcon size={20} weight="duotone" />} />
        <main className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6">
          <div className={`iux-card flex flex-wrap items-center gap-4 px-5 py-5 ${overall === "fail" ? "border-red-500/50" : ""}`} role="status" aria-live="polite">
            <span className="flex size-12 items-center justify-center rounded-full border border-(--iux-border) bg-(--iux-muted)">
              {STATE_ICON[overall]}
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold tracking-tight">{headline}</h2>
              <p className="text-xs text-(--iux-muted-foreground)">
                {overall === "ok"
                  ? "The engine answers and this computer can run what it advertises."
                  : overall === "fail"
                    ? "Nothing on this page is live until the engine answers."
                    : overall === "idle"
                      ? "Asking the engine…"
                      : "Details and fixes are listed below. Nothing here changes your system."}
              </p>
            </div>
            <button type="button" className="iux-btn" data-variant="outline" onClick={() => { void refreshHealth(); void refreshHost(); }}>
              <ArrowClockwiseIcon size={14} /> Re-check
            </button>
          </div>

          {!health && !healthError ? (
            <Skeleton rows={5} />
          ) : (
            <Section icon={<HeartbeatIcon size={16} />} title="Checks" description="Live, refreshed every few seconds.">
              {checks.length === 0 ? (
                <Empty>No answer from the lab engine.</Empty>
              ) : (
                <ul className="divide-y divide-(--iux-border)">
                  {checks.map((c) => (
                    <li key={c.id} className="flex items-start gap-3 py-3">
                      <span className="mt-0.5 shrink-0">{STATE_ICON[c.state]}</span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">{c.label}</span>
                        <span className="block text-xs text-(--iux-muted-foreground)">{c.detail}</span>
                        {c.fix ? <span className="mt-1 block text-xs">{c.fix}</span> : null}
                        {c.helpUrl ? <a className="mt-1 inline-block text-xs text-[#f36c21] underline" href={c.helpUrl} target="_blank" rel="noreferrer">{c.helpLabel} setup guide</a> : null}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          )}

          <Section
            icon={<HeartbeatIcon size={16} />}
            title="What os-lab supports"
            description="Pick a platform to see which labs and features it can run. Your own computer is marked and shows live status."
          >
            {capabilities.error ? <Empty>Could not load platform capabilities: {capabilities.error}</Empty>
              : capabilities.data ? <PlatformTabs catalog={capabilities.data} hostOs={hostOs} labs={labs} />
                : <Skeleton rows={5} />}
          </Section>

          <details className="iux-card px-5 py-4">
            <summary className="cursor-pointer text-sm font-medium">Technical details</summary>
            <div className="mt-3 flex items-center justify-between gap-3 text-xs text-(--iux-muted-foreground)">
              <span>
                The raw answer of <code>/api/health</code> and host detection, for bug reports.
              </span>
              <CopyButton text={raw} label="Copy details" />
            </div>
            <pre className="mt-2 max-h-80 overflow-auto rounded-md border border-(--iux-border) bg-(--iux-muted) p-3 text-xs" translate="no">{raw}</pre>
          </details>
        </main>
      </div>
    </AppShell>
  );
}
