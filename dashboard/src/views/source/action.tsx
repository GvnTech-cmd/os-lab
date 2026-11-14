import { useEffect, useState } from "react";
import { api, jobsStore, message, type LabJob, type LabPlan } from "../../lib/api";
import { Status } from "../../components/ui";
import { sourceRequest } from "./client";

/** Shared exact-preview workflow. Tokens stay in memory and are discarded on edits. */
export function SourceAction({ endpoint, options, ready, initialJob, onFinished }: {
  endpoint: string; options: Record<string, unknown>; ready: boolean; initialJob?: LabJob | null; onFinished?: () => void;
}) {
  const { data: jobs } = jobsStore.use();
  const [preview, setPreview] = useState<{ plan: LabPlan; token: string }>();
  const [job, setJob] = useState<LabJob>();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const [pollError, setPollError] = useState<string>();
  const fingerprint = JSON.stringify(options);
  useEffect(() => { setPreview(undefined); setError(undefined); }, [fingerprint, endpoint]);
  useEffect(() => { if (initialJob) setJob(initialJob); }, [initialJob?.id]);
  useEffect(() => {
    if (!job?.id) return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api.job(job.id); if (!active) return;
        setJob(previous => previous?.state !== "running" && next.state === "running" ? previous : next);
        setPollError(undefined);
        if (next.state === "running") timer = setTimeout(poll, 1000);
        else if (job.state === "running") { onFinished?.(); void jobsStore.refresh(); }
      } catch (e) { if (active) { setPollError(message(e)); if (job.state === "running") timer = setTimeout(poll, 2000); } }
    };
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [job?.id, job?.state, onFinished]);
  const conflict = job?.state === "running" || (jobs ?? []).some(j => j.lab === "source" && j.state === "running");
  async function act(kind: "preview" | "run" | "cancel") {
    setBusy(true); setError(undefined);
    try {
      if (kind === "preview") setPreview(await sourceRequest(endpoint, { options, preview: true }));
      if (kind === "run" && preview) { const result = await sourceRequest<{ job: LabJob }>(endpoint, { options, token: preview.token }); setJob(result.job); setPreview(undefined); void jobsStore.refresh(); }
      if (kind === "cancel" && job) { setJob(await api.cancel(job.id)); void jobsStore.refresh(); }
    } catch (e) { setError(message(e)); if (kind === "run") setPreview(undefined); }
    finally { setBusy(false); }
  }
  return <div className="mt-4 space-y-3">
    <div className="flex flex-wrap gap-2"><button className="iux-btn" disabled={!ready || busy || conflict} onClick={() => void act("preview")}>Preview action</button>{preview && <button className="iux-btn" disabled={!ready || busy || conflict} onClick={() => void act("run")}>Confirm and run</button>}{job?.state === "running" && <button className="iux-btn" disabled={busy} onClick={() => void act("cancel")}>Cancel</button>}</div>
    {conflict && <p role="status">A Source job is running. Wait or cancel it before starting another.</p>}
    {preview && <div className="space-y-2 rounded border border-(--iux-border) p-3"><pre className="overflow-auto text-xs">{preview.plan.display}</pre><ul>{preview.plan.effects.map(effect => <li key={effect} data-no-translate>{effect}</li>)}</ul><p>Privileges <span data-no-translate>{String(preview.plan.privileged)}</span></p><p>Timeout <span data-no-translate>{preview.plan.timeoutSec}s</span></p></div>}
    <Status value={error || pollError ? { ok: false, text: error ?? pollError! } : null} />
    {job && <div className="space-y-2"><p role="status" data-no-translate>{job.state} · {job.lines}</p>{job.error && <Status value={{ ok: false, text: job.error }} />}<pre aria-label="Operation logs" className="max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{job.logs?.join("\n")}</pre>{job.truncated && <p>Logs are truncated.</p>}</div>}
  </div>;
}
