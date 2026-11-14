import { useEffect, useState } from "react";
import { Badge, CopyButton, Empty, Section, Status } from "../../components/ui";
import { api, type CleanupAuxJob, type CleanupContainerCapabilities, type CleanupContainerPreview, type CleanupContainerResult, type CleanupVMInventory } from "../../lib/api";
import { bytes, containerActionLabel, riskLabel, riskTone } from "./format";

const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

export function CleanupExtraTools({ now }: { now: number }) {
  const [capabilities, setCapabilities] = useState<CleanupContainerCapabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState("");
  const [preview, setPreview] = useState<CleanupContainerPreview | null>(null);
  const [containerJob, setContainerJob] = useState<CleanupAuxJob<CleanupContainerResult> | null>(null);
  const [vmJob, setVmJob] = useState<CleanupAuxJob<CleanupVMInventory> | null>(null);
  const [containerError, setContainerError] = useState("");
  const [vmError, setVMError] = useState("");
  const [containerPending, setContainerPending] = useState(false);
  const [vmPending, setVMPending] = useState(false);

  useEffect(() => {
    let alive = true;
    void api.cleanupContainers().then((value) => { if (alive) setCapabilities(value); })
      .catch((error) => { if (alive) setCapabilityError(errorText(error)); });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (containerJob?.state !== "running") return;
    let alive = true;
    const timer = window.setInterval(() => {
      void api.cleanupAuxJob<CleanupContainerResult>(containerJob.id)
        .then((job) => { if (alive) setContainerJob(job); })
        .catch((error) => { if (alive) setContainerJob((old) => old ? { ...old, state: "failed", error: errorText(error) } : old); });
    }, 650);
    return () => { alive = false; window.clearInterval(timer); };
  }, [containerJob?.id, containerJob?.state]);

  useEffect(() => {
    if (vmJob?.state !== "running") return;
    let alive = true;
    const timer = window.setInterval(() => {
      void api.cleanupAuxJob<CleanupVMInventory>(vmJob.id)
        .then((job) => { if (alive) setVmJob(job); })
        .catch((error) => { if (alive) setVmJob((old) => old ? { ...old, state: "failed", error: errorText(error) } : old); });
    }, 650);
    return () => { alive = false; window.clearInterval(timer); };
  }, [vmJob?.id, vmJob?.state]);

  async function loadPreview(actionId: string) {
    setContainerPending(true); setContainerError(""); setPreview(null); setContainerJob(null);
    try { setPreview(await api.cleanupContainerPreview(actionId)); }
    catch (error) { setContainerError(errorText(error)); }
    finally { setContainerPending(false); }
  }

  async function prune() {
    if (!preview || preview.expiresAt <= now || preview.candidateCount === 0) return;
    setContainerPending(true); setContainerError("");
    try { setContainerJob(await api.cleanupContainerPrune(preview.previewId)); setPreview(null); }
    catch (error) { setContainerError(errorText(error)); }
    finally { setContainerPending(false); }
  }

  async function scanVMs() {
    setVMPending(true); setVMError(""); setVmJob(null);
    try { setVmJob(await api.cleanupVMScan()); }
    catch (error) { setVMError(errorText(error)); }
    finally { setVMPending(false); }
  }

  const containerBusy = containerPending || containerJob?.state === "running";
  return <>
    <Section title="Containers" description="Preview candidates before pruning. Volumes may contain persistent data.">
      {capabilityError && <Status value={{ ok: false, text: capabilityError }} />}
      {capabilityError && <button type="button" className="iux-btn" onClick={() => {
        setCapabilityError("");
        void api.cleanupContainers().then(setCapabilities).catch((error) => setCapabilityError(errorText(error)));
      }}>Retry</button>}
      {!capabilities && !capabilityError && <p role="status">Checking container engine…</p>}
      {capabilities && !capabilities.available && <p>{capabilities.reason}</p>}
      {capabilities?.available && <>
        <p>Container engine: <code translate="no">{capabilities.engine}</code></p>
        <div className="mt-2 flex flex-wrap gap-2">{capabilities.actions.map((action) =>
          <button key={action.id} type="button" className="iux-btn" disabled={containerBusy} title={action.id}
            onClick={() => void loadPreview(action.id)}>
            <span className="text-(--iux-muted-foreground)">Preview</span> {containerActionLabel(action.id)}
          </button>)}</div>
      </>}
      {preview && <div className="mt-3 border-t border-(--iux-border) pt-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <strong>{containerActionLabel(preview.actionId)}</strong>
          <Badge tone={riskTone(preview.risk)}>{riskLabel(preview.risk)}</Badge>
          <span className="tabular-nums text-(--iux-muted-foreground)">{preview.candidateCount} <span>candidates</span></span>
          <span className="ms-auto"><CopyButton text={preview.command.join(" ")} label="Copy command" /></span>
        </div>
        <p className="mt-1 text-xs"><span className="font-medium text-(--iux-muted-foreground)">Command</span> <code translate="no">{preview.command.join(" ")}</code></p>
        <details className="mt-2"><summary className="cursor-pointer text-xs text-(--iux-muted-foreground)">Candidates</summary>
          <pre className="iux-scroll mt-1 max-h-48 overflow-auto rounded-md border border-(--iux-border) p-2 text-xs" translate="no">{JSON.stringify(preview.candidates, null, 2)}</pre>
        </details>
        {preview.expiresAt <= now ? <p className="mt-2">Preview expired. Preview again.</p> :
          <button type="button" className="iux-btn mt-2" data-variant="primary" disabled={containerBusy || preview.candidateCount === 0}
            onClick={() => void prune()}>Confirm prune</button>}
        {preview.candidateCount === 0 && <p>No candidates to prune.</p>}
      </div>}
      {containerJob?.state === "running" && <p role="status">Container prune in progress…</p>}
      {containerJob?.state === "done" && containerJob.result && <p role="status">Prune completed. <span translate="no">{containerJob.result.output}</span></p>}
      {containerJob?.state === "failed" && <Status value={{ ok: false, text: containerJob.error || containerJob.result?.error || "Container prune failed." }} />}
      {containerError && <Status value={{ ok: false, text: containerError }} />}
    </Section>
    <Section title="Virtual machines" description="Report only. No virtual machines are deleted here.">
      <button type="button" className="iux-btn" disabled={vmPending || vmJob?.state === "running"} onClick={() => void scanVMs()}>Scan virtual machines</button>
      {vmJob?.state === "running" && <p role="status">VM inventory in progress…</p>}
      {vmJob?.state === "failed" && <Status value={{ ok: false, text: vmJob.error || "VM inventory failed." }} />}
      {vmError && <Status value={{ ok: false, text: vmError }} />}
      {vmJob?.result && <>
        {vmJob.result.cancelled && <p>Scan cancelled. Results are partial.</p>}
        {vmJob.result.items.length === 0 ? <Empty>No virtual machines found.</Empty> : vmJob.result.items.map((item) =>
          <div key={item.path} className="border-b border-(--iux-border) py-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
              <Badge>Report only</Badge>
              <span dir="ltr" className="tabular-nums">{bytes(item.sizeBytes)}</span>
            </div>
            <p className="break-all text-xs text-(--iux-muted-foreground)" translate="no">{item.path}</p>
          </div>)}
        {vmJob.result.unavailable.map((item, index) => <p key={`${item.id}-${index}`} className="text-sm"><span translate="no">{item.root || item.id}</span>: {item.reason}</p>)}
      </>}
    </Section>
  </>;
}
