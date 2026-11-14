import { useState } from "react";
import reference from "../../../../console/source_pipeline.json";
import { Section, Skeleton, Status } from "../../components/ui";
import { ArtifactDetails } from "./evidence";
import { useSource } from "./client";
interface Stage { id: string; order: number; label: string; phase: string; description: string; reads: string[]; writes: string[]; network: string[]; failure: string }
interface PipelineData { stages: Stage[]; requests: unknown; signatures: unknown; riskRules: unknown; manifestCandidates: unknown; dependencyManifests: unknown; flowSteps: unknown }
export function SourcePipeline() {
  const remote = useSource<{ data: PipelineData | null; source: string; date?: string; revision?: string }>("pipeline");
  const [selected, setSelected] = useState("");
  const payload = remote.data?.data ?? reference.data;
  const stages = Array.isArray(payload.stages) ? payload.stages : [];
  const stage = stages.find(s => s.id === selected) ?? stages[0];
  return <>
    <Section title="Pipeline" description="Pinned architecture reference; no live run or automatic regeneration is implied." action={<button className="iux-btn" onClick={remote.refresh}>Refresh</button>}>
      {remote.loading && <Skeleton />}{remote.error && <Status value={{ ok: false, text: remote.error }} />}
      <p data-no-translate>{remote.data?.source ?? "bundled-reference"} · {remote.data?.date ?? reference.date} · {remote.data?.revision ?? reference.revision}</p>
      <p>Console controls use guarded options. This reference also describes the engine CLI.</p>
      <ol className="my-4 grid gap-2 sm:grid-cols-3">{stages.map(s => <li key={s.id}><button className="iux-btn h-full w-full justify-start" aria-pressed={stage?.id === s.id} data-no-translate onClick={() => setSelected(s.id)}>{s.order} → {s.label}</button></li>)}</ol>
      {stage && <article className="space-y-3 rounded border border-(--iux-border) p-3" data-no-translate><h3 className="font-semibold">{stage.label}</h3><p>{stage.description}</p><p>{stage.phase}</p><ArtifactDetails title="Inputs" value={stage.reads} /><ArtifactDetails title="Outputs" value={stage.writes} /><ArtifactDetails title="Network" value={stage.network} /><p>{stage.failure}</p></article>}
    </Section>
    <Section title="Pipeline reference"><div className="space-y-3"><ArtifactDetails title="GitHub requests" value={payload.requests} /><ArtifactDetails title="Signatures" value={payload.signatures} /><ArtifactDetails title="Risk rules" value={payload.riskRules} /><ArtifactDetails title="Manifest candidates" value={payload.manifestCandidates} /><ArtifactDetails title="Dependency manifests" value={payload.dependencyManifests} /><ArtifactDetails title="Flow steps" value={payload.flowSteps} /></div></Section>
  </>;
}
