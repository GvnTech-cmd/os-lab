/**
 * CLNP-11: the background-monitor card and its warning banner.
 *
 * The card edits the typed config through POST /api/cleanup/monitor/config
 * (the whole config is sent; the engine validates and normalizes it) and
 * shows the runner state, per-volume floors against live free space, and the
 * recent events. The monitor state itself is polled by pages.tsx — only
 * while the runner is enabled — and passed in through props, so this card
 * never starts a second poller. Public Pages never mounts it.
 */
import { useState } from "react";
import { BellIcon, PlusIcon, TrashIcon } from "@phosphor-icons/react";
import { Badge, Empty, Section, Status } from "../../components/ui";
import { api, formatBytes, message, usePoll, type CleanupMonitorConfig, type CleanupMonitorStatus, type CleanupVolume } from "../../lib/api";

const INTERVALS = [60, 120, 300, 600, 1800, 3600];

function formatInterval(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600} h`;
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} s`;
}

export function MonitorBanner({ monitor, scanHref }: { monitor: CleanupMonitorStatus | null; scanHref: string }) {
  if (!monitor?.enabled || !monitor.activeWarnings.length) return null;
  return <div role="status" className="rounded-md border border-(--iux-warning)/50 bg-(--iux-warning)/10 p-3 text-sm">
    <p className="font-medium">Free space is running low</p>
    {monitor.activeWarnings.map((warning, index) => <p key={index} className="mt-1 text-xs">
      <span translate="no">{warning.volume}</span> — the monitor warned about this volume.{" "}
      <a className="underline" href={scanHref}>Run a scan to see what can be freed.</a>
    </p>)}
  </div>;
}

