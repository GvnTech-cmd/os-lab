/**
 * CLNP-23: the Space Explorer — a dua-like, read-only size tree.
 *
 * The walk names a registered root id (deep-roots or the custom overlay);
 * drill-down sends a relative path that stays inside that root. Folder rows
 * carry proportional size bars, largest first; a folder click measures its
 * subtree. The explorer never deletes: its hint links cleaning back to the
 * plan → confirm → run flow on the Advanced scan page.
 */
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, ArrowsClockwiseIcon, FolderOpenIcon, HardDrivesIcon } from "@phosphor-icons/react";
import { Badge, Empty, Section, Status } from "../../components/ui";
import { api, formatBytes, message, type CleanupExplorerJob, type CleanupExplorerNode, type CleanupExplorerRoot } from "../../lib/api";

function NodeRows({
  node, maxBytes, relative, onDescend, depth
}: {
  node: CleanupExplorerNode; maxBytes: number; relative: string; onDescend: (relative: string) => void; depth: number;
}) {
  if (depth > 1) return null; // dua-style: expand one level at a time via drill-down
  return <>
    {node.children.map((child) => {
      const childRelative = relative ? `${relative}/${child.name}` : child.name;
      return <div key={child.path} className="py-2 text-sm">
        <div className="flex items-center gap-2">
          <button type="button" className="iux-btn min-w-0 flex-1 justify-start" data-variant="ghost" title={`Measure ${child.name}`}
            onClick={() => onDescend(childRelative)}>
            <FolderOpenIcon size={14} className="shrink-0 text-[#f36c21]" />
            <span className="min-w-0 flex-1 truncate text-start" translate="no">{child.name}</span>
            {child.truncated && <Badge tone="warning">partial</Badge>}
            <ArrowRightIcon size={12} className="shrink-0 text-(--iux-muted-foreground)" />
          </button>
          <span dir="ltr" className="tabular-nums">{formatBytes(child.sizeBytes)}</span>
          {child.unreadable > 0 && <Badge tone="warning">{child.unreadable} unreadable</Badge>}
        </div>
        {maxBytes > 0 && <div className="mt-1 h-1 overflow-hidden rounded-full bg-(--iux-muted)" aria-hidden="true">
          <div className="h-full rounded-full bg-[#f36c21]" style={{ width: `${Math.round((child.sizeBytes / maxBytes) * 100)}%` }} />
        </div>}
        <p className="mt-0.5 text-xs text-(--iux-muted-foreground)">
          {child.files} <span>files</span> · {child.folders} <span>folders</span>
        </p>
        {relative === "" && <NodeRows node={child} maxBytes={maxBytes} relative={childRelative} onDescend={onDescend} depth={depth + 1} />}
      </div>;
    })}
  </>;
}

export function SpaceExplorer({ scanHref }: { scanHref: string }) {
  const [roots, setRoots] = useState<CleanupExplorerRoot[] | null>(null);
  const [rootId, setRootId] = useState("");
  const [job, setJob] = useState<CleanupExplorerJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    void api.cleanupExplorerRoots()
      .then((report) => {
        if (!alive.current) return;
        setRoots(report.roots);
        const first = report.roots.find((item) => item.available);
        if (first) setRootId((current) => current || first.id);
      })
      .catch((e) => { if (alive.current) setError(message(e)); });
    return () => { alive.current = false; };
  }, []);

  // Poll the walk job while it runs, like every other console job.
  useEffect(() => {
    if (!job || job.state !== "running") return;
    let live = true;
    const timer = window.setInterval(() => {
      void api.cleanupJob(job.id).then((fresh) => {
        if (!live) return;
        setJob(fresh as unknown as CleanupExplorerJob);
      }).catch((e) => { if (live) { setError(message(e)); setJob(null); } });
    }, 650);
    return () => { live = false; window.clearInterval(timer); };
  }, [job?.id, job?.state]);

  async function run(action: () => Promise<CleanupExplorerJob>) {
    setBusy(true); setError("");
    try {
      setJob(await action());
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  const result = job && job.state !== "running" ? job.result : null;
  const tree = result?.tree ?? null;
  const availableRoots = (roots ?? []).filter((item) => item.available);
  const relative = result?.relative ?? "";
  const segments = relative ? relative.split("/") : [];
  const maxBytes = tree?.children[0]?.sizeBytes ?? tree?.sizeBytes ?? 0;

  return <Section title="Space Explorer" description="Browse folders by size. The explorer only measures — cleaning always happens through a reviewed plan.">
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-sm">Root{" "}
        <select className="iux-input ml-1" value={rootId} disabled={busy || !availableRoots.length}
          onChange={(event) => { setRootId(event.target.value); setJob(null); }}>
          {availableRoots.map((item) => <option key={item.id} value={item.id}>
            {item.name} {item.source === "custom" ? "(your folder)" : ""}
          </option>)}
        </select>
      </label>
      <button type="button" className="iux-btn" data-variant="primary" disabled={busy || !rootId}
        onClick={() => void run(() => api.cleanupExplorerScan(rootId))}>
        {tree ? <><ArrowsClockwiseIcon size={14} className="inline" /> Re-measure</> : "Measure"}
      </button>
      {job?.state === "running" && <span role="status" className="text-xs text-(--iux-muted-foreground)">
        measuring… <span translate="no">{String(job.progress?.currentPath ?? "")}</span>
      </span>}
    </div>
    {error && <Status value={{ ok: false, text: error }} />}
    {job?.state === "failed" && <Status value={{ ok: false, text: job.error || "The walk failed." }} />}
    {tree && <>
      <div className="mt-3 flex flex-wrap items-center gap-1 text-sm">
        <button type="button" className="iux-btn" data-variant="ghost" onClick={() => void run(() => api.cleanupExplorerScan(rootId))} disabled={busy}>
          <HardDrivesIcon size={14} className="inline" /> {(roots ?? []).find((item) => item.id === rootId)?.name ?? result?.rootId ?? "root"}
        </button>
        {segments.map((segment, index) => <span key={index} className="flex items-center gap-1">
          <span className="text-(--iux-muted-foreground)">/</span>
          <button type="button" className="iux-btn" data-variant="ghost" disabled={busy}
            onClick={() => void run(() => api.cleanupExplorerSubtree(rootId, segments.slice(0, index + 1).join("/")))}
            translate="no">{segment}</button>
        </span>)}
        <span className="ms-auto text-xs text-(--iux-muted-foreground)">
          {formatBytes(tree.sizeBytes)} · {result?.nodes ?? 0} entries{result?.truncated ? " · partially shown (walk budget reached)" : ""}
        </span>
      </div>
      <div className="mt-2 divide-y divide-(--iux-border)">
        {tree.children.length
          ? <NodeRows node={tree} maxBytes={maxBytes} relative={relative} onDescend={(next) => void run(() => api.cleanupExplorerSubtree(rootId, next))} depth={0} />
          : <Empty>Nothing to break down here.</Empty>}
      </div>
      <p className="mt-3 text-xs text-(--iux-muted-foreground)">
        The explorer never deletes. To clean something it found, bookmark it or use the{" "}
        <a className="underline" href={scanHref}>Advanced scan</a> plan flow.
      </p>
    </>}
    {!tree && job?.state !== "running" && !error && <Empty>Pick a root and measure it to see its folders by size.</Empty>}
  </Section>;
}
