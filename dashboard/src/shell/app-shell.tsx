/**
 * The page frame for every dashboard page, ported from qLar's shell/app-shell.tsx (PR #174):
 * a collapsible sidebar with nested nav on desktop, the same nav in a left drawer on small screens,
 * and Spotlight (⌘K / Ctrl+K) over the pages, labs, lab actions and recent jobs.
 *
 * The sidebar is built from the live host report: each lab carries its availability on this
 * computer (Ready / Setup / N/A) and a dot while one of its jobs runs.
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AndroidLogoIcon,
  AppleLogoIcon,
  BookOpenIcon,
  BroomIcon,
  CircleIcon,
  CpuIcon,
  DesktopTowerIcon,
  FireIcon,
  ChatCircleTextIcon,
  GitPullRequestIcon,
  HeartbeatIcon,
  ScalesIcon,
  LaptopIcon,
  ListChecksIcon,
  ListIcon,
  MagnifyingGlassIcon,
  MoonIcon,
  ArrowClockwiseIcon,
  ShieldCheckIcon,
  SidebarSimpleIcon,
  SunIcon,
  TerminalWindowIcon,
  WindowsLogoIcon,
  XIcon
} from "@phosphor-icons/react";
import { AppSidebar, SidebarBadge, useSidebarCollapsed, type SidebarGroup } from "./sidebar";
import { Spotlight, type SpotlightCommand, type SpotlightMeta, type SpotlightRecord } from "./spotlight";
import { toggleMode, useThemeMode } from "./theme";
import { androidLogsStore, healthStore, hostStore, jobsStore, type LabId, type LabStatus } from "../lib/api";
import { copy, firewallPath, type FirewallLocale } from "../firewall/locale";
import { localeFromPath, localePath } from "../i18n/paths";

export const REPO_URL = "https://github.com/keyvanarasteh/os-lab";
const PUBLIC_PAGES = import.meta.env.PUBLIC_SITE_MODE === "pages";

export const LAB_ICON: Record<LabId, (size?: number) => ReactNode> = {
  android: (s = 16) => <AndroidLogoIcon size={s} />,
  windows: (s = 16) => <WindowsLogoIcon size={s} />,
  linux: (s = 16) => <TerminalWindowIcon size={s} />,
  ios: (s = 16) => <AppleLogoIcon size={s} />,
  source: (s = 16) => <TerminalWindowIcon size={s} />,
  macos: (s = 16) => <LaptopIcon size={s} />
};

/** Where a section id leads. Pages are static files, so every section is a plain href. */
export function sectionHref(id: string): string {
  const localized = (path: string) => localePath(path, typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname));
  if (id === "host") return PUBLIC_PAGES ? `${import.meta.env.BASE_URL.replace(/\/$/, "")}/` : localized("/");
  if (id === "jobs") return localized("/jobs/");
  if (id === "repo") return REPO_URL;
  if (id === "health") return localized("/health/");
  if (id === "legal") return localized("/legal/");
  if (id === "contribute") return localized("/contribute/");
  if (id === "how-to-use") return localized("/how-to-use/");
  if (id === "feedback") return localized("/feedback/");
  if (id === "content") return localized("/content/");
  if (id.startsWith("cleanup-")) return localized(`/cleanup/${id === "cleanup-scan" ? "" : id.slice(8) + "/"}`);
  if (id === "firewall") {
    const locale = typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname);
    return firewallPath(locale);
  }
  if (id.startsWith("legal-")) return localized(`/legal/${id.slice(6)}/`);
  if (id === "android-overview") return localized("/android/");
  if (id.startsWith("android-")) return localized(`/android/${id.slice(8)}/`);
  if (id.startsWith("source-")) return localized(`/source/${id === "source-overview" ? "" : id.slice(7) + "/"}`);
  if (id.startsWith("lab-")) return localized(`/labs/${id.slice(4)}/`);
  return localized("/");
}
export const labHref = (lab: LabId) => localePath(`/labs/${lab}/`, typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname));

function StatePill({ lab }: { lab?: LabStatus }) {
  if (!lab) return null;
  if (lab.state === "ready") return <SidebarBadge>Ready</SidebarBadge>;
  if (lab.state === "needs-setup") return <SidebarBadge tone="warn">Setup</SidebarBadge>;
  return (
    <span className="ml-auto rounded-full border border-(--iux-border) px-1.5 py-px text-[10px] leading-none text-(--iux-muted-foreground)">
      N/A
    </span>
  );
}

function RunningDot() {
  return <span className="ml-auto size-2 animate-pulse rounded-full bg-[#00d084]" aria-label="running" />;
}

