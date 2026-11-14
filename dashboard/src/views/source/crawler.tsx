import { useEffect, useMemo, useState } from "react";
import { api, hostStore, jobsStore, message, type LabJob, type LabPlan } from "../../lib/api";
import { Empty, Field, Section, Skeleton, Status } from "../../components/ui";
import { sourceRequest, useSource } from "./client";
interface AnalyzerData { sourceFiles: { name: string; format: string }[]; sourceFilesTruncated: boolean; run: LabJob | null; summaryCount: number; summaryRows: Record<string, unknown>[]; report: unknown }
interface Preview { plan: LabPlan; token: string }
export function SourceCrawler({ targetKey }: { targetKey?: string }) {
  const state = useSource<AnalyzerData>("analyzer");
  const { data: host, error: hostError } = hostStore.use();
  const { data: jobs } = jobsStore.use();
  const [mode, setMode] = useState("repos"); const [repos, setRepos] = useState(""); const [sourceFile, setSourceFile] = useState("");
  const [workers, setWorkers] = useState(1); const [depth, setDepth] = useState(1);
  const [noAst, setNoAst] = useState(true); const [noMetadata, setNoMetadata] = useState(true);
  const [resume, setResume] = useState(false); const [keepWorkspace, setKeepWorkspace] = useState(true);
  const [tuning, setTuning] = useState<Record<string, number>>({});
  const [preview, setPreview] = useState<Preview>(); const [job, setJob] = useState<LabJob>();
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string>();
  const [pollError, setPollError] = useState<string>();
  const lab = host?.labs.find(lab => lab.id === "source");
  const ready = lab?.state === "ready" && !hostError && (Boolean(targetKey) || !lab.requirements?.some(r => r.id === "git" && !r.found));
  const conflict = (jobs ?? []).some(j => j.lab === "source" && j.state === "running") || job?.state === "running";
  const options = useMemo(() => ({ ...(targetKey ? { target: targetKey } : mode === "repos" ? { repos: repos.split(/[\s,]+/).filter(Boolean) } : { sourceFile }), workers, depth, noAst, noMetadata, resume, keepWorkspace, ...tuning }), [targetKey, tuning, mode, repos, sourceFile, workers, depth, noAst, noMetadata, resume, keepWorkspace]);
  const tuningCaps: Record<string, number> = { retries: 5, cloneTimeout: 600, apiMaxWait: 120, maxTreeEntries: 50000, maxAstFiles: 1000, mapMaxFiles: 10000, mapBudgetMs: 120000 };
  const tuningValid = Object.entries(tuning).every(([key, value]) => Number.isInteger(value) && value >= 1 && value <= tuningCaps[key]);
  const repoList = "repos" in options ? options.repos : [];
  const valid = Number.isInteger(workers) && workers >= 1 && workers <= 8 && Number.isInteger(depth) && depth >= 1 && depth <= 10 && (Boolean(targetKey) || (mode === "repos" ? repoList!.length > 0 && repoList!.length <= 100 && repoList!.every(r => /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/.test(r) && !r.split("/").some(p => p === "." || p === "..")) : Boolean(state.data?.sourceFiles.some(f => f.name === sourceFile))));
  useEffect(() => { setPreview(undefined); setError(undefined); }, [options]);
  useEffect(() => {
    if (!state.data?.run) return;
    const id = state.data.run.id; let active = true;
    setJob(state.data.run);
    void api.job(id).then(next => { if (active) setJob(next); }).catch(e => { if (active) setPollError(message(e)); });
    return () => { active = false; };
  }, [state.data?.run?.id]);
  useEffect(() => {
    if (!job || job.state !== "running") return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api.job(job.id);
        if (!active) return;
        setJob(previous => previous?.id === next.id && previous.state !== "running" ? previous : next); setPollError(undefined);
        if (next.state === "running") timer = setTimeout(poll, 1000);
        else { state.refresh(); void jobsStore.refresh(); }
      } catch (e) { if (active) { setPollError(message(e)); timer = setTimeout(poll, 2000); } }
    };
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [job?.id, job?.state, state.refresh]);
  async function act(kind: "preview" | "run" | "cancel") {
    setBusy(true); setError(undefined);
    try {
      if (kind === "preview") setPreview(await sourceRequest<Preview>("analyzer", { options, preview: true }));
      else if (kind === "run" && preview) { const result = await sourceRequest<{ job: LabJob }>("analyzer", { options, token: preview.token }); setJob(result.job); setPreview(undefined); void jobsStore.refresh(); }
      else if (kind === "cancel" && job) { setJob(await api.cancel(job.id)); void jobsStore.refresh(); }
    } catch (e) { setError(message(e)); if (kind === "run") setPreview(undefined); }
    finally { setBusy(false); }
  }
  return <>
    <Section title="Source crawler" description="Select only repositories you own or are authorized to assess. Crawling contacts GitHub and may clone sources.">
      {state.loading ? <Skeleton /> : state.error ? <><Status value={{ ok: false, text: state.error }} /><button className="iux-btn" onClick={state.refresh}>Retry</button></> : <>
        {!ready && <p role="status">Crawler needs live Source Lab readiness and Git. Check Readiness & setup for missing requirements.</p>}
        <fieldset disabled={busy || Boolean(conflict)} className="grid gap-3 sm:grid-cols-2">
          {!targetKey && <Field label="Input mode"><select className="iux-input" value={mode} onChange={e => setMode(e.target.value)}><option value="repos">Repositories</option><option value="source">Source list</option></select></Field>}
          {!targetKey && (mode === "repos" ? <Field label="GitHub repositories" hint="One owner/repo per line; at most 100. Credentials come from the operator environment."><textarea className="iux-input" rows={3} value={repos} onChange={e => setRepos(e.target.value)} /></Field> : <Field label="Source list"><select className="iux-input" value={sourceFile} onChange={e => setSourceFile(e.target.value)}><option value="">Select a source list</option>{state.data?.sourceFiles.map(file => <option value={file.name} key={file.name}>{file.name} ({file.format})</option>)}</select></Field>)}
          {targetKey && <p data-no-translate>{targetKey}</p>}
          <Field label="Workers"><input className="iux-input" type="number" min={1} max={8} value={workers} onChange={e => setWorkers(Number(e.target.value))} /></Field>
          <Field label="Clone depth"><input className="iux-input" type="number" min={1} max={10} value={depth} onChange={e => setDepth(Number(e.target.value))} /></Field>
          <label><input type="checkbox" checked={noAst} onChange={e => setNoAst(e.target.checked)} /> Skip AST</label>
          <label><input type="checkbox" checked={noMetadata} onChange={e => setNoMetadata(e.target.checked)} /> Skip GitHub metadata</label>
          <label><input type="checkbox" checked={resume} onChange={e => setResume(e.target.checked)} /> Resume completed bundles</label>
          <label><input type="checkbox" checked={keepWorkspace} onChange={e => setKeepWorkspace(e.target.checked)} /> Keep workspace</label>
        </fieldset>
        <details className="mt-3 rounded border border-(--iux-border) p-3"><summary>Advanced settings</summary><div className="mt-3 grid gap-3 sm:grid-cols-2">{[
          { key: "retries", label: "Retries", value: 3, max: 5 }, { key: "cloneTimeout", label: "Clone timeout", value: 300, max: 600 },
          { key: "apiMaxWait", label: "Rate-limit wait", value: 90, max: 120 }, { key: "maxTreeEntries", label: "Tree entry limit", value: 50000, max: 50000 },
          { key: "maxAstFiles", label: "AST file limit", value: 200, max: 1000 }, { key: "mapMaxFiles", label: "Map file limit", value: 4000, max: 10000 },
          { key: "mapBudgetMs", label: "Map budget", value: 30000, max: 120000 }
        ].map(field => <Field key={field.key} label={field.label}><input className="iux-input" type="number" min={1} max={field.max} disabled={busy || Boolean(conflict)} value={tuning[field.key] ?? field.value} onChange={e => setTuning(previous => ({ ...previous, [field.key]: Number(e.target.value) }))} /></Field>)}</div></details>
        {state.data?.sourceFilesTruncated && <p role="status">Source lists are capped.</p>}
        <div className="mt-4 flex flex-wrap gap-2"><button className="iux-btn" disabled={!ready || !valid || !tuningValid || busy || Boolean(conflict)} onClick={() => void act("preview")}>Preview crawl</button>{preview && <button className="iux-btn" disabled={!ready || busy || Boolean(conflict)} onClick={() => void act("run")}>Confirm and run</button>}{job?.state === "running" && <button className="iux-btn" disabled={busy} onClick={() => void act("cancel")}>Cancel crawl</button>}</div>
        {conflict && <p role="status">A Source job is running. Wait or cancel it before starting another.</p>}
        {preview && <section className="mt-4 space-y-2 rounded border border-(--iux-border) p-3" aria-label="Crawl preview"><pre className="overflow-auto text-xs">{preview.plan.display}</pre><ul>{preview.plan.effects.map(effect => <li key={effect} data-no-translate>{effect}</li>)}</ul><p>Privileges <span data-no-translate>{String(preview.plan.privileged)}</span></p><p>Timeout <span data-no-translate>{preview.plan.timeoutSec}s</span></p></section>}
      </>}
      <div className="mt-3"><Status value={error || pollError ? { ok: false, text: error ?? pollError! } : null} /></div>
    </Section>
    <Section title="Crawl progress" description="Progress follows engine output. Partial artifacts after cancellation or interruption require review.">
      {job ? <div className="space-y-3"><p role="status" data-no-translate>{job.state} · {job.lines} lines</p>{job.error && <Status value={{ ok: false, text: job.error }} />}<pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-(--iux-muted) p-3 text-xs" aria-label="Crawler logs">{job.logs?.join("\n") ?? ""}</pre>{job.truncated && <p>Logs are truncated.</p>}</div> : <Empty>No crawl has run yet.</Empty>}
    </Section>
    <Section title="Crawl results"><p>{state.data?.summaryCount ?? 0} <span>summary rows</span></p>{state.data?.summaryRows.length ? <div className="mt-3 overflow-auto"><table className="w-full text-sm"><thead><tr>{Object.keys(state.data.summaryRows[0]).map(key => <th key={key} className="p-2 text-start" data-no-translate>{key}</th>)}</tr></thead><tbody>{state.data.summaryRows.map((row, index) => <tr key={index}>{Object.keys(state.data!.summaryRows[0]).map(key => <td className="p-2" key={key} data-no-translate>{String(row[key] ?? "")}</td>)}</tr>)}</tbody></table></div> : <Empty>No crawl results are available.</Empty>}</Section>
    <Section title="H1–H5 reference" description="These heuristics prioritize review; they do not prove malicious behavior."><dl className="grid gap-3 sm:grid-cols-2">
      <div><dt>H1 (+2)</dt><dd>Manifest version is present.</dd></div>
      <div><dt>H2a (+3) / H2b (+2)</dt><dd>Broad host or high-risk permissions; native messaging or web request access.</dd></div>
      <div><dt>H3 (+1)</dt><dd>Content script match patterns are present.</dd></div>
      <div><dt>H4 (+2)</dt><dd>Background execution or assets/popup architecture.</dd></div>
      <div><dt>H5 (+3)</dt><dd>At least two JavaScript files in modules/.</dd></div>
    </dl></Section>
  </>;
}
