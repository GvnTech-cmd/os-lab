/**
 * Client for the os-lab console API (android-lab/lab/web_ui.py + console/oslab.py).
 *
 * The lab contract mirrors qLar's shared/os-lab.ts (PR #174): pages send typed requests
 * ({lab, action, …}), preview the returned plan, then start it with the plan's token.
 * Every POST carries X-OSLab: 1, which the server requires so other sites cannot drive the lab.
 */
import { useEffect, useReducer } from "react";
import type { CapabilityCatalog } from "../health/capabilities";

export type LabId = "android" | "windows" | "linux" | "ios" | "macos" | "source";
export type LabState = "ready" | "needs-setup" | "unavailable";

export interface HostTool {
  id: string;
  label: string;
  found: boolean;
  path: string | null;
}
export interface HostProvider {
  id: string;
  guest: string;
  candidate: boolean;
  requirements: string;
}
export interface HostInfo {
  os: string;
  osPretty: string;
  arch: string;
  hostname: string;
  cpus: number | null;
  memory: number | null;
  disk: { total: number; free: number } | null;
  kvm: { present: boolean; usable: boolean };
  wsl: { guest: boolean; distributions: string[] };
  runtime: string | null;
  xcode: { installed: boolean; iosRuntime: boolean; iosDevice: boolean } | null;
  python: string;
  root: string;
  tools: HostTool[];
  providers: HostProvider[];
}
export interface Requirement {
  id: string;
  label: string;
  found: boolean;
  required: boolean;
  hint: string;
}
export interface LabAction {
  id: string;
  label: string;
  description: string;
  privileged: boolean;
}
export interface LabStatus {
  id: LabId;
  label: string;
  summary: string;
  state: LabState;
  provider: string | null;
  reasons: string[];
  requirements: Requirement[];
  notes: string[];
  actions: LabAction[];
  installed: boolean;
}
export interface LabRequest {
  lab: LabId;
  action: string;
  options?: Record<string, unknown>;
  profile?: string;
  cpus?: string;
  ram?: string;
  disk?: string;
  device?: string;
  wslDistro?: string;
  clickPid?: number;
  clickX?: number;
  clickY?: number;
}
export interface SetupDetails {
  dependencies: string[];
  downloads: string[];
  privileges: string;
  guestDisk: string | null;
  diskNote: string;
  verifiedDownloads: boolean;
}
export interface LabPlan {
  lab: LabId;
  action: string;
  provider: string;
  workspace: string;
  program: string | null;
  args: string[];
  effects: string[];
  timeoutSec: number;
  privileged: boolean;
  runnable: boolean;
  manualCommand: string | null;
  setup: SetupDetails | null;
  display: string;
}
export type JobState = "running" | "succeeded" | "failed" | "cancelled" | "timed-out" | "interrupted";
export interface LabJob {
  id: string;
  label: string;
  lab: LabId;
  action: string;
  command: string;
  state: JobState;
  startedAt: number;
  finishedAt: number | null;
  exitCode: number | null;
  error: string | null;
  truncated: boolean;
  lines: number;
  logs?: string[];
}
export interface LabConfig {
  lab: LabId;
  path: string;
  exists: boolean;
  fields: { key: string; value: string; local: boolean }[];
  profiles: string[];
  backups: string[];
  endpoints: { label: string; address: string }[];
}
export interface LabMonitor {
  lab: LabId;
  state: string;
  note?: string;
  runtime?: string;
  containers: { name: string; state: string; status: string; ports: string; cpu: string; memory: string }[];
}
export interface AndroidLogs {
  logs: string[];
  running: boolean;
}
/** One installed, available iOS Simulator device (console/oslab.py::ios_simulator). */
export interface IosSimulatorDevice {
  udid: string;
  name: string;
  runtime: string;
  state: string;
}
export interface IosSimulatorInfo {
  available: boolean;
  reason: string | null;
  devices: IosSimulatorDevice[];
  runtimes: string[];
  booted: IosSimulatorDevice[];
  configuredDevice: string | null;
}
export interface MacWindow {
  windowId: number;
  pid: number;
  app: string;
  title: string;
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface MacAppsInfo {
  available: boolean;
  reason: string | null;
  screenRecording: boolean;
  windows: MacWindow[];
}
export interface MacElement {
  role: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}
export interface MacElementsInfo {
  windowId: number;
  app: string;
  bounds: { x: number; y: number; width: number; height: number };
  elements: MacElement[];
}
export interface MacControlState {
  armed: boolean;
  expiresInSec: number;
}
export interface Report {
  name: string;
  url: string;
}
export interface Hook {
  name: string;
  path: string;
  code: string;
}

export interface CleanupStatus {
  state: LabState;
  platform?: { id: string; label: string; supported: boolean };
  reasons: string[];
  requirements: { id: string; label: string; found: boolean; hint: string; detail: string }[];
  capabilities: { id: string; label: string; found: boolean; detail: string }[];
}
export interface CleanupEntry {
  id: string; name: string; category: string; risk: string; hint: string; impact: string;
  defaultSelected: boolean; needsPrivilege: boolean;
  paths: { template: string; path: string | null; reason: string; source?: string }[];
}
export interface CleanupScan {
  cancelled: boolean;
  entries: { id: string; name: string; category: string; risk: string; sizeBytes: number; files: number; folders: number; unreadable: string[]; paths: { path: string | null; reason: string; source?: string; sizeBytes: number; error: string | null }[] }[];
  totals: { sizeBytes: number; files: number; folders: number; unreadable: number };
}
export interface CleanupPlan {
  planId: string; mode: "trash" | "delete"; expiresAt: number;
  items: { entryId: string; entryName: string; path: string | null; status: string; code: string; reason: string; source?: string; sizeBytes: number; files: number; folders: number }[];
  totals: { ready: number; skipped: number; bytes: number };
}
export interface CleanupResult {
  planId: string; mode: "trash" | "delete"; cancelled: boolean;
  results: { entryId: string; entryName: string; path: string | null; status: string; code: string; reason: string; source?: string; error: string | null; bytes: number; trashPath: string | null }[];
  totals: { items: number; trashed: number; deleted: number; skipped: number; failed: number; bytes: number };
}
export interface CleanupJob {
  id: string; kind: "scan" | "plan" | "clean"; state: "running" | "done" | "cancelled" | "failed";
  request: { entryIds?: string[]; mode?: "trash" | "delete"; planId?: string };
  progress: Record<string, string | number> | null;
  result: CleanupScan | CleanupPlan | CleanupResult | null;
  error: string | null;
}
export interface CleanupHistory { entries: { id: number; result: CleanupResult; hmac: string }[]; total: number; verified: boolean }

export interface CleanupContainerCapabilities {
  available: boolean; engine: "docker" | "podman" | null; reason: string;
  actions: { id: string; risk: string; defaultSelected: false; pruneArgv: string[] }[];
}
export interface CleanupContainerPreview {
  previewId: string; actionId: string; engine: "docker" | "podman"; risk: string;
  candidateCount: number; candidates: Record<string, unknown>[]; command: string[]; expiresAt: number;
}
export interface CleanupContainerResult {
  actionId: string; engine: string; status: "completed" | "failed"; error?: string;
  candidateCount?: number; command?: string[]; output?: string; bytesRemoved: number | null;
}
export interface CleanupVMInventory {
  cancelled: boolean;
  items: { id: string; name: string; path: string; sizeBytes: number; sizeOnDiskBytes: number | null; files: number; reportOnly: true }[];
  unavailable: { id: string; root: string | null; reason: string }[];
}
export interface CleanupAuxJob<T> {
  id: string; kind: "container-prune" | "vm-scan" | "leftovers"; state: "running" | "done" | "cancelled" | "failed";
  result: T | null; error: string | null;
}
export interface CleanupCrossLeftovers {
  available: boolean; reason?: string; cancelled: boolean;
  items: { id: string; name: string; path: string; status: string; confidence: number; rule: string; sizeBytes: number; sizeOnDiskBytes: number | null; reportOnly: true }[];
  inventorySources?: string[]; inventoryErrors?: string[]; unreadable?: string[];
}
/** CLNP-01: one typed permission record from GET /api/cleanup/permissions. */
export interface CleanupPermission {
  id: string; name: string; applicable: boolean; granted: boolean | null;
  probePaths: string[];
  results: { path: string; readable: boolean | null; reason: string }[];
  guidance: string; grantUrl: string | null;
}
export interface CleanupPermissions {
  platform: string; permissions: CleanupPermission[];
  classification?: { classified: { path: string; permissionId: string; state: string; reason: string }[]; unmatched: { path: string; permissionId: null; state: string; reason: string }[] };
}
/** CLNP-09/10: one configured volume of the background monitor. */
export interface CleanupMonitorVolumeConfig {
  mountPoint: string; minFreeBytes: number; minFreePercent: number; enabled: boolean;
  volume: { freeBytes: number | null; totalBytes: number | null; usage: number | null; kind: string | null } | null;
}
export interface CleanupMonitorStatus {
  enabled: boolean; running: boolean; intervalSeconds: number; cooldownSeconds: number;
  volumes: CleanupMonitorVolumeConfig[];
  state: {
    volumes: Record<string, { armed: boolean; lastWarningAt: number | null; state: string }>;
    events: { at: number; kind: string; volume: string | null; freeBytes: number | null; thresholdBytes: number | null; message: string }[];
    lastEvaluationAt: number | null; lastError: string | null;
  };
  activeWarnings: { volume: string; lastWarningAt: number | null }[];
  configError: string | null;
  checkedAt: number;
}
export interface CleanupMonitorConfig {
  enabled: boolean; intervalSeconds: number; cooldownSeconds: number;
  volumes: { mountPoint: string; minFreeBytes: number; minFreePercent: number; enabled: boolean }[];
}
/** CLNP-23: one registered Space Explorer root. */
export interface CleanupExplorerRoot {
  id: string; name: string; source: string; path: string | null; available: boolean; reason: string;
}
export interface CleanupExplorerNode {
  name: string; path: string; sizeBytes: number; files: number; folders: number;
  children: CleanupExplorerNode[]; truncated: boolean; unreadable: number;
}
export interface CleanupExplorerResult {
  rootId: string; path: string; relative: string | null;
  tree: CleanupExplorerNode; nodes: number; truncated: boolean; cancelled: boolean; checkedAt: number;
}
export interface CleanupExplorerJob {
  id: string; kind: "explorer"; state: "running" | "done" | "cancelled" | "failed";
  progress: Record<string, string | number> | null;
  result: CleanupExplorerResult | null; error: string | null;
}
/** CLN-28: one local volume from GET /api/cleanup/volumes. */
export interface CleanupVolume {
  mountPoint: string; name: string; device: string; filesystem: string | null; kind: string;
  totalBytes: number | null; freeBytes: number | null; usedBytes: number | null; usage: number | null;
  purgeableBytes: number | null;
  isHome: boolean; pressure: string; error: string | null;
}
export interface CleanupVolumes {
  platform: string; threshold: number;
  volumes: CleanupVolume[];
  homeVolume: string | null; warnings: string[]; error: string | null;
}
/** CLNP-14: one bookmark — a catalog-entry reference with its behaviours. */
export interface BookmarkRecord {
  entryId: string; createdAt: number; priority: number; quickClean: boolean;
  autoCleanHook: { enabled: boolean; lastRunAt: number | null };
  sizeAlert: { enabled: boolean; thresholdBytes: number; armed: boolean; lastAlertAt: number | null };
  entry: { name: string; risk: string; category: string; needsPrivilege: boolean; paths: { template: string; path: string | null; reason: string }[] } | null;
}
export interface BookmarksPayload { bookmarks: BookmarkRecord[]; error: string | null }
export interface BookmarkChanges {
  priority?: number; quickClean?: boolean;
  autoCleanHook?: { enabled: boolean; lastRunAt?: number | null };
  sizeAlert?: { enabled?: boolean; thresholdBytes?: number; armed?: boolean; lastAlertAt?: number | null };
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw new ApiError(data.error || `${res.status} ${res.statusText}`, res.status);
  return data;
}
const post = <T>(path: string, body: unknown = {}) =>
  call<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-OSLab": "1" },
    body: JSON.stringify(body)
  });