/** Labs this computer cannot run are left out of navigation; the page of one you are on stays. */
function labShown(labs: LabStatus[] | undefined, id: LabId, activeId: string): boolean {
  const lab = labs?.find((l) => l.id === id);
  return !lab || lab.state !== "unavailable" || activeId === `lab-${id}`;
}

function buildGroups(labs: LabStatus[] | undefined, running: Set<string>, androidRunning: boolean, locale: FirewallLocale, activeId: string): SidebarGroup[] {
  if (PUBLIC_PAGES) return [
    { label: "os-lab", items: [
      { id: "host", label: "Home", icon: <DesktopTowerIcon size={16} /> },
      { id: "firewall", label: copy[locale].lab, icon: <FireIcon size={16} /> },
      { id: "source-overview", label: "Source Lab", icon: LAB_ICON.source() },
      { id: "cleanup-scan", label: "Cleanup Lab", icon: <BroomIcon size={16} /> },
      { id: "feedback", label: "Feedback", icon: <ChatCircleTextIcon size={16} /> },
      { id: "repo", label: "Repository", icon: <BookOpenIcon size={16} /> }
    ] },
    { label: "Workspace", items: [
      { id: "how-to-use", label: "How to use", icon: <BookOpenIcon size={16} /> }
    ] }
  ];
  const lab = (id: LabId) => labs?.find((l) => l.id === id);
  const labItem = (id: LabId, label: string) => ({
    id: `lab-${id}`,
    label,
    icon: LAB_ICON[id](),
    badge: running.has(id) ? <RunningDot /> : <StatePill lab={lab(id)} />
  });
  return [
    {
      label: "Workspace",
      items: [
        { id: "host", label: "This computer", icon: <DesktopTowerIcon size={16} /> },
        { id: "how-to-use", label: "How to use", icon: <BookOpenIcon size={16} /> },
        {
          id: "jobs",
          label: "Jobs",
          icon: <ListChecksIcon size={16} />,
          badge: running.size ? <SidebarBadge tone="warn">{running.size} running</SidebarBadge> : undefined
        }
      ]
    },
    {
      label: "OS Lab",
      items: [
        {
          id: "android",
          label: "Android Lab",
          icon: <ShieldCheckIcon size={16} />,
          badge: androidRunning || running.has("android") ? <RunningDot /> : <StatePill lab={lab("android")} />,
          children: [
            { id: "android-overview", label: "Overview" },
            { id: "lab-android", label: "Runtime & setup" },
            { id: "android-providers", label: "Code & Providers" },
            { id: "android-workflows", label: "Workflows & DAG" },
            { id: "android-console", label: "Execution & Logs" },
            { id: "android-analytics", label: "Analytics" },
            { id: "android-sitemap", label: "Routes & Sitemap" }
          ]
        },
        { id: "source", label: "Source Lab", icon: LAB_ICON.source(),
          badge: running.has("source") ? <RunningDot /> : <StatePill lab={lab("source")} />,
          children: [
            { id: "source-overview", label: "Overview" }, { id: "lab-source", label: "Readiness & setup" },
            { id: "source-analyzer", label: "Crawler" }, { id: "source-evidence", label: "Evidence" },
            { id: "source-deep-analysis", label: "Deep analysis" }, { id: "source-pipeline", label: "Pipeline" },
            { id: "source-brain", label: "Brain" }, { id: "source-sources", label: "Sources" },
            { id: "source-settings/runtime", label: "Runtime settings" }, { id: "source-docs", label: "Documentation" }
          ] },
        { id: "cleanup", label: "Cleanup Lab", icon: <BroomIcon size={16} />,
          children: [
            { id: "cleanup-scan", label: "Scan & clean" },
            { id: "cleanup-results", label: "Results" },
            { id: "cleanup-leftovers", label: "Leftovers" },
            { id: "cleanup-history", label: "History" }
          ] },
        ...(labShown(labs, "ios", activeId) ? [labItem("ios", "iOS Lab")] : []),
        ...(labShown(labs, "windows", activeId) ? [labItem("windows", "Windows Lab")] : []),
        ...(labShown(labs, "macos", activeId) ? [labItem("macos", "macOS Lab")] : []),
        ...(labShown(labs, "linux", activeId) ? [labItem("linux", "Linux Lab")] : []),
        { id: "firewall", label: copy[locale].lab, icon: <FireIcon size={16} /> }
      ]
    },
    {
      label: "Help",
      items: [
        { id: "health", label: "Health check", icon: <HeartbeatIcon size={16} /> },
        {
          id: "legal",
          label: "Legal",
          icon: <ScalesIcon size={16} />,
          children: [
            { id: "legal-terms", label: "Terms of Use" },
            { id: "legal-acceptable-use", label: "Acceptable Use" },
            { id: "legal-privacy", label: "Privacy Notice" },
            { id: "legal-third-party", label: "Third-Party Notices" }
          ]
        },
        { id: "contribute", label: "Contribute", icon: <GitPullRequestIcon size={16} /> },
        { id: "feedback", label: "Feedback", icon: <ChatCircleTextIcon size={16} /> },
        { id: "repo", label: "Repository", icon: <BookOpenIcon size={16} /> }
      ]
    }
  ];
}