export function MonitorCard({
  monitor, reload
}: {
  monitor: CleanupMonitorStatus | null; reload: () => void;
}) {
  const { data: volumes } = usePoll(() => api.cleanupVolumes().then((report) => report.volumes), 0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(mutate: (current: CleanupMonitorStatus) => CleanupMonitorConfig) {
    if (!monitor) return;
    setBusy(true); setError("");
    try {
      await api.cleanupMonitorConfig(mutate(monitor));
      reload();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  function configFrom(current: CleanupMonitorStatus): CleanupMonitorConfig {
    return {
      enabled: current.enabled,
      intervalSeconds: current.intervalSeconds,
      cooldownSeconds: current.cooldownSeconds,
      volumes: current.volumes.map(({ mountPoint, minFreeBytes, minFreePercent, enabled }) => ({
        mountPoint, minFreeBytes, minFreePercent, enabled,
      })),
    };
  }

  if (!monitor || !Array.isArray(monitor.volumes)) return null;
  const configuredMounts = new Set(monitor.volumes.map((entry) => entry.mountPoint).filter(Boolean));
  const addable = (volumes ?? []).filter((volume) => !configuredMounts.has(volume.mountPoint));

  return <Section title="Background monitor" description="Checks disk free space while the console runs and warns when a volume crosses its threshold. Nothing is cleaned automatically by this card.">
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className="iux-btn" data-variant={monitor.enabled ? "primary" : "outline"} disabled={busy}
        onClick={() => void save((current) => ({ ...configFrom(current), enabled: !current.enabled }))}>
        {monitor.enabled ? "Monitoring" : "Enable monitoring"}
      </button>
      <label className="text-sm">Check every{" "}
        <select className="iux-input ml-1" value={monitor.intervalSeconds} disabled={busy || !monitor.enabled}
          onChange={(event) => void save((current) => ({ ...configFrom(current), intervalSeconds: Number(event.target.value) }))}>
          {INTERVALS.map((seconds) => <option key={seconds} value={seconds}>{formatInterval(seconds)}</option>)}
        </select>
      </label>
      <span className="text-xs text-(--iux-muted-foreground)">
        {monitor.enabled ? (monitor.running ? "runner active" : "runner starting") : "off — no checks run"}
      </span>
      <button type="button" className="iux-btn ms-auto" disabled={busy || !monitor.enabled} onClick={() => { setBusy(true); setError(""); void api.cleanupMonitorEvaluate().then(() => reload()).catch((e) => setError(message(e))).finally(() => setBusy(false)); }}>
        Check now
      </button>
    </div>
    {monitor.configError && <Status value={{ ok: false, text: monitor.configError }} />}
    {error && <Status value={{ ok: false, text: error }} />}
    <div className="mt-3 divide-y divide-(--iux-border)">
      {monitor.volumes.map((entry, index) => {
        const state = monitor.state.volumes[`volumes:${entry.mountPoint}`];
        return <div key={`${entry.mountPoint}-${index}`} className="flex flex-wrap items-center gap-2 py-2 text-sm">
          <input type="checkbox" className="iux-touch-target size-4 accent-[#f36c21]" aria-label="Check this volume"
            checked={entry.enabled} disabled={busy}
            onChange={(event) => void save((current) => ({
              ...configFrom(current),
              volumes: current.volumes.map((row, rowIndex) => rowIndex === index ? { ...row, enabled: event.target.checked } : row),
            }))} />
          <span className="min-w-0 flex-1 truncate" translate="no">{entry.mountPoint || "Home volume"}</span>
          {entry.volume && <span dir="ltr" className="tabular-nums text-xs text-(--iux-muted-foreground)">
            {formatBytes(entry.volume.freeBytes)} free
          </span>}
          <Badge tone={state?.state === "warning" ? "danger" : state?.state === "ok" ? "success" : undefined}>
            {state?.state === "warning" ? "warning" : state?.state === "ok" ? "ok" : "no data"}
          </Badge>
          <label className="text-xs">warn under{" "}
            <input type="number" className="iux-input w-20" min={0} dir="ltr" disabled={busy} defaultValue={Math.round(entry.minFreeBytes / (1024 * 1024 * 1024))}
              onBlur={(event) => void save((current) => ({
                ...configFrom(current),
                volumes: current.volumes.map((row, rowIndex) => rowIndex === index ? { ...row, minFreeBytes: Math.max(0, Number(event.target.value)) * 1024 * 1024 * 1024 } : row),
              }))} />{" "}GiB
          </label>
          <label className="text-xs">or{" "}
            <input type="number" className="iux-input w-16" min={0} max={100} dir="ltr" disabled={busy} defaultValue={entry.minFreePercent}
              onBlur={(event) => void save((current) => ({
                ...configFrom(current),
                volumes: current.volumes.map((row, rowIndex) => rowIndex === index ? { ...row, minFreePercent: Math.min(100, Math.max(0, Number(event.target.value))) } : row),
              }))} />{" "}%
          </label>
          <button type="button" className="iux-btn" data-variant="ghost" disabled={busy} title="Remove this volume"
            onClick={() => void save((current) => ({ ...configFrom(current), volumes: current.volumes.filter((_, rowIndex) => rowIndex !== index) }))}>
            <TrashIcon size={14} />
          </button>
        </div>;
      })}
    </div>
    {addable.length > 0 && <details className="mt-2 text-sm">
      <summary className="iux-btn cursor-pointer" data-variant="ghost"><PlusIcon size={14} className="inline" /> Add a volume</summary>
      <div className="mt-2 space-y-1">
        {addable.map((volume) => <button key={volume.mountPoint} type="button" className="iux-btn w-full justify-start text-left" disabled={busy}
          onClick={() => void save((current) => ({
            ...configFrom(current),
            volumes: [...current.volumes, { mountPoint: volume.mountPoint, minFreeBytes: 10 * 1024 * 1024 * 1024, minFreePercent: 10, enabled: true }],
          }))}>
          <span translate="no">{volume.mountPoint}</span> <span className="text-xs text-(--iux-muted-foreground)">{volume.kind}</span>
        </button>)}
      </div>
    </details>}
    <div className="mt-3">
      <p className="text-xs font-medium text-(--iux-muted-foreground)">Recent events</p>
      {monitor.state.events.length ? <ul className="mt-1 space-y-1 text-xs">
        {monitor.state.events.slice(-8).reverse().map((event, index) => <li key={index} className="flex gap-2">
          <BellIcon size={12} className={event.kind === "warning" ? "mt-0.5 text-(--iux-danger)" : event.kind === "recovered" ? "mt-0.5 text-(--iux-success)" : "mt-0.5 text-(--iux-muted-foreground)"} />
          <span>{new Date(event.at * 1000).toLocaleTimeString()} · {event.kind} · <span translate="no">{event.volume}</span>{event.freeBytes != null && ` · ${formatBytes(event.freeBytes)} free`}{event.message && ` · ${event.message}`}</span>
        </li>)}
      </ul> : <Empty>Nothing recorded yet.</Empty>}
    </div>
  </Section>;
}
