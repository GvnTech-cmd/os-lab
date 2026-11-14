import { useEffect, useState } from "react";
import { Badge, Empty, Section, Status } from "../../components/ui";
import { api, type CleanupAuxJob, type CleanupCrossLeftovers } from "../../lib/api";
import { bytes } from "./format";
import { InfoPopover } from "./info-popover";

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

/** Spoken confidence band; the exact percentage stays available on hover and in the popover. */
function ConfidenceBadge({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  const tone = value >= 0.8 ? "success" : value >= 0.4 ? "warning" : undefined;
  const label = value >= 0.8 ? "Likely leftover" : value >= 0.4 ? "Possible leftover" : "Uncertain";
  return <Badge tone={tone} title={`Confidence: ${percent}%`}>{label}</Badge>;
}

export function CrossPlatformLeftovers() {
  const [job, setJob] = useState<CleanupAuxJob<CleanupCrossLeftovers> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (job?.state !== "running") return;
    let alive = true;
    const timer = window.setInterval(() => {
      void api.cleanupAuxJob<CleanupCrossLeftovers>(job.id)
        .then((value) => { if (alive) setJob(value); })
        .catch((failure) => { if (alive) setJob((old) => old ? { ...old, state: "failed", error: errorText(failure) } : old); });
    }, 650);
    return () => { alive = false; window.clearInterval(timer); };
  }, [job?.id, job?.state]);

  async function scan() {
    setSubmitting(true); setError(""); setJob(null);
    try { setJob(await api.cleanupCrossLeftovers()); }
    catch (failure) { setError(errorText(failure)); }
    finally { setSubmitting(false); }
  }

  async function cancel() {
    if (!job) return;
    setError("");
    try { await api.cleanupCancel(job.id); }
    catch (failure) { setError(errorText(failure)); }
  }

  const items = [...(job?.result?.items ?? [])].sort((a, b) => b.confidence - a.confidence || b.sizeBytes - a.sizeBytes);
  return <Section title="Leftovers" description="Report only. No files are deleted here.">
    <div className="flex gap-2">
      <button type="button" className="iux-btn" disabled={submitting || job?.state === "running"} onClick={() => void scan()}>Scan</button>
      {job?.state === "running" && <button type="button" className="iux-btn" onClick={() => void cancel()}>Cancel</button>}
    </div>
    {job?.state === "running" && <p role="status">Scanning app leftovers…</p>}
    {job?.state === "failed" && <Status value={{ ok: false, text: job.error || "Scan failed." }} />}
    {error && <Status value={{ ok: false, text: error }} />}
    {job?.result && <>
      {!job.result.available && <p>{job.result.reason}</p>}
      {job.result.cancelled && <p>Scan cancelled. Results are partial.</p>}
      {!!job.result.inventorySources?.length && <p>Source: <span translate="no">{job.result.inventorySources.join(", ")}</span></p>}
      {job.result.inventoryErrors?.map((message, index) => <Status key={index} value={{ ok: false, text: message }} />)}
      {items.length === 0 ? <Empty>No leftovers were reported.</Empty> : items.map((item) =>
        <div key={item.path} className="border-b border-(--iux-border) py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
            <Badge><span translate="no">{item.status}</span></Badge>
            <ConfidenceBadge value={item.confidence} />
            <span dir="ltr" className="tabular-nums">{bytes(item.sizeBytes)}</span>
            <InfoPopover>
              <p className="break-all text-xs" translate="no">{item.path}</p>
              <p className="mt-1 text-xs" translate="no">{item.rule}</p>
              <p className="mt-1 text-xs text-(--iux-muted-foreground)">Confidence: {Math.round(item.confidence * 100)}%</p>
            </InfoPopover>
          </div>
        </div>)}
      {!!job.result.unreadable?.length && <p className="mt-2 text-xs text-(--iux-muted-foreground)">unreadable paths: <span translate="no">{job.result.unreadable.join(", ")}</span></p>}
    </>}
  </Section>;
}