function buildMeta(): Record<string, SpotlightMeta> {
  return {
    host: { description: "OS, hardware, KVM, tools and which labs run here", aliases: ["host", "computer", "dependencies", "kvm", "wsl"] },
    jobs: { description: "Every lab job with its output", aliases: ["jobs", "runs", "history", "logs"] },
    "android-overview": { description: "Android Lab overview, quick launch and APK staging", aliases: ["apk", "android", "upload"] },
    "lab-android": { description: "Start, stop and set up the Android emulator stack", aliases: ["docker-android", "emulator", "setup"] },
    "android-providers": { description: "ADB devices, target APK, endpoints and Frida hooks", aliases: ["adb", "frida", "hooks"] },
    "android-workflows": { description: "Static and dynamic pipelines and every runnable action", aliases: ["wf1", "wf2", "dag"] },
    "android-console": { description: "Live output of Android jobs", aliases: ["console", "logs", "novnc"] },
    "android-analytics": { description: "Run outcomes and generated HTML reports", aliases: ["reports", "findings"] },
    "android-sitemap": { description: "Every page, endpoint and lab route", aliases: ["routes", "topology", "sitemap"] },
    "lab-ios": { description: "iOS Simulator via the macOS VM, or native Xcode", aliases: ["ios", "simulator", "xcode"] },
    "lab-windows": { description: "Windows VM with web desktop and RDP", aliases: ["windows", "rdp", "vm"] },
    "lab-macos": { description: "Native Xcode Simulator and Appium on a Mac", aliases: ["mac", "appium", "xcuitest"] },
    "lab-linux": { description: "Linux VM with web console and SSH", aliases: ["linux", "ssh", "vm"] },
    firewall: { description: "BGT207 dream-company firewall designs — branches, segmentation, products and rule sets", aliases: ["firewall", "bgt207", "ufw", "rules", "vlan", "dmz", "company"] },
    health: { description: "GET /api/health", aliases: ["status", "api"] },
    contribute: { description: "How to set up, test, rebuild, open a pull request and view roadmap TODOs", aliases: ["contribute", "contributing", "pull request", "pr", "development", "tests", "todos", "roadmap", "pentesting", "firewall", "tasks"] },
    "how-to-use": { description: "Create a task prompt with os-lab capabilities for any LLM", aliases: ["how to", "guide", "prompt", "llm", "help", "task"] },
    feedback: { description: "Report issues, suggest features, and share feedback", aliases: ["feedback", "bug", "issue", "request", "suggestion", "help"] },
    "legal-terms": { description: "Licence, authorized use, OS licences, no warranty", aliases: ["legal", "terms", "license", "warranty", "liability"] },
    "legal-acceptable-use": { description: "Supported and unsupported use, responsible disclosure", aliases: ["legal", "aup", "policy", "disclosure"] },
    "legal-privacy": { description: "Local-only console, browser storage, network connections, analytics", aliases: ["legal", "privacy", "gdpr", "kvkk", "telemetry", "cookies"] },
    "legal-third-party": { description: "Licences of images, tools and bundled components", aliases: ["legal", "licenses", "notices", "open source"] },
    repo: { description: "os-lab on GitHub", aliases: ["github", "source", "docs"] }
  };
}

// ── Shell ─────────────────────────────────────────────────────────────

const ShellContext = createContext<{ openNav: () => void; openSpotlight: () => void }>({
  openNav: () => {},
  openSpotlight: () => {}
});

/** Menu and search buttons for a page's top bar on small screens, where the sidebar is hidden. */
export function ShellMenuButton() {
  const { openNav, openSpotlight } = useContext(ShellContext);
  return (
    <div className="iux flex items-center gap-1 bg-transparent lg:hidden">
      <button type="button" className="iux-btn" data-variant="ghost" data-size="icon" aria-label="Open navigation" onClick={openNav}>
        <ListIcon size={18} />
      </button>
      <button type="button" className="iux-btn" data-variant="ghost" data-size="icon" aria-label="Search" onClick={openSpotlight}>
        <MagnifyingGlassIcon size={16} />
      </button>
    </div>
  );
}