export interface ContentState {
  installed: boolean;
  version: string | null;
  sequence: number;
  hooks: boolean;
  updatedAt: number | null;
  fileCount: number;
  latest: { version: string | null; sequence: number; files: { data: number; hooks: number } } | null;
  checkedAt: number | null;
  offline: boolean;
  source: string;
  updateAvailable?: boolean;
}

export interface AppUpdateState {
  installed: string | null;
  latest: string | null;
  updateAvailable: boolean;
  checkedAt: number | null;
  platform: string | null;
  kind: string;
  releaseUrl: string | null;
  asset: { name: string; url: string } | null;
  supported: boolean;
  offline: boolean;
  installing: boolean;
  install: {
    phase: "downloading" | "opening" | "done" | "error";
    error: string | null;
    path: string | null;
    version?: string;
  } | null;
}

export const api = {
  cleanupStatus: () => call<CleanupStatus>("/api/cleanup/status"),
  cleanupCatalog: () => call<{ platform: string; entries: CleanupEntry[] }>("/api/cleanup/catalog"),
  cleanupHistory: () => call<CleanupHistory>("/api/cleanup/history"),
  cleanupJobs: () => call<{ jobs: CleanupJob[] }>("/api/cleanup/jobs"),
  cleanupScan: (entryIds: string[]) => post<CleanupJob>("/api/cleanup/scan", { entryIds }),
  cleanupPlan: (entryIds: string[], mode: "trash" | "delete") => post<CleanupJob>("/api/cleanup/plan", { entryIds, mode }),
  cleanupClean: (planId: string) => post<CleanupJob>("/api/cleanup/clean", { planId }),
  cleanupJob: (id: string) => call<CleanupJob>(`/api/cleanup/jobs/${encodeURIComponent(id)}`),
  cleanupCancel: (id: string) => post<CleanupJob>(`/api/cleanup/jobs/${encodeURIComponent(id)}/cancel`),
  cleanupContainers: () => call<CleanupContainerCapabilities>("/api/cleanup/containers"),
  cleanupPermissions: () => call<CleanupPermissions>("/api/cleanup/permissions"),
  cleanupMonitor: () => call<CleanupMonitorStatus>("/api/cleanup/monitor"),
  cleanupMonitorConfig: (config: CleanupMonitorConfig) => post<CleanupMonitorStatus>("/api/cleanup/monitor/config", config),
  cleanupMonitorEvaluate: () => post<CleanupMonitorStatus>("/api/cleanup/monitor/evaluate"),
  cleanupVolumes: () => call<CleanupVolumes>("/api/cleanup/volumes"),
  cleanupBookmarks: () => call<BookmarksPayload>("/api/cleanup/bookmarks"),
  cleanupBookmarkAdd: (entryId: string) => post<BookmarksPayload>("/api/cleanup/bookmarks", { entryId }),
  cleanupBookmarkUpdate: (entryId: string, changes: BookmarkChanges) => post<BookmarksPayload>("/api/cleanup/bookmarks/update", { entryId, ...changes }),
  cleanupBookmarkRemove: (entryId: string) => post<BookmarksPayload>("/api/cleanup/bookmarks/remove", { entryId }),
  cleanupBookmarkQuickClean: () => post<{ job: CleanupJob; refusals: { entryId: string; reason: string }[] }>("/api/cleanup/bookmarks/quick-clean"),
  /** CLNP-20: the raw path appears exactly once, here; afterwards ids only. */
  cleanupCustomAdd: (name: string, path: string) => post<{ entries: { id: string; name: string; risk: string; paths: Record<string, string[]> }[]; error: string | null }>("/api/cleanup/custom-entries", { name, path }),
  cleanupCustomRemove: (entryId: string) => post<{ entries: unknown[]; bookmarks?: BookmarkRecord[]; error: string | null }>("/api/cleanup/custom-entries/remove", { entryId }),
  /** CLNP-23: the Space Explorer (read-only size trees over registered roots). */
  cleanupExplorerRoots: () => call<{ roots: CleanupExplorerRoot[] }>("/api/cleanup/explorer/roots"),
  cleanupExplorerScan: (rootId: string) => post<CleanupExplorerJob>("/api/cleanup/explorer/scan", { rootId }),
  cleanupExplorerSubtree: (rootId: string, relative: string) => post<CleanupExplorerJob>("/api/cleanup/explorer/subtree", { rootId, relative }),
  cleanupContainerPreview: (actionId: string) => post<CleanupContainerPreview>("/api/cleanup/containers/preview", { actionId }),
  cleanupContainerPrune: (previewId: string) => post<CleanupAuxJob<CleanupContainerResult>>("/api/cleanup/containers/prune", { previewId }),
  cleanupVMScan: () => post<CleanupAuxJob<CleanupVMInventory>>("/api/cleanup/vms/scan"),
  cleanupCrossLeftovers: () => post<CleanupAuxJob<CleanupCrossLeftovers>>("/api/cleanup/leftovers/scan"),
  cleanupAuxJob: <T>(id: string) => call<CleanupAuxJob<T>>(`/api/cleanup/jobs/${encodeURIComponent(id)}`),
  health: () => call<{ status: string; version: string; console: boolean }>("/api/health"),
  host: () => call<{ host: HostInfo; labs: LabStatus[] }>("/api/host"),
  capabilities: () => call<CapabilityCatalog>("/api/capabilities"),
  config: (lab: LabId) => call<LabConfig>(`/api/labs/${lab}/config`),
  monitor: (lab: LabId) => call<LabMonitor>(`/api/labs/${lab}/monitor`),
  iosSimulator: () => call<IosSimulatorInfo>(`/api/labs/ios/simulator`),
  iosScreenshotUrl: "/api/labs/ios/screenshot",
  macosApps: () => call<MacAppsInfo>("/api/labs/macos/apps"),
  macosAppScreenshotUrl: (windowId: number) => `/api/labs/macos/apps/${windowId}/screenshot`,
  macosElements: (windowId: number) => call<MacElementsInfo>(`/api/labs/macos/apps/${windowId}/elements`),
  macosControl: () => call<MacControlState>("/api/labs/macos/control"),
  macosControlArm: (armed: boolean) => post<MacControlState>("/api/labs/macos/control", { armed }),
  macosClick: (pid: number, x: number, y: number) =>
    post<{ ok: boolean; pid: number; x: number; y: number }>("/api/labs/macos/click", { pid, x, y }),
  plan: (request: LabRequest) => post<{ plan: LabPlan; token: string }>("/api/labs/plan", { request }),
  start: (request: LabRequest, token: string) => post<LabJob>("/api/labs/start", { request, token }),
  jobs: () => call<{ jobs: LabJob[] }>("/api/jobs"),
  job: (id: string) => call<LabJob>(`/api/jobs/${encodeURIComponent(id)}`),
  cancel: (id: string) => post<LabJob>(`/api/jobs/${encodeURIComponent(id)}/cancel`),
  // Android Lab workbench
  logs: () => call<AndroidLogs>("/api/logs"),
  clearLogs: () => post("/api/logs/clear"),
  stop: () => post("/api/stop"),
  run: (action: string, apk: string) => post<{ status: string; title: string }>("/api/run", { action, apk }),
  devices: () => call<{ devices: string }>("/api/devices"),
  reports: () => call<{ reports: Report[] }>("/api/reports"),
  apks: () => call<{ apks: { name: string; path: string; size: number }[] }>("/api/apks"),
  hooks: () => call<{ hooks: Hook[] }>("/api/hooks"),
  // Signed content packs (console/content.py): only check/update touch the network
  contentStatus: () => call<ContentState>("/api/content/status"),
  contentCheck: () => post<ContentState>("/api/content/check"),
  contentUpdate: (hooks: boolean) => post<ContentState>("/api/content/update", { hooks }),
  contentReset: () => post<ContentState>("/api/content/reset"),
  contentCompanies: () => call<{ companies: unknown[]; source: "downloaded" | "bundled"; version: string | null }>("/api/content/companies"),
  // Signed app releases (console/app_update.py): only the desktop app reports a version
  appUpdateStatus: () => call<AppUpdateState>("/api/app/update"),
  appUpdateCheck: () => post<AppUpdateState>("/api/app/update/check"),
  appUpdateInstall: () => post<AppUpdateState>("/api/app/update/install"),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("apk", file);
    return call<{ status: string; filename: string; path: string; size: number }>("/api/upload", {
      method: "POST",
      headers: { "X-OSLab": "1" },
      body: form
    });
  }
};

