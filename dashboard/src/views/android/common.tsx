/** Shared Android Lab workbench pieces: the action catalog, run buttons, APK target and job parsing. */
import { useRef, useState, type ReactNode } from "react";
import {
  BugIcon,
  KeyIcon,
  MagicWandIcon,
  PackageIcon,
  PlayIcon,
  PulseIcon,
  ScanIcon,
  ShieldCheckIcon,
  UploadSimpleIcon,
  WrenchIcon
} from "@phosphor-icons/react";
import { androidLogsStore, api, message, useApk, usePoll, formatBytes } from "../../lib/api";
import { Field, Status } from "../../components/ui";
import { localeFromPath, localePath } from "../../i18n/paths";

/** Runnable workbench actions; ids match POST /api/run in web_ui.py. */
export const ACTIONS: Record<string, { label: string; desc: string; group: string; icon: ReactNode; primary?: boolean }> = {
  preflight: { label: "Pre-flight check", desc: "Verify Python, ADB, JADX and the lab toolchain before a run.", group: "Setup", icon: <PulseIcon size={18} /> },
  "create-sample": { label: "Generate sample APK", desc: "Build the deliberately vulnerable test APK used by the demo workflows.", group: "Setup", icon: <PackageIcon size={18} /> },
  wf1: { label: "WF1 static audit", desc: "Decompile with JADX, audit the manifest, apply OWASP MASVS rules and render the report.", group: "Static", icon: <ShieldCheckIcon size={18} />, primary: true },
  "scan-secrets": { label: "Scan secrets", desc: "Search the APK for API keys, tokens and hard-coded credentials.", group: "Static", icon: <KeyIcon size={18} /> },
  analyze: { label: "Extract attack surface", desc: "Enumerate exported activities, services, receivers, providers and deep links.", group: "Static", icon: <ScanIcon size={18} /> },
  fuzz: { label: "IPC fuzzer", desc: "Probe exported components and content providers with boundary and SQLi payloads.", group: "Dynamic", icon: <BugIcon size={18} /> },
  patch: { label: "Patch APK", desc: "Inject a permissive network-security config and the Frida gadget for non-root testing.", group: "Dynamic", icon: <WrenchIcon size={18} /> },
  agentic: { label: "Agentic playbook", desc: "Rank attack hypotheses and generate tailored Frida hooks for the target.", group: "Agentic", icon: <MagicWandIcon size={18} />, primary: true }
};

/** Start a workbench action on the current target APK and open the console. */
export function useRun() {
  const [apk] = useApk();
  const { data } = androidLogsStore.use();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const run = async (action: string, openConsole = true) => {
    if (submitting || data?.running) return;
    setError(null);
    setSubmitting(true);
    try {
      await api.run(action, apk);
      await androidLogsStore.refresh();
      if (openConsole) window.location.assign(localePath("/android/console/", localeFromPath(window.location.pathname)));
    } catch (e) {
      setError(message(e));
    } finally {
      setSubmitting(false);
    }
  };
  return { run, running: Boolean(data?.running) || submitting, error };
}

export function RunButton({ action, label, variant }: { action: string; label?: string; variant?: "brand" | "outline" }) {
  const { run, running, error } = useRun();
  const a = ACTIONS[action];
  const brand = (variant ?? (a.primary ? "brand" : "outline")) === "brand";
  return (<>
    <button
      type="button"
      disabled={running}
      onClick={() => void run(action)}
      className={
        brand
          ? "flex items-center gap-2 rounded-lg bg-[#f36c21] px-4 py-2 text-xs font-semibold text-white shadow-md transition-colors hover:bg-[#fa7b32] disabled:opacity-50"
          : "iux-btn"
      }
      data-variant={brand ? undefined : "outline"}
    >
      <PlayIcon size={14} weight="fill" />
      {label ?? a.label}
    </button>
    {error ? <Status value={{ ok: false, text: error }} /> : null}
  </>);
}

export function ActionTile({ id }: { id: string }) {
  const a = ACTIONS[id];
  return (
    <div className="iux-card group gap-3 p-5 transition-colors hover:border-[#f36c21]/40">
      <div className="flex items-center justify-between">
        <span className="flex size-8 items-center justify-center rounded-md border border-(--iux-border) bg-(--iux-muted) text-(--iux-muted-foreground) group-hover:text-[#f36c21]">
          {a.icon}
        </span>
        <span className="iux-badge" data-variant="outline">
          {a.group}
        </span>
      </div>
      <h3 className="text-sm font-semibold">{a.label}</h3>
      <p className="flex-1 text-xs text-(--iux-muted-foreground)">{a.desc}</p>
      <div>
        <RunButton action={id} />
      </div>
    </div>
  );
}