/** Light/dark switch for a page's top bar. */
export function ThemeToggle() {
  const dark = useThemeMode() === "dark";
  return (
    <button type="button" className="iux-btn" data-variant="outline" data-size="icon" onClick={toggleMode} aria-label="Toggle theme">
      {dark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
    </button>
  );
}

/** Logo and name, as tall as the pages' top bars (h-14) so the borders line up. */
function Brand({ compact = false, action }: { compact?: boolean; action?: ReactNode }) {
  return (
    <div
      className={
        compact
          ? "flex h-14 shrink-0 items-center justify-center border-b border-(--iux-border)"
          : "flex h-14 shrink-0 items-center gap-2.5 border-b border-(--iux-border) pr-2 pl-4"
      }
    >
      <img src={localePath("/favicon.svg", "en")} alt="os-lab" width={28} height={28} className="iux-logo" />
      {!compact && (
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm leading-5 font-semibold tracking-tight">os-lab</div>
          <div className="truncate text-xs leading-4 text-(--iux-muted-foreground)">Security lab console</div>
        </div>
      )}
      {!compact && action}
    </div>
  );
}

function go(href: string) {
  if (/^https?:/.test(href)) {
    window.open(href, "_blank", "noreferrer");
    return;
  }
  if (href === window.location.pathname + window.location.hash) return;
  window.location.assign(href);
}

export function AppShell({
  activeId,
  commands = [],
  children
}: {
  activeId: string;
  /** Page-specific Spotlight commands, listed before the shared ones. */
  commands?: SpotlightCommand[];
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useSidebarCollapsed("oslab.sidebar.collapsed");
  const [sourceQuery, setSourceQuery] = useState("");
  const [sourceRecords, setSourceRecords] = useState<SpotlightRecord[]>([]);
  const [sourceSearchError, setSourceSearchError] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [spotlightOpen, setSpotlightOpen] = useState(false);
  const drawerRef = useRef<HTMLDialogElement>(null);
  const mode = useThemeMode();
  const { data: host } = hostStore.use();
  const { data: jobs } = jobsStore.use();
  const { data: health, error: healthError } = healthStore.use();
  const { data: androidLogs } = androidLogsStore.use();
  const locale: FirewallLocale = typeof window === "undefined" ? "en" : localeFromPath(window.location.pathname);

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return;
    if (navOpen && !drawer.open) drawer.showModal();
    if (!navOpen && drawer.open) drawer.close();
  }, [navOpen]);

  useEffect(() => {
    if (PUBLIC_PAGES || !spotlightOpen) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const query = sourceQuery.replace(/^source:\s*/i, "").slice(0, 200);
      void fetch(`/api/source/spotlight?section=evidence&limit=25&q=${encodeURIComponent(query)}`, { signal: controller.signal })
        .then(async response => { if (!response.ok) throw new Error(); return response.json(); })
        .then(result => {
          setSourceSearchError(false);
          setSourceRecords((result.data ?? []).filter((r: { href?: string }) => r.href?.startsWith("/source/")).map((r: { title: string; href: string }) => ({
            id: r.href, section: "source-evidence", title: r.title, href: r.href
          })));
        }).catch(() => { if (!controller.signal.aborted) { setSourceRecords([]); setSourceSearchError(true); } });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [spotlightOpen, sourceQuery]);

  const running = useMemo(() => new Set((jobs ?? []).filter((j) => j.state === "running").map((j) => j.lab)), [jobs]);
  const groups = useMemo(
    () => buildGroups(host?.labs, running, Boolean(androidLogs?.running), locale, activeId),
    [host?.labs, running, androidLogs?.running, locale, activeId]
  );
  const meta = useMemo(buildMeta, []);
  const records = useMemo<SpotlightRecord[]>(
    () => [
      ...sourceRecords,
      ...(host?.labs ?? []).flatMap((lab) =>
        lab.actions.map((action) => ({
          id: `${lab.id}:${action.id}`,
          section: `lab-${lab.id}`,
          title: `${lab.label}: ${action.label}`,
          description: action.description,
          badge: action.privileged ? "admin" : "action"
        }))
      ),
      ...(jobs ?? []).slice(0, 20).map((job) => ({
        id: job.id,
        section: "jobs",
        title: job.label,
        description: job.command,
        badge: job.state
      }))
    ],
    [host?.labs, jobs, sourceRecords]
  );
  const allCommands = useMemo<SpotlightCommand[]>(
    () => [
      ...commands,
      ...(!PUBLIC_PAGES ? [{
        id: "refresh",
        label: "Re-detect this computer",
        description: "Refresh OS, tools and lab availability",
        aliases: ["refresh", "detect", "rescan"],
        icon: <ArrowClockwiseIcon size={16} />,
        run: () => void hostStore.refresh()
      }] : []),
      {
        id: "theme",
        label: "Toggle theme",
        description: `Switch to ${mode === "dark" ? "light" : "dark"} mode`,
        aliases: ["dark", "light", "appearance"],
        icon: mode === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />,
        run: toggleMode
      },
      {
        id: "sidebar",
        label: collapsed ? "Expand sidebar" : "Collapse sidebar",
        aliases: ["sidebar", "rail", "nav"],
        icon: <SidebarSimpleIcon size={16} />,
        run: () => setCollapsed(!collapsed)
      }
    ],
    [commands, mode, collapsed, setCollapsed]
  );

  const connected = health?.status === "ok" && !healthError;
  const footer = () => (
    <div className="flex items-center justify-between border-t border-(--iux-border) px-4 py-3 text-[10px] text-(--iux-muted-foreground)/70">
      {!PUBLIC_PAGES && <span className="inline-flex items-center gap-1.5">
        <CircleIcon size={7} weight="fill" className={connected ? "text-(--iux-success)" : "text-(--iux-danger)"} />
        {connected ? "Lab engine connected" : healthError ? "Lab engine offline" : "Connecting…"}
      </span>}
      <span>{host ? `${host.host.os} · ${host.host.arch}` : "os-lab"}</span>
    </div>
  );
  const shell = useMemo(() => ({ openNav: () => setNavOpen(true), openSpotlight: () => setSpotlightOpen(true) }), []);
  const select = (id: string) => {
    setNavOpen(false);
    go(sectionHref(id));
  };

  return (
    <ShellContext.Provider value={shell}>
      <div className="flex h-dvh overflow-hidden">
        <AppSidebar
          groups={groups}
          activeId={activeId}
          onSelect={select}
          collapsed={collapsed}
          onCollapsedChange={setCollapsed}
          onSearch={() => setSpotlightOpen(true)}
          header={(c, toggle) => <Brand compact={c} action={toggle} />}
          footer={footer}
        />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</div>
        </div>
      </div>
      <Spotlight
        onQueryChange={setSourceQuery}
        searchError={sourceSearchError && !PUBLIC_PAGES ? "Source search unavailable" : undefined}
        open={spotlightOpen}
        onOpenChange={setSpotlightOpen}
        groups={groups}
        meta={meta}
        commands={allCommands}
        records={PUBLIC_PAGES ? [] : records}
        tips={PUBLIC_PAGES ? [] : [
          { scope: "jobs", description: "Search recent jobs", icon: <ListChecksIcon size={16} /> },
          ...(labShown(host?.labs, "windows", activeId) ? [{ scope: "windows", description: "Windows Lab actions", icon: <WindowsLogoIcon size={16} /> }] : []),
          { scope: "android", description: "Android Lab pages and actions", icon: <AndroidLogoIcon size={16} /> },
          ...(labShown(host?.labs, "linux", activeId) ? [{ scope: "linux", description: "Linux Lab actions", icon: <CpuIcon size={16} /> }] : [])
        ]}
        onNavigate={(section, record) => {
          if (record?.href?.startsWith("/source/")) return go(localePath(record.href, locale));
          if (record && section === "jobs") return go(`${sectionHref("jobs")}#${record.id}`);
          if (record && section.startsWith("lab-")) return go(`${sectionHref(section)}#action=${record.id.split(":")[1]}`);
          go(sectionHref(section));
        }}
      />
      {/* oxlint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- backdrop click closes; Escape is native to the dialog */}
      <dialog
        ref={drawerRef}
        aria-label="Navigation"
        className="iux iux-dialog iux-drawer"
        onClose={() => setNavOpen(false)}
        onClick={(e) => {
          if (e.target === e.currentTarget) setNavOpen(false);
        }}
      >
        <Brand
          action={
            <button type="button" className="iux-btn shrink-0" data-variant="ghost" data-size="icon" aria-label="Close navigation" onClick={() => setNavOpen(false)}>
              <XIcon size={16} />
            </button>
          }
        />
        <AppSidebar
          variant="drawer"
          groups={groups}
          activeId={activeId}
          onSelect={select}
          onSearch={() => {
            setNavOpen(false);
            setSpotlightOpen(true);
          }}
          header={() => null}
          footer={footer}
        />
      </dialog>
    </ShellContext.Provider>
  );
}