export const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * A polled value shared by every component that uses it: the shell's sidebar and the page read the
 * same host report and job list, fetched once per interval while anything is subscribed.
 */
export function createStore<T>(load: () => Promise<T>, intervalMs: number) {
  let data: T | undefined;
  let error: string | null = null;
  let loading = false;
  let timer: ReturnType<typeof setInterval> | undefined;
  const subscribers = new Set<() => void>();
  const notify = () => subscribers.forEach((fn) => fn());

  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      data = await load();
      error = null;
    } catch (e) {
      error = message(e);
    } finally {
      loading = false;
      notify();
    }
  }
  function subscribe(fn: () => void) {
    subscribers.add(fn);
    if (subscribers.size === 1) {
      void refresh();
      timer = setInterval(() => {
        if (!document.hidden) void refresh();
      }, intervalMs);
    }
    return () => {
      subscribers.delete(fn);
      if (!subscribers.size) clearInterval(timer);
    };
  }
  function use() {
    const [, rerender] = useReducer((n: number) => n + 1, 0);
    useEffect(() => import.meta.env.PUBLIC_SITE_MODE === "pages" ? undefined : subscribe(rerender), []);
    return { data, error, refresh };
  }
  return { use, refresh, get: () => data };
}

export const hostStore = createStore(api.host, 15000);
export const contentStore = createStore(api.contentStatus, 30000);
export const jobsStore = createStore(async () => (await api.jobs()).jobs, 2500);
export const healthStore = createStore(api.health, 5000);
export const androidLogsStore = createStore(api.logs, 1000);