/** Target APK: upload or drop a package, pick a staged one, or type a path. */
export function ApkTarget() {
  const [apk, setApk] = useApk();
  const staged = usePoll(api.apks, 0, []);
  const picker = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const upload = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    setStatus({ ok: true, text: `Uploading ${file.name}…` });
    try {
      const res = await api.upload(file);
      setApk(res.path);
      setStatus({ ok: true, text: `Staged ${res.path} (${formatBytes(res.size)}) and set it as the target.` });
      staged.reload();
    } catch (e) {
      setStatus({ ok: false, text: message(e) });
    }
  };
  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={() => picker.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          void upload(e.dataTransfer.files);
        }}
        className={`apk-dot-grid-dense flex flex-col items-center gap-2 rounded-xl border border-dashed px-5 py-8 text-center transition-colors ${over ? "border-[#f36c21] bg-[#f36c21]/10" : "border-[#f36c21]/50 bg-[#f36c21]/5 hover:bg-[#f36c21]/10"}`}
      >
        <span className="flex size-12 items-center justify-center rounded-xl border border-(--iux-border) bg-(--iux-card) text-[#f36c21]">
          <UploadSimpleIcon size={24} />
        </span>
        <strong className="text-sm">Drop an APK here or click to upload</strong>
        <span className="text-xs text-(--iux-muted-foreground)">Staged into apks/ and set as the target for the next run.</span>
      </button>
      <input ref={picker} type="file" accept=".apk" hidden onChange={(e) => void upload(e.target.files)} />
      <Status value={status} />
      {staged.data?.apks.length ? (
        <div className="flex flex-wrap gap-2">
          {staged.data.apks.map((f) => (
            <button
              key={f.path}
              type="button"
              onClick={() => setApk(f.path)}
              className={`rounded-md border px-2.5 py-1 font-mono text-xs ${apk === f.path ? "border-[#f36c21] bg-[#f36c21]/10 text-[#f36c21]" : "border-(--iux-border) text-(--iux-muted-foreground) hover:text-(--iux-foreground)"}`}
              title={formatBytes(f.size)}
            >
              {f.name}
            </button>
          ))}
        </div>
      ) : null}
      <Field label="Target APK" hint="Relative to android-lab/lab. Used by every workflow that takes an APK.">
        <input className="iux-input font-mono" value={apk} onChange={(e) => setApk(e.target.value)} spellCheck={false} />
      </Field>
    </div>
  );
}

export interface ParsedJob {
  id: string;
  title: string;
  status: "running" | "ok" | "err";
  code: number | null;
  lines: number;
}

/** Split the workbench log into jobs by web_ui.py's "=== Executing:" / "exit code" markers. */
export function parseJobs(lines: string[], running: boolean): ParsedJob[] {
  const jobs: ParsedJob[] = [];
  let cur: ParsedJob | null = null;
  for (const raw of lines) {
    const line = raw.trim();
    let m = /\[\+\] === Executing: (.*) ===/.exec(line);
    if (m) {
      if (cur?.status === "running") cur.status = "err";
      cur = { id: `${jobs.length}`, title: m[1], status: "running", code: null, lines: 0 };
      jobs.push(cur);
      continue;
    }
    if (!cur) continue;
    m = /\[\+\] Task finished with exit code (-?\d+)/.exec(line);
    if (m) {
      cur.code = Number(m[1]);
      cur.status = cur.code === 0 ? "ok" : "err";
      continue;
    }
    if (line.startsWith("[!] Error:")) {
      cur.status = "err";
      continue;
    }
    cur.lines++;
  }
  if (cur?.status === "running" && !running) cur.status = "err";
  return jobs;
}

export function Kpi({ icon, label, value, sub }: { icon: ReactNode; label: string; value: ReactNode; sub: ReactNode }) {
  return (
    <div className="iux-card gap-1 px-5 py-4">
      <span className="flex items-center gap-1.5 text-xs text-(--iux-muted-foreground)">
        {icon}
        {label}
      </span>
      <span className="text-2xl font-bold tracking-tight tabular-nums">{value}</span>
      <span className="truncate text-xs text-(--iux-muted-foreground)">{sub}</span>
    </div>
  );
}

export const ANDROID_ENDPOINTS = [
  { label: "noVNC", address: "http://127.0.0.1:6080/" },
  { label: "MobSF", address: "http://127.0.0.1:8000/" },
  { label: "mitmweb", address: "http://127.0.0.1:8081/" },
  { label: "mitmproxy", address: "127.0.0.1:8080" },
  { label: "ADB", address: "127.0.0.1:5555" }
];

export function useDevices() {
  const { data, error, reload } = usePoll(api.devices, 15000, []);
  const raw = data?.devices ?? "";
  const list = /List of devices/.test(raw)
    ? raw
        .split(/\r?\n/)
        .slice(1)
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("*"))
        .map((l) => {
          const [serial, state] = l.split(/\s+/);
          return { serial, state: state ?? "unknown" };
        })
    : [];
  return { list, raw, loaded: data !== undefined, error, reload };
}