/** Poll one endpoint while mounted (for page-specific data such as one lab's monitor). */
export function usePoll<T>(load: () => Promise<T>, intervalMs: number, deps: unknown[] = []) {
  const [state, set] = useReducer(
    (s: { data?: T; error: string | null; n: number }, a: Partial<{ data: T; error: string | null }>) => ({
      ...s,
      ...a,
      n: s.n + 1
    }),
    { error: null, n: 0 }
  );
  const [tick, reload] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    let live = true;
    const run = () =>
      load().then(
        (data) => live && set({ data, error: null }),
        (e) => live && set({ error: message(e) })
      );
    void run();
    const timer = intervalMs > 0 ? setInterval(() => !document.hidden && void run(), intervalMs) : undefined;
    return () => {
      live = false;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, intervalMs]);
  return { data: state.data, error: state.error, reload };
}

/** The Android target APK, remembered per browser. */
const APK_KEY = "oslab.apk";
export const DEFAULT_APK = "scripts/vulnerable-test.apk";
export function getApk(): string {
  try {
    return localStorage.getItem(APK_KEY) || DEFAULT_APK;
  } catch {
    return DEFAULT_APK;
  }
}
export function setApk(value: string) {
  try {
    localStorage.setItem(APK_KEY, value || DEFAULT_APK);
  } catch {
    // Storage unavailable: the choice lasts for this page view
  }
  window.dispatchEvent(new Event("oslab:apk"));
}
export function useApk(): [string, (value: string) => void] {
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  useEffect(() => {
    window.addEventListener("oslab:apk", rerender);
    return () => window.removeEventListener("oslab:apk", rerender);
  }, []);
  return [getApk(), setApk];
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  const locale = typeof document === "undefined" ? "en" : document.documentElement.lang || "en";
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: v >= 10 || i === 0 ? 0 : 1 }).format(v)} ${units[i]}`;
}
export function ago(seconds: number | null | undefined): string {
  if (!seconds) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - seconds));
  const locale = typeof document === "undefined" ? "en" : document.documentElement.lang || "en";
  const format = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "short" });
  if (s < 60) return format.format(-s, "second");
  if (s < 3600) return format.format(-Math.round(s / 60), "minute");
  if (s < 86400) return format.format(-Math.round(s / 3600), "hour");
  return format.format(-Math.round(s / 86400), "day");
}
